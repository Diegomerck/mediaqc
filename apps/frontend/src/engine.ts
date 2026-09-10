import { invoke } from '@tauri-apps/api/core';

export interface EngineError {
  code: string;
  message: string;
}

export interface Capabilities {
  engine_version: string;
  protocol_version: string;
  schema_version: number;
  platform: string;
  ffmpeg: { available: boolean; version: string | null };
  ffprobe: { available: boolean; version: string | null };
  ai: { local_available: boolean; provider: string | null };
  detectors: {
    id: string;
    version: string;
    media_types: string[];
    requires_ai: boolean;
  }[];
}

export interface EngineStatus {
  phase: 'stopped' | 'starting' | 'ready' | 'stopping' | 'error';
  pid: number | null;
  capabilities: Capabilities | null;
  error: EngineError | null;
  log_path: string;
  desktop_version: string;
}

export const engine = {
  status: () => invoke<EngineStatus>('engine_status'),
  start: () => invoke<Capabilities>('engine_start'),
  ping: () => invoke<{ pong: true }>('engine_ping'),
  stop: () => invoke<{ forced: boolean }>('engine_stop'),
};

export function engineError(value: unknown): EngineError {
  if (
    typeof value === 'object' &&
    value !== null &&
    'code' in value &&
    'message' in value &&
    typeof value.code === 'string' &&
    typeof value.message === 'string'
  ) {
    return { code: value.code, message: value.message };
  }
  return {
    code: 'DESKTOP_CONNECTION_FAILED',
    message:
      'The desktop engine controller is unavailable. Open the built MediaQC desktop application or relaunch it.',
  };
}
