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
OPENAI_MODEL=gpt-5.4
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
- `GET http://localhost:8000/runs/{id}/detail`
- `GET http://localhost:8000/runs/{id}/counterfactual`
- `POST http://localhost:8000/simulation/run`
- `POST http://localhost:8000/simulation/run/custom`
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
- `http://localhost:3000/runs/{id}/replay`

## Run A Full Simulation Locally

From the frontend:

1. Open `http://localhost:3000/` or `http://localhost:3000/runs`
2. Enter a random seed
3. Click `Run Simulation`
4. The app creates three tomato-ketchup simulations and refreshes the runs list
5. Open any generated run detail page from the runs list

## Counterfactual Replay And Time Travel

From a run detail page:

1. Click `Open Counterfactual Replay`.
2. Review the cheap deterministic scenario estimates. These do not call OpenAI.
3. Click `Run AI Rerun` only when you want to spend tokens on a new AI-backed counterfactual run.
4. Use `Time Travel Branches` to select any recorded step from the original run.
5. Enter a branch instruction that describes the alternate history.
6. Click `Run Branch` only when you want to spend tokens on a new AI-backed branch.
7. Open the generated run from the success link.

The original run is never mutated by replay, rerun, or branch actions.

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
- a structured event log per run in `events/`
- an export bundle per run in `exports/{run_id}/`

## Tracing

What gets traced when Langfuse is configured:

- the full simulation run
- each negotiation phase
- each agent decision
- each tool call
- each OpenAI decision call
- the final run result

Tracing is best-effort:

- if `LANGFUSE_PUBLIC_KEY` or `LANGFUSE_SECRET_KEY` is missing, the simulation still runs
- if the Langfuse SDK is unavailable or tracing init fails, the simulation still runs
- trace metadata is only exported when a real trace id is available

How to check if tracing is working:

1. Set valid `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, and `LANGFUSE_HOST` values in `.env`.
2. Run a simulation from the frontend or with `POST /simulation/run`.
3. Open the run detail page and check the `Trace status and exports` section.
4. Inspect `exports/{run_id}/trace-metadata.json` for the saved trace id and trace URL.
5. Inspect `exports/{run_id}/conversation.json` if you want the ordered negotiation transcript in chat-like form.

If tracing is not working, the app will still complete the simulation, but the run detail page and trace export will show tracing as unavailable.

## Storage

What gets saved in `runs/`:

- one canonical JSON run record per run at `runs/{run_id}.json`
- product context, agents, phases, steps, negotiations, diagnosis, and run status

What gets saved in `events/`:

- one structured event stream per run at `events/{run_id}.events.json`
- run lifecycle events, phase transitions, offers, tool calls, market checks, accept/reject/timeout outcomes, and final outcome

What gets saved in `exports/`:

- one folder per exported run at `exports/{run_id}/`
- `summary.json`: run snapshot plus lightweight derived values
- `event-log.json`: exported structured event log for downstream use
- `trace-metadata.json`: saved trace id, trace URL, Langfuse status, and phase-level trace summary
- `conversation.json`: ordered negotiation transcript derived from the run steps

Derived fields currently exported include:

- belief gap samples and average belief gap
- manufacturer margin after the first deal
- where the run failed
- suspected failure type when one can be inferred cheaply

Runtime storage directories are intentionally kept out of version control except for
their `.gitkeep` placeholders. Local tests can isolate storage by setting
`A2A_RUNS_DIR`, `A2A_EVENTS_DIR`, and `A2A_EXPORTS_DIR`.

## Tests

```bash
npm test
```

The test suite covers the backend health and run APIs, missing-OpenAI preflight
behavior, deterministic seeded scenario generation, price coercion, and a fake-LLM
negotiation path.

## Notes

- Backend run records are stored as JSON in `runs/`
- Structured event logs are stored as JSON in `events/`
- Simulation export bundles are stored as JSON in `exports/{run_id}/`
- Each run simulates two linked negotiations: seller to manufacturer, then manufacturer to retailer
- Each seed produces three ketchup business scenarios
- The first deal affects the second through the manufacturer cost basis and downstream sell floor
- The frontend uses typed API calls against the FastAPI backend
