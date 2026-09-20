import {
    useRaceStore,
} from "../stores/raceStore"


export function ConnectionStatus() {
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
        : "connection disconnected"
    }
    >
    <span className="status-dot" />

    {connected
        ? "CONNECTED"
        : "DISCONNECTED"}
    </div>
)
}