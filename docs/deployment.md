# Public deployment

Pitwall ships as one production image. FastAPI serves the compiled React assets,
REST endpoints under `/api`, and replay WebSockets under `/ws`. This avoids separate
frontend CORS and WebSocket configuration.

## Services

- One Render web service using the root `Dockerfile` and `render.yaml`
- A durable PostgreSQL database
- A Redis-compatible service
- A private S3-compatible bucket, preferably Cloudflare R2

Keep the web service at one instance. Replay controllers and the preparation worker
currently live in one process.

## Object storage

Create a private bucket and an API credential with object read/write access. Set the
following Render environment variables:

```text
STORAGE_BACKEND=s3
S3_BUCKET=<bucket name>
S3_PREFIX=pitwall
S3_ENDPOINT_URL=<S3-compatible endpoint>
S3_REGION=auto
S3_ACCESS_KEY_ID=<credential id>
S3_SECRET_ACCESS_KEY=<credential secret>
STORAGE_CACHE_MAX_BYTES=1073741824
FASTF1_CLEANUP_AFTER_PREPARE=true
FASTF1_USE_REQUESTS_CACHE=false
PERSIST_HISTORICAL_EVENTS_IN_DATABASE=false
```

Objects are uploaded with a SHA-256 metadata value and verified with a `HEAD`
request before the session manifest is published. The manifest is the readiness
marker. Hosted instances download requested Parquet files into a one-gigabyte LRU
cache, so an ephemeral filesystem is sufficient.

Upload the existing prepared sessions from a trusted local shell after setting the
same S3 variables:

```sh
cd backend
../.venv/bin/python -m scripts.storage_admin
```

## Database and Redis

Set `DATABASE_URL` to an asyncpg URL. If the provider gives a URL beginning with
`postgresql://`, change only the scheme to `postgresql+asyncpg://`. Set `REDIS_URL`
to the provider's Redis connection URL. The container applies Alembic migrations on
every start.

The existing local database can be copied with `pg_dump` and `pg_restore`, or the
sessions can be prepared again against the hosted database. Never commit a database
URL, access key, token, or dump file.

## Historical ingestion

FastF1 preparation can exceed the memory available to a free web instance. Run the
backend locally with the hosted PostgreSQL, Redis, and S3 variables, then process one
season at a time:

```sh
cd backend
../.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
../.venv/bin/python -m scripts.prepare_catalogue --years 2023 --stop-on-error
../.venv/bin/python -m scripts.prepare_catalogue --years 2024 --stop-on-error
../.venv/bin/python -m scripts.prepare_catalogue --years 2025 --stop-on-error
../.venv/bin/python -m scripts.prepare_catalogue --years 2026 --stop-on-error
```

Use separate terminals for the server and batch command. Completed sessions are
skipped on reruns. Each session is downloaded, normalized, uploaded and verified
before its FastF1 cache is removed.

The current 11-session sample occupies 174.7 MiB in canonical objects. At that
measured rate, 480 sessions would occupy approximately 7.45 GiB. Historical events
are stored once as compressed objects instead of being duplicated in PostgreSQL.

## Verification

After deployment, check:

```text
GET /health
GET /health/db
GET /health/redis
GET /api/catalog/2025
GET /api/sessions
```

Open one prepared race, run a Strategy scenario, compare laps in Analyze, play and
seek the replay, select multiple drivers, load the track map, and verify the browser
uses a secure `wss://` replay connection.

Render's Blueprint format, Docker deployment, and health checks are documented in
the [Render Blueprint reference](https://render.com/docs/blueprint-spec),
[Docker guide](https://render.com/docs/docker), and
[health-check guide](https://render.com/docs/health-checks). Cloudflare documents
the current R2 allowance and usage pricing in its
[R2 pricing guide](https://developers.cloudflare.com/r2/pricing/).
