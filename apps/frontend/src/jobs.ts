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
  ai_mode?: 'OFF' | 'LOCAL';
  media?: {
    file_name: string;
    duration_seconds: number | null;
    absolute_path: string;
  };
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
    dispositions?: Record<string, number>;
    counts: { INFO: number; WARN: number; FAIL: number };
    qc_available: boolean;
  };
  findings?: Finding[];
  total?: number;
}
export interface Finding {
  explanation?: {
    summary: string;
    comparisons: {
      label: string;
      measured: number | null;
      unit: string;
      target: number | null;
      minimum: number | null;
      maximum: number | null;
      difference_from_limit: number | null;
    }[];
  };
  ai_review?: {
    status: 'COMPLETED' | 'UNAVAILABLE';
    error_code: string | null;
    model_id: string | null;
    model_version: string | null;
    prompt_version: string;
    created_at: string;
    output: {
      classification: string;
      confidence: number;
      summary: string;
      recommended_action: 'REVIEW' | 'LIKELY_VALID' | 'LIKELY_FALSE_POSITIVE';
      evidence_refs: string[];
    } | null;
  };
  feedback?: {
    previous_disposition: string;
    new_disposition: string;
    note: string | null;
    created_at: string;
  }[];
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
  capabilities: () =>
    call<{ ai: { local_available: boolean; reason?: string | null } }>(
      'system.capabilities',
      {},
    ),
  finding: (finding_id: string) => call<Finding>('finding.get', { finding_id }),
  disposition: (finding_id: string, disposition: string, note: string) =>
    call<Finding>('finding.set_disposition', { finding_id, disposition, note }),
  evidence: (evidence_id: string) =>
    call<{
      data_url?: string;
      text?: string;
      start_time_seconds?: number;
      end_time_seconds?: number;
      metadata?: {
        finding_start_seconds?: number | null;
        finding_end_seconds?: number | null;
        window_seconds?: number | null;
      };
    }>('evidence.read', { evidence_id }),
  profiles: () => call<{ profiles: Profile[] }>('profile.list', {}),
  report: (analysis_run_id: string, format: 'HTML' | 'PDF') =>
    call<{ absolute_path: string }>('report.generate', {
      analysis_run_id,
      format,
    }),
  start: (
    project_id: string,
    media_asset_id: string,
    profile: Profile,
    ai_mode: 'OFF' | 'LOCAL' = 'OFF',
  ) =>
    call<{ analysis_run_id: string; status: string }>('analysis.start', {
      project_id,
      media_asset_id,
      profile_key: profile.profile_key,
      profile_version: profile.version,
      ai_mode,
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
