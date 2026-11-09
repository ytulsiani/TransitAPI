## Setup

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## Run locally

```bash
source venv/bin/activate
uvicorn api.index:app --reload --port 8080
```

## Deploy to Vercel

```bash
vercel
```

## API

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | Health check |
| GET | `/lines` | Get all MBTA lines |
| GET | `/directions/{route}` | Get directions for a route |
| GET | `/stops/{route}` | Get stops for a route |
| POST | `/predictions` | Get arrival predictions |
| GET | `/weather?zip=02139` | Get current weather and today's forecast for a U.S. ZIP code |

### Predictions request body

```json
{
  "stop_id": "place-harsq",
  "routes": ["Red"],
  "direction": 0,
  "limit": 3
}
```

Only `stop_id` is required.

### Weather

```bash
curl 'http://localhost:8080/weather?zip=02139'
```

`zip` must be exactly five ASCII digits. Keep leading zeroes: `02139` is valid;
`2139` and ZIP+4 values are not supported. Locations must have an exact matching
U.S. ZIP code in the provider's location database. Weather is representative of
the matching town/city, rather than an individual address.

Example response (illustrative values):

```json
{
  "location": {
    "zip_code": "02139",
    "city": "Cambridge",
    "state": "Massachusetts",
    "latitude": 42.3751,
    "longitude": -71.10561,
    "timezone": "America/New_York"
  },
  "current": {
    "time": 1794241800,
    "temperature_f": 52.7,
    "feels_like_f": 46.2,
    "weather_code": 3,
    "condition": "Overcast",
    "is_day": true
  },
  "today": {
    "date": "2026-11-09",
    "high_f": 53.0,
    "low_f": 42.6,
    "precipitation_probability_percent": 10
  },
  "fetched_at": 1794242100,
  "attribution": "Weather data by Open-Meteo.com",
  "attribution_url": "https://open-meteo.com/"
}
```

- All temperatures are Fahrenheit. `feels_like_f` and precipitation probability
  can be `null` when the provider has no reading; `null` does not mean zero.
- `current.time` is the time the provider's current conditions apply to;
  `fetched_at` is when this API fetched them. Both are Unix timestamps in UTC.
  Current conditions are model estimates, not a local weather station reading.
- `today.date` is the forecast date in the location's time zone. Precipitation
  probability is the **maximum hourly probability for that local calendar day**,
  including rain and snow. It is not a rain-only or next-hour forecast.
- Weather is cached for 10 minutes and ZIP locations for 24 hours, in memory per
  server process. Cache reuse is not guaranteed across Vercel instances or cold
  starts. The daily forecast is refreshed when the local calendar day changes.
- Errors use `{"detail": "..."}`: `422` for a missing/malformed ZIP, `404` when
  the ZIP is not found, `502` for unavailable/invalid provider data, and `504`
  for a provider timeout. Failed weather responses are not cached.

Weather data is supplied by [Open-Meteo](https://open-meteo.com/) and its
[geocoding service](https://open-meteo.com/en/docs/geocoding-api). The free
service requires no API key for non-commercial use, subject to the provider's
[usage limits and terms](https://open-meteo.com/en/terms). Commercial use needs
an appropriate subscription and corresponding API configuration. Display the
returned attribution with a link when showing weather data. Values are selected
and renamed from the provider response; condition codes are mapped to short
English descriptions. Data is provided under
[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).

### Tests

```bash
python -m unittest discover -s tests -v
```

Tests use simulated provider responses and do not require an API key or network
access.
