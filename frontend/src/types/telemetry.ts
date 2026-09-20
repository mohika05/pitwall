export interface CarTelemetry {
    Date?: string | null
    SessionTime?: number | null

    RPM?: number | null
    Speed?: number | null
    nGear?: number | null

    Throttle?: number | null
    Brake?: boolean | null
    DRS?: number | null

    LapNumber?: number | null
    }

    export interface PositionTelemetry {
    Date?: string | null
    SessionTime?: number | null

    X?: number | null
    Y?: number | null
    Z?: number | null

    Status?: string | null

    LapNumber?: number | null
    }


    export interface DriverTelemetrySnapshot {
    driver_number?: number

    driver: string

    requested_timestamp?: string

    car:
        | CarTelemetry
        | null

    position:
        | PositionTelemetry
        | null

    car_sample_age_seconds?:
        | number
        | null

    position_sample_age_seconds?:
        | number
        | null

    error?: string
    }


    export interface TelemetrySnapshot {
    session_key: number

    timestamp: string

    drivers:
        DriverTelemetrySnapshot[]
    }


    export interface TrackPoint {
    x: number
    y: number
    z?: number | null
    }


    export interface TrackShape {
    session_key: number
    driver: string
    lap_number: number

    points: TrackPoint[]
    }