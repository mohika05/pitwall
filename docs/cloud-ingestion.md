# Cloud ingestion setup

Pitwall uses three storage layers during historical ingestion:

- Cloudflare R2 Standard stores compressed replay events, Parquet telemetry and
  completed-session manifests.
- PostgreSQL stores searchable session, driver, lap, stint and pit-stop metadata.
- The Mac temporarily decodes one FastF1 session at a time. Both the decoded cache
  and the one-gigabyte object cache are disposable.

Redis can remain local during ingestion. A hosted Redis service is only required when
the application is deployed.

## 1. Create the R2 bucket

In Cloudflare, open **Storage & databases → R2 → Overview** and enable R2. Create a
private bucket named `pitwall-data` using the Standard storage class. R2 may require a
payment method even while usage remains within its free allowance.

Under **Manage R2 API Tokens**, create a token with **Object Read & Write** access
limited to this bucket. Record the Access Key ID and Secret Access Key when they are
shown. The endpoint has this form:

```text
https://<ACCOUNT_ID>.r2.cloudflarestorage.com
```

Do not make the bucket public and do not paste either credential into source files,
issues, commits or chat messages.

## 2. Create PostgreSQL

Create a Neon Postgres project named `pitwall` in a nearby region. Use the direct
connection string for the ingestion run. Pitwall converts `postgresql://` to
`postgresql+asyncpg://` and converts `sslmode=require` for the async driver.

The current local database is 61 MB, of which 48 MB is old duplicated race-event
data. New historical events are stored only as compressed R2 objects. The remaining
metadata projects below Neon's current 0.5 GB free storage limit, but storage usage
must be checked during the batch.

## 3. Configure the untracked `.env`

Keep the existing `.env` file out of Git and set:

```text
DATABASE_URL=postgresql://<user>:<password>@<direct-neon-host>/<database>?sslmode=require

STORAGE_BACKEND=s3
STORAGE_CACHE_DIR=./data/object_cache
STORAGE_CACHE_MAX_BYTES=1073741824
S3_BUCKET=pitwall-data
S3_PREFIX=pitwall
S3_ENDPOINT_URL=https://<ACCOUNT_ID>.r2.cloudflarestorage.com
S3_REGION=auto
S3_ACCESS_KEY_ID=<R2 access key ID>
S3_SECRET_ACCESS_KEY=<R2 secret access key>

FASTF1_CLEANUP_AFTER_PREPARE=true
FASTF1_USE_REQUESTS_CACHE=false
PERSIST_HISTORICAL_EVENTS_IN_DATABASE=false
```

The existing local `REDIS_URL` can remain unchanged while ingestion runs on the Mac.

## 4. Initialize and verify

Apply the schema to the new database:

```sh
cd backend
../.venv/bin/alembic upgrade head
../.venv/bin/python -m scripts.cloud_preflight
```

The preflight performs a real R2 upload, verifies its SHA-256 metadata, downloads and
compares the object, deletes it, lists bucket usage, connects to PostgreSQL and checks
local free space. It never prints credentials.

## 5. Preserve the existing sample

Before changing `DATABASE_URL`, dump the current local database:

```sh
pg_dump 'postgresql://pitwall:pitwall@localhost:5433/pitwall' \
  --format=custom --no-owner --no-privileges --file=/tmp/pitwall-local.dump
```

After creating the empty cloud database and applying migrations, restore the data
using the standard Neon URL copied from its dashboard:

```sh
pg_restore --dbname="$NEON_DATABASE_URL" --no-owner --no-privileges \
  --clean --if-exists /tmp/pitwall-local.dump
```

Then upload the 11 existing canonical sessions to R2:

```sh
cd backend
../.venv/bin/python -m scripts.storage_admin
../.venv/bin/python -m scripts.cloud_preflight
```

The second preflight should report 11 completed-session manifests and roughly
0.18 GB of canonical objects.

## 6. Rehearse and run the batch

Start the backend with the cloud `.env` and local Redis:

```sh
cd backend
../.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
```

In another terminal, prepare one new session as an end-to-end rehearsal:

```sh
cd backend
../.venv/bin/python -m scripts.prepare_catalogue \
  --years 2023 --max-sessions 1 --stop-on-error
../.venv/bin/python -m scripts.cloud_preflight
```

When that passes, process each season sequentially:

```sh
../.venv/bin/python -m scripts.prepare_catalogue --years 2023
../.venv/bin/python -m scripts.prepare_catalogue --years 2024
../.venv/bin/python -m scripts.prepare_catalogue --years 2025
../.venv/bin/python -m scripts.prepare_catalogue --years 2026
../.venv/bin/python -m scripts.cloud_preflight
```

The runner skips completed manifests, retries a failed session once and refuses to
start a new session below 3 GB of local free space. Rerunning the same command resumes
from the first incomplete session. The preflight enforces a default 9.5 GB remote
budget, leaving headroom under R2's 10 GB Standard free allowance.

Do not start ML retraining or deployment until every intended session has a complete
manifest, the final preflight passes, and failed/partial preparation jobs have been
reviewed.

## 7. Automatic post-session ingestion

The `Historical ingestion` GitHub Actions workflow runs every six hours and can also
be started manually. It waits two hours after a session ends, inspects the previous
30 days, checks R2 manifests directly, and prepares only sessions without a complete
manifest. This direct cloud check prevents a fresh Actions runner from redownloading
the historical archive when its Redis instance starts empty.

Configure these GitHub Actions repository secrets before enabling the schedule:

```text
DATABASE_URL
S3_BUCKET
S3_ENDPOINT_URL
S3_ACCESS_KEY_ID
S3_SECRET_ACCESS_KEY
```

The workflow uses an ephemeral Redis service, applies migrations, removes FastF1
cache data after each session, and runs the cloud preflight when ingestion ends.
Only one scheduled or manually dispatched ingestion run can execute at a time.
