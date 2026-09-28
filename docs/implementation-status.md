# Implementation status

The roadmap remains in scope. This delivery adds working first implementations of
its remaining modules; it is not a claim of production-grade race simulation.

| Area | Implemented | Validation / remaining limitations |
| --- | --- | --- |
| Replay | Continuous clock, deterministic seeks, stale-response guards | Unit regressions |
| Independent playback | Tab identities, separate channels, durable cursor recovery | Real PostgreSQL/Redis integration check |
| Preparation | On-demand jobs, progress, retries, partial results, interrupted-job recovery | Job lifecycle tests; downloading new sessions depends on provider availability |
| F1 interface | Replay-first navigation, responsive timing tower, compact status, telemetry instruments, three workspaces | Desktop/mobile browser smoke checks |
| Analysis | Lap/telemetry comparison, stints, event timeline, bookmarks, classification | Real-session analysis and telemetry API checks |
| Session views | Practice pace summaries, recorded qualifying stages, Race/Sprint strategy gating | Qualifying enrichment needs a prepared qualifying session; no guessed elimination cutoffs |
| Strategy | Historical/forecast branches, pit/tyre/traffic assumptions, saved comparisons, sensitivity reruns and recorded-stop backtesting | Determinism and future-data-isolation tests; approximate lap-level model |
| ML | Training, session-separated holdout, versioned results, five-percent eligibility margin and deterministic fallback | Eight 2024 races trained with Singapore 2025 held out: 0.770s MAE versus 0.823s baseline; accepted with temporal season separation |
| Operations | Dockerfiles, full Compose stack, CI, health endpoints, request metrics, local/S3 canonical storage, verified manifests, cache cleanup, resumable catalogue preparation and a same-origin Render blueprint | Local build/lint/tests and Docker image builds; provider credentials and the public deployment still need to be created |

Use a single backend worker. There are no viewer accounts in this local-first
application; an administrator token protects preparation endpoints. Viewer IDs
separate playback but are not an authorization boundary.
Browser checks use deterministic API fixtures; the opt-in integration check uses
real local PostgreSQL/Redis and prepared session  data.

Real Saudi data exposed and helped fix missing stint starts and safety-car
clearance handling. Practice ingestion now tolerates absent interval feeds.
Recorded-stop validation covered 82 cases across five dry races. Mean session MAE
was 11.09s versus 13.73s for constant pace, with the model winning four of five
races. Bahrain remained worse than baseline. These are horizon elapsed-time errors,
not per-lap accuracy or evidence of counterfactual correctness.
