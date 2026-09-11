import { fireEvent, render, screen } from '@testing-library/react';
import { expect, test, vi } from 'vitest';
import AudioResults from '../src/AudioResults';
import { jobs, type Finding, type Run } from '../src/jobs';

vi.mock('../src/jobs', () => ({ jobs: { findings: vi.fn() } }));
const finding: Finding = {
  id: 'finding',
  detector_id: 'audio.clipping',
  detector_version: '1.0.0',
  stream_id: 'left',
  severity: 'FAIL',
  title: 'Clipping evidence',
  description: 'Near-full-scale samples',
  start_time_seconds: 1,
  end_time_seconds: 1.1,
  duration_seconds: 0.1,
  confidence: null,
  disposition: 'OPEN',
  measurements: { clipped_sample_count: 4800 },
  threshold: { near_full_scale_dbfs: -0.01 },
  metadata: {},
  evidence: [
    {
      id: 'evidence',
      evidence_type: 'METRICS_JSON',
      relative_path: 'evidence/audio/run/finding.json',
    },
  ],
};
const run: Run = {
  id: 'run',
  analysis_run_id: 'run',
  media_asset_id: 'asset',
  status: 'COMPLETED',
  started_at: '2026-09-11T12:00:00Z',
  completed_at: '2026-09-11T12:00:10Z',
  qc_profile_snapshot_json: '{}',
  error_code: null,
  error_message: null,
  progress: {
    overall_progress: 1,
    stage: 'COMPLETED',
    current_detector_id: null,
    media_time_seconds: 6,
    media_duration_seconds: 6,
    message: 'Complete',
  },
  detector_states: [
    {
      id: 'noise',
      detector_id: 'audio.noise_floor',
      status: 'COMPLETED',
      metrics_json: '{"state":"INSUFFICIENT_QUIET_REGIONS"}',
    },
  ],
  overall_result: 'FAIL',
  summary: { counts: { FAIL: 1, WARN: 0, INFO: 0 }, qc_available: true },
  findings: [finding],
  total: 1,
};
test('shows saved audio result, raw measurements, thresholds and evidence', () => {
  render(<AudioResults run={run} />);
  expect(screen.getByText('Audio QC: FAIL')).toBeTruthy();
  fireEvent.click(screen.getByText(/Clipping evidence/u));
  expect(screen.getByText(/4800/u)).toBeTruthy();
  expect(screen.getByText(/-0.01/u)).toBeTruthy();
  expect(screen.getByText(/evidence\/audio\/run\/finding.json/u)).toBeTruthy();
  expect(screen.getByText(/INSUFFICIENT_QUIET_REGIONS/u)).toBeTruthy();
});
test('missing evidence is explicit and cancelled runs remain incomplete', () => {
  render(
    <AudioResults
      run={{
        ...run,
        status: 'CANCELLED',
        overall_result: null,
        findings: [
          {
            ...finding,
            evidence: [],
            metadata: { evidence_error: 'Disk full' },
          },
        ],
      }}
    />,
  );
  expect(screen.getByText('Audio QC: Incomplete')).toBeTruthy();
  expect(screen.getByRole('alert').textContent).toContain('Disk full');
});
test('loads additional saved findings through bounded IPC pages', async () => {
  vi.mocked(jobs.findings).mockResolvedValue({
    findings: [{ ...finding, id: 'second', title: 'Second issue' }],
    total: 2,
  });
  render(<AudioResults run={{ ...run, total: 2 }} />);
  fireEvent.click(screen.getByRole('button', { name: /Load more/u }));
  await screen.findByText(/Second issue/u);
  expect(jobs.findings).toHaveBeenCalledWith('run', 1);
});
