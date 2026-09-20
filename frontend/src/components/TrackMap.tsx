import {
    useEffect,
    useMemo,
    useState,
} from "react"

import {
    getTrackShape,
} from "../lib/api"

import {
    useRaceStore,
} from "../stores/raceStore"

import type {
    TrackShape,
} from "../types/telemetry"


interface MapPoint {
    x: number
    y: number
}


function normaliseColour(
    colour:
        | string
        | null
        | undefined
    ): string {
    if (!colour) {
        return "#F4F4F5"
    }

    return colour.startsWith("#")
        ? colour
        : `#${colour}`
}


export function TrackMap() {
    const sessionKey =
        useRaceStore(
        (store) =>
            store.sessionKey
        )

    const raceState =
        useRaceStore(
        (store) =>
            store.state
        )

    const telemetry =
        useRaceStore(
        (store) =>
            store.telemetry
        )

    const selectedDriver =
        useRaceStore(
        (store) =>
            store.selectedDriver
        )

    const setSelectedDriver =
        useRaceStore(
        (store) =>
            store.setSelectedDriver
        )


    const [
        track,
        setTrack,
    ] = useState<
        TrackShape | null
    >(null)


    const [
        error,
        setError,
    ] = useState<
        string | null
    >(null)


    // -------------------------------------------------------
    // LOAD CIRCUIT SHAPE
    // -------------------------------------------------------

    useEffect(
        () => {
        if (
            sessionKey === null
        ) {

            return
        }


        const activeSessionKey =
            sessionKey

        let cancelled =
            false


        async function load() {
            try {
            // App keys this component by session, clearing the previous map immediately.


            const result =
                await getTrackShape(
                activeSessionKey
                )


            if (!cancelled) {
                setTrack(
                result
                )
            }
            } catch (err) {
            if (!cancelled) {
                setError(
                err instanceof Error
                    ? err.message
                    : "Failed to load track"
                )
            }
            }
        }


        load()


        return () => {
            cancelled =
            true
        }
        },
        [
        sessionKey,
        ]
    )


    // -------------------------------------------------------
    // DRIVER METADATA LOOKUP
    // -------------------------------------------------------

    const driverMetadata =
        useMemo(
        () => {
            const lookup =
            new Map<
                string,
                {
                teamName:
                    | string
                    | null
                    | undefined

                teamColour:
                    string
                }
            >()


            if (!raceState) {
            return lookup
            }


            for (
            const driver
            of Object.values(
                raceState.drivers
            )
            ) {
            if (
                !driver.name_acronym
            ) {
                continue
            }


            lookup.set(
                driver.name_acronym,
                {
                teamName:
                    driver.team_name,

                teamColour:
                    normaliseColour(
                    driver.team_colour
                    ),
                }
            )
            }


            return lookup
        },
        [
            raceState,
        ]
        )


    // -------------------------------------------------------
    // TRACK COORDINATES
    // -------------------------------------------------------

    const transformedTrack =
        useMemo(
        () => {
            if (!track) {
            return []
            }


            return track.points.map(
            (point) => ({
                x:
                point.x,

                /*
                * SVG Y grows downward,
                * so flip FastF1 Y.
                */
                y:
                -point.y,
            })
            )
        },
        [
            track,
        ]
        )


    // -------------------------------------------------------
    // SVG VIEWBOX
    // -------------------------------------------------------

    const bounds =
        useMemo(
        () => {
            if (
            transformedTrack.length ===
            0
            ) {
            return null
            }


            const xs =
            transformedTrack.map(
                (point) =>
                point.x
            )

            const ys =
            transformedTrack.map(
                (point) =>
                point.y
            )


            const minX =
            Math.min(
                ...xs
            )

            const maxX =
            Math.max(
                ...xs
            )

            const minY =
            Math.min(
                ...ys
            )

            const maxY =
            Math.max(
                ...ys
            )


            const width =
            maxX - minX

            const height =
            maxY - minY


            const padding =
            Math.max(
                width,
                height
            ) * 0.02


            return {
            minX:
                minX -
                padding,

            minY:
                minY -
                padding,

            width:
                width +
                padding * 2,

            height:
                height +
                padding * 2,
            }
        },
        [
            transformedTrack,
        ]
        )


    // -------------------------------------------------------
    // CURRENT DRIVER POSITIONS
    // -------------------------------------------------------

    const driverPoints =
        useMemo(
        () => {
            if (!telemetry) {
            return []
            }


            return telemetry.drivers
            .map(
                (
                driver
                ): {
                driver:
                    string

                point:
                    MapPoint
                } | null => {
                const x =
                    driver.position?.X

                const y =
                    driver.position?.Y


                if (
                    x == null ||
                    y == null
                ) {
                    return null
                }


                return {
                    driver:
                    driver.driver,

                    point: {
                    x,
                    y: -y,
                    },
                }
                }
            )
            .filter(
                (
                item
                ): item is {
                driver:
                    string

                point:
                    MapPoint
                } =>
                item !== null
            )
        },
        [
            telemetry,
        ]
        )


    // -------------------------------------------------------
    // NO SESSION
    // -------------------------------------------------------

    if (
        sessionKey === null
    ) {
        return (
        <section className="panel track-panel">

            <div className="panel-title">
            Track Map
            </div>

            <div className="track-loading">
            Select a race.
            </div>

        </section>
        )
    }


    // -------------------------------------------------------
    // ERROR
    // -------------------------------------------------------

    if (error) {
        return (
        <section className="panel track-panel">

            <div className="panel-title">
            Track Map
            </div>

            <div className="track-error">
            {error}
            </div>

        </section>
        )
    }


    // -------------------------------------------------------
    // LOADING
    // -------------------------------------------------------

    if (
        !track ||
        !bounds
    ) {
        return (
        <section className="panel track-panel">

            <div className="panel-title">
            Track Map
            </div>

            <div className="track-loading">
            Loading circuit...
            </div>

        </section>
        )
    }


    /*
    * Explicitly close the circuit by
    * reconnecting the final point to
    * the first point.
    */
    const closedTrack =
        transformedTrack.length > 0
        ? [
            ...transformedTrack,
            transformedTrack[0],
            ]
        : []


    const polylinePoints =
        closedTrack
        .map(
            (point) =>
            `${point.x},${point.y}`
        )
        .join(" ")


    // -------------------------------------------------------
    // RENDER
    // -------------------------------------------------------

    return (
        <section className="panel track-panel">

        <div className="panel-title track-title-row">

            <span>
            Track Map
            </span>

            <span className="track-meta">
            Reference lap{" "}
            {track.lap_number}
            </span>

        </div>


        <div className="track-map-container">

            <svg
            className="track-svg"
            viewBox={
                `${bounds.minX} ` +
                `${bounds.minY} ` +
                `${bounds.width} ` +
                `${bounds.height}`
            }
            preserveAspectRatio="xMidYMid meet"
            >

            {/* Outer track shadow */}

            <polyline
                className="track-outline-shadow"
                points={
                polylinePoints
                }
            />


            {/* Main circuit */}

            <polyline
                className="track-outline"
                points={
                polylinePoints
                }
            />


            {/* Current driver positions */}

            {driverPoints.map(
                ({
                driver,
                point,
                }) => {
                const selected =
                    driver ===
                    selectedDriver


                const metadata =
                    driverMetadata.get(
                    driver
                    )


                const colour =
                    metadata?.teamColour ??
                    "#F4F4F5"


                return (
                    <g
                    key={driver}
                    className={
                        selected
                        ? "driver-marker selected"
                        : "driver-marker"
                    }
                    transform={
                        `translate(` +
                        `${point.x} ` +
                        `${point.y}` +
                        `)`
                    }
                    onClick={() =>
                        setSelectedDriver(
                        driver
                        )
                    }
                    >

                    {selected && (
                        <circle
                        className="driver-marker-ring"
                        r="140"
                        />
                    )}


                    <circle
                        className="driver-marker-dot"
                        r={
                        selected
                            ? 120
                            : 98
                        }
                        style={{
                        fill:
                            colour,
                        }}
                    />


                    <text
                        className={
                        selected
                            ? "driver-marker-label selected"
                            : "driver-marker-label"
                        }
                        y={
                        selected
                            ? -200
                            : -160
                        }
                        textAnchor="middle"
                    >
                        {driver}
                    </text>


                    <title>
                        {driver}
                        {metadata?.teamName
                        ? ` · ${metadata.teamName}`
                        : ""}
                    </title>

                    </g>
                )
                }
            )}

            </svg>

        </div>

        </section>
    )
    }