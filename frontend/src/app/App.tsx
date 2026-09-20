import {
    useEffect,
} from "react"

import {
    DriverTelemetry,
} from "../components/DriverTelemetry"

import {
    Header,
} from "../components/Header"

import {
    RaceBoard,
} from "../components/RaceBoard"

import {
    RaceInfo,
} from "../components/RaceInfo"

import {
    RaceStatus,
} from "../components/RaceStatus"

import {
    ReplayControls,
} from "../components/ReplayControls"

import {
    TelemetrySync,
} from "../components/TelemetrySync"

import {
    TrackMap,
} from "../components/TrackMap"

import {
    RaceWebSocket,
} from "../lib/websocket"

import {
    useRaceStore,
} from "../stores/raceStore"

import {
    RaceBrowser,
} from "../components/RaceBrowser"

export default function App() {
    const sessionKey =
        useRaceStore(
        (state) =>
            state.sessionKey
        )


    useEffect(
        () => {
        /*
        * IMPORTANT:
        *
        * Do not create a WebSocket until
        * a real session has been selected.
        */
        if (
            sessionKey === null
        ) {
            return
        }


        const activeSessionKey =
            sessionKey


        const socket =
            new RaceWebSocket(
            activeSessionKey
            )


        socket.connect()


        const pingInterval =
            window.setInterval(
            () => {
                socket.ping()
            },
            20_000
            )


        return () => {
            window.clearInterval(
            pingInterval
            )

            socket.disconnect()
        }
        },
        [
        sessionKey,
        ]
    )


    return (
        <main className="app-shell">

        <Header />
        <RaceBrowser />


        {sessionKey === null ? (
            <section className="panel no-session-panel">
            Loading available races...
            </section>
        ) : (
            <>
            <TelemetrySync />
            <RaceStatus />
            <ReplayControls key={sessionKey} />

            <div className="dashboard-grid">
                <RaceBoard />
                <TrackMap key={sessionKey} />
            </div>

            <DriverTelemetry />
            <RaceInfo />
            </>
        )}

        </main>
    )
    }