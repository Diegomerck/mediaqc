import { describe, it, expect } from 'vitest';
import {
  formatDuration,
  formatTimecode,
  formatTimeRange,
  getMediaBadge,
  formatFileSize,
  formatDate,
} from '../src/formatters';

describe('formatters', () => {
  describe('formatDuration', () => {
    it('formats seconds into human readable duration strings', () => {
      expect(formatDuration(0)).toBe('0s');
      expect(formatDuration(12)).toBe('12s');
      expect(formatDuration(58)).toBe('58s');
      expect(formatDuration(59.4)).toBe('59s');
      expect(formatDuration(60)).toBe('1m 00s');
      expect(formatDuration(117)).toBe('1m 57s');
      expect(formatDuration(3605)).toBe('60m 05s');
    });

    it('handles null, undefined or negative numbers gracefully', () => {
      expect(formatDuration(null)).toBe('0s');
      expect(formatDuration(undefined)).toBe('0s');
      expect(formatDuration(-10)).toBe('0s');
    });
  });
  describe('formatTimecode', () => {
    it('formats seconds into HH:MM:SS', () => {
      expect(formatTimecode(0)).toBe('00:00:00');
      expect(formatTimecode(53)).toBe('00:00:53');
      expect(formatTimecode(64)).toBe('00:01:04');
      expect(formatTimecode(3665)).toBe('01:01:05');
    });

    it('handles null, undefined or negative numbers gracefully', () => {
      expect(formatTimecode(null)).toBe('00:00:00');
      expect(formatTimecode(undefined)).toBe('00:00:00');
      expect(formatTimecode(-5)).toBe('00:00:00');
    });
  });

  describe('formatTimeRange', () => {
    it('formats human-friendly time ranges', () => {
      expect(formatTimeRange(53, 64)).toBe('from 00:00:53 to 00:01:04');
      expect(formatTimeRange(12, null)).toBe('at 00:00:12');
      expect(formatTimeRange(null, null)).toBe('Whole file');
    });
  });

  describe('getMediaBadge', () => {
    it('identifies video and audio file types and codecs', () => {
      const mxf = getMediaBadge('clip_001.mxf');
      expect(mxf.type).toBe('Video');
      expect(mxf.badge).toBe('Video · MXF');

      const mp4 = getMediaBadge('show.mp4');
      expect(mp4.type).toBe('Video');
      expect(mp4.badge).toBe('Video · MP4');

      const wav = getMediaBadge('dialogue.wav');
      expect(wav.type).toBe('Audio');
      expect(wav.badge).toBe('Audio · PCM (WAV)');

      const aac = getMediaBadge('track.aac');
      expect(aac.type).toBe('Audio');
      expect(aac.badge).toBe('Audio · AAC');

      const unknown = getMediaBadge('data.bin');
      expect(unknown.type).toBe('Media');
      expect(unknown.badge).toBe('Media · BIN');
    });
  });

  describe('formatFileSize', () => {
    it('formats bytes into KB, MB, GB', () => {
      expect(formatFileSize(500)).toBe('500 B');
      expect(formatFileSize(1024 * 500)).toBe('500.0 KB');
      expect(formatFileSize(1024 * 1024 * 250)).toBe('250.0 MB');
      expect(formatFileSize(1024 * 1024 * 1024 * 2.5)).toBe('2.50 GB');
      expect(formatFileSize(null)).toBe('—');
    });
  });

  describe('formatDate', () => {
    it('formats ISO dates or returns fallback', () => {
      expect(formatDate(null)).toBe('—');
      expect(formatDate('')).toBe('—');
      const formatted = formatDate('2026-10-15T14:30:00Z');
      expect(formatted).not.toBe('—');
      expect(formatted.length).toBeGreaterThan(5);
    });
  });
});
