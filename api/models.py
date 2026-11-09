from datetime import date
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


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


class WeatherLocation(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)

    zip_code: str
    city: str
    state: Optional[str] = None
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    timezone: str


class CurrentWeather(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)

    time: int = Field(ge=0)
    temperature_f: float
    feels_like_f: Optional[float]
    weather_code: int = Field(ge=0)
    condition: str
    is_day: bool


class DailyWeather(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)

    date: date
    high_f: float
    low_f: float
    precipitation_probability_percent: Optional[int] = Field(ge=0, le=100)


class WeatherResponse(BaseModel):
    location: WeatherLocation
    current: CurrentWeather
    today: DailyWeather
    fetched_at: int
    attribution: str = "Weather data by Open-Meteo.com"
    attribution_url: str = "https://open-meteo.com/"


class TransitClientError(Exception):
    def __init__(self, message: str, status_code: int = 502):
        self.message = message
        self.status_code = status_code
        super().__init__(message)
