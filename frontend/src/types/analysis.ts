export interface Lap {
  driver_number: number; driver: string; lap: number; seconds: number;
  start: string; end: string; compound: string; tyre_age: number | null;
  stint: number; pit_out: boolean; neutralized: boolean;
  sectors: (number | null)[]; stage: string | null;
}
export interface Analysis {
  session: { session_key: number; year: number; country_name: string; session_name: string; session_type: string };
  start: string; end: string;
  drivers: { driver_number: number; name_acronym: string; full_name: string; team_colour: string; laps: number; best: number | null; median_pace: number | null }[];
  laps: Lap[];
  stints: { driver: string; driver_number: number; compound: string; stint_number: number; lap_start: number; lap_end: number | null }[];
  timeline: { id: string; event_index: number; type: string; timestamp: string; driver: string | null; lap: number | null; payload: { message?: string; flag?: string; lane_duration?: number; stop_duration?: number } }[];
  qualifying: { driver_number: number; Q1: number | null; Q2: number | null; Q3: number | null; position: number | null }[];
  official_result: { driver_number: number; position?: number; dnf?: boolean; dns?: boolean; dsq?: boolean }[];
  quality: { source: string; telemetry_drivers: string[]; total_drivers: number; note: string };
}
export interface PreparationJob {
  session_key: number; state: string; progress: number; message: string;
  events_ready: boolean; telemetry_ready: boolean; errors: string[];
}
export interface Scenario {
  id: string; created_at: string; delta_seconds: number; branch_lap: number; model: string;
  trajectory: { lap: number; baseline: number; alternative: number; delta: number; compound: string; tyre_age: number; pit: boolean; rejoin_position: number | null }[];
  sensitivity: { optimistic: number; central: number; pessimistic: number };
  assumptions: { name: string; session_key: number; mode: string; pit_lap: number; compound: string };
  warnings: string[]; comparison: string; uncertainty_note: string;
}
export interface PaceModel {
  id: string; accepted: boolean; mae_seconds: number; baseline_mae_seconds: number;
  training_sessions: number[]; holdout_session: number; training_laps: number; limits: string;
}
