# Strategy model v1

Inputs: historical session, driver, branch timestamp, pit lap, target compound,
horizon and explicit model assumptions. The branch uses the selected driver's last
completed lap. At least three clean historical laps are required to estimate pace.

The deterministic model separates base pace, compound offset, age-dependent wear,
fuel trend, warm-up, traffic penalty, pit transit loss and stationary service time.
Rejoin estimates use numeric gaps at the branch point. Opponents are not reactive;
those estimates should not be interpreted as a full simulated final classification.

Historical mode compares simulated elapsed time against recorded future lap times,
reuses observed neutralization context, replaces the next recorded stop and retains
later recorded stops. Decision-time mode does not use future lap data: it compares
against a user-specified baseline stop and holds branch conditions constant. These
are distinct questions and are labeled separately in the UI.

Sensitivity reruns the simulation with lower/higher pit-loss, degradation and traffic
assumptions. It reports the range of those runs, not a statistical confidence interval.
Saved results include inputs, model identifier, branch fingerprint and trajectories.

The ML module fits ridge regression to pace deltas with tyre-age and compound
features, centers pace by driver/session and holds the latest session out entirely.
Eligible models must beat the held-out constant-delta baseline. The simulator rejects
models trained/validated on its target session and models using future data in a
forecast. Outside the modeled compound/age range, it falls back to the tyre model.
Fuel, track evolution and traffic still confound this model; validation MAE does not
establish causal counterfactual accuracy.

Limitations: wet/intermediate pace is not calibrated; tyre allocation and dry-compound
constraints are user supplied; race interruptions, penalties, overtaking and opponent
responses are not fully simulated. Circuit-specific calibration and broader backtests
are required before interpreting predicted gains as realistic strategy recommendations.
