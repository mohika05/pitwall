# Implementation status

The roadmap remains in scope. This delivery adds working first implementations of
its remaining modules; it is not a claim of production-grade race simulation.

| Area | Implemented | Validation / remaining limitations |
| --- | --- | --- |
| Replay | Continuous clock, deterministic seeks, stale-response guards | Unit regressions |
| Independent playback | Tab identities, separate channels, durable cursor recovery | Real PostgreSQL/Redis integration check |
| Preparation | On-demand jobs, progress, retries, partial results, interrupted-job recovery | Job lifecycle tests; downloading new sessions depends on provider availability |
| F1 interface | Responsive timing tower, compact status, telemetry instruments, four workspaces | Desktop/mobile browser smoke checks |
| Analysis | Lap/telemetry comparison, stints, event timeline, bookmarks, classification | Real-session analysis and telemetry API checks |
| Session views | Practice pace summaries, recorded qualifying stages, Race/Sprint strategy gating | Qualifying enrichment needs a prepared qualifying session; no guessed elimination cutoffs |
| Strategy | Historical/forecast branches, pit/tyre/traffic assumptions, saved comparisons, sensitivity reruns and recorded-stop backtesting | Determinism and future-data-isolation tests; approximate lap-level model |
| ML | Training, session-separated holdout, versioned results, eligibility and fallback | Synthetic training tests; no pretrained model or real multi-race validation supplied |
| Live | Token-gated feed, source-row correction merging, shared normalizers, timing/telemetry/circuit UI | Merge tests; live reception requires credentials and an active session |
| Operations | Dockerfiles, full Compose stack, CI, health endpoints, request metrics | Local build/lint/tests and Docker image builds; public deployment not performed |

Use a single backend worker. There is no account authentication in this local-first
application. Viewer IDs separate playback but are not an authorization boundary.
Browser checks use deterministic API fixtures; the opt-in integration check uses
real local PostgreSQL/Redis and prepared session  data.
