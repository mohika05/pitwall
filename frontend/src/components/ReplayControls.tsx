import {
    useState,
} from "react"

import {
    pauseReplay,
    playReplay,
    resetReplay,
    seekReplayIndex,
    setReplaySpeed,
} from "../lib/api"

import {
    useRaceStore,
} from "../stores/raceStore"


const SPEEDS = [
    1,
    5,
    10,
    25,
    50,
    100,
]


export function ReplayControls() {
    const sessionKey =
        useRaceStore(
        (state) =>
            state.sessionKey
        )

    const playing =
        useRaceStore(
        (state) =>
            state.playing
        )

    const speed =
        useRaceStore(
        (state) =>
            state.speed
        )

    const eventIndex =
        useRaceStore(
        (state) =>
            state.eventIndex
        )

    const totalEvents =
        useRaceStore(
        (state) =>
            state.totalEvents
        )


    const [
        seekValue,
        setSeekValue,
    ] = useState<number | null>(null)


    const [
        busy,
        setBusy,
    ] = useState(false)


    const [
        error,
        setError,
    ] = useState<
        string | null
    >(null)


    /*
    * All hooks have already been called,
    * so it is safe to return here.
    */
    if (
        sessionKey === null
    ) {
        return null
    }


    /*
    * Keep a definitely-number variable
    * for callbacks.
    */
    const activeSessionKey =
        sessionKey


    async function run(
        operation: () =>
        Promise<unknown>
    ) {
        try {
        setBusy(true)
        setError(null)

        await operation()
        } catch (err) {
        setError(
            err instanceof Error
            ? err.message
            : "Request failed"
        )
        } finally {
        setBusy(false)
        }
    }


    function togglePlay() {
        run(
        () =>
            playing
            ? pauseReplay(
                activeSessionKey
                )
            : playReplay(
                activeSessionKey
                )
        )
    }


    function changeSpeed(
        newSpeed: number
    ) {
        run(
        () =>
            setReplaySpeed(
            activeSessionKey,
            newSpeed
            )
        )
    }


    function reset() {
        run(
        () =>
            resetReplay(
            activeSessionKey
            )
        )
    }


    function commitSeek() {
        if (
        totalEvents <= 0 || seekValue === null
        ) {
        return
        }

        const target = seekValue
        void run(() => seekReplayIndex(activeSessionKey, target))
            .finally(() => setSeekValue(null))
    }


    return (
        <section className="replay-controls">

        <div className="control-buttons">
            <button
            className="primary-button"
            onClick={
                togglePlay
            }
            disabled={busy}
            >
            {playing
                ? "Pause"
                : "Play"}
            </button>


            <button
            onClick={reset}
            disabled={busy}
            >
            Reset
            </button>
        </div>


        <div className="speed-controls">
            {SPEEDS.map(
            (option) => (
                <button
                key={option}
                className={
                    speed === option
                    ? "active"
                    : ""
                }
                onClick={() =>
                    changeSpeed(
                    option
                    )
                }
                disabled={busy}
                >
                {option}×
                </button>
            )
            )}
        </div>


        <div className="timeline">
            <input
            type="range"
            min={0}
            max={Math.max(
                totalEvents - 1,
                0
            )}
            value={
                seekValue ?? Math.max(eventIndex, 0)
            }
            disabled={
                totalEvents === 0 ||
                busy
            }
            onChange={(
                event
            ) =>
                setSeekValue(
                Number(
                    event.target.value
                )
                )
            }
            onPointerUp={
                commitSeek
            }
            onKeyUp={
                commitSeek
            }
            />

            <span>
            {totalEvents > 0
                ? `${Math.max(
                    0,
                    Math.round(
                    (
                        Math.max(
                        eventIndex,
                        0
                        ) /
                        (
                        Math.max(totalEvents - 1, 1)
                        )
                    ) *
                        100
                    )
                )}%`
                : "0%"}
            </span>
        </div>


        {error && (
            <div className="control-error">
            {error}
            </div>
        )}

        </section>
    )
    }