import {
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react"

import {
  getCatalogYears,
  getSessions,
  getYearCatalogue,
} from "../lib/api"

import {
  useRaceStore,
} from "../stores/raceStore"

import type {
  CatalogMeeting,
  CatalogSession,
  YearCatalogue,
} from "../types/catalog"


function meetingLabel(
  meeting: CatalogMeeting
) {
  if (
    meeting.meeting_name
  ) {
    return meeting.meeting_name
      .replace(
        /\s+Grand Prix$/i,
        ""
      )
      .replace(
        /\s+GP$/i,
        ""
      )
  }

  return (
    meeting.location ??
    meeting.country_name ??
    "Grand Prix"
  )
}


export function RaceBrowser() {
  const sessionKey =
    useRaceStore(
      (store) =>
        store.sessionKey
    )

  const setSessionKey =
    useRaceStore(
      (store) =>
        store.setSessionKey
    )


  const [
    years,
    setYears,
  ] = useState<number[]>([])


  const [
    selectedYear,
    setSelectedYear,
  ] = useState<number | null>(
    null
  )


  const [
    catalogue,
    setCatalogue,
  ] = useState<
    YearCatalogue | null
  >(null)


  const [
    selectedMeetingKey,
    setSelectedMeetingKey,
  ] = useState<number | null>(
    null
  )


  const [
    loading,
    setLoading,
  ] = useState(true)


  const [
    error,
    setError,
  ] = useState<string | null>(
    null
  )


  const raceScrollRef =
    useRef<HTMLDivElement>(
      null
    )


  const sessionScrollRef =
    useRef<HTMLDivElement>(
      null
    )


  // -------------------------------------------------------
  // INITIAL LOAD
  // -------------------------------------------------------

  useEffect(() => {
    let cancelled = false


    async function initialise() {
      try {
        const [
          yearResponse,
          localResponse,
        ] = await Promise.all([
          getCatalogYears(),
          getSessions(),
        ])


        if (cancelled) {
          return
        }


        setYears(
          yearResponse.years
        )


        const localSession =
          localResponse.sessions[0]


        if (
          localSession?.year != null
        ) {
          setSelectedYear(
            localSession.year
          )


          const currentSession =
            useRaceStore
              .getState()
              .sessionKey


          if (
            currentSession === null
          ) {
            setSessionKey(
              localSession.session_key
            )
          }


          return
        }


        const newestYear =
          yearResponse.years.at(
            -1
          )


        if (
          newestYear !== undefined
        ) {
          setSelectedYear(
            newestYear
          )
        }
      } catch (err) {
        if (!cancelled) {
          setError(
            err instanceof Error
              ? err.message
              : "Unable to load race catalogue"
          )
        }
      }
    }


    initialise()


    return () => {
      cancelled = true
    }
  }, [
    setSessionKey,
  ])


  // -------------------------------------------------------
  // LOAD YEAR
  // -------------------------------------------------------

  useEffect(() => {
    if (
      selectedYear === null
    ) {
      return
    }


    const activeYear =
      selectedYear

    let cancelled =
      false


    async function loadYear() {
      try {
        setLoading(true)
        setError(null)


        const result =
          await getYearCatalogue(
            activeYear
          )


        if (cancelled) {
          return
        }


        setCatalogue(
          result
        )


        const activeMeeting =
          result.meetings.find(
            (meeting) =>
              meeting.sessions.some(
                (session) =>
                  session.session_key ===
                  sessionKey
              )
          )


        if (activeMeeting) {
          setSelectedMeetingKey(
            activeMeeting.meeting_key
          )

          return
        }


        setSelectedMeetingKey(
          result.meetings[0]
            ?.meeting_key ??
            null
        )
      } catch (err) {
        if (!cancelled) {
          setError(
            err instanceof Error
              ? err.message
              : "Unable to load season"
          )

          setCatalogue(
            null
          )
        }
      } finally {
        if (!cancelled) {
          setLoading(false)
        }
      }
    }


    loadYear()


    return () => {
      cancelled = true
    }
  }, [
    selectedYear,
    sessionKey,
  ])


  const meetings = useMemo(() => catalogue?.meetings ?? [], [catalogue])


  const selectedMeeting =
    useMemo<
      CatalogMeeting | undefined
    >(
      () =>
        meetings.find(
          (meeting) =>
            meeting.meeting_key ===
            selectedMeetingKey
        ),
      [
        meetings,
        selectedMeetingKey,
      ]
    )


  // -------------------------------------------------------
  // AUTO-CENTRE SELECTED RACE
  // -------------------------------------------------------

  useEffect(() => {
    if (
      selectedMeetingKey ===
        null ||
      !raceScrollRef.current
    ) {
      return
    }


    const element =
      raceScrollRef.current
        .querySelector(
          `[data-meeting-key="${selectedMeetingKey}"]`
        )


    element?.scrollIntoView({
      behavior: "smooth",
      block: "nearest",
      inline: "center",
    })
  }, [
    selectedMeetingKey,
  ])


  // -------------------------------------------------------
  // AUTO-CENTRE ACTIVE SESSION
  // -------------------------------------------------------

  useEffect(() => {
    if (
      sessionKey === null ||
      !sessionScrollRef.current
    ) {
      return
    }


    const element =
      sessionScrollRef.current
        .querySelector(
          `[data-session-key="${sessionKey}"]`
        )


    element?.scrollIntoView({
      behavior: "smooth",
      block: "nearest",
      inline: "center",
    })
  }, [
    sessionKey,
    selectedMeetingKey,
  ])


  function scrollRow(
    ref: React.RefObject<
      HTMLDivElement | null
    >,
    direction:
      | "left"
      | "right"
  ) {
    if (!ref.current) {
      return
    }


    ref.current.scrollBy({
      left:
        direction ===
        "left"
          ? -420
          : 420,

      behavior: "smooth",
    })
  }


  function chooseSession(
    session: CatalogSession
  ) {
    if (
      !session.ingested
    ) {
      return
    }


    setSessionKey(
      session.session_key
    )
  }


  if (error) {
    return (
      <section className="race-browser">
        <div className="race-browser-error">
          {error}
        </div>
      </section>
    )
  }


  return (
    <section className="race-browser">

      {/* HEADER */}

      <div className="race-browser-header">

        <div className="race-browser-heading">

          <span className="race-browser-kicker">
            GRAND PRIX
          </span>

          <h2>
            {selectedMeeting
              ?.meeting_name ??
              selectedMeeting
                ?.country_name ??
              "Race Calendar"}
          </h2>

        </div>


        <label className="season-control">

          <span>
            SEASON
          </span>

          <select
            value={
              selectedYear ??
              ""
            }
            onChange={(
              event
            ) => {
              setSelectedYear(
                Number(
                  event.target.value
                )
              )

              setSelectedMeetingKey(
                null
              )
            }}
          >
            {years.map(
              (year) => (
                <option
                  key={year}
                  value={year}
                >
                  {year}
                </option>
              )
            )}
          </select>

        </label>

      </div>


      {/* RACES */}

      <div className="catalogue-row">

        <span className="catalogue-label">
          RACE
        </span>


        <button
          type="button"
          className="catalogue-arrow"
          onClick={() =>
            scrollRow(
              raceScrollRef,
              "left"
            )
          }
          aria-label="Previous races"
        >
          ‹
        </button>


        <div
          className="catalogue-tabs"
          ref={raceScrollRef}
        >

          {loading ? (
            <span className="catalogue-loading">
              Loading calendar…
            </span>
          ) : (
            meetings.map(
              (meeting) => {
                const active =
                  meeting
                    .meeting_key ===
                  selectedMeetingKey


                return (
                  <button
                    key={
                      meeting
                        .meeting_key
                    }
                    data-meeting-key={
                      meeting
                        .meeting_key
                    }
                    type="button"
                    className={
                      active
                        ? "catalogue-tab catalogue-tab--active"
                        : "catalogue-tab"
                    }
                    onClick={() =>
                      setSelectedMeetingKey(
                        meeting
                          .meeting_key
                      )
                    }
                  >
                    {meetingLabel(
                      meeting
                    )}
                  </button>
                )
              }
            )
          )}

        </div>


        <button
          type="button"
          className="catalogue-arrow"
          onClick={() =>
            scrollRow(
              raceScrollRef,
              "right"
            )
          }
          aria-label="Next races"
        >
          ›
        </button>

      </div>


      {/* SESSIONS */}

      <div className="catalogue-row catalogue-row--sessions">

        <span className="catalogue-label">
          SESSION
        </span>


        <button
          type="button"
          className="catalogue-arrow"
          onClick={() =>
            scrollRow(
              sessionScrollRef,
              "left"
            )
          }
          aria-label="Previous sessions"
        >
          ‹
        </button>


        <div
          className="catalogue-tabs"
          ref={
            sessionScrollRef
          }
        >

          {!selectedMeeting ? (
            <span className="catalogue-loading">
              Select a race
            </span>
          ) : (
            selectedMeeting
              .sessions
              .map(
                (session) => {
                  const active =
                    session
                      .session_key ===
                    sessionKey


                  return (
                    <button
                      key={
                        session
                          .session_key
                      }
                      data-session-key={
                        session
                          .session_key
                      }
                      type="button"
                      className={[
                        "catalogue-tab",
                        "catalogue-session",

                        active
                          ? "catalogue-tab--active"
                          : "",

                        !session.ingested
                          ? "catalogue-session--remote"
                          : "",
                      ]
                        .filter(
                          Boolean
                        )
                        .join(
                          " "
                        )}
                      onClick={() =>
                        chooseSession(
                          session
                        )
                      }
                    >

                      <span>
                        {session
                          .session_name ??
                          session
                            .session_type ??
                          "Session"}
                      </span>


                      <span
                        className={
                          session
                            .ingested
                            ? "catalogue-status catalogue-status--ready"
                            : "catalogue-status"
                        }
                      />

                    </button>
                  )
                }
              )
          )}

        </div>


        <button
          type="button"
          className="catalogue-arrow"
          onClick={() =>
            scrollRow(
              sessionScrollRef,
              "right"
            )
          }
          aria-label="Next sessions"
        >
          ›
        </button>

      </div>

    </section>
  )
}