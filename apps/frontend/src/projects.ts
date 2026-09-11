import { invoke } from '@tauri-apps/api/core';
import type { Run } from './jobs';

export interface Stream {
  stream_index: number;
  stream_type: string;
  codec_name: string | null;
  width: number | null;
  height: number | null;
  avg_frame_rate: string | null;
  real_frame_rate: string | null;
  sample_rate_hz: number | null;
  channel_count: number | null;
  channel_layout: string | null;
}
export interface MediaAsset {
  id: string;
  absolute_path: string;
  file_name: string;
  file_size_bytes: number;
  modified_at: string | null;
  duration_seconds: number | null;
  container_format: string | null;
  fast_fingerprint_sha256: string | null;
  inspection_status: string;
  inspection_error_code: string | null;
  inspection_error_message: string | null;
  source_status: string;
  streams: Stream[];
}
export interface Project {
  id: string;
  name: string;
  project_file: string;
  media_assets: MediaAsset[];
  analysis_runs?: Run[];
}
export const projects = {
  pick: (kind: 'directory' | 'project' | 'media') =>
    invoke<string | null>('pick_path', { kind }),
  create: (directory: string, name: string) =>
    invoke<Project>('engine_request', {
      method: 'project.create',
      params: { directory, name },
    }),
  open: (project_file: string) =>
    invoke<Project>('engine_request', {
      method: 'project.open',
      params: { project_file },
    }),
  get: () =>
    invoke<Project>('engine_request', { method: 'project.get', params: {} }),
  inspect: (project_id: string, absolute_path: string) =>
    invoke('engine_request', {
      method: 'media.inspect',
      params: { project_id, absolute_path },
    }),
};
