import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, expect, test, vi } from 'vitest';
import IssueDrawer from '../src/IssueDrawer';
import { jobs, type Finding, type Run } from '../src/jobs';
import type { BatchItem } from '../src/batches';

vi.mock('../src/jobs', () => ({
  jobs: {
    get: vi.fn(),
    disposition: vi.fn(),
  },
}));

vi.mock('../src/EvidenceView', () => ({
  default: () => <div data-testid="evidence-view">Evidence Preview</div>,
}));

const mockFinding: Finding = {
  id: 'finding-1',
  detector_id: 'video.freeze',
  detector_version: '1.0',
  stream_id: 'v0',
  severity: 'FAIL',
  title: 'Video Freeze Dropout',
  description: 'Frame remains static for 11 seconds',
  start_time_seconds: 53.0,
  end_time_seconds: 64.0,
  duration_seconds: 11.0,
  confidence: 1.0,
  disposition: 'OPEN',
  measurements: { freeze_duration: 11.0 },
  threshold: { max_freeze: 2.0 },
  metadata: {},
  evidence: [
    {
      id: 'ev-1',
      evidence_type: 'VIDEO_FRAME',
      relative_path: 'evidence/video/ev-1.png',
    },
  ],
  explanation: {
    summary: 'Video Freeze Dropout from 00:00:53 to 00:01:04',
    comparisons: [
      {
        label: 'Freeze Duration',
        measured: 11.0,
        unit: 's',
        target: 2.0,
        minimum: null,
        maximum: 2.0,
        difference_from_limit: 9.0,
      },
    ],
  },
};

const mockAudioFinding: Finding = {
  id: 'finding-2',
  detector_id: 'audio.true_peak',
  detector_version: '1.0',
  stream_id: 'a0',
  severity: 'WARN',
  title: 'True Peak Exceeded',
  description: 'True peak exceeds limit',
  start_time_seconds: 12.0,
  end_time_seconds: 15.0,
  duration_seconds: 3.0,
  confidence: 1.0,
  disposition: 'OPEN',
  measurements: { true_peak_dbtp: -0.5 },
  threshold: { max_dbtp: -1.0 },
  metadata: {},
  evidence: [
    {
      id: 'ev-2',
      evidence_type: 'AUDIO_WAVEFORM',
      relative_path: 'evidence/audio/ev-2.png',
    },
  ],
  explanation: {
    summary: 'True peak of -0.5 dBTP exceeds -1.0 dBTP limit',
    comparisons: [
      {
        label: 'True Peak',
        measured: -0.5,
        unit: 'dBTP',
        target: -1.0,
        minimum: null,
        maximum: -1.0,
        difference_from_limit: 0.5,
      },
    ],
  },
};

const mockRun: Run = {
  id: 'run-1',
  analysis_run_id: 'run-1',
  media_asset_id: 'asset-1',
  status: 'COMPLETED',
  started_at: '2026-10-15T14:30:00Z',
  completed_at: '2026-10-15T14:30:15Z',
  qc_profile_snapshot_json: '{}',
  error_code: null,
  error_message: null,
  progress: {
    overall_progress: 1,
    stage: 'complete',
    current_detector_id: null,
    media_time_seconds: null,
    media_duration_seconds: null,
    message: 'Finished',
  },
  detector_states: [],
  overall_result: 'FAIL',
  findings: [mockFinding],
};

const mockItem: BatchItem = {
  item_id: 'item-1',
  file_name: 'feature_reel_01.mxf',
  relative_path: 'Reels/feature_reel_01.mxf',
  absolute_path: 'D:/Footage/Reels/feature_reel_01.mxf',
  status: 'COMPLETED',
  overall_result: 'FAIL',
  analysis_run_id: 'run-1',
  error_message: null,
  exclusion_reason: null,
  duplicate_count: 0,
};

beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(jobs.get).mockResolvedValue(mockRun);
});

test('IssueDrawer renders file title, relative path and human-friendly time range', async () => {
  render(<IssueDrawer item={mockItem} onClose={() => {}} />);

  await screen.findByText('feature_reel_01.mxf');
  expect(screen.getByText('Reels/feature_reel_01.mxf')).toBeDefined();
  expect(screen.getByText('Video Freeze Dropout')).toBeDefined();
  expect(screen.getByText('⏱️ from 00:00:53 to 00:01:04')).toBeDefined();
  expect(
    screen.getByText('Video Freeze Dropout from 00:00:53 to 00:01:04'),
  ).toBeDefined();
});

test('clicking Mark OK / False Alarm invokes jobs.disposition with WAIVED and updates badge to Approved', async () => {
  const waivedFinding: Finding = {
    ...mockFinding,
    disposition: 'WAIVED',
  };
  const waivedRun: Run = {
    ...mockRun,
    overall_result: 'PASS',
    findings: [waivedFinding],
  };

  vi.mocked(jobs.disposition).mockResolvedValue(waivedFinding);

  const onUpdated = vi.fn();
  render(
    <IssueDrawer item={mockItem} onClose={() => {}} onUpdated={onUpdated} />,
  );

  const markBtn = await screen.findByRole('button', {
    name: 'Mark OK / False Alarm',
  });
  expect(markBtn).toBeDefined();

  vi.mocked(jobs.get).mockResolvedValue(waivedRun);
  fireEvent.click(markBtn);

  expect(jobs.disposition).toHaveBeenCalledWith(
    'finding-1',
    'WAIVED',
    'Approved by editor',
  );

  await screen.findByText('🔵 Approved (All issues waived)');
  expect(screen.getByText('✓ Marked OK (False Alarm)')).toBeDefined();
  expect(onUpdated).toHaveBeenCalled();
});

test('displays error notice banner when item.status is FAILED or has error_message, while still rendering findings', async () => {
  const failedItem: BatchItem = {
    ...mockItem,
    status: 'FAILED',
    error_message: 'FFmpeg decode terminated unexpectedly at packet 42',
  };

  render(<IssueDrawer item={failedItem} onClose={() => {}} />);

  await screen.findByText('⚠️ Analysis Failed');
  expect(
    screen.getByText('FFmpeg decode terminated unexpectedly at packet 42'),
  ).toBeDefined();
  // Findings are still rendered below
  expect(screen.getByText('Video Freeze Dropout')).toBeDefined();
});

test('separates video and audio findings, defaulting audio to collapsed when video issues exist', async () => {
  const mixedRun: Run = {
    ...mockRun,
    findings: [mockFinding, mockAudioFinding],
  };
  vi.mocked(jobs.get).mockResolvedValue(mixedRun);

  render(<IssueDrawer item={mockItem} onClose={() => {}} />);

  await screen.findByText('🎬 Video Issues (1)');
  expect(screen.getByText('Video Freeze Dropout')).toBeDefined();
  expect(screen.getByTestId('evidence-view')).toBeDefined();

  // Audio section exists in accordion
  const audioSummary = screen.getByText(/🔊 Audio Checks \(1 finding\)/);
  expect(audioSummary).toBeDefined();

  // Audio details is collapsed by default when video issues exist
  const accordion = audioSummary.closest('details');
  expect(accordion).not.toBeNull();
  expect(accordion?.open).toBe(false);
});

test('defaults audio section to open when no video issues exist', async () => {
  const audioOnlyRun: Run = {
    ...mockRun,
    findings: [mockAudioFinding],
  };
  vi.mocked(jobs.get).mockResolvedValue(audioOnlyRun);

  render(<IssueDrawer item={mockItem} onClose={() => {}} />);

  const audioSummary = await screen.findByText(/🔊 Audio Checks \(1 finding\)/);
  const accordion = audioSummary.closest('details');
  expect(accordion?.open).toBe(true);
  expect(screen.getByText('True Peak Exceeded')).toBeDefined();
});

test('toggles technical details on and off when clicking Show technical details', async () => {
  render(<IssueDrawer item={mockItem} onClose={() => {}} />);

  await screen.findByText('Video Freeze Dropout');

  // Technical details are collapsed initially
  expect(screen.queryByText('Freeze Duration:')).toBeNull();

  const toggleBtn = screen.getByRole('button', {
    name: /Show technical details/,
  });
  fireEvent.click(toggleBtn);

  // Comparisons and measurements are now visible
  expect(screen.getByText('Freeze Duration:')).toBeDefined();
  expect(screen.getByText('Measurements:')).toBeDefined();

  // Click again to hide
  fireEvent.click(screen.getByRole('button', { name: /Hide technical details/ }));
  expect(screen.queryByText('Freeze Duration:')).toBeNull();
});

test('IssueDrawer renders duration pill when item.duration_seconds is present', async () => {
  const itemWithDuration: BatchItem = {
    ...mockItem,
    duration_seconds: 58.2,
  };
  render(<IssueDrawer item={itemWithDuration} onClose={() => {}} />);
  await screen.findByText('feature_reel_01.mxf');
  expect(screen.getByText('⏱️ Analyzed in 58s')).toBeDefined();
});
