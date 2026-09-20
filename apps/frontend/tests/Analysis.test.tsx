import { act, fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, expect, test, vi } from 'vitest';
import AnalysisView from '../src/AnalysisView';
import { jobs, type AnalysisEvent, type Run } from '../src/jobs';
import type { Project } from '../src/projects';

vi.mock('../src/jobs', () => ({
  jobs: {
    profiles: vi.fn(),
    capabilities: vi.fn(),
    start: vi.fn(),
    get: vi.fn(),
    cancel: vi.fn(),
    retry: vi.fn(),
    listen: vi.fn(),
  },
}));
const profile = {
  profile_key: 'general_technical_qc',
  version: '1.0.0',
  name: 'General Technical QC',
};
const project: Project = {
  id: 'project',
  name: 'Episode',
  project_file: 'C:/QC/project.sqlite',
  media_assets: [
    {
      id: 'asset',
      file_name: 'audio.wav',
      absolute_path: 'D:/audio.wav',
      inspection_status: 'COMPLETED',
      source_status: 'UNCHANGED',
      file_size_bytes: 10,
      modified_at: null,
      duration_seconds: 1,
      container_format: 'wav',
      fast_fingerprint_sha256: 'f',
      inspection_error_code: null,
      inspection_error_message: null,
      streams: [],
    },
  ],
};
const run: Run = {
  id: 'run',
  analysis_run_id: 'run',
  media_asset_id: 'asset',
  status: 'ANALYZING',
  started_at: '2026-09-10T00:00:00Z',
  completed_at: null,
  qc_profile_snapshot_json: JSON.stringify(profile),
  error_code: null,
  error_message: null,
  progress: {
    overall_progress: 0.4,
    stage: 'ANALYZING',
    current_detector_id: null,
    media_time_seconds: null,
    media_duration_seconds: 1,
    message: 'Working locally',
  },
  detector_states: [],
};
let eventCallback: (event: AnalysisEvent) => void;
beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(jobs.capabilities).mockResolvedValue({
    ai: { local_available: false },
  });
  vi.mocked(jobs.profiles).mockResolvedValue({ profiles: [profile] });
  vi.mocked(jobs.start).mockResolvedValue({
    analysis_run_id: 'run',
    status: 'QUEUED',
  });
  vi.mocked(jobs.get).mockResolvedValue(run);
  vi.mocked(jobs.listen).mockImplementation((callback) => {
    eventCallback = callback;
    return Promise.resolve(vi.fn());
  });
});
async function selectAndStart() {
  await screen.findByRole('option', { name: 'General Technical QC 1.0.0' });
  fireEvent.change(screen.getByLabelText('Analysis media'), {
    target: { value: 'asset' },
  });
  fireEvent.change(screen.getByLabelText('QC profile'), {
    target: { value: 'general_technical_qc@1.0.0' },
  });
  fireEvent.click(screen.getByRole('button', { name: 'Start analysis' }));
  await screen.findByText('audio.wav — ANALYZING');
}
test('valid selection starts with AI off, remains responsive and displays actual progress', async () => {
  const active = vi.fn();
  render(<AnalysisView project={project} onActive={active} />);
  expect(
    screen
      .getByRole('button', { name: 'Start analysis' })
      .hasAttribute('disabled'),
  ).toBe(true);
  await selectAndStart();
  expect(jobs.start).toHaveBeenCalledWith('project', 'asset', profile, 'OFF');
  expect(screen.getByRole('progressbar').getAttribute('value')).toBe('0.4');
  fireEvent.click(screen.getByRole('button', { name: 'Cancel run' }));
  expect(jobs.cancel).toHaveBeenCalledWith('run');
  expect(active).toHaveBeenCalledWith(true);
});
test('terminal event enables retry and preserves previous run', async () => {
  render(<AnalysisView project={project} onActive={vi.fn()} />);
  await selectAndStart();
  vi.mocked(jobs.get).mockResolvedValue({ ...run, status: 'CANCELLED' });
  act(() => {
    eventCallback({
      type: 'event',
      protocol_version: '1.0',
      event: 'analysis.cancelled',
      data: { analysis_run_id: 'run' },
    });
  });
  await screen.findByText('audio.wav — CANCELLED');
  vi.mocked(jobs.retry).mockResolvedValue({
    analysis_run_id: 'retry',
    status: 'QUEUED',
  });
  fireEvent.click(screen.getByRole('button', { name: 'Retry run' }));
  expect(jobs.retry).toHaveBeenCalledWith('run');
});
test('start errors are visible and allow another attempt', async () => {
  vi.mocked(jobs.start).mockRejectedValue({
    code: 'RUN_START_FAILED',
    message: 'Conflicting run',
  });
  render(<AnalysisView project={project} onActive={vi.fn()} />);
  await screen.findByRole('option', { name: 'General Technical QC 1.0.0' });
  fireEvent.change(screen.getByLabelText('Analysis media'), {
    target: { value: 'asset' },
  });
  fireEvent.change(screen.getByLabelText('QC profile'), {
    target: { value: 'general_technical_qc@1.0.0' },
  });
  fireEvent.click(screen.getByRole('button', { name: 'Start analysis' }));
  expect((await screen.findByRole('alert')).textContent).toContain(
    'RUN_START_FAILED',
  );
  expect(
    screen
      .getByRole('button', { name: 'Start analysis' })
      .hasAttribute('disabled'),
  ).toBe(false);
});

test('Phase 8 LOCAL is disabled without installed capability', async () => {
  render(<AnalysisView project={project} onActive={vi.fn()} />);
  await screen.findByText(/No compatible embedded model installed/u);
  expect(
    screen.getByRole('option', { name: 'LOCAL' }).hasAttribute('disabled'),
  ).toBe(true);
  expect(screen.getByLabelText<HTMLSelectElement>('AI mode').value).toBe('OFF');
});

test('Phase 8 compatible embedded capability enables explicit LOCAL selection', async () => {
  vi.mocked(jobs.capabilities).mockResolvedValue({
    ai: { local_available: true },
  });
  render(<AnalysisView project={project} onActive={vi.fn()} />);
  await screen.findByText(/Compatible embedded model available/u);
  fireEvent.change(screen.getByLabelText('AI mode'), {
    target: { value: 'LOCAL' },
  });
  await selectAndStart();
  expect(jobs.start).toHaveBeenCalledWith('project', 'asset', profile, 'LOCAL');
});

test('Phase 8 capability failure leaves deterministic analysis usable', async () => {
  vi.mocked(jobs.capabilities).mockRejectedValue(new Error('Unavailable'));
  render(<AnalysisView project={project} onActive={vi.fn()} />);
  await screen.findByText(/Local model status unavailable/u);
  await selectAndStart();
  expect(jobs.start).toHaveBeenCalledWith('project', 'asset', profile, 'OFF');
});
