export interface DriverState {
    driver_number: number

    name_acronym?: string | null
    full_name?: string | null

    team_name?: string | null
    team_colour?: string | null

    position: number | null
    classified_position?: number | null

    current_lap: number
    last_lap_time?: number | null

    gap_to_leader?: number | string | null
    interval?: number | string | null

    compound?: string | null
    stint_number?: number | null
    tyre_age?: number | null

    pit_stop_count?: number
    last_pit_duration?: number | null

    dnf?: boolean
    dns?: boolean
    dsq?: boolean
    }

    export interface WeatherState {
    air_temperature?: number | null
    track_temperature?: number | null
    humidity?: number | null
    pressure?: number | null
    rainfall?: number | null
    wind_direction?: number | null
    wind_speed?: number | null
    }

    export interface RaceState {
    session_key: number
    meeting_key: number

    current_lap: number
    replay_timestamp: string

    drivers: Record<string, DriverState>

    flag?: string | null
    safety_car?: string | null

    latest_race_control_message?:
    | string
    | null

    weather?: WeatherState | null
    }

    export interface RaceStatePayload {
    revision: number
    state: RaceState

    event_index: number
    total_events: number

    playing: boolean
    speed: number
    }

    export interface RaceStateMessage {
    type: "race_state"
    session_key: number
    payload: RaceStatePayload
    }

    export interface PongMessage {
    type: "pong"
    session_key: number
    }

    export type RealtimeMessage =
    | RaceStateMessage
    | PongMessage