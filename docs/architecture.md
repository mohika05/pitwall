# Architecture

Pitwall is a modular monolith. Provider adapters retrieve OpenF1 timing and FastF1
telemetry; normalization emits stable domain events. PostgreSQL stores normalized
source entities; compressed historical events live in object storage.
The replay engine applies ordered events to `RaceState` and
uses copied snapshots for seeking. An interchangeable local/S3 object store keeps
high-frequency Parquet telemetry, compressed event exports and verified session
manifests outside the event stream. Remote objects are materialized into a bounded
local read cache. Redis caches replay state but is not the durable source of truth.

`workspace_records` stores versioned application payloads: replay checkpoints,
preparation jobs, session enrichment, scenarios and trained pace models. Replay
checkpoints include an event-dataset fingerprint to avoid restoring a cursor into
changed history. Each tab's viewer UUID plus session key identifies a controller
and its broadcast channel. REST commands and WebSockets carry that same identity.

The current deployment is one backend process. Preparation uses a bounded worker
semaphore and durable job states. Startup marks abandoned jobs interrupted rather
than silently starting expensive downloads. A session manifest is published only
after object sizes are verified; successful preparation then removes that session's
disposable decoded FastF1 cache. A shared provider request budget covers catalogue
and preparation requests.

Frontend entry: `index.html` → `src/main.tsx` → `src/app/App.tsx`. React renders
Strategy, Analyze and Replay workspaces. Zustand holds replay state and driver
selection. `useResource` loads cancellable REST resources. The replay WebSocket and
telemetry polling remain separate. Global CSS defines the F1 timing-screen theme.
URL query parameters (`session`, `time`, `driver`) carry shareable race moments.

Historical analysis exposes laps, stints, event markers, provider qualifying stages,
weather/race control, telemetry coverage and official classification separately.
Strategy simulation branches into an independent engine. It never writes generated
events into historical storage.
