export interface CatalogSession {
    session_key: number
    meeting_key: number

    session_name:
        | string
        | null

    session_type:
        | string
        | null

    date_start:
        | string
        | null

    date_end:
        | string
        | null

    is_cancelled: boolean

    ingested: boolean

    telemetry_available:
        boolean
    }


    export interface CatalogMeeting {
    meeting_key: number

    meeting_name:
        | string
        | null

    meeting_official_name:
        | string
        | null

    country_name:
        | string
        | null

    country_code:
        | string
        | null

    location:
        | string
        | null

    circuit_short_name:
        | string
        | null

    date_start:
        | string
        | null

    sessions:
        CatalogSession[]
    }


    export interface YearCatalogue {
    year: number

    meetings:
        CatalogMeeting[]
    }


    export interface CatalogYears {
    years: number[]
    }