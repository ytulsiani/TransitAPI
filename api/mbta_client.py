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

MBTA_BASE_URL = "https://api-v3.mbta.com"

HEADSIGN_ABBREVIATIONS = {
    "Government Center": "Govt Ctr",
    "North Station": "North Sta",
    "South Station": "South Sta",
    "Park Street": "Park St",
    "Downtown Crossing": "Dtx Crossing",
    "Cleveland Circle": "Clvlnd Cir",
    "Heath Street": "Heath St",
    "Union Square": "Union Sq",
}


def _abbreviate_headsign(headsign: Optional[str]) -> Optional[str]:
    if headsign is None:
        return None
    return HEADSIGN_ABBREVIATIONS.get(headsign, headsign)


class MbtaClient(TransitClient):
    def __init__(self):
        self.lines_cache: TTLCache = TTLCache(maxsize=1, ttl=300)
        self.stops_cache: TTLCache = TTLCache(maxsize=100, ttl=300)
        self.directions_cache: TTLCache = TTLCache(maxsize=100, ttl=300)

    async def fetch_lines(self) -> list[LineSummary]:
        cache_key = "lines"
        if cache_key in self.lines_cache:
            return self.lines_cache[cache_key]

        async with httpx.AsyncClient() as client:
            response = await client.get(f"{MBTA_BASE_URL}/lines?include=routes")
            if response.status_code != 200:
                raise TransitClientError(
                    f"MBTA lines request failed with status {response.status_code}"
                )

            data = response.json()
            lines = []

            for line_data in data.get("data", []):
                routes = []
                relationships = line_data.get("relationships", {})
                route_data = relationships.get("routes", {}).get("data", [])
                for route in route_data:
                    route_id = route.get("id")
                    if route_id and not route_id.startswith("Shuttle"):
                        routes.append(route_id)

                attributes = line_data.get("attributes", {})
                lines.append(
                    LineSummary(
                        id=line_data.get("id"),
                        long_name=attributes.get("long_name"),
                        routes=routes,
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
            params = {"filter[route]": route_id}
            response = await client.get(f"{MBTA_BASE_URL}/stops", params=params)
            if response.status_code != 200:
                raise TransitClientError(
                    f"MBTA stops request failed with status {response.status_code}"
                )

            data = response.json()
            stops = []

            for stop_data in data.get("data", []):
                attributes = stop_data.get("attributes", {})
                stops.append(
                    StopSummary(
                        id=stop_data.get("id"),
                        name=attributes.get("name"),
                    )
                )

            self.stops_cache[route_id] = stops
            return stops

    async def fetch_directions(
        self, route_id: str, route_type: Optional[str] = None
    ) -> list[DirectionSummary]:
        if route_id in self.directions_cache:
            return self.directions_cache[route_id]

        async with httpx.AsyncClient() as client:
            response = await client.get(f"{MBTA_BASE_URL}/routes/{route_id}")
            if response.status_code != 200:
                raise TransitClientError(
                    f"MBTA directions request failed with status {response.status_code}"
                )

            data = response.json()
            directions = []

            route_data = data.get("data", {})
            attributes = route_data.get("attributes", {})
            destinations = attributes.get("direction_destinations", [])

            for i, destination in enumerate(destinations or []):
                directions.append(DirectionSummary(id=str(i), destination=destination))

            self.directions_cache[route_id] = directions
            return directions

    async def fetch_predictions(
        self,
        stop_id: str,
        routes: Optional[set[str]] = None,
        direction: Optional[int] = None,
        limit: int = 10,
        route_type: Optional[str] = None,
    ) -> list[PredictionSummary]:
        params = {"filter[stop]": stop_id}

        if direction is not None:
            params["filter[direction_id]"] = str(direction)

        if routes:
            filtered_routes = [r for r in routes if r and r.strip()]
            if filtered_routes:
                params["filter[route]"] = ",".join(filtered_routes)

        params["sort"] = "arrival_time"
        params["include"] = "trip"

        params["page[limit]"] = str(limit + 10)

        async with httpx.AsyncClient() as client:
            response = await client.get(f"{MBTA_BASE_URL}/predictions", params=params)
            if response.status_code != 200:
                raise TransitClientError(
                    f"MBTA predictions request failed with status {response.status_code}"
                )

            data = response.json()
            predictions = []

            trip_headsigns = {}
            for included in data.get("included", []):
                if included.get("type") == "trip":
                    trip_id = included.get("id")
                    headsign = included.get("attributes", {}).get("headsign")
                    if trip_id:
                        trip_headsigns[trip_id] = headsign

            for pred_data in data.get("data", []):
                attributes = pred_data.get("attributes", {})
                arrival_time_str = attributes.get("arrival_time")

                if not arrival_time_str:
                    continue

                try:
                    arrival_dt = datetime.fromisoformat(arrival_time_str.replace("Z", "+00:00"))
                    arrival_epoch = int(arrival_dt.timestamp())
                except (ValueError, AttributeError):
                    continue

                trip_id = (
                    pred_data.get("relationships", {})
                    .get("trip", {})
                    .get("data", {})
                    .get("id")
                )

                headsign = attributes.get("headsign") or trip_headsigns.get(trip_id)

                predictions.append(
                    PredictionSummary(
                        headsign=_abbreviate_headsign(headsign),
                        arrival_time=arrival_epoch,
                        arrival_uncertainty=attributes.get("arrival_uncertainty"),
                    )
                )

            predictions.sort(key=lambda p: p.arrival_time or float("inf"))

            now_epoch = int(datetime.now().timestamp())
            predictions = [p for p in predictions if p.arrival_time and p.arrival_time >= now_epoch]

            return predictions[:limit]
