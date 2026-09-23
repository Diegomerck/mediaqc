import { invoke } from '@tauri-apps/api/core';
import { listen } from '@tauri-apps/api/event';
import type { Profile } from './jobs';

export interface Batch {
  batch_id: string;
  name: string;
  status: string;
  revision: number;
  profile: Profile | null;
  ai_mode: 'OFF' | 'LOCAL';
  counts: Record<
    | 'total'
    | 'processed'
    | 'pass'
    | 'warn'
    | 'fail'
    | 'error'
    | 'cancelled'
    | 'processing'
    | 'pending',
    number
  >;
  import_summary: {
    excluded: number;
    duplicate_encounters: number;
    directory_errors: number;
    complete: boolean;
    partial: boolean;
  };
  current: {
    item_id: string;
    file_name: string;
    file_progress: number | null;
    stage: string;
  } | null;
  overall_progress: number;
  can_continue_pending: boolean;
  error_message: string | null;
  engine_session_id: string;
  progress_sequence: number;
}
export interface BatchItem {
  item_id: string;
  file_name: string;
  relative_path: string;
  absolute_path: string;
  status: string;
  overall_result: string | null;
  analysis_run_id: string | null;
  error_message: string | null;
  exclusion_reason: string | null;
  duplicate_count: number;
}
export interface BatchPage {
  items: BatchItem[];
  total: number;
  revision: number;
}
export interface HistoricalRun {
  id: string;
  file_name: string;
  status: string;
  overall_result: string | null;
}
const call = <T>(method: string, params: object) =>
  invoke<T>('engine_request', { method, params });
export const batches = {
  create: (
    project_id: string,
    name: string,
    source_kind: 'FILE' | 'FOLDER',
    absolute_path: string,
    recursive: boolean,
  ) =>
    call<{ batch_id: string }>('batch.create', {
      project_id,
      name,
      source_kind,
      absolute_path,
      recursive,
    }),
  list: (project_id: string, offset = 0) =>
    call<{ batches: Batch[]; total: number }>('batch.list', {
      project_id,
      limit: 50,
      offset,
    }),
  history: (project_id: string, offset = 0) =>
    call<{ runs: HistoricalRun[]; total: number }>('analysis.list', {
      project_id,
      limit: 50,
      offset,
    }),
  get: (batch_id: string) => call<Batch>('batch.get', { batch_id }),
  items: (batch_id: string, filter: string, offset: number) =>
    call<BatchPage>('batch.items', { batch_id, filter, offset, limit: 50 }),
  start: (batch_id: string, profile: Profile, ai_mode: 'OFF' | 'LOCAL') =>
    call('batch.start', {
      batch_id,
      profile_key: profile.profile_key,
      profile_version: profile.version,
      ai_mode,
    }),
  control: (batch_id: string, action: 'pause' | 'resume' | 'stop') =>
    call(`batch.${action}`, { batch_id }),
  retry: (batch_id: string) =>
    call<{ batch_id: string }>('batch.retry', {
      batch_id,
      selection: 'ALL_UNSUCCESSFUL',
    }),
  report: (batch_id: string, format: 'HTML' | 'PDF') =>
    call<{ absolute_path: string }>('batch.report.generate', {
      batch_id,
      format,
    }),
  listen: (
    callback: (
      batchId: string,
      revision?: number,
      error?: string | null,
    ) => void,
  ) =>
    listen<{
      data: {
        batch_id?: string;
        revision?: number;
        error_message?: string | null;
      };
    }>('engine-event', (event) => {
      if (event.payload.data.batch_id)
        callback(
          event.payload.data.batch_id,
          event.payload.data.revision,
          event.payload.data.error_message,
        );
    }),
};
