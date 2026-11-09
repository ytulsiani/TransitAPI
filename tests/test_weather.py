import copy
import unittest
from datetime import datetime, time, timedelta
from unittest.mock import AsyncMock, Mock, patch
from zoneinfo import ZoneInfo

import httpx
from cachetools import TTLCache

from api.index import app
from api.models import PredictionSummary
from api.weather_client import WeatherClient


def forecast_data(timezone_name="America/New_York"):
    local_timezone = ZoneInfo(timezone_name)
    now = datetime.now(local_timezone)
    midnight = datetime.combine(now.date(), time.min, tzinfo=local_timezone)
    return {
        "timezone": timezone_name,
        "current": {
            "time": int(now.timestamp()),
            "temperature_2m": 52.7,
            "apparent_temperature": 46.2,
            "weather_code": 3,
            "is_day": 1,
        },
        "daily": {
            "time": [int(midnight.timestamp())],
            "temperature_2m_max": [53.0],
            "temperature_2m_min": [42.6],
            "precipitation_probability_max": [10],
        },
    }


class WeatherApiTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.requests = []
        self.geocoding = {
            "results": [{
                "name": "Cambridge",
                "admin1": "Massachusetts",
                "country_code": "US",
                "latitude": 42.3751,
                "longitude": -71.10561,
                "timezone": "America/New_York",
                "postcodes": ["02138", "02139"],
            }],
        }
        self.forecast = forecast_data()
        self.forecast_status = 200
        self.provider_exception = None
        self.provider_raw_body = None
        self.weather_client = WeatherClient(transport=httpx.MockTransport(self.upstream))
        client_patch = patch("api.weather.weather_client", self.weather_client)
        client_patch.start()
        self.addCleanup(client_patch.stop)
        self.api = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")
        self.addAsyncCleanup(self.api.aclose)

    def upstream(self, request):
        self.requests.append(request)
        if self.provider_exception:
            raise self.provider_exception("Provider failure", request=request)
        if self.provider_raw_body is not None:
            return httpx.Response(200, text=self.provider_raw_body)
        if request.url.host == "geocoding-api.open-meteo.com":
            return httpx.Response(200, json=self.geocoding)
        self.assertEqual(request.url.host, "api.open-meteo.com")
        return httpx.Response(self.forecast_status, json=self.forecast)

    async def test_weather_response_and_provider_parameters(self):
        response = await self.api.get("/weather", params={"zip": "02139"})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["location"]["zip_code"], "02139")
        self.assertEqual(data["location"]["city"], "Cambridge")
        self.assertEqual(data["location"]["timezone"], "America/New_York")
        self.assertEqual(data["current"]["temperature_f"], 52.7)
        self.assertEqual(data["current"]["feels_like_f"], 46.2)
        self.assertEqual(data["current"]["condition"], "Overcast")
        self.assertTrue(data["current"]["is_day"])
        self.assertEqual(data["current"]["time"], self.forecast["current"]["time"])
        self.assertEqual(data["today"], {
            "date": str(datetime.now(ZoneInfo("America/New_York")).date()),
            "high_f": 53.0,
            "low_f": 42.6,
            "precipitation_probability_percent": 10,
        })
        self.assertGreater(data["fetched_at"], 0)
        self.assertEqual(data["attribution_url"], "https://open-meteo.com/")
        self.assertEqual(len(self.requests), 2)
        self.assertEqual(self.requests[0].url.params["name"], "02139")
        self.assertEqual(self.requests[0].url.params["countryCode"], "US")
        self.assertEqual(self.requests[1].url.params["temperature_unit"], "fahrenheit")
        self.assertEqual(self.requests[1].url.params["timezone"], "auto")
        self.assertEqual(self.requests[1].url.params["timeformat"], "unixtime")
        self.assertEqual(self.requests[1].url.params["forecast_days"], "1")

    async def test_zip_must_be_exactly_five_ascii_digits(self):
        for zip_code in (None, "", "2139", "021390", "02139-1234", "ABCDE", "１２３４５", "02139\n"):
            with self.subTest(zip_code=zip_code):
                params = {} if zip_code is None else {"zip": zip_code}
                response = await self.api.get("/weather", params=params)
                self.assertEqual(response.status_code, 422)
        self.assertEqual(self.requests, [])

    async def test_unknown_zip_returns_404(self):
        self.geocoding = {}
        response = await self.api.get("/weather?zip=00000")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json(), {"detail": "ZIP code not found"})
        self.assertEqual(len(self.requests), 1)

    async def test_search_requires_exact_us_postcode_match(self):
        other_country = copy.deepcopy(self.geocoding["results"][0])
        other_country["country_code"] = "DE"
        other_zip = copy.deepcopy(self.geocoding["results"][0])
        other_zip["postcodes"] = ["02138"]
        self.geocoding["results"] = [other_country, other_zip]
        response = await self.api.get("/weather?zip=02139")
        self.assertEqual(response.status_code, 404)

    async def test_repeat_request_uses_weather_cache(self):
        first = await self.api.get("/weather?zip=02139")
        second = await self.api.get("/weather?zip=02139")
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.json(), second.json())
        self.assertEqual(len(self.requests), 2)

    async def test_expired_weather_reuses_cached_location(self):
        clock = [0]
        self.weather_client.weather_cache = TTLCache(maxsize=10, ttl=600, timer=lambda: clock[0])
        await self.api.get("/weather?zip=02139")
        clock[0] = 601
        response = await self.api.get("/weather?zip=02139")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(self.requests), 3)

    async def test_yesterdays_daily_forecast_is_not_served_from_cache(self):
        await self.api.get("/weather?zip=02139")
        cached = self.weather_client.weather_cache["02139"]
        cached.today.date -= timedelta(days=1)
        response = await self.api.get("/weather?zip=02139")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["today"]["date"], str(datetime.now(ZoneInfo("America/New_York")).date()))
        self.assertEqual(len(self.requests), 3)

    async def test_provider_timezone_controls_today(self):
        self.forecast = forecast_data("Pacific/Honolulu")
        response = await self.api.get("/weather?zip=02139")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["location"]["timezone"], "Pacific/Honolulu")
        self.assertEqual(response.json()["today"]["date"], str(datetime.now(ZoneInfo("Pacific/Honolulu")).date()))

    async def test_missing_optional_readings_stay_null_and_zero_stays_zero(self):
        self.forecast["current"]["apparent_temperature"] = None
        self.forecast["current"]["temperature_2m"] = 0
        self.forecast["current"]["is_day"] = 0
        self.forecast["daily"]["precipitation_probability_max"] = [None]
        response = await self.api.get("/weather?zip=02139")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["current"]["temperature_f"], 0)
        self.assertIsNone(response.json()["current"]["feels_like_f"])
        self.assertFalse(response.json()["current"]["is_day"])
        self.assertIsNone(response.json()["today"]["precipitation_probability_percent"])

    async def test_unknown_condition_has_readable_fallback(self):
        self.forecast["current"]["weather_code"] = 999
        response = await self.api.get("/weather?zip=02139")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["current"]["condition"], "Unknown")

    async def test_provider_http_failure_is_not_cached(self):
        self.forecast_status = 429
        response = await self.api.get("/weather?zip=02139")
        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.json(), {"detail": "Weather provider is unavailable"})
        self.forecast_status = 200
        response = await self.api.get("/weather?zip=02139")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(self.requests), 3)

    async def test_provider_timeout_and_connection_failure(self):
        for exception, status in ((httpx.ReadTimeout, 504), (httpx.ConnectError, 502)):
            with self.subTest(exception=exception):
                self.provider_exception = exception
                response = await self.api.get("/weather?zip=02139")
                self.assertEqual(response.status_code, status)

    async def test_invalid_forecasts_return_controlled_502(self):
        valid = forecast_data()
        malformed = [[], {}, {**valid, "timezone": "Invalid/Zone"}]
        for key, value in (("temperature_2m_max", []), ("temperature_2m_min", [None]), ("precipitation_probability_max", [101])):
            item = copy.deepcopy(valid)
            item["daily"][key] = value
            malformed.append(item)
        for forecast in malformed:
            with self.subTest(forecast=forecast):
                self.forecast = forecast
                response = await self.api.get("/weather?zip=02139")
                self.assertEqual(response.status_code, 502)
        self.assertEqual(len(self.weather_client.weather_cache), 0)

    async def test_invalid_location_data_returns_controlled_502(self):
        self.geocoding = {"results": None}
        response = await self.api.get("/weather?zip=02139")
        self.assertEqual(response.status_code, 502)

    async def test_malformed_postcodes_cannot_produce_a_partial_match(self):
        self.geocoding["results"][0]["postcodes"] = "021390"
        response = await self.api.get("/weather?zip=02139")
        self.assertEqual(response.status_code, 502)

    async def test_invalid_json_returns_controlled_502(self):
        self.provider_raw_body = "<html>Service unavailable</html>"
        response = await self.api.get("/weather?zip=02139")
        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.json(), {
            "detail": "Weather provider returned invalid JSON data"
        })

    async def test_previous_day_from_provider_is_rejected(self):
        self.forecast["daily"]["time"][0] -= 86400
        response = await self.api.get("/weather?zip=02139")
        self.assertEqual(response.status_code, 502)

    async def test_health_and_existing_transit_endpoints_still_work(self):
        response = await self.api.get("/health")
        self.assertEqual(response.json(), {"status": "ok"})
        predictions = [PredictionSummary(headsign="Alewife", arrival_time=1800000000)]
        transit_client = Mock(fetch_predictions=AsyncMock(return_value=predictions))
        with patch("api.index.METROS", {"mbta": {"client": transit_client}}):
            for endpoint in ("/predictions", "/metros/mbta/predictions"):
                response = await self.api.post(endpoint, json={"stop_id": "place-harsq"})
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()["predictions"][0]["headsign"], "Alewife")
        self.assertEqual(self.requests, [])


if __name__ == "__main__":
    unittest.main()
