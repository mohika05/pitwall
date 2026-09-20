import { viewerId } from "./viewer"
import {
    useRaceStore,
} from "../stores/raceStore"

import type {
    RealtimeMessage,
} from "../types/race"


const WS_BASE =
    import.meta.env
        ?.VITE_WS_BASE_URL ??
    (typeof window === "undefined" ? "ws://127.0.0.1:8000" : `${window.location.protocol === "https:" ? "wss:" : "ws:"}//${window.location.host}`)


export class RaceWebSocket {
    private socket:
        | WebSocket
        | null = null

    private reconnectTimer:
        | number
        | null = null

    private shouldReconnect =
        true

    private reconnectAttempts =
        0

    private readonly sessionKey:
        number


    constructor(
        sessionKey: number
    ) {
        this.sessionKey =
        sessionKey
    }


    connect() {
        this.shouldReconnect =
        true

        /*
        * Avoid opening another socket
        * if one is already connecting/open.
        */
        if (
        this.socket &&
        (
            this.socket.readyState ===
            WebSocket.OPEN ||
            this.socket.readyState ===
            WebSocket.CONNECTING
        )
        ) {
        return
        }


        const url =
        `${WS_BASE}/ws/replay/` +
        `${this.sessionKey}?viewer_id=${viewerId()}`


        const socket = new WebSocket(url)
        this.socket = socket
        const isCurrent = () => this.socket === socket
            && this.shouldReconnect
            && useRaceStore.getState().sessionKey === this.sessionKey


        this.socket.onopen =
        () => {
            if (!isCurrent()) return
            this.reconnectAttempts =
            0

            useRaceStore
            .getState()
            .setConnected(
                true
            )

            console.log(
            `Pitwall WebSocket connected: ${this.sessionKey}`
            )
        }


        this.socket.onmessage =
        (event) => {
            if (!isCurrent()) return
            try {
            const message =
                JSON.parse(
                event.data
                ) as RealtimeMessage


            if (
                message.type ===
                "race_state" && message.session_key === this.sessionKey
            ) {
                useRaceStore
                .getState()
                .applyRealtimeState(
                    message.payload
                )
            }
            } catch (error) {
            console.error(
                "Invalid WebSocket message",
                error
            )
            }
        }


        this.socket.onerror =
        () => {
            /*
            * onclose handles reconnection.
            */
            if (isCurrent()) socket.close()
        }


        this.socket.onclose =
        () => {
            if (!isCurrent()) return
            this.socket =
            null

            useRaceStore
            .getState()
            .setConnected(
                false
            )


            if (
            this.shouldReconnect
            ) {
            this.scheduleReconnect()
            }
        }
    }


    disconnect() {
        this.shouldReconnect =
        false


        if (
        this.reconnectTimer !==
        null
        ) {
        window.clearTimeout(
            this.reconnectTimer
        )

        this.reconnectTimer =
            null
        }


        const socket =
        this.socket

        this.socket =
        null


        if (socket) {
        socket.onopen = null
        socket.onmessage = null
        socket.onerror = null
        socket.onclose = null

        socket.close()
        }


        if (useRaceStore.getState().sessionKey === this.sessionKey) {
            useRaceStore.getState().setConnected(false)
        }
    }


    ping() {
        if (
        this.socket?.readyState ===
        WebSocket.OPEN
        ) {
        this.socket.send(
            "ping"
        )
        }
    }


    private scheduleReconnect() {
        if (
        this.reconnectTimer !==
        null
        ) {
        return
        }


        /*
        * 1s -> 2s -> 4s -> 8s,
        * capped at 8 seconds.
        */
        const delay =
        Math.min(
            1000 *
            2 **
                this.reconnectAttempts,
            8000
        )


        this.reconnectAttempts +=
        1


        this.reconnectTimer =
        window.setTimeout(
            () => {
            this.reconnectTimer =
                null

            this.connect()
            },
            delay
        )
    }
    }