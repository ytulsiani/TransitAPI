from abc import ABC, abstractmethod
from typing import Optional

from api.models import DirectionSummary, LineSummary, PredictionSummary, StopSummary


class TransitClient(ABC):

    @abstractmethod
    async def fetch_lines(self) -> list[LineSummary]: ...

    @abstractmethod
    async def fetch_stops(
        self, route_id: str, route_type: Optional[str] = None
    ) -> list[StopSummary]: ...

    @abstractmethod
    async def fetch_directions(
        self, route_id: str, route_type: Optional[str] = None
    ) -> list[DirectionSummary]: ...

    @abstractmethod
    async def fetch_predictions(
        self,
        stop_id: str,
        routes: Optional[set[str]] = None,
        direction: Optional[int] = None,
        limit: int = 10,
        route_type: Optional[str] = None,
    ) -> list[PredictionSummary]: ...
