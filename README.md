# Pitwall

Formula 1 historical replay, session analysis, strategy experiments and live timing.
React/TypeScript + FastAPI, PostgreSQL, Redis and FastF1 Parquet telemetry.

## Run locally

Requirements: Python 3.12, Node 22.13+ and Docker (for PostgreSQL/Redis).

```sh
cp .env.example .env  # only for a new checkout; preserve existing credentials
python3 -m venv .venv
.venv/bin/pip install -e './backend[dev]'
docker compose up -d postgres redis
cd backend
../.venv/bin/alembic upgrade head
../.venv/bin/uvicorn app.main:app --reload
```

In a second terminal:

```sh
cd frontend
npm ci
npm run dev
```

Open http://localhost:5173. Vite proxies `/api` and `/ws` to the backend.
`VITE_API_BASE_URL` and `VITE_WS_BASE_URL` can override those defaults.

## Run the complete stack

```sh
docker compose up --build
```

Open http://localhost:8080. The backend applies migrations before startup. Existing
PostgreSQL/Redis volumes are retained and `./data` stores telemetry and provider caches.
The provided deployment binds application ports to localhost and uses one backend
worker. Put authentication and HTTPS in front of it before exposing it publicly;
viewer UUIDs isolate playback but are not user authentication. Do not scale backend
workers until the job/replay ownership layer is moved to shared coordination.

## Workspaces

- **Replay:** choose a real weekend/session, prepare it on demand, control playback,
  seek by time/lap, select drivers, inspect the circuit, tyres, weather and telemetry.
- **Analyze:** compare lap times and telemetry, review stints, practice long-run pace,
  recorded qualifying stages, race-control events and separate official results.
- **Strategy:** branch at a replay moment, replace the next pit decision, compare
  recorded history or a decision-time baseline, save scenarios and inspect sensitivity.
- **Live:** start/stop a session feed using its OpenF1 session ID. Requires a valid
  `OPENF1_ACCESS_TOKEN`; access during an active session depends on your provider plan.

Preparation downloads timing first, then per-driver telemetry. Partial failures keep
usable timing available and can be retried. Interrupted jobs are marked for retry on
restart. Qualifying stage data is enriched during FastF1 preparation. Historical
catalogue metadata is cached while local readiness is refreshed from storage.

Each browser tab has a replay identity. Cursor checkpoints are saved to PostgreSQL
at most every five seconds while playing, and on commands. Reload/restart recovery
is paused and only restores against the same event dataset fingerprint.

## Strategy and ML boundaries

The simulator is an explicit, deterministic **lap-level approximation**. It models
compound pace, age degradation, fuel trend, pit transit/service loss, warm-up and a
simple rejoin/traffic penalty. Historical mode reuses recorded future conditions;
forecast mode uses only pre-branch laps and holds current conditions constant.
Opponent strategies do not react. Rejoin is estimated from branch-point gaps.
The branch starts at the driver's last completed lap, not a physical mid-lap state.
Wet strategy calibration and verified tyre inventories are not available. The dry
compound constraint is optional and user-supplied; the application is not a full
regulation engine. Sensitivity ranges are not statistical confidence intervals.

ML training requires at least two prepared sessions and 30 clean dry laps per
session. The latest session is held out. Only models beating a constant pace-delta
baseline are eligible. Target training/holdout sessions and future training data
in forecast mode are excluded. Unsupported models/ages/compounds use the baseline.
Training implements a ridge pace-delta model, not a validated causal tyre model.
No pretrained model is shipped; actual accuracy must be assessed on your dataset.

Live polling shares the provider rate budget with downloads and catalogue requests.
It merges duplicates/corrections and reconstructs state through the same domain
engine. Updates are batched, not a low-latency streaming guarantee. A three-minute
lookback catches recent corrections; older corrections need a fresh feed restart.

## Verification

```sh
cd backend
../.venv/bin/python -m pytest -q
# Opt-in: migrated local PostgreSQL/Redis and at least one prepared race required
PITWALL_INTEGRATION=1 ../.venv/bin/python -m pytest tests/integration -q
cd ../frontend
npm test
npm run lint
npm run build
npm run test:e2e
```

Browser checks use installed Chrome locally and Playwright Chromium in CI. Screenshots
and traces are written under `frontend/test-results/` (ignored). Backend integration
checks create and clean up their own checkpoint/scenario records.

Health: `/health`, `/health/db`, `/health/redis`. Metrics: `/metrics` (Prometheus text).
API documentation: http://localhost:8000/docs.

See [architecture](docs/architecture.md), [strategy model](docs/strategy-model.md),
[data sources](docs/data-sources.md), and [implementation status](docs/implementation-status.md).
