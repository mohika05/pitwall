from typing import Literal

from pydantic import AwareDatetime, BaseModel, Field, model_validator

Compound = Literal["SOFT", "MEDIUM", "HARD", "INTERMEDIATE", "WET"]


class StrategyRequest(BaseModel):
    session_key: int = Field(gt=0)
    driver_number: int = Field(gt=0)
    timestamp: AwareDatetime
    mode: Literal["historical", "forecast"] = "historical"
    pit_lap: int = Field(ge=1, le=150)
    compound: Compound = "HARD"
    total_laps: int = Field(ge=1, le=150)
    baseline_pit_lap: int | None = Field(default=None, ge=1, le=150)
    baseline_compound: Compound = "HARD"
    pit_lane_loss: float = Field(default=20, ge=0, le=90, allow_inf_nan=False)
    stationary_time: float = Field(default=2.5, ge=0, le=60, allow_inf_nan=False)
    degradation: float = Field(default=0.06, ge=0, le=2, allow_inf_nan=False)
    fuel_gain: float = Field(default=0.03, ge=0, le=0.2, allow_inf_nan=False)
    traffic_penalty: float = Field(default=0.35, ge=0, le=5, allow_inf_nan=False)
    warmup_loss: float = Field(default=1, ge=0, le=10, allow_inf_nan=False)
    safety_car_multiplier: float = Field(default=0.6, gt=0, le=1, allow_inf_nan=False)
    uncertainty: float = Field(default=0.15, ge=0, le=1, allow_inf_nan=False)
    available_compounds: list[Compound] = Field(default_factory=lambda: ["SOFT", "MEDIUM", "HARD"])
    enforce_dry_compounds: bool = False
    model_id: str | None = None
    name: str = Field(default="Pit strategy", min_length=1, max_length=100)

    @model_validator(mode="after")
    def validate_plan(self):
        if self.compound not in self.available_compounds:
            raise ValueError("Selected compound is not in the available tyre allocation")
        if self.pit_lap > self.total_laps:
            raise ValueError("Pit lap exceeds the simulation horizon")
        if self.baseline_pit_lap and self.baseline_pit_lap > self.total_laps:
            raise ValueError("Baseline pit lap exceeds the simulation horizon")
        return self
