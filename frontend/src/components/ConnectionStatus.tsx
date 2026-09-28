import {
    useRaceStore,
} from "../stores/raceStore"


export function ConnectionStatus() {
    const sessionKey =
        useRaceStore(
        (state) =>
            state.sessionKey
        )

    const connected =
        useRaceStore(
        (state) =>
            state.connected
    )

return (
    <div
    className={
        connected
        ? "connection connected"
        : sessionKey === null
            ? "connection idle"
            : "connection disconnected"
    }
    >
    <span className="status-dot" />

    {sessionKey === null
        ? "SELECT SESSION"
        : connected
            ? "REPLAY LINKED"
            : "RECONNECTING"}
    </div>
)
}
