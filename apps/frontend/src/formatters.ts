export function formatDuration(seconds: number | null | undefined): string {
  if (
    seconds === null ||
    seconds === undefined ||
    isNaN(seconds) ||
    seconds <= 0
  ) {
    return '0s';
  }
  if (seconds < 60) return `${Math.round(seconds)}s`;
  const m = Math.floor(seconds / 60);
  const s = Math.round(seconds % 60);
  return `${m}m ${s.toString().padStart(2, '0')}s`;
}

export function formatTimecode(seconds: number | null | undefined): string {
  if (
    seconds === null ||
    seconds === undefined ||
    isNaN(seconds) ||
    seconds < 0
  ) {
    return '00:00:00';
  }
  const total = Math.floor(seconds);
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  return `${h.toString().padStart(2, '0')}:${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
}

export function formatTimeRange(
  start: number | null | undefined,
  end: number | null | undefined,
): string {
  const hasStart = start !== null && start !== undefined && !isNaN(start);
  const hasEnd = end !== null && end !== undefined && !isNaN(end);

  if (hasStart && hasEnd) {
    return `from ${formatTimecode(start)} to ${formatTimecode(end)}`;
  }
  if (hasStart) {
    return `at ${formatTimecode(start)}`;
  }
  return 'Whole file';
}

export interface MediaBadgeInfo {
  type: 'Video' | 'Audio' | 'Media';
  codec: string;
  badge: string;
}

export function getMediaBadge(filename: string): MediaBadgeInfo {
  const ext = filename.split('.').pop()?.toUpperCase() ?? '';
  switch (ext) {
    case 'MXF':
      return { type: 'Video', codec: 'MXF', badge: 'Video · MXF' };
    case 'MP4':
      return { type: 'Video', codec: 'H.264 / AVC', badge: 'Video · MP4' };
    case 'MOV':
      return { type: 'Video', codec: 'ProRes / MOV', badge: 'Video · MOV' };
    case 'MKV':
      return { type: 'Video', codec: 'Matroska', badge: 'Video · MKV' };
    case 'AVI':
      return { type: 'Video', codec: 'AVI', badge: 'Video · AVI' };
    case 'WAV':
      return { type: 'Audio', codec: 'PCM', badge: 'Audio · PCM (WAV)' };
    case 'MP3':
      return { type: 'Audio', codec: 'MPEG Audio', badge: 'Audio · MP3' };
    case 'AAC':
      return { type: 'Audio', codec: 'AAC', badge: 'Audio · AAC' };
    case 'M4A':
      return { type: 'Audio', codec: 'AAC / ALAC', badge: 'Audio · M4A' };
    case 'FLAC':
      return { type: 'Audio', codec: 'FLAC', badge: 'Audio · FLAC' };
    case 'AIFF':
    case 'AIF':
      return { type: 'Audio', codec: 'PCM (AIFF)', badge: 'Audio · AIFF' };
    default:
      return {
        type: 'Media',
        codec: ext || 'FILE',
        badge: ext ? `Media · ${ext}` : 'Media',
      };
  }
}

export function formatFileSize(bytes?: number | null): string {
  if (bytes === null || bytes === undefined || isNaN(bytes) || bytes <= 0) {
    return '—';
  }
  if (bytes < 1024) return `${String(bytes)} B`;
  const kb = bytes / 1024;
  if (kb < 1024) return `${kb.toFixed(1)} KB`;
  const mb = kb / 1024;
  if (mb < 1024) return `${mb.toFixed(1)} MB`;
  const gb = mb / 1024;
  return `${gb.toFixed(2)} GB`;
}

export function formatDate(iso?: string | null): string {
  if (!iso) return '—';
  try {
    const d = new Date(iso);
    if (isNaN(d.getTime())) return iso;
    return d.toLocaleDateString(undefined, {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  } catch {
    return iso;
  }
}

export function humanFriendlyTitle(finding: {
  title?: string;
  detector_id: string;
}): string {
  if (
    finding.title &&
    !finding.title.toLowerCase().endsWith('candidate') &&
    finding.title !== 'Total video signal loss'
  ) {
    return finding.title;
  }
  const id = finding.detector_id.toLowerCase();
  if (id === 'video.freeze') return 'Video Freeze Dropout';
  if (id === 'video.black_frame') return 'Total Video Blankout';
  if (id === 'video.near_black_frame') return 'Near-Black Video Frames';
  if (id === 'video.luminance_anomaly') return 'Luminance Anomaly';
  if (id === 'video.visual_anomaly') return 'Visual Corruption Anomaly';
  if (id === 'video.flash') return 'Video Flash / Exposure Spike';
  if (id === 'video.duplicate_frame') return 'Duplicate Frame Repeat';
  if (id === 'video.frame_cadence') return 'Frame Cadence Irregularity';
  if (id === 'video.exposure_anomaly') return 'Extreme Exposure Anomaly';
  if (id === 'video.decode_integrity') return 'Video Decode / Integrity Failure';

  if (finding.title === 'Total video signal loss') return 'Total Video Blankout';
  return finding.title || id;
}
