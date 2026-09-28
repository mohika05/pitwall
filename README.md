# Pitwall

Formula 1 strategy experiments, historical replay and session analysis.
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

- **Strategy:** branch at a replay moment, replace the next pit decision, compare
  recorded history or a decision-time baseline, save scenarios and inspect sensitivity.
- **Analyze:** compare lap times and telemetry, review stints, practice long-run pace,
  recorded qualifying stages, race-control events and separate official results.
- **Replay:** choose a real weekend/session, prepare it on demand, control playback,
  seek by time/lap, select drivers, inspect the circuit, tyres, weather and telemetry.

Preparation downloads timing first, then per-driver telemetry. Partial failures keep
usable timing available and can be retried. Interrupted jobs are marked for retry on
restart. Qualifying stage data is enriched during FastF1 preparation. Historical
catalogue metadata is cached while local readiness is refreshed from storage.

Prepared telemetry and compressed replay exports are written through a configurable
storage backend. Development uses `data/`; production can use any S3-compatible
service. A verified manifest is published last, and only then is that session's
data considered ready. Decoded FastF1 data is removed after each preparation attempt,
including partial failures, and remote files use a bounded local cache.

To index telemetry that predates storage manifests and reclaim its decoded cache:

```sh
cd backend
../.venv/bin/python -m scripts.storage_admin --prune-fastf1-cache
```

To prepare completed sessions sequentially with restart-safe readiness checks:

```sh
cd backend
../.venv/bin/python -m scripts.prepare_catalogue --years 2023
```

Run one season first and inspect storage before continuing through every supported
year. Re-running the command skips sessions whose telemetry is already ready.
For a small hosted instance, run ingestion from the local backend configured with
the production PostgreSQL and object-storage credentials. The Mac performs the
FastF1 processing while completed objects and database rows go directly to the
hosted services.

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

See [architecture](docs/architecture.md), [cloud ingestion](docs/cloud-ingestion.md),
[strategy model](docs/strategy-model.md), [data sources](docs/data-sources.md),
[deployment](docs/deployment.md), and [implementation status](docs/implementation-status.md).

## Public deployment

The root `Dockerfile` builds the React app and FastAPI service into one same-origin
image. `render.yaml` is a deployable Render blueprint; supply PostgreSQL, Redis and
S3-compatible storage credentials in the Render dashboard. The backend binds Render's
`PORT`, applies migrations on startup, serves REST at `/api`, WebSockets at `/ws`, and
the frontend at `/`. Keep one backend worker because replay controllers and the
preparation queue are process-local.

Build and exercise that combined image locally with:

```sh
docker compose --profile deployment build production
docker compose --profile deployment up production
```
