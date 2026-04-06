import re
from datetime import datetime
from typing import Optional

import httpx
from cachetools import TTLCache

from api.base_client import TransitClient, shorten_headsign
from api.models import (
    DirectionSummary,
    LineSummary,
    PredictionSummary,
    StopSummary,
    TransitClientError,
)

WMATA_BASE_URL = "https://api.wmata.com"

_DIR_PATTERN = re.compile(r"\b(North|South|East|West)\b")
_DIR_MAP = {"North": "N", "South": "S", "East": "E", "West": "W"}


def _abbreviate_directions(text: str) -> str:
    text = _DIR_PATTERN.sub(lambda m: _DIR_MAP[m.group()], text)
    return shorten_headsign(text)


class WmataClient(TransitClient):
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.lines_cache: TTLCache = TTLCache(maxsize=1, ttl=300)
        self.stops_cache: TTLCache = TTLCache(maxsize=100, ttl=300)
        self.directions_cache: TTLCache = TTLCache(maxsize=100, ttl=300)
        self.bus_stops_cache: TTLCache = TTLCache(maxsize=1, ttl=300)
        self.bus_routes_cache: TTLCache = TTLCache(maxsize=1, ttl=300)

    def _headers(self) -> dict[str, str]:
        return {"api_key": self.api_key}

    async def _fetch_all_bus_stops(self, client: httpx.AsyncClient) -> list[dict]:
        cache_key = "all_bus_stops"
        if cache_key in self.bus_stops_cache:
            return self.bus_stops_cache[cache_key]

        response = await client.get(
            f"{WMATA_BASE_URL}/Bus.svc/json/jStops",
            headers=self._headers(),
            timeout=30,
        )
        if response.status_code != 200:
            raise TransitClientError(
                f"WMATA bus stops request failed with status {response.status_code}"
            )

        stops = response.json().get("Stops", [])
        self.bus_stops_cache[cache_key] = stops
        return stops

    async def _fetch_bus_routes(self, client: httpx.AsyncClient) -> list[dict]:
        cache_key = "bus_routes"
        if cache_key in self.bus_routes_cache:
            return self.bus_routes_cache[cache_key]

        response = await client.get(
            f"{WMATA_BASE_URL}/Bus.svc/json/jRoutes",
            headers=self._headers(),
        )
        if response.status_code != 200:
            raise TransitClientError(
                f"WMATA bus routes request failed with status {response.status_code}"
            )

        routes = response.json().get("Routes", [])
        self.bus_routes_cache[cache_key] = routes
        return routes

    async def fetch_lines(self) -> list[LineSummary]:
        cache_key = "lines"
        if cache_key in self.lines_cache:
            return self.lines_cache[cache_key]

        async with httpx.AsyncClient() as client:
            # Fetch rail lines
            response = await client.get(
                f"{WMATA_BASE_URL}/Rail.svc/json/jLines",
                headers=self._headers(),
            )
            if response.status_code != 200:
                raise TransitClientError(
                    f"WMATA lines request failed with status {response.status_code}"
                )

            data = response.json()
            lines = []

            for line_data in data.get("Lines", []):
                line_code = line_data.get("LineCode")
                lines.append(
                    LineSummary(
                        id=line_code,
                        long_name=line_data.get("DisplayName"),
                        routes=[line_code] if line_code else [],
                        type="rail",
                    )
                )

            # Fetch bus routes
            bus_routes = await self._fetch_bus_routes(client)
            for route in bus_routes:
                route_id = route.get("RouteID")
                lines.append(
                    LineSummary(
                        id=route_id,
                        long_name=route.get("Name"),
                        routes=[route_id] if route_id else [],
                        type="bus",
                    )
                )

            self.lines_cache[cache_key] = lines
            return lines

    async def fetch_stops(
        self, route_id: str, route_type: Optional[str] = None
    ) -> list[StopSummary]:
        if route_id in self.stops_cache:
            return self.stops_cache[route_id]

        async with httpx.AsyncClient() as client:
            if route_type == "bus":
                stops = await self._fetch_bus_stops(client, route_id)
            else:
                stops = await self._fetch_rail_stops(client, route_id)

            self.stops_cache[route_id] = stops
            return stops

    async def _fetch_rail_stops(
        self, client: httpx.AsyncClient, route_id: str
    ) -> list[StopSummary]:
        response = await client.get(
            f"{WMATA_BASE_URL}/Rail.svc/json/jStations",
            params={"LineCode": route_id},
            headers=self._headers(),
        )
        if response.status_code != 200:
            raise TransitClientError(
                f"WMATA stops request failed with status {response.status_code}"
            )

        data = response.json()
        return [
            StopSummary(id=station.get("Code"), name=station.get("Name"))
            for station in data.get("Stations", [])
        ]

    async def _fetch_bus_stops(
        self, client: httpx.AsyncClient, route_id: str
    ) -> list[StopSummary]:
        all_stops = await self._fetch_all_bus_stops(client)
        seen: set[str] = set()
        stops = []
        for stop in all_stops:
            if route_id in stop.get("Routes", []):
                stop_id = stop.get("StopID")
                if stop_id and stop_id not in seen:
                    seen.add(stop_id)
                    stops.append(
                        StopSummary(id=stop_id, name=stop.get("Name"))
                    )
        return stops

    async def fetch_directions(
        self, route_id: str, route_type: Optional[str] = None
    ) -> list[DirectionSummary]:
        if route_id in self.directions_cache:
            return self.directions_cache[route_id]

        async with httpx.AsyncClient() as client:
            if route_type == "bus":
                directions = await self._fetch_bus_directions(client, route_id)
            else:
                directions = await self._fetch_rail_directions(client, route_id)

            self.directions_cache[route_id] = directions
            return directions

    async def _fetch_rail_directions(
        self, client: httpx.AsyncClient, route_id: str
    ) -> list[DirectionSummary]:
        response = await client.get(
            f"{WMATA_BASE_URL}/Rail.svc/json/jLines",
            headers=self._headers(),
        )
        if response.status_code != 200:
            raise TransitClientError(
                f"WMATA directions request failed with status {response.status_code}"
            )

        data = response.json()
        line_info = None
        for line_data in data.get("Lines", []):
            if line_data.get("LineCode") == route_id:
                line_info = line_data
                break

        if not line_info:
            raise TransitClientError(
                f"WMATA line {route_id} not found", status_code=404
            )

        start_code = line_info.get("StartStationCode")
        end_code = line_info.get("EndStationCode")

        # Look up station names for start and end
        station_names = {}
        for code in [start_code, end_code]:
            if code:
                station_resp = await client.get(
                    f"{WMATA_BASE_URL}/Rail.svc/json/jStationInfo",
                    params={"StationCode": code},
                    headers=self._headers(),
                )
                if station_resp.status_code == 200:
                    station_data = station_resp.json()
                    station_names[code] = station_data.get("Name", code)
                else:
                    station_names[code] = code

        return [
            DirectionSummary(
                id="1",
                destination=station_names.get(end_code, end_code or "Unknown"),
            ),
            DirectionSummary(
                id="2",
                destination=station_names.get(start_code, start_code or "Unknown"),
            ),
        ]

    async def _fetch_bus_directions(
        self, client: httpx.AsyncClient, route_id: str
    ) -> list[DirectionSummary]:
        # Name format is always "ROUTE_ID - ENDPOINT1 - ENDPOINT2"
        bus_routes = await self._fetch_bus_routes(client)
        for route in bus_routes:
            if route.get("RouteID") == route_id:
                name = route.get("Name", "")
                name_parts = name.split(" - ", 2)
                if len(name_parts) == 3:
                    return [
                        DirectionSummary(id="0", destination=name_parts[1].strip().title()),
                        DirectionSummary(id="1", destination=name_parts[2].strip().title()),
                    ]
                return [
                    DirectionSummary(id="0", destination="Direction 1"),
                    DirectionSummary(id="1", destination="Direction 2"),
                ]

        raise TransitClientError(
            f"WMATA bus route {route_id} not found", status_code=404
        )

    async def fetch_predictions(
        self,
        stop_id: str,
        routes: Optional[set[str]] = None,
        direction: Optional[int] = None,
        limit: int = 10,
        route_type: Optional[str] = None,
    ) -> list[PredictionSummary]:
        async with httpx.AsyncClient() as client:
            if route_type == "bus":
                return await self._fetch_bus_predictions(
                    client, stop_id, routes, direction, limit
                )
            else:
                return await self._fetch_rail_predictions(
                    client, stop_id, routes, direction, limit
                )

    async def _fetch_rail_predictions(
        self,
        client: httpx.AsyncClient,
        stop_id: str,
        routes: Optional[set[str]],
        direction: Optional[int],
        limit: int,
    ) -> list[PredictionSummary]:
        response = await client.get(
            f"{WMATA_BASE_URL}/StationPrediction.svc/json/GetPrediction/{stop_id}",
            headers=self._headers(),
        )
        if response.status_code != 200:
            raise TransitClientError(
                f"WMATA predictions request failed with status {response.status_code}"
            )

        data = response.json()
        predictions = []
        now_epoch = int(datetime.now().timestamp())

        for train in data.get("Trains", []):
            line_code = train.get("Line")
            group = train.get("Group")
            min_value = train.get("Min", "")

            if routes and line_code not in routes:
                continue

            if direction is not None and group != str(direction):
                continue

            arrival_epoch = _parse_min_to_epoch(min_value, now_epoch)
            if arrival_epoch is None:
                continue

            predictions.append(
                PredictionSummary(
                    headsign=train.get("Destination"),
                    arrival_time=arrival_epoch,
                    arrival_uncertainty=None,
                )
            )

        predictions.sort(key=lambda p: p.arrival_time or float("inf"))
        return predictions[:limit]

    async def _fetch_bus_predictions(
        self,
        client: httpx.AsyncClient,
        stop_id: str,
        routes: Optional[set[str]],
        direction: Optional[int],
        limit: int,
    ) -> list[PredictionSummary]:
        response = await client.get(
            f"{WMATA_BASE_URL}/NextBusService.svc/json/jPredictions",
            params={"StopID": stop_id},
            headers=self._headers(),
        )
        if response.status_code != 200:
            raise TransitClientError(
                f"WMATA bus predictions request failed with status {response.status_code}"
            )

        data = response.json()
        predictions = []
        now_epoch = int(datetime.now().timestamp())

        for pred in data.get("Predictions", []):
            route_id = pred.get("RouteID")
            dir_num = pred.get("DirectionNum")
            minutes = pred.get("Minutes")

            if routes and route_id not in routes:
                continue

            if direction is not None and dir_num != str(direction):
                continue

            if minutes is None:
                continue

            predictions.append(
                PredictionSummary(
                    headsign=_abbreviate_directions(pred.get("DirectionText", "")),
                    arrival_time=now_epoch + (int(minutes) * 60),
                    arrival_uncertainty=None,
                )
            )

        predictions.sort(key=lambda p: p.arrival_time or float("inf"))
        return predictions[:limit]


def _parse_min_to_epoch(min_value: str, now_epoch: int) -> Optional[int]:
    if not min_value or min_value == "---":
        return None
    if min_value in ("BRD", "ARR"):
        return now_epoch
    try:
        minutes = int(min_value)
        return now_epoch + (minutes * 60)
    except ValueError:
        return None
