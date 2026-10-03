import {
    useRaceStore,
} from "../stores/raceStore"


export function ConnectionStatus({ archivePending = false }: { archivePending?: boolean }) {
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
        archivePending
        ? "connection pending"
        : connected
        ? "connection connected"
        : sessionKey === null
            ? "connection idle"
            : "connection disconnected"
    }
    >
    <span className="status-dot" />

    {archivePending
        ? "ARCHIVE PENDING"
        : sessionKey === null
        ? "SELECT SESSION"
        : connected
            ? "REPLAY LINKED"
            : "RECONNECTING"}
    </div>
)
}
