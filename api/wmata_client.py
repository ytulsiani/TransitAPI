from datetime import datetime
from typing import Optional

import httpx
from cachetools import TTLCache

from api.base_client import TransitClient
from api.models import (
    DirectionSummary,
    LineSummary,
    PredictionSummary,
    StopSummary,
    TransitClientError,
)

WMATA_BASE_URL = "https://api.wmata.com"


class WmataClient(TransitClient):
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.lines_cache: TTLCache = TTLCache(maxsize=1, ttl=300)
        self.stops_cache: TTLCache = TTLCache(maxsize=100, ttl=300)
        self.directions_cache: TTLCache = TTLCache(maxsize=100, ttl=300)

    def _headers(self) -> dict[str, str]:
        return {"api_key": self.api_key}

    async def fetch_lines(self) -> list[LineSummary]:
        cache_key = "lines"
        if cache_key in self.lines_cache:
            return self.lines_cache[cache_key]

        async with httpx.AsyncClient() as client:
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
                    )
                )

            self.lines_cache[cache_key] = lines
            return lines

    async def fetch_stops(self, route_id: str) -> list[StopSummary]:
        if route_id in self.stops_cache:
            return self.stops_cache[route_id]

        async with httpx.AsyncClient() as client:
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
            stops = []

            for station in data.get("Stations", []):
                stops.append(
                    StopSummary(
                        id=station.get("Code"),
                        name=station.get("Name"),
                    )
                )

            self.stops_cache[route_id] = stops
            return stops

    async def fetch_directions(self, route_id: str) -> list[DirectionSummary]:
        if route_id in self.directions_cache:
            return self.directions_cache[route_id]

        # Fetch lines to get start/end station codes for this line
        async with httpx.AsyncClient() as client:
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

            directions = [
                DirectionSummary(
                    id="1",
                    destination=station_names.get(end_code, end_code or "Unknown"),
                ),
                DirectionSummary(
                    id="2",
                    destination=station_names.get(start_code, start_code or "Unknown"),
                ),
            ]

            self.directions_cache[route_id] = directions
            return directions

    async def fetch_predictions(
        self,
        stop_id: str,
        routes: Optional[set[str]] = None,
        direction: Optional[int] = None,
        limit: int = 10,
    ) -> list[PredictionSummary]:
        async with httpx.AsyncClient() as client:
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

                # Filter by route if specified
                if routes and line_code not in routes:
                    continue

                # Filter by direction if specified (Group maps to direction)
                if direction is not None and group != str(direction):
                    continue

                # Parse Min to epoch
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
