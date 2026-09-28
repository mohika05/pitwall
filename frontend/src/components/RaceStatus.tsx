import {
    useRaceStore,
} from "../stores/raceStore"
import { F1Term } from './F1Glossary'


export function RaceStatus() {
    const state =
        useRaceStore(
        (store) =>
            store.state
        )

    if (!state) {
        return (
        <section className="race-status">
            <div>
            <span className="label">
                STATUS
            </span>

            <strong>
                Waiting for race data...
            </strong>
            </div>
        </section>
        )
    }


    const timestamp =
        new Date(
        state.replay_timestamp
        )


    return (
        <section className="race-status">
        <div>
            <span className="label">
            LAP COMPLETED
            </span>

            <strong>
            {state.current_lap}
            </strong>
        </div>


        <div>
            <span className="label">
            REPLAY TIME
            </span>

            <strong>
            {timestamp
                .toLocaleTimeString()}
            </strong>
        </div>


        <div>
            <span className="label">
            <F1Term term="Flag">FLAG</F1Term>
            </span>

            <strong>
            {state.flag ?? "—"}
            </strong>
        </div>


        <div>
            <span className="label">
            <F1Term term="Safety car">SAFETY CAR</F1Term>
            </span>

            <strong>
            {state.safety_car ??
                "NONE"}
            </strong>
        </div>
        </section>
    )
}
