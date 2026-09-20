# Architecture

Pitwall is a modular monolith. Provider adapters retrieve OpenF1 timing and FastF1
telemetry; normalization emits stable domain events. PostgreSQL stores source
entities and events. The replay engine applies ordered events to `RaceState` and
uses copied snapshots for seeking. Parquet stores high-frequency telemetry outside
the event stream. Redis caches replay state but is not the durable source of truth.

`workspace_records` stores versioned application payloads: replay checkpoints,
preparation jobs, session enrichment, scenarios and trained pace models. Replay
checkpoints include an event-dataset fingerprint to avoid restoring a cursor into
changed history. Each tab's viewer UUID plus session key identifies a controller
and its broadcast channel. REST commands and WebSockets carry that same identity.

The current deployment is one backend process. Preparation uses a bounded worker
semaphore and durable job states. Startup marks abandoned jobs interrupted rather
than silently starting expensive downloads. Live ingestion has a separate registry
and does not mutate historical replay controllers. A shared provider request budget
covers catalogue, preparation, and live requests.

Frontend entry: `index.html` → `src/main.tsx` → `src/app/App.tsx`. React renders
Replay, Analyze, Strategy and Live workspaces. Zustand holds replay state and driver
selection. `useResource` loads cancellable REST resources. The replay WebSocket and
telemetry polling remain separate. Global CSS defines the F1 timing-screen theme.
URL query parameters (`session`, `time`, `driver`) carry shareable race moments.

Historical analysis exposes laps, stints, event markers, provider qualifying stages,
weather/race control, telemetry coverage and official classification separately.
Strategy simulation branches into an independent engine. It never writes generated
events into historical storage. Live reconstruction merges corrected source rows
and normalizes/replays them using the same domain logic.
