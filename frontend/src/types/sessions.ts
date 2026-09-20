export interface SessionSummary {
    session_key: number

    meeting_key:
        | number
        | null

    year:
        | number
        | null

    country:
        | string
        | null

    session_name:
        | string
        | null

    meeting_name:
        | string
        | null

    date_start:
        | string
        | null

    telemetry_available:
        boolean

    label: string
    }


export interface SessionListResponse {
    sessions:
        SessionSummary[]
    }