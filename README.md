# A2A Supply Chain Negotiations

Minimal monorepo scaffold for a multi-step negotiation simulator with:

- `web`: Next.js + TypeScript frontend
- `backend`: FastAPI backend
- `runs`: local JSON run records
- `exports`: simulation pipeline exports
- `shared`: shared docs or future schemas
- `docs`: project notes

The backend now runs tomato-ketchup negotiation batches through the OpenAI decision step. One seed creates three different seller, manufacturer, and retailer simulations. If the LLM decision call fails, the run fails cleanly and no fallback simulation data is generated.

## Structure

```text
.
├── backend
├── docs
├── exports
├── runs
├── scripts
├── shared
└── web
```

## Environment Setup

1. Copy the example file:

```bash
cp env.example .env
```

2. Fill in the values you want to test:

```bash
OPENAI_API_KEY=your_openai_api_key
OPENAI_MODEL=gpt-4.1-mini
LANGFUSE_PUBLIC_KEY=your_langfuse_public_key
LANGFUSE_SECRET_KEY=your_langfuse_secret_key
LANGFUSE_HOST=https://cloud.langfuse.com
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
```

Notes:

- If `OPENAI_API_KEY` is missing, the simulation endpoint fails cleanly and no run is created.
- If `LANGFUSE_PUBLIC_KEY` or `LANGFUSE_SECRET_KEY` is missing, the simulation still runs and tracing is skipped cleanly.
- There is no deterministic fallback path for failed LLM decisions.

## Backend Install

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
```

## Frontend Install

```bash
npm install
```

## One-Step Setup

```bash
./scripts/setup-all.sh
```

This script:

- creates `.venv` if needed
- installs backend dependencies
- installs frontend dependencies

## Start The Backend

```bash
source .venv/bin/activate
./scripts/run-backend.sh
```

Backend URL:

- `http://localhost:8000`

Useful backend endpoints:

- `GET http://localhost:8000/health`
- `GET http://localhost:8000/runs`
- `GET http://localhost:8000/runs/{id}`
- `POST http://localhost:8000/simulation/run`
- `POST http://localhost:8000/simulation/test-pipeline`
- `http://localhost:8000/docs`

## Start The Frontend

```bash
./scripts/run-web.sh
```

## Start Everything

```bash
./scripts/run-all.sh
```

Or via npm:

```bash
npm run setup:all
npm run dev
```

Frontend URL:

- `http://localhost:3000`

Useful frontend pages:

- `http://localhost:3000/`
- `http://localhost:3000/runs`
- `http://localhost:3000/runs/{id}`

## Run A Full Simulation Locally

From the frontend:

1. Open `http://localhost:3000/` or `http://localhost:3000/runs`
2. Enter a random seed
3. Click `Run Simulation`
4. The app creates three tomato-ketchup simulations and refreshes the runs list
5. Open any generated run detail page from the runs list

From the backend directly:

```bash
curl -X POST http://localhost:8000/simulation/run \
  -H "Content-Type: application/json" \
  -d '{"seed": 42}'
```

What gets saved:

- three run JSON records in `runs/`
- one sourcing, one packaging-cost, and one promotion-demand ketchup scenario derived from the seed
- both phase records when phase one accepts
- round-by-round step history
- offers, market checks, and final outcomes

## How To Test The Pipeline

### From the frontend

1. Post a seed to the backend pipeline endpoint
3. Review the inline result block

Expected behavior:

- Three seeded ketchup runs are created and saved in `runs/`
- A simulation export file is saved in `exports/`
- A trace reference is returned only when Langfuse keys are configured
- Missing OpenAI or Langfuse keys do not crash the app; the result still returns cleanly

### From the backend directly

```bash
curl -X POST http://localhost:8000/simulation/test-pipeline \
  -H "Content-Type: application/json" \
  -d '{"seed": 42}'
```

## Notes

- Backend run records are stored as JSON in `runs/`
- Simulation exports are stored as JSON in `exports/`
- Each run simulates two linked negotiations: seller to manufacturer, then manufacturer to retailer
- Each seed produces three ketchup business scenarios
- The first deal affects the second through the manufacturer cost basis and downstream sell floor
- The frontend uses typed API calls against the FastAPI backend
