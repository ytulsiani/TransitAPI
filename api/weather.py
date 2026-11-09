from fastapi import APIRouter, HTTPException, Query

from api.models import WeatherResponse
from api.weather_client import WeatherClient, WeatherClientError

router = APIRouter()
weather_client = WeatherClient()


@router.get("/weather", response_model=WeatherResponse)
async def get_weather(
    zip_code: str = Query(
        ..., alias="zip", pattern=r"^[0-9]{5}$", description="Five-digit U.S. ZIP code"
    ),
) -> WeatherResponse:
    try:
        return await weather_client.fetch_weather(zip_code)
    except WeatherClientError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from None
