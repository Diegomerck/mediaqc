import { invoke } from '@tauri-apps/api/core';
import { listen } from '@tauri-apps/api/event';

export interface Progress {
  overall_progress: number;
  stage: string;
  current_detector_id: string | null;
  media_time_seconds: number | null;
  media_duration_seconds: number | null;
  message: string;
}
export interface Run {
  id: string;
  analysis_run_id: string;
  media_asset_id: string;
  status: string;
  started_at: string | null;
  completed_at: string | null;
  qc_profile_snapshot_json: string;
  error_code: string | null;
  error_message: string | null;
  progress: Progress;
  detector_states: { id: string; detector_id: string; status: string }[];
}
export interface Profile {
  profile_key: string;
  version: string;
  name: string;
}
export interface AnalysisEvent {
  type: 'event';
  protocol_version: '1.0';
  event: string;
  data: { analysis_run_id: string };
}
const call = <T>(method: string, params: object) =>
  invoke<T>('engine_request', { method, params });
export const jobs = {
  profiles: () => call<{ profiles: Profile[] }>('profile.list', {}),
  start: (project_id: string, media_asset_id: string, profile: Profile) =>
    call<{ analysis_run_id: string; status: string }>('analysis.start', {
      project_id,
      media_asset_id,
      profile_key: profile.profile_key,
      profile_version: profile.version,
      ai_mode: 'OFF',
    }),
  get: (analysis_run_id: string) =>
    call<Run>('analysis.get', { analysis_run_id }),
  cancel: (analysis_run_id: string) =>
    call('analysis.cancel', { analysis_run_id }),
  retry: (analysis_run_id: string) =>
    call<{ analysis_run_id: string; status: string }>('analysis.retry', {
      analysis_run_id,
    }),
  listen: (callback: (event: AnalysisEvent) => void) =>
    listen<AnalysisEvent>('engine-event', (event) => {
      callback(event.payload);
    }),
};
