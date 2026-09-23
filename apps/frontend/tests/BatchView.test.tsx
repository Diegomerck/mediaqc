import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react';
import { beforeEach, expect, test, vi } from 'vitest';
import BatchView from '../src/BatchView';
import { batches, type Batch } from '../src/batches';
import { projects } from '../src/projects';
import { jobs } from '../src/jobs';

vi.mock('../src/batches', () => ({
  batches: {
    create: vi.fn(),
    list: vi.fn(),
    get: vi.fn(),
    items: vi.fn(),
    listen: vi.fn(),
    start: vi.fn(),
    control: vi.fn(),
    retry: vi.fn(),
    report: vi.fn(),
  },
}));
vi.mock('../src/projects', () => ({ projects: { pick: vi.fn() } }));
vi.mock('../src/jobs', () => ({
  jobs: {
    profiles: vi.fn(),
    capabilities: vi.fn(),
    get: vi.fn(),
    evidence: vi.fn(),
  },
}));
vi.mock('../src/FileResults', () => ({
  default: ({ runId, back }: { runId: string; back: () => void }) => (
    <div>
      Selected {runId}
      <button onClick={back}>Back to batch</button>
    </div>
  ),
}));

const batch: Batch = {
  batch_id: 'batch',
  name: 'Delivery',
  status: 'COMPLETED',
  revision: 1,
  profile: { name: 'General', profile_key: 'general', version: '1' },
  ai_mode: 'OFF',
  counts: {
    total: 1000,
    processed: 1000,
    pass: 998,
    warn: 1,
    fail: 0,
    error: 1,
    cancelled: 0,
    processing: 0,
    pending: 0,
  },
  import_summary: {
    excluded: 2,
    duplicate_encounters: 0,
    directory_errors: 0,
    complete: true,
    partial: false,
  },
  current: null,
  overall_progress: 1,
  can_continue_pending: false,
  error_message: null,
  engine_session_id: 'session',
  progress_sequence: 1,
};
const project = {
  id: 'project',
  name: 'QC',
  project_file: 'C:/QC/project.sqlite',
  media_assets: [],
};
beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(batches.list).mockResolvedValue({ batches: [batch], total: 1 });
  vi.mocked(batches.get).mockResolvedValue(batch);
  vi.mocked(batches.items).mockImplementation((_id, filter, offset) =>
    Promise.resolve({
      total: filter === 'ERROR' ? 1 : 1000,
      revision: 1,
      items: Array.from(
        { length: filter === 'ERROR' ? 1 : 50 },
        (_, index) => ({
          item_id: String(index + offset),
          relative_path: `file-${String(index + offset)}.wav`,
          absolute_path: `D:/file-${String(index + offset)}.wav`,
          file_name: `file-${String(index + offset)}.wav`,
          status: 'COMPLETED',
          overall_result: 'PASS',
          analysis_run_id: `run-${String(index + offset)}`,
          error_message: null,
          exclusion_reason: null,
          duplicate_count: 0,
        }),
      ),
    }),
  );
  vi.mocked(batches.listen).mockResolvedValue(() => {});
  if (!batch.profile) throw new Error('Test profile is required');
  vi.mocked(jobs.profiles).mockResolvedValue({ profiles: [batch.profile] });
  vi.mocked(jobs.capabilities).mockResolvedValue({
    ai: { local_available: false },
  });
});

test('1000 files use bounded pages and fetch no unselected run details', async () => {
  render(<BatchView project={project} onActive={() => {}} />);
  fireEvent.click(await screen.findByRole('button', { name: 'Delivery' }));
  await screen.findByRole('button', { name: 'file-0.wav' });
  expect(screen.getAllByRole('row')).toHaveLength(51);
  expect(jobs.get).not.toHaveBeenCalled();
  expect(jobs.evidence).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('button', { name: 'Next files' }));
  await screen.findByRole('button', { name: 'file-50.wav' });
  expect(screen.queryByRole('button', { name: 'file-0.wav' })).toBeNull();
  expect(batches.items).toHaveBeenLastCalledWith('batch', 'ALL', 50);
  fireEvent.click(screen.getByRole('button', { name: 'file-50.wav' }));
  await screen.findByText('Selected run-50');
  fireEvent.click(screen.getByRole('button', { name: 'Back to batch' }));
  await screen.findByRole('button', { name: 'file-50.wav' });
  fireEvent.change(screen.getByLabelText('Filter files'), {
    target: { value: 'ERROR' },
  });
  await waitFor(() => {
    expect(batches.items).toHaveBeenLastCalledWith('batch', 'ERROR', 0);
  });
});

test('folder import defaults to nonrecursive and waits for Run QC Analysis', async () => {
  vi.mocked(projects.pick).mockResolvedValue('D:/Delivery');
  vi.mocked(batches.create).mockResolvedValue({ batch_id: 'batch' });
  vi.mocked(batches.get).mockResolvedValue({
    ...batch,
    status: 'READY',
    profile: null,
  });
  render(<BatchView project={project} onActive={() => {}} />);
  expect(
    screen.getByLabelText<HTMLInputElement>('Include subfolders').checked,
  ).toBe(false);
  fireEvent.click(screen.getByRole('button', { name: 'Select Folder' }));
  await waitFor(() => {
    expect(batches.create).toHaveBeenCalledWith(
      'project',
      'Delivery',
      'FOLDER',
      'D:/Delivery',
      false,
    );
  });
  expect(batches.start).not.toHaveBeenCalled();
  await screen.findByText('Batch: Delivery');
  fireEvent.change(screen.getByLabelText('QC profile'), {
    target: { value: 'general@1' },
  });
  fireEvent.click(screen.getByRole('button', { name: 'Run QC Analysis' }));
  await waitFor(() => {
    expect(batches.start).toHaveBeenCalledWith('batch', batch.profile, 'OFF');
  });
});

test('PAUSING is explicit and Stop remains available; interrupted pending work needs a click', async () => {
  vi.mocked(batches.get).mockResolvedValue({ ...batch, status: 'PAUSING' });
  render(<BatchView project={project} onActive={() => {}} />);
  fireEvent.click(await screen.findByRole('button', { name: 'Delivery' }));
  await screen.findByText('Pausing after current file...');
  expect(
    screen.getByRole('button', { name: 'Stop' }).hasAttribute('disabled'),
  ).toBe(false);
  fireEvent.click(screen.getByRole('button', { name: 'Stop' }));
  await waitFor(() => {
    expect(batches.control).toHaveBeenCalledWith('batch', 'stop');
  });
  vi.mocked(batches.get).mockResolvedValue({
    ...batch,
    status: 'INTERRUPTED',
    can_continue_pending: true,
  });
  const resume = await screen.findByRole('button', {
    name: 'Continue pending files',
  });
  expect(batches.control).not.toHaveBeenCalledWith('batch', 'resume');
  fireEvent.click(resume);
  await waitFor(() => {
    expect(batches.control).toHaveBeenCalledWith('batch', 'resume');
  });
});

test('progress does not reload unchanged pages and storage errors remain visible', async () => {
  render(<BatchView project={project} onActive={() => {}} />);
  fireEvent.click(await screen.findByRole('button', { name: 'Delivery' }));
  await screen.findByRole('button', { name: 'file-0.wav' });
  const notify = vi.mocked(batches.listen).mock.calls[0]?.[0];
  if (!notify) throw new Error('Missing event subscription');
  act(() => {
    notify('batch', 1);
  });
  await waitFor(() => {
    expect(batches.get).toHaveBeenCalledTimes(2);
  });
  expect(batches.items).toHaveBeenCalledTimes(1);
  act(() => {
    notify('batch', 0, 'Stale error');
  });
  expect(screen.queryByText('Stale error')).toBeNull();
  vi.mocked(batches.get).mockRejectedValue(new Error('Storage unavailable'));
  act(() => {
    notify('batch', 1, 'Storage unavailable');
  });
  await screen.findByRole('alert');
});
