import {
    ConnectionStatus,
} from "./ConnectionStatus"


export function Header() {
    return (
        <header className="header">

        <div>
            <div className="brand">
            PITWALL
            </div>

            <div className="subtitle">
            Race Strategy &
            Replay Platform
            </div>
        </div>


        <ConnectionStatus />

        </header>
    )
    }