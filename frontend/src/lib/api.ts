import { viewerId } from "./viewer"
import type {
    TelemetrySnapshot,
    TrackShape,
} from "../types/telemetry"

import type {
    SessionListResponse,
} from "../types/sessions"

import type {
    CatalogYears,
    YearCatalogue,
} from "../types/catalog"

const API_BASE =
    import.meta.env
        .VITE_API_BASE_URL ??
    "/api"


export async function request<T>(
    path: string,
    options?: RequestInit
): Promise<T> {
    if (path.startsWith("/replay/")) {
        path += `${path.includes("?") ? "&" : "?"}viewer_id=${viewerId()}`
    }
    const response = await fetch(
        `${API_BASE}${path}`,
        {
        ...options,

        headers: {
            "Content-Type":
            "application/json",

            ...options?.headers,
        },
        }
    )

    if (!response.ok) {
        const text = await response.text()
        let message = text
        try {
            const payload = JSON.parse(text) as { detail?: unknown }
            if (typeof payload.detail === "string") message = payload.detail
            else if (Array.isArray(payload.detail)) {
                message = payload.detail.map(item => typeof item === "object" && item && "msg" in item ? String(item.msg) : String(item)).join("; ")
            }
        } catch {
            // Keep a plain-text server message when the response is not JSON.
        }
        throw new Error(message || `Request failed (${response.status})`)
    }

    return response.json()
    }


export interface ReplayStatus {
    session_key: number

    playing: boolean
    speed: number

    event_index: number
    total_events: number

    replay_timestamp: string
    current_lap: number
}


export function getReplayStatus(
    sessionKey: number
    ) {
    return request<ReplayStatus>(
        `/replay/${sessionKey}/status`
    )
}


export function playReplay(
    sessionKey: number
    ) {
    return request<ReplayStatus>(
        `/replay/${sessionKey}/play`,
        {
        method: "POST",
        }
    )
}


export function pauseReplay(
    sessionKey: number
    ) {
    return request<ReplayStatus>(
        `/replay/${sessionKey}/pause`,
        {
        method: "POST",
        }
    )
}


export function resetReplay(
    sessionKey: number
    ) {
    return request<ReplayStatus>(
        `/replay/${sessionKey}/reset`,
        {
        method: "POST",
        }
    )
}


export function setReplaySpeed(
    sessionKey: number,
    speed: number
    ) {
    return request<ReplayStatus>(
        `/replay/${sessionKey}/speed`,
        {
        method: "POST",

        body: JSON.stringify({
            speed,
        }),
        }
    )
}


export function seekReplayIndex(
    sessionKey: number,
    eventIndex: number
    ) {
    return request<ReplayStatus>(
        `/replay/${sessionKey}/seek/index`,
        {
        method: "POST",

        body: JSON.stringify({
            event_index:
            eventIndex,
        }),
        }
    )
}


export function getTelemetrySnapshot(
    sessionKey: number,
    timestamp: string
    ) {
    const params =
        new URLSearchParams({
        timestamp,
        })

    return request<TelemetrySnapshot>(
        `/telemetry/${sessionKey}/snapshot?${params}`
    )
}


export function getTrackShape(
    sessionKey: number
    ) {
    const params =
        new URLSearchParams({
        max_points: "400",
        })

    return request<TrackShape>(
        `/telemetry/${sessionKey}/track?${params}`
    )
}


export function getSessions() {
    return request<SessionListResponse>(
    "/sessions"
    )
}


export function getCatalogYears() {
    return request<CatalogYears>(
        "/catalog/years"
    )
}


export function getYearCatalogue(
    year: number
    ) {
    return request<YearCatalogue>(
        `/catalog/${year}`
    )
}
