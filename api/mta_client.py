import asyncio
import csv
import io
import re
from datetime import datetime, timezone
from typing import Optional
from zoneinfo import ZoneInfo

NY_TZ = ZoneInfo("America/New_York")

import httpx
from cachetools import TTLCache
from nyct_gtfs import NYCTFeed

from api.base_client import TransitClient, shorten_headsign
from api.models import (
    DirectionSummary,
    LineSummary,
    PredictionSummary,
    StopSummary,
    TransitClientError,
)

MTA_STATIONS_CSV_URL = (
    "https://data.ny.gov/api/views/39hk-dx4f/rows.csv?accessType=DOWNLOAD"
)
OBA_BASE = "https://bustime-classic.mta.info/api/where"
SIRI_BASE = "https://bustime-classic.mta.info/api/siri"


SUBWAY_ROUTES: list[tuple[str, str]] = [
    ("1", "1 Train"), ("2", "2 Train"), ("3", "3 Train"),
    ("4", "4 Train"), ("5", "5 Train"), ("6", "6 Train"), ("7", "7 Train"),
    ("A", "A Train"), ("C", "C Train"), ("E", "E Train"),
    ("B", "B Train"), ("D", "D Train"), ("F", "F Train"), ("M", "M Train"),
    ("G", "G Train"),
    ("J", "J Train"), ("Z", "Z Train"),
    ("L", "L Train"),
    ("N", "N Train"), ("Q", "Q Train"), ("R", "R Train"), ("W", "W Train"),
    ("SI", "SI Railway"),
]

# (northbound terminus label, southbound terminus label)
# Direction "0" = N-suffix stop IDs (northbound/uptown)
# Direction "1" = S-suffix stop IDs (southbound/downtown)
SUBWAY_DIRECTION_LABELS: dict[str, tuple[str, str]] = {
    "1": ("Van Cortlandt", "South Ferry"),
    "2": ("Wakefield-241", "Flatbush Av"),
    "3": ("Harlem-148 St", "New Lots Av"),
    "4": ("Woodlawn", "Utica Av"),
    "5": ("Eastchester", "Flatbush Av"),
    "6": ("Pelham Bay Pk", "Brooklyn Br"),
    "7": ("Flushing Main", "Hudson Yards"),
    "A": ("Inwood-207 St", "Far Rockaway"),
    "C": ("168 St", "Euclid Av"),
    "E": ("Jamaica-179", "World Trade"),
    "B": ("145 St", "Brighton Bch"),
    "D": ("Norwood-205", "Coney Island"),
    "F": ("Jamaica-179", "Coney Island"),
    "M": ("Forest Hills", "Metropolitan"),
    "G": ("Court Sq", "Church Av"),
    "J": ("Jamaica Ctr", "Broad St"),
    "Z": ("Jamaica Ctr", "Broad St"),
    "L": ("8 Av", "Canarsie"),
    "N": ("Ditmars Blvd", "Coney Island"),
    "Q": ("96 St", "Coney Island"),
    "R": ("Forest Hills", "Bay Ridge"),
    "W": ("Ditmars Blvd", "Whitehall St"),
    "SI": ("St George", "Tottenville"),
}

# Strips fractional seconds for Python <3.11 fromisoformat compatibility
_ISO_MILLIS_RE = re.compile(r"\.\d+(?=[+\-Z]|$)")


def _parse_iso_dt(s: str) -> Optional[datetime]:
    try:
        cleaned = _ISO_MILLIS_RE.sub("", s).replace("Z", "+00:00")
        return datetime.fromisoformat(cleaned)
    except (ValueError, AttributeError):
        return None


class MtaClient(TransitClient):
    def __init__(self, bus_api_key: Optional[str] = None):
        self.bus_api_key = bus_api_key
        self.lines_cache: TTLCache = TTLCache(maxsize=1, ttl=86400)
        self.stops_cache: TTLCache = TTLCache(maxsize=500, ttl=86400)
        self.stations_cache: TTLCache = TTLCache(maxsize=1, ttl=86400)
        self.rt_cache: TTLCache = TTLCache(maxsize=8, ttl=5)

    async def fetch_lines(self) -> list[LineSummary]:
        cache_key = "lines"
        if cache_key in self.lines_cache:
            return self.lines_cache[cache_key]

        lines: list[LineSummary] = [
            LineSummary(id=route_id, long_name=name, routes=[route_id], type="rail")
            for route_id, name in SUBWAY_ROUTES
        ]

        if not self.bus_api_key:
            self.lines_cache[cache_key] = lines
            return lines

        async with httpx.AsyncClient() as client:
            agencies_resp = await client.get(
                f"{OBA_BASE}/agencies-with-coverage.json",
                params={"key": self.bus_api_key},
                timeout=30,
            )
            if agencies_resp.status_code != 200:
                raise TransitClientError(
                    f"MTA agencies request failed with status {agencies_resp.status_code}"
                )
            agencies = [
                entry["agency"]["id"]
                for entry in agencies_resp.json().get("data", [])
                if entry.get("latSpan", 0) > 0
            ]

            for agency_id in agencies:
                encoded_id = agency_id.replace(" ", "%20")
                resp = await client.get(
                    f"{OBA_BASE}/routes-for-agency/{encoded_id}.json",
                    params={"key": self.bus_api_key},
                    timeout=30,
                )
                if resp.status_code != 200:
                    raise TransitClientError(
                        f"MTA bus routes request failed with status {resp.status_code}"
                    )
                for route in resp.json().get("data", {}).get("list", []):
                    route_id = route.get("id")
                    if not route_id:
                        continue
                    lines.append(
                        LineSummary(
                            id=route_id,
                            long_name=route.get("shortName") or route.get("longName"),
                            routes=[route_id],
                            type="bus",
                            has_directions=False,
                        )
                    )

        self.lines_cache[cache_key] = lines
        return lines

    async def _fetch_stations_csv(self, client: httpx.AsyncClient) -> list[dict]:
        cache_key = "stations"
        if cache_key in self.stations_cache:
            return self.stations_cache[cache_key]

        resp = await client.get(MTA_STATIONS_CSV_URL, timeout=30)
        if resp.status_code != 200:
            raise TransitClientError(
                f"MTA stations CSV fetch failed with status {resp.status_code}"
            )
        stations = list(csv.DictReader(io.StringIO(resp.text)))
        self.stations_cache[cache_key] = stations
        return stations

    def _is_bus_route(self, route_id: str, route_type: Optional[str]) -> bool:
        return route_type == "bus" or "_" in route_id

    async def fetch_stops(
        self, route_id: str, route_type: Optional[str] = None
    ) -> list[StopSummary]:
        if route_id in self.stops_cache:
            return self.stops_cache[route_id]

        stops = (
            await self._fetch_bus_stops(route_id)
            if self._is_bus_route(route_id, route_type)
            else await self._fetch_subway_stops(route_id)
        )
        self.stops_cache[route_id] = stops
        return stops

    async def _fetch_subway_stops(self, route_id: str) -> list[StopSummary]:
        async with httpx.AsyncClient() as client:
            stations = await self._fetch_stations_csv(client)

        seen: set[str] = set()
        stops: list[StopSummary] = []
        for row in stations:
            if route_id not in row.get("Daytime Routes", "").split():
                continue
            gtfs_id = row.get("GTFS Stop ID", "").strip()
            if gtfs_id and gtfs_id not in seen:
                seen.add(gtfs_id)
                stops.append(StopSummary(id=gtfs_id, name=row.get("Stop Name", "").strip()))
        return stops

    async def _fetch_bus_stops(self, route_id: str) -> list[StopSummary]:
        if not self.bus_api_key:
            raise TransitClientError("MTA_BUS_API_KEY not configured", status_code=503)
        encoded_id = route_id.replace(" ", "%20")
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{OBA_BASE}/stops-for-route/{encoded_id}.json",
                params={
                    "key": self.bus_api_key,
                    "includePolylines": "false",
                    "version": "2",
                },
                timeout=30,
            )
        if resp.status_code != 200:
            raise TransitClientError(
                f"MTA bus stops request failed with status {resp.status_code}"
            )
        refs = resp.json().get("data", {}).get("references", {}).get("stops", [])
        return [
            StopSummary(id=s.get("id"), name=s.get("name"))
            for s in refs
            if s.get("id")
        ]

    async def _fetch_bus_directions(self, route_id: str) -> list[DirectionSummary]:
        if not self.bus_api_key:
            raise TransitClientError("MTA_BUS_API_KEY not configured", status_code=503)
        encoded_id = route_id.replace(" ", "%20")
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{OBA_BASE}/stops-for-route/{encoded_id}.json",
                params={
                    "key": self.bus_api_key,
                    "includePolylines": "false",
                    "version": "2",
                },
                timeout=30,
            )
        if resp.status_code != 200:
            raise TransitClientError(
                f"MTA bus directions request failed with status {resp.status_code}"
            )
        directions = []
        groupings = (
            resp.json().get("data", {}).get("entry", {}).get("stopGroupings", [])
        )
        for grouping in groupings:
            for group in grouping.get("stopGroups", []):
                group_id = group.get("id")
                name = group.get("name", {}).get("name", "")
                if group_id is not None and name:
                    directions.append(
                        DirectionSummary(
                            id=str(group_id),
                            destination=shorten_headsign(name.title()),
                        )
                    )
        return directions or [
            DirectionSummary(id="0", destination="Direction 1"),
            DirectionSummary(id="1", destination="Direction 2"),
        ]

    async def fetch_directions(
        self, route_id: str, route_type: Optional[str] = None
    ) -> list[DirectionSummary]:
        if self._is_bus_route(route_id, route_type):
            return await self._fetch_bus_directions(route_id)

        labels = SUBWAY_DIRECTION_LABELS.get(route_id)
        if not labels:
            raise TransitClientError(
                f"Unknown MTA subway route: {route_id}", status_code=404
            )
        north, south = labels
        return [
            DirectionSummary(id="0", destination=north),
            DirectionSummary(id="1", destination=south),
        ]

    async def fetch_predictions(
        self,
        stop_id: str,
        routes: Optional[set[str]] = None,
        direction: Optional[int] = None,
        limit: int = 10,
        route_type: Optional[str] = None,
    ) -> list[PredictionSummary]:
        is_bus = self._is_bus_route(next(iter(routes), ""), route_type) if routes else route_type == "bus"
        if is_bus:
            return await self._fetch_bus_predictions(stop_id, routes, direction, limit)
        return await self._fetch_subway_predictions(stop_id, routes, direction, limit)

    async def _fetch_subway_predictions(
        self,
        stop_id: str,
        routes: Optional[set[str]],
        direction: Optional[int],
        limit: int,
    ) -> list[PredictionSummary]:
        route_universe = routes if routes else set(NYCTFeed._train_to_url.keys())
        feed_urls = {
            NYCTFeed._train_to_url[r]
            for r in route_universe
            if r in NYCTFeed._train_to_url
        }

        if direction == 0:
            target_stops = {f"{stop_id}N"}
        elif direction == 1:
            target_stops = {f"{stop_id}S"}
        else:
            target_stops = {f"{stop_id}N", f"{stop_id}S"}

        now = datetime.now(timezone.utc)
        predictions: list[PredictionSummary] = []

        for url in feed_urls:
            if url not in self.rt_cache:
                try:
                    feed = await asyncio.to_thread(NYCTFeed, url)
                except Exception as e:
                    raise TransitClientError(f"Failed to fetch MTA subway feed: {e}")
                self.rt_cache[url] = feed
            feed: NYCTFeed = self.rt_cache[url]

            for trip in feed.trips:
                if routes and trip.route_id not in routes:
                    continue
                for stu in trip.stop_time_updates:
                    if stu.stop_id not in target_stops:
                        continue
                    arrival = stu.arrival
                    if arrival is None:
                        continue
                    if arrival.tzinfo is None:
                        arrival = arrival.replace(tzinfo=NY_TZ)
                    if arrival < now:
                        continue
                    predictions.append(
                        PredictionSummary(
                            headsign=shorten_headsign(
                                trip.headsign_text or trip.route_id or ""
                            ),
                            arrival_time=int(arrival.timestamp()),
                            arrival_uncertainty=None,
                        )
                    )

        predictions.sort(key=lambda p: p.arrival_time or float("inf"))
        return predictions[:limit]

    async def _fetch_bus_predictions(
        self,
        stop_id: str,
        routes: Optional[set[str]],
        direction: Optional[int],
        limit: int,
    ) -> list[PredictionSummary]:
        if not self.bus_api_key:
            raise TransitClientError("MTA_BUS_API_KEY not configured", status_code=503)
        siri_stop_id = stop_id.removeprefix("MTA_")
        params: dict = {
            "key": self.bus_api_key,
            "MonitoringRef": siri_stop_id,
            "version": "2",
            "MaximumStopVisits": str(limit * 3),
        }
        if direction is not None:
            params["DirectionRef"] = str(direction)

        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{SIRI_BASE}/stop-monitoring.json",
                params=params,
                timeout=30,
            )
        if resp.status_code != 200:
            raise TransitClientError(
                f"MTA SIRI request failed with status {resp.status_code}"
            )

        visits = (
            resp.json()
            .get("Siri", {})
            .get("ServiceDelivery", {})
            .get("StopMonitoringDelivery", [{}])[0]
            .get("MonitoredStopVisit", [])
        )

        now_epoch = int(datetime.now().timestamp())
        predictions: list[PredictionSummary] = []

        for visit in visits:
            journey = visit.get("MonitoredVehicleJourney", {})
            if routes and journey.get("LineRef", "") not in routes:
                continue
            call = journey.get("MonitoredCall", {})
            expected = call.get("ExpectedArrivalTime")
            if not expected:
                continue
            arrival_dt = _parse_iso_dt(expected)
            if arrival_dt is None:
                continue
            arrival_epoch = int(arrival_dt.timestamp())
            if arrival_epoch < now_epoch:
                continue
            dest = journey.get("DestinationName") or journey.get("PublishedLineName") or ""
            headsign = shorten_headsign(dest[0] if isinstance(dest, list) else dest)
            predictions.append(
                PredictionSummary(
                    headsign=headsign,
                    arrival_time=arrival_epoch,
                    arrival_uncertainty=None,
                )
            )

        predictions.sort(key=lambda p: p.arrival_time or float("inf"))
        return predictions[:limit]
