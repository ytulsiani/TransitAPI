import os
from typing import Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from api.base_client import TransitClient
from api.mbta_client import MbtaClient
from api.models import (
    DirectionSummary,
    LineSummary,
    MetroSummary,
    PredictionSummary,
    StopSummary,
    TransitClientError,
)
from api.mta_client import MtaClient
from api.wmata_client import WmataClient

load_dotenv()

app = FastAPI(title="Transit Display API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Metro Registry ---

METROS: dict[str, dict] = {
    "mbta": {
        "name": "MBTA",
        "region": "Boston, MA",
        "client": MbtaClient(),
    },
}

_wmata_key = os.environ.get("WMATA_API_KEY")
if _wmata_key:
    METROS["wmata"] = {
        "name": "WMATA",
        "region": "Washington, DC",
        "client": WmataClient(api_key=_wmata_key),
    }

METROS["mta"] = {
    "name": "MTA",
    "region": "New York, NY",
    "client": MtaClient(bus_api_key=os.environ.get("MTA_BUS_API_KEY")),
}


def _get_client(metro_id: str) -> TransitClient:
    metro = METROS.get(metro_id)
    if not metro:
        raise HTTPException(status_code=404, detail=f"Unknown metro: {metro_id}")
    return metro["client"]


# --- Exception Handlers ---


@app.exception_handler(TransitClientError)
async def transit_client_error_handler(request: Request, exc: TransitClientError):
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.message})


@app.exception_handler(Exception)
async def generic_error_handler(request: Request, exc: Exception):
    return JSONResponse(status_code=502, content={"detail": str(exc)})


# --- Request/Response Models ---


class PredictionRequest(BaseModel):
    stop_id: str
    routes: Optional[set[str]] = None
    direction: Optional[int] = None
    limit: int = 10
    route_type: Optional[str] = None


class MetrosResponse(BaseModel):
    metros: list[MetroSummary]


class LinesResponse(BaseModel):
    lines: list[LineSummary]


class StopsResponse(BaseModel):
    stops: list[StopSummary]


class DirectionsResponse(BaseModel):
    directions: list[DirectionSummary]


class PredictionsResponse(BaseModel):
    predictions: list[PredictionSummary]


class HealthResponse(BaseModel):
    status: str


# --- Endpoints ---


@app.get("/health", response_model=HealthResponse)
async def health():
    return HealthResponse(status="ok")


@app.get("/metros", response_model=MetrosResponse)
async def get_metros():
    metros = [
        MetroSummary(id=metro_id, name=info["name"], region=info["region"])
        for metro_id, info in METROS.items()
    ]
    return MetrosResponse(metros=metros)


# --- Metro-scoped endpoints ---


@app.get("/metros/{metro_id}/lines", response_model=LinesResponse)
async def get_metro_lines(metro_id: str):
    client = _get_client(metro_id)
    lines = await client.fetch_lines()
    return LinesResponse(lines=lines)


@app.get("/metros/{metro_id}/directions/{route}", response_model=DirectionsResponse)
async def get_metro_directions(
    metro_id: str, route: str, route_type: Optional[str] = None
):
    client = _get_client(metro_id)
    directions = await client.fetch_directions(route, route_type=route_type)
    return DirectionsResponse(directions=directions)


@app.get("/metros/{metro_id}/stops/{route}", response_model=StopsResponse)
async def get_metro_stops(
    metro_id: str, route: str, route_type: Optional[str] = None
):
    client = _get_client(metro_id)
    stops = await client.fetch_stops(route, route_type=route_type)
    return StopsResponse(stops=stops)


@app.post("/metros/{metro_id}/predictions", response_model=PredictionsResponse)
async def get_metro_predictions(metro_id: str, request: PredictionRequest):
    client = _get_client(metro_id)
    predictions = await client.fetch_predictions(
        stop_id=request.stop_id,
        routes=request.routes,
        direction=request.direction,
        limit=request.limit,
        route_type=request.route_type,
    )
    return PredictionsResponse(predictions=predictions)


# --- Backward-compatible routes (delegate to MBTA) ---


@app.get("/lines", response_model=LinesResponse)
async def get_lines():
    client = _get_client("mbta")
    lines = await client.fetch_lines()
    return LinesResponse(lines=lines)


@app.get("/directions/{route}", response_model=DirectionsResponse)
async def get_directions(route: str, route_type: Optional[str] = None):
    client = _get_client("mbta")
    directions = await client.fetch_directions(route, route_type=route_type)
    return DirectionsResponse(directions=directions)


@app.get("/stops/{route}", response_model=StopsResponse)
async def get_stops(route: str, route_type: Optional[str] = None):
    client = _get_client("mbta")
    stops = await client.fetch_stops(route, route_type=route_type)
    return StopsResponse(stops=stops)


@app.post("/predictions", response_model=PredictionsResponse)
async def get_predictions(request: PredictionRequest):
    client = _get_client("mbta")
    predictions = await client.fetch_predictions(
        stop_id=request.stop_id,
        routes=request.routes,
        direction=request.direction,
        limit=request.limit,
        route_type=request.route_type,
    )
    return PredictionsResponse(predictions=predictions)
