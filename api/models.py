from typing import Optional

from pydantic import BaseModel


class LineSummary(BaseModel):
    id: Optional[str] = None
    long_name: Optional[str] = None
    routes: list[str] = []
    type: Optional[str] = None
    has_directions: bool = True


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


class MetroSummary(BaseModel):
    id: str
    name: str
    region: str


class TransitClientError(Exception):
    def __init__(self, message: str, status_code: int = 502):
        self.message = message
        self.status_code = status_code
        super().__init__(message)
