import {
    create,
} from "zustand"

import type {
    RaceState,
    RaceStatePayload,
} from "../types/race"

import type {
    TelemetrySnapshot,
} from "../types/telemetry"


interface RaceStore {
    sessionKey: number | null
    revision: number

    state: RaceState | null

    eventIndex: number
    totalEvents: number

    playing: boolean
    speed: number

    connected: boolean

    selectedDriver: string

    telemetry:
        | TelemetrySnapshot
        | null


    setSessionKey: (
        sessionKey: number
    ) => void


    setConnected: (
        connected: boolean
    ) => void


    applyRealtimeState: (
        payload: RaceStatePayload
    ) => void


    setSelectedDriver: (
        driver: string
    ) => void


    setTelemetry: (
        telemetry:
        | TelemetrySnapshot
        | null,
        revision: number
    ) => void
    }


    export const useRaceStore =
    create<RaceStore>()(
        (set, get) => ({
        sessionKey: null,
        revision: 0,

        state: null,

        eventIndex: -1,
        totalEvents: 0,

        playing: false,
        speed: 1,

        connected: false,

        selectedDriver: "",

        telemetry: null,


        setSessionKey: (
            sessionKey
        ) => {
            if (get().sessionKey === sessionKey) return
            set({
            sessionKey,
            revision: 0,

            state: null,

            eventIndex: -1,
            totalEvents: 0,

            playing: false,
            speed: 1,

            connected: false,

            selectedDriver: "",

            telemetry: null,
            })
        },


        setConnected: (
            connected
        ) => {
            set({
            connected,
            })
        },


        applyRealtimeState: (
            payload
        ) => {
            const current =
            get()

            if (payload.state.session_key !== current.sessionKey) return

            let selectedDriver =
            current.selectedDriver


            /*
            * When changing race, automatically
            * select the first available driver.
            */
            const drivers =
            Object.values(
                payload.state.drivers
            )


            const selectionStillExists =
            drivers.some(
                (driver) =>
                driver.name_acronym ===
                selectedDriver
            )


            if (
            !selectedDriver ||
            !selectionStillExists
            ) {
            selectedDriver =
                drivers
                .sort(
                    (a, b) =>
                    (
                        a.position ??
                        999
                    ) -
                    (
                        b.position ??
                        999
                    )
                )[0]
                ?.name_acronym ??
                ""
            }


            set({
            revision: payload.revision,
            telemetry: payload.revision !== current.revision ? null : current.telemetry,
            state:
                payload.state,

            eventIndex:
                payload.event_index,

            totalEvents:
                payload.total_events,

            playing:
                payload.playing,

            speed:
                payload.speed,

            selectedDriver,
            })
        },


        setSelectedDriver: (
            driver
        ) => {
            set({
            selectedDriver:
                driver,
            })
        },


        setTelemetry: (
            telemetry,
            revision
        ) => {
            const current = get()
            if (revision !== current.revision) return
            if (telemetry && telemetry.session_key !== current.sessionKey) return
            set({
            telemetry,
            })
        },
        })
    )