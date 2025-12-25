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
