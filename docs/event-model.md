# Event and time contract

Historical events have stable IDs, session/meeting keys, timestamps, optional driver
and lap identifiers, and typed payloads. Ordering is timestamp, event priority, then
ID. Duplicate ingestion upserts those identities. Corrections replace corresponding
source rows/events before reconstruction.

The playback cursor is separate from event arrival: at each tick all events at or
before the cursor are applied, then state is broadcast. Snapshots are deep copies.
Commands which move the cursor increment a revision so telemetry from an older
revision cannot overwrite the new view. Official classification remains separate
from reconstructed running order.
