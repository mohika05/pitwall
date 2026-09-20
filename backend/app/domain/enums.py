from enum import Enum

class EventType(str, Enum):
    STINT_STARTED = "stint_started"
    POSITION_CHANGED = "position_changed"
    INTERVAL_UPDATED = "interval_updated"
    PIT_STOP = "pit_stop"
    LAP_COMPLETED = "lap_completed"
    RACE_CONTROL = "race_control"
    WEATHER_UPDATED = "weather_updated"

class SafetyCarState(str, Enum):
    NONE = "none"
    VIRTUAL = "virtual"
    FULL = "full"