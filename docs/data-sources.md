# Data sources

- [OpenF1 documentation](https://openf1.org/docs): catalogue, timing, laps, stints,
  positions, gaps, pit stops, race control and weather.
- [FastF1](https://docs.fastf1.dev/): per-driver car/position telemetry, circuit
  reference laps and qualifying stage enrichment.

The catalogue begins in 2023, matching the adapter's supported historical range.
Provider access, availability and coverage vary by session. Pitwall uses OpenF1's
free historical API after sessions have left the provider's live window. Request
budgeting uses conservative shared spacing plus retry/Retry-After handling.

Telemetry offsets and missing samples remain visible. Circuit shape is selected
from a usable driver lap rather than requiring a particular driver abbreviation.
Qualifying stages use provider timing segments rather than fixed weekend assumptions.
No claim is made that deterministic reconstruction eliminates missing or incorrect
source observations.
