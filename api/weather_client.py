from datetime import datetime, timezone
from typing import Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import httpx
from cachetools import TTLCache

from api.models import CurrentWeather, DailyWeather, WeatherLocation, WeatherResponse

GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

# Open-Meteo's WMO weather codes. Keep descriptions here so firmware does not
# need a new release to understand a provider's condition codes.
CONDITIONS = {
    0: "Clear",
    1: "Mostly clear",
    2: "Partly cloudy",
    3: "Overcast",
    45: "Fog",
    48: "Freezing fog",
    51: "Light drizzle",
    53: "Drizzle",
    55: "Heavy drizzle",
    56: "Light freezing drizzle",
    57: "Heavy freezing drizzle",
    61: "Light rain",
    63: "Rain",
    65: "Heavy rain",
    66: "Light freezing rain",
    67: "Heavy freezing rain",
    71: "Light snow",
    73: "Snow",
    75: "Heavy snow",
    77: "Snow grains",
    80: "Light rain showers",
    81: "Rain showers",
    82: "Heavy rain showers",
    85: "Light snow showers",
    86: "Heavy snow showers",
    95: "Thunderstorm",
    96: "Thunderstorm with hail",
    97: "Heavy thunderstorm",
    99: "Thunderstorm with heavy hail",
}


class WeatherClientError(Exception):
    def __init__(self, message: str, status_code: int = 502):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class WeatherClient:
    def __init__(self, transport: Optional[httpx.AsyncBaseTransport] = None):
        self.transport = transport
        self.locations_cache: TTLCache = TTLCache(maxsize=1000, ttl=86400)
        self.weather_cache: TTLCache = TTLCache(maxsize=1000, ttl=600)

    async def fetch_weather(self, zip_code: str) -> WeatherResponse:
        cached = self.weather_cache.get(zip_code)
        if cached is not None:
            # A ten-minute cache must not serve yesterday's daily forecast
            # across midnight in the location's time zone.
            local_today = datetime.now(ZoneInfo(cached.location.timezone)).date()
            if cached.today.date == local_today:
                return cached

        async with httpx.AsyncClient(timeout=10, transport=self.transport) as client:
            location = await self._fetch_location(client, zip_code)
            forecast = await self._get_json(
                client,
                FORECAST_URL,
                {
                    "latitude": location.latitude,
                    "longitude": location.longitude,
                    "current": "temperature_2m,apparent_temperature,weather_code,is_day",
                    "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max",
                    "temperature_unit": "fahrenheit",
                    "timezone": "auto",
                    "forecast_days": 1,
                    "timeformat": "unixtime",
                },
            )

        try:
            local_timezone = ZoneInfo(forecast["timezone"])
            current = forecast["current"]
            daily = forecast["daily"]
            if current["is_day"] not in (0, 1):
                raise ValueError("Invalid day/night value")
            result = WeatherResponse(
                location=location.model_copy(
                    update={"timezone": forecast["timezone"]}
                ),
                current=CurrentWeather(
                    time=current["time"],
                    temperature_f=current["temperature_2m"],
                    feels_like_f=current["apparent_temperature"],
                    weather_code=current["weather_code"],
                    condition=CONDITIONS.get(current["weather_code"], "Unknown"),
                    is_day=bool(current["is_day"]),
                ),
                today=DailyWeather(
                    date=(
                        datetime.fromtimestamp(daily["time"][0], tz=timezone.utc)
                        .astimezone(local_timezone)
                        .date()
                    ),
                    high_f=daily["temperature_2m_max"][0],
                    low_f=daily["temperature_2m_min"][0],
                    precipitation_probability_percent=(
                        daily["precipitation_probability_max"][0]
                    ),
                ),
                fetched_at=int(datetime.now(timezone.utc).timestamp()),
            )
            if result.today.date != datetime.now(local_timezone).date():
                raise ValueError("Provider returned a forecast for a different day")
        except (
            KeyError, IndexError, TypeError, ValueError,
            OverflowError, ZoneInfoNotFoundError,
        ):
            raise WeatherClientError(
                "Weather provider returned invalid forecast data"
            ) from None

        self.weather_cache[zip_code] = result
        return result

    async def _fetch_location(
        self, client: httpx.AsyncClient, zip_code: str
    ) -> WeatherLocation:
        if zip_code in self.locations_cache:
            return self.locations_cache[zip_code]

        data = await self._get_json(
            client,
            GEOCODING_URL,
            {"name": zip_code, "countryCode": "US", "count": 100, "language": "en"},
        )
        try:
            results = data.get("results", [])
            if not isinstance(results, list):
                raise ValueError("Invalid locations")
            for location in results:
                # Search can also return name matches; never substitute a
                # nearby or unrelated place for the exact requested ZIP.
                if not isinstance(location, dict):
                    raise ValueError("Invalid location")
                postcodes = location.get("postcodes", [])
                if not isinstance(postcodes, list):
                    raise ValueError("Invalid postcodes")
                if location["country_code"] == "US" and zip_code in postcodes:
                    result = WeatherLocation(
                        zip_code=zip_code,
                        city=location["name"],
                        state=location.get("admin1"),
                        latitude=location["latitude"],
                        longitude=location["longitude"],
                        timezone=location["timezone"],
                    )
                    self.locations_cache[zip_code] = result
                    return result
        except (KeyError, TypeError, ValueError):
            raise WeatherClientError(
                "Weather provider returned invalid location data"
            ) from None

        raise WeatherClientError("ZIP code not found", status_code=404)

    @staticmethod
    async def _get_json(client: httpx.AsyncClient, url: str, params: dict) -> dict:
        try:
            response = await client.get(url, params=params)
            response.raise_for_status()
        except httpx.TimeoutException:
            raise WeatherClientError(
                "Weather provider timed out", status_code=504
            ) from None
        except httpx.HTTPError:
            raise WeatherClientError("Weather provider is unavailable") from None

        try:
            data = response.json()
            if not isinstance(data, dict) or data.get("error"):
                raise ValueError("Invalid response")
            return data
        except ValueError:
            raise WeatherClientError("Weather provider returned invalid JSON data") from None
