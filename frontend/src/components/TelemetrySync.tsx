import {
    useEffect,
} from "react"

import {
    getTelemetrySnapshot,
} from "../lib/api"

import {
    useRaceStore,
} from "../stores/raceStore"


export function TelemetrySync() {
    const sessionKey =
        useRaceStore(
        (store) =>
            store.sessionKey
        )


    useEffect(
        () => {
        if (
            sessionKey === null
        ) {
            return
        }


        /*
        * From here onward this is guaranteed
        * to be a number.
        *
        * We use this inside the async function
        * instead of sessionKey directly so
        * TypeScript keeps the narrowed type.
        */
        const activeSessionKey =
            sessionKey


        let stopped = false

        let inFlight = false

        let lastRevision = -1
        let lastEpoch = -1

        let lastTimestamp:
            | string
            | null = null

        let lastDriver = ""
        let retryAfter = 0


        async function sync() {
            if (
            stopped ||
            inFlight ||
            Date.now() < retryAfter
            ) {
            return
            }


            const { state: race, revision, streamEpoch, selectedDriver } = useRaceStore.getState()


            if (!race) {
            return
            }


            const timestamp =
            race.replay_timestamp


            if (
                timestamp ===
                lastTimestamp && revision === lastRevision && streamEpoch === lastEpoch && selectedDriver === lastDriver
            ) {
            return
            }


            inFlight = true


            try {
            const telemetry =
                await getTelemetrySnapshot(
                activeSessionKey,
                timestamp,
                selectedDriver
                )


            if (stopped || useRaceStore.getState().revision !== revision || useRaceStore.getState().streamEpoch !== streamEpoch) {
                return
            }


            lastEpoch = streamEpoch
            lastRevision = revision
            lastTimestamp =
                timestamp
            lastDriver = selectedDriver
            retryAfter = 0


            useRaceStore
                .getState()
                .setTelemetry(
                telemetry,
                revision,
                streamEpoch
                )
            } catch (error) {
            retryAfter = Date.now() + 5000
            console.error(
                "Telemetry sync failed",
                error
            )
            } finally {
            inFlight = false
            }
        }


        sync()


        const interval =
            window.setInterval(
            sync,
            250
            )


        return () => {
            stopped = true

            window.clearInterval(
            interval
            )
        }
        },
        [
        sessionKey,
        ]
    )


    return null
    }
