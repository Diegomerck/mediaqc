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
  detector_states: {
    id: string;
    detector_id: string;
    status: string;
    metrics_json?: string | null;
    error_message?: string | null;
    finding_count?: number;
    worst_severity?: string | null;
  }[];
  overall_result?: 'PASS' | 'WARN' | 'FAIL' | null;
  summary?: {
    counts: { INFO: number; WARN: number; FAIL: number };
    qc_available: boolean;
  };
  findings?: Finding[];
  total?: number;
}
export interface Finding {
  id: string;
  detector_id: string;
  detector_version: string;
  stream_id: string | null;
  severity: 'INFO' | 'WARN' | 'FAIL';
  title: string;
  description: string;
  start_time_seconds: number | null;
  end_time_seconds: number | null;
  duration_seconds: number | null;
  confidence: number | null;
  disposition: string;
  measurements: Record<string, unknown>;
  threshold: Record<string, unknown>;
  metadata: Record<string, unknown>;
  evidence: { id: string; evidence_type: string; relative_path: string }[];
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
  findings: (analysis_run_id: string, offset: number) =>
    call<{ findings: Finding[]; total: number }>('finding.list', {
      analysis_run_id,
      offset,
      limit: 100,
    }),
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
