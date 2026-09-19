import { fireEvent, render, screen, within } from '@testing-library/react';
import { beforeEach, expect, test, vi } from 'vitest';
import AudioResults from '../src/AudioResults';
import EvidenceView from '../src/EvidenceView';
import ResultsTimeline from '../src/ResultsTimeline';
import { timelinePosition } from '../src/timeline';
import { jobs, type Finding, type Run } from '../src/jobs';

vi.mock('../src/jobs', () => ({
  jobs: {
    findings: vi.fn(),
    evidence: vi.fn(),
    disposition: vi.fn(),
    get: vi.fn(),
  },
}));
const finding: Finding = {
  id: 'one',
  detector_id: 'video.black_frame',
  detector_version: '1.0.0',
  stream_id: 'video-stream',
  severity: 'FAIL',
  title: 'Black frame',
  description: 'Measured black region',
  start_time_seconds: 20,
  end_time_seconds: 21,
  duration_seconds: 1,
  confidence: 0.8,
  disposition: 'OPEN',
  measurements: { mean_luma_normalized: 0.001 },
  threshold: { max_luma: 0.01 },
  metadata: {},
  evidence: ['VIDEO_FRAME_BEFORE', 'VIDEO_FRAME', 'VIDEO_FRAME_AFTER'].map(
    (evidence_type) => ({
      id: evidence_type,
      evidence_type,
      relative_path: `evidence/video/é space/${evidence_type}.png`,
    }),
  ),
};
const second: Finding = {
  ...finding,
  id: 'two',
  title: 'Audio issue',
  detector_id: 'audio.clipping',
  severity: 'WARN',
  start_time_seconds: null,
  end_time_seconds: null,
  evidence: [],
};
const run: Run = {
  id: 'run',
  analysis_run_id: 'run',
  media_asset_id: 'asset',
  media: {
    file_name: 'é space.mp4',
    absolute_path: 'C:/source/é space.mp4',
    duration_seconds: 3600,
  },
  status: 'COMPLETED',
  started_at: '2026-09-18T00:00:00Z',
  completed_at: '2026-09-18T00:01:00Z',
  qc_profile_snapshot_json: '{"name":"General QC","version":"1.2.0"}',
  error_code: null,
  error_message: null,
  progress: {
    overall_progress: 1,
    stage: 'COMPLETED',
    current_detector_id: null,
    media_time_seconds: 3600,
    media_duration_seconds: 3600,
    message: 'Complete',
  },
  detector_states: [],
  findings: [finding, second],
  total: 2,
  overall_result: 'FAIL',
  summary: {
    counts: { FAIL: 1, WARN: 1, INFO: 0 },
    qc_available: true,
    dispositions: { OPEN: 2 },
  },
};
beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(jobs.evidence).mockResolvedValue({
    data_url: 'data:image/png;base64,eA==',
    start_time_seconds: 19,
    end_time_seconds: 22,
    metadata: { finding_start_seconds: 20, finding_end_seconds: 21 },
  });
});

test('finding list selects every issue and inspector exposes profile and measurements', () => {
  render(<AudioResults run={run} />);
  expect(screen.getByRole('table').textContent).toContain('Whole stream');
  expect(
    within(screen.getByRole('region', { name: 'Issue inspector' })).getByText(
      /mean_luma_normalized/u,
    ),
  ).toBeTruthy();
  expect(screen.getByText('Profile: General QC v1.2.0')).toBeTruthy();
  fireEvent.click(screen.getByRole('button', { name: 'Audio issue' }));
  const inspector = screen.getByRole('region', { name: 'Issue inspector' });
  expect(inspector.textContent).toContain('audio.clipping v1.0.0');
  expect(inspector.textContent).toContain('Stream: video-stream');
  expect(inspector.textContent).toContain('Confidence: 0.8');
  expect(inspector.textContent).toContain('max_luma');
});

test('severity, detector, disposition, media kind and search filters affect list', () => {
  render(<AudioResults run={run} />);
  fireEvent.change(screen.getByLabelText('Filter severity'), {
    target: { value: 'WARN' },
  });
  expect(screen.queryByRole('button', { name: 'Black frame' })).toBeNull();
  fireEvent.change(screen.getByLabelText('Filter severity'), {
    target: { value: '' },
  });
  fireEvent.change(screen.getByLabelText('Filter kind'), {
    target: { value: 'video.' },
  });
  expect(screen.queryByRole('button', { name: 'Audio issue' })).toBeNull();
  fireEvent.change(screen.getByLabelText('Search text'), {
    target: { value: 'not present' },
  });
  expect(screen.getByText('No findings match these filters.')).toBeTruthy();
});

test('timeline maps, zooms, pans and selects a finding', () => {
  expect(timelinePosition(50, 0, 100)).toBe(50);
  expect(timelinePosition(-1, 0, 100)).toBe(0);
  expect(timelinePosition(500, 0, 100)).toBe(100);
  const select = vi.fn();
  render(
    <ResultsTimeline
      findings={[finding]}
      duration={3600}
      selected={finding}
      select={select}
    />,
  );
  fireEvent.click(screen.getByRole('button', { name: 'FAIL · 20.000 s' }));
  expect(select).toHaveBeenCalledWith(finding);
  fireEvent.change(screen.getByLabelText('Timeline zoom'), {
    target: { value: '100' },
  });
  fireEvent.change(screen.getByLabelText('Timeline pan'), {
    target: { value: '100' },
  });
  expect(screen.getByText(/100.000 s — 136.000 s/u)).toBeTruthy();
  expect(screen.queryByRole('button', { name: 'FAIL · 20.000 s' })).toBeNull();
});

test('long-form timeline clusters thousands of findings into bounded targets', () => {
  render(
    <ResultsTimeline
      findings={Array.from({ length: 5000 }, (_, index) => ({
        ...finding,
        id: String(index),
      }))}
      duration={3600}
      selected={undefined}
      select={vi.fn()}
    />,
  );
  expect(screen.getAllByRole('button')).toHaveLength(1);
  expect(screen.getByRole('button').textContent).toContain('5000 findings');
});

test('renders current still and before/after video images with timestamps', async () => {
  render(<EvidenceView finding={finding} />);
  expect(await screen.findByAltText('VIDEO FRAME')).toBeTruthy();
  expect(screen.getByAltText('VIDEO FRAME BEFORE')).toBeTruthy();
  expect(screen.getByAltText('VIDEO FRAME AFTER')).toBeTruthy();
  expect(screen.getAllByText(/Time ruler: 19.000–22.000 s/u)).toHaveLength(3);
});

test('renders waveform and spectrogram with time ruler and finding region', async () => {
  render(
    <EvidenceView
      finding={{
        ...second,
        evidence: ['AUDIO_WAVEFORM', 'AUDIO_SPECTROGRAM'].map(
          (evidence_type) => ({
            id: evidence_type,
            evidence_type,
            relative_path: `evidence/audio/${evidence_type}.png`,
          }),
        ),
      }}
    />,
  );
  expect(await screen.findByAltText('AUDIO WAVEFORM')).toBeTruthy();
  expect(screen.getByAltText('AUDIO SPECTROGRAM')).toBeTruthy();
  expect(screen.getAllByText(/Finding region: 20–21 s/u)).toHaveLength(2);
});

test.each(['CONFIRMED', 'FALSE_POSITIVE', 'IGNORED', 'OPEN'])(
  'saves %s and refreshes overall status from engine',
  async (value) => {
    const labels: Record<string, string> = {
      CONFIRMED: 'Confirm',
      FALSE_POSITIVE: 'Mark False Positive',
      IGNORED: 'Ignore',
      OPEN: 'Reopen',
    };
    const overall_result =
      value === 'FALSE_POSITIVE' || value === 'IGNORED' ? 'WARN' : 'FAIL';
    vi.mocked(jobs.disposition).mockResolvedValue({
      ...finding,
      disposition: value,
    });
    vi.mocked(jobs.get).mockResolvedValue({
      ...run,
      overall_result,
      findings: [{ ...finding, disposition: value }, second],
    });
    render(<AudioResults run={run} />);
    fireEvent.change(screen.getByLabelText('Disposition note'), {
      target: { value: 'Intentional slate' },
    });
    fireEvent.click(screen.getByRole('button', { name: labels[value] ?? '' }));
    await vi.waitFor(() => {
      expect(jobs.get).toHaveBeenCalledWith('run');
    });
    expect(jobs.disposition).toHaveBeenCalledWith(
      'one',
      value,
      'Intentional slate',
    );
    expect(screen.getByText(`Audio QC: ${overall_result}`)).toBeTruthy();
  },
);

test('missing and failed visual evidence are explicit even with metrics references', () => {
  render(
    <EvidenceView
      finding={{
        ...second,
        metadata: {
          visual_evidence_errors: [
            { code: 'EVIDENCE_WRITE_FAILED', message: 'Disk full' },
          ],
        },
      }}
    />,
  );
  expect(screen.getByRole('alert').textContent).toContain('Disk full');
  expect(screen.getByRole('alert').textContent).toContain('AUDIO_SPECTROGRAM');
});

test.each(['EVIDENCE_STALE', 'EVIDENCE_UNAVAILABLE'])(
  'displays %s evidence loading error',
  async (code) => {
    vi.mocked(jobs.evidence).mockRejectedValue({
      code,
      message: 'Restore evidence',
      recoverable: true,
    });
    render(<EvidenceView finding={finding} />);
    await vi.waitFor(() => {
      expect(screen.getAllByRole('alert')).toHaveLength(3);
    });
    expect(screen.getAllByRole('alert')[0]?.textContent).toContain(code);
  },
);
