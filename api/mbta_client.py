from datetime import datetime
from typing import Optional

import httpx
from cachetools import TTLCache
from pydantic import BaseModel

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

lines_cache: TTLCache = TTLCache(maxsize=1, ttl=300)
stops_cache: TTLCache = TTLCache(maxsize=100, ttl=300)
directions_cache: TTLCache = TTLCache(maxsize=100, ttl=300)


class LineSummary(BaseModel):
    id: Optional[str] = None
    long_name: Optional[str] = None
    routes: list[str] = []


class StopSummary(BaseModel):
    id: Optional[str] = None
    name: Optional[str] = None


class DirectionSummary(BaseModel):
    id: str
    destination: str


class PredictionSummary(BaseModel):
    headsign: Optional[str] = None
    arrival_time: Optional[int] = None
    arrival_uncertainty: Optional[int] = None


class MbtaClientError(Exception):
    def __init__(self, message: str, status_code: int = 502):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


def abbreviate_headsign(headsign: Optional[str]) -> Optional[str]:
    if headsign is None:
        return None
    return HEADSIGN_ABBREVIATIONS.get(headsign, headsign)


async def fetch_lines() -> list[LineSummary]:
    cache_key = "lines"
    if cache_key in lines_cache:
        return lines_cache[cache_key]

    async with httpx.AsyncClient() as client:
        response = await client.get(f"{MBTA_BASE_URL}/lines?include=routes")
        if response.status_code != 200:
            raise MbtaClientError(
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

        lines_cache[cache_key] = lines
        return lines


async def fetch_stops(route_id: str) -> list[StopSummary]:
    if route_id in stops_cache:
        return stops_cache[route_id]

    async with httpx.AsyncClient() as client:
        params = {"filter[route]": route_id}
        response = await client.get(f"{MBTA_BASE_URL}/stops", params=params)
        if response.status_code != 200:
            raise MbtaClientError(
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

        stops_cache[route_id] = stops
        return stops


async def fetch_directions(route_id: str) -> list[DirectionSummary]:
    if route_id in directions_cache:
        return directions_cache[route_id]

    async with httpx.AsyncClient() as client:
        response = await client.get(f"{MBTA_BASE_URL}/routes/{route_id}")
        if response.status_code != 200:
            raise MbtaClientError(
                f"MBTA directions request failed with status {response.status_code}"
            )

        data = response.json()
        directions = []

        route_data = data.get("data", {})
        attributes = route_data.get("attributes", {})
        destinations = attributes.get("direction_destinations", [])

        for i, destination in enumerate(destinations or []):
            directions.append(DirectionSummary(id=str(i), destination=destination))

        directions_cache[route_id] = directions
        return directions


async def fetch_predictions(
    stop_id: str,
    routes: Optional[set[str]] = None,
    direction: Optional[int] = None,
    limit: int = 10,
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
            raise MbtaClientError(
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
                    headsign=abbreviate_headsign(headsign),
                    arrival_time=arrival_epoch,
                    arrival_uncertainty=attributes.get("arrival_uncertainty"),
                )
            )

        predictions.sort(key=lambda p: p.arrival_time or float("inf"))

        now_epoch = int(datetime.now().timestamp())
        predictions = [p for p in predictions if p.arrival_time and p.arrival_time >= now_epoch]

        return predictions[:limit]
