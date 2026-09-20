# Data sources

- [OpenF1 documentation](https://openf1.org/docs): catalogue, timing, laps, stints,
  positions, gaps, pit stops, race control, weather and live samples.
- [FastF1](https://docs.fastf1.dev/): per-driver car/position telemetry, circuit
  reference laps and qualifying stage enrichment.

The catalogue begins in 2023, matching the adapter's supported historical range.
Provider access, availability and coverage vary by session. Live data requires an
access token with the appropriate provider entitlement. Current rate budgeting uses
a conservative shared 2.1-second spacing for anonymous requests and 1.1 seconds
with a token, plus the existing retry/Retry-After handling.

Telemetry offsets and missing samples remain visible. Circuit shape is selected
from a usable driver lap rather than requiring a particular driver abbreviation.
Qualifying stages use provider timing segments rather than fixed weekend assumptions.
No claim is made that deterministic reconstruction eliminates missing or incorrect
source observations.
