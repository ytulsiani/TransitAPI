from typing import Optional

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from api import mbta_client

app = FastAPI(title="MBTA API")


@app.exception_handler(mbta_client.MbtaClientError)
async def mbta_client_error_handler(request: Request, exc: mbta_client.MbtaClientError):
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.message})


@app.exception_handler(Exception)
async def generic_error_handler(request: Request, exc: Exception):
    return JSONResponse(status_code=502, content={"detail": str(exc)})


class PredictionRequest(BaseModel):
    stop_id: str
    routes: Optional[set[str]] = None
    direction: Optional[int] = None
    limit: int = 10


class LinesResponse(BaseModel):
    lines: list[mbta_client.LineSummary]


class StopsResponse(BaseModel):
    stops: list[mbta_client.StopSummary]


class DirectionsResponse(BaseModel):
    directions: list[mbta_client.DirectionSummary]


class PredictionsResponse(BaseModel):
    predictions: list[mbta_client.PredictionSummary]


class HealthResponse(BaseModel):
    status: str


class ErrorResponse(BaseModel):
    error: str
    details: Optional[str] = None


@app.get("/health", response_model=HealthResponse)
async def health():
    return HealthResponse(status="ok")


@app.get("/lines", response_model=LinesResponse)
async def get_lines():
    lines = await mbta_client.fetch_lines()
    return LinesResponse(lines=lines)


@app.get("/directions/{route}", response_model=DirectionsResponse)
async def get_directions(route: str):
    directions = await mbta_client.fetch_directions(route)
    return DirectionsResponse(directions=directions)


@app.get("/stops/{route}", response_model=StopsResponse)
async def get_stops(route: str):
    stops = await mbta_client.fetch_stops(route)
    return StopsResponse(stops=stops)


@app.post("/predictions", response_model=PredictionsResponse)
async def get_predictions(request: PredictionRequest):
    predictions = await mbta_client.fetch_predictions(
        stop_id=request.stop_id,
        routes=request.routes,
        direction=request.direction,
        limit=request.limit,
    )
    return PredictionsResponse(predictions=predictions)
