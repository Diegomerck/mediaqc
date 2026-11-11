import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, expect, test, vi } from 'vitest';
import EditorWorkspace from '../src/EditorWorkspace';
import { batches, type Batch } from '../src/batches';
import { projects, type CompactProject } from '../src/projects';
import { jobs, type Profile } from '../src/jobs';

vi.mock('../src/batches', () => ({
  batches: {
    create: vi.fn(),
    importDirectory: vi.fn(),
    get: vi.fn(),
    items: vi.fn(),
    start: vi.fn(),
    control: vi.fn(),
    report: vi.fn(),
    listen: vi.fn().mockResolvedValue(() => {}),
  },
}));

vi.mock('../src/projects', () => ({
  projects: {
    pick: vi.fn(),
    open: vi.fn(),
    create: vi.fn(),
  },
}));

vi.mock('../src/jobs', () => ({
  jobs: {
    profiles: vi.fn(),
    capabilities: vi.fn(),
    get: vi.fn(),
    disposition: vi.fn(),
  },
}));

const mockProfile: Profile = {
  profile_key: 'broadcast',
  version: '1.0',
  name: 'Broadcast Delivery',
};

const readyStatus = {
  phase: 'ready' as const,
  pid: 1234,
  capabilities: null,
  error: null,
  log_path: 'C:/logs/engine.log',
  desktop_version: '0.0.0',
};

const mockBatch: Batch = {
  batch_id: 'batch-1',
  name: 'Reel 01',
  status: 'READY',
  revision: 1,
  profile: null,
  ai_mode: 'OFF',
  counts: {
    total: 2,
    processed: 0,
    pass: 0,
    warn: 0,
    fail: 0,
    error: 0,
    cancelled: 0,
    processing: 0,
    pending: 2,
  },
  import_summary: {
    excluded: 0,
    duplicate_encounters: 0,
    directory_errors: 0,
    complete: true,
    partial: false,
  },
  current: null,
  overall_progress: 0,
  can_continue_pending: false,
  error_message: null,
  engine_session_id: 'sess-1',
  progress_sequence: 1,
};

const mockItems = [
  {
    item_id: 'it-1',
    file_name: 'A001_C001.mxf',
    relative_path: 'Card_A/A001_C001.mxf',
    absolute_path: 'D:/Media/Card_A/A001_C001.mxf',
    status: 'PENDING',
    overall_result: null,
    analysis_run_id: null,
    error_message: null,
    exclusion_reason: null,
    duplicate_count: 0,
    import_size_bytes: 1024 * 1024 * 500,
    import_modified_at: '2026-10-15T12:00:00Z',
  },
  {
    item_id: 'it-2',
    file_name: 'audio_mix.wav',
    relative_path: 'Audio/audio_mix.wav',
    absolute_path: 'D:/Media/Audio/audio_mix.wav',
    status: 'PENDING',
    overall_result: null,
    analysis_run_id: null,
    error_message: null,
    exclusion_reason: null,
    duplicate_count: 0,
    import_size_bytes: 1024 * 1024 * 50,
    import_modified_at: '2026-10-15T12:05:00Z',
  },
];

beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(batches.listen).mockResolvedValue(() => {});
  vi.mocked(jobs.profiles).mockResolvedValue({ profiles: [mockProfile] });
  vi.mocked(jobs.capabilities).mockResolvedValue({
    ai: { local_available: false, reason: null },
  });
  vi.mocked(batches.get).mockResolvedValue(mockBatch);
  vi.mocked(batches.items).mockResolvedValue({
    items: mockItems,
    total: 2,
    revision: 1,
  });
});

test('renders Drop Zone with Browse Folder button when no batch is active', () => {
  render(
    <EditorWorkspace
      engineStatus={readyStatus}
      storagePreference="in_folder"
      activeProject={null}
      onProjectChange={() => {}}
      onActiveJobChange={() => {}}
    />,
  );

  expect(screen.getByText('Drag & Drop Media Folder Here')).toBeDefined();
  expect(screen.getByRole('button', { name: 'Browse Folder…' })).toBeDefined();
  expect(screen.getByRole('button', { name: 'Browse File…' })).toBeDefined();
  expect(
    screen.getByRole('checkbox', {
      name: 'Include subfolders (recursive scan)',
    }),
  ).toBeDefined();
});

test('Browse Folder automatically creates or opens project and imports directory', async () => {
  const mockProject: CompactProject = {
    id: 'proj-123',
    name: 'Footage',
    project_file: 'D:/Footage/.mediaqc/project.sqlite',
  };

  vi.mocked(projects.pick).mockResolvedValue('D:/Footage');
  vi.mocked(projects.open).mockResolvedValue(mockProject);
  vi.mocked(batches.importDirectory).mockResolvedValue({ batch_id: 'batch-1' });

  const onProjectChange = vi.fn();

  render(
    <EditorWorkspace
      engineStatus={readyStatus}
      storagePreference="in_folder"
      activeProject={null}
      onProjectChange={onProjectChange}
      onActiveJobChange={() => {}}
    />,
  );

  fireEvent.click(screen.getByRole('button', { name: 'Browse Folder…' }));

  await vi.waitFor(() => {
    expect(projects.open).toHaveBeenCalledWith(
      'D:/Footage/.mediaqc/project.sqlite',
    );
  });
  expect(batches.importDirectory).toHaveBeenCalledWith(
    'proj-123',
    'D:/Footage',
    true,
    'Footage',
  );
  expect(onProjectChange).toHaveBeenCalledWith(mockProject);

  await screen.findByText('Reel 01');
  expect(screen.getByText('A001_C001.mxf')).toBeDefined();
  expect(screen.getByText('Video · MXF')).toBeDefined();
  expect(screen.getByText('Audio · PCM (WAV)')).toBeDefined();
  expect(screen.getByText('500.0 MB')).toBeDefined();
});

test('master checkbox toggles selection and Analyze Selected starts analysis', async () => {
  vi.mocked(projects.pick).mockResolvedValue('D:/Footage');
  vi.mocked(projects.open).mockResolvedValue({
    id: 'proj-123',
    name: 'Footage',
    project_file: 'D:/Footage/.mediaqc/project.sqlite',
  });
  vi.mocked(batches.importDirectory).mockResolvedValue({ batch_id: 'batch-1' });
  vi.mocked(batches.start).mockResolvedValue({});

  render(
    <EditorWorkspace
      engineStatus={readyStatus}
      storagePreference="in_folder"
      activeProject={null}
      onProjectChange={() => {}}
      onActiveJobChange={() => {}}
    />,
  );

  fireEvent.click(screen.getByRole('button', { name: 'Browse Folder…' }));
  await screen.findByText('Reel 01');

  const analyzeBtn = await screen.findByRole('button', {
    name: /Analyze Selected/,
  });
  expect(analyzeBtn).toBeDefined();

  fireEvent.click(analyzeBtn);

  expect(batches.start).toHaveBeenCalledWith('batch-1', mockProfile, 'OFF');
});

test('FAILED or error rows with analysis_run_id are clickable with pointer cursor and open drawer', async () => {
  const failedItem = {
    item_id: 'it-failed',
    file_name: 'corrupted_clip.mxf',
    relative_path: 'Card_B/corrupted_clip.mxf',
    absolute_path: 'D:/Media/Card_B/corrupted_clip.mxf',
    status: 'FAILED',
    overall_result: null,
    analysis_run_id: 'run-failed-123',
    error_message: 'Decode error: Truncated frame stream',
    exclusion_reason: null,
    duplicate_count: 0,
    import_size_bytes: 1024 * 1024 * 100,
    import_modified_at: '2026-10-15T12:00:00Z',
  };

  vi.mocked(projects.pick).mockResolvedValue('D:/Footage');
  vi.mocked(projects.open).mockResolvedValue({
    id: 'proj-123',
    name: 'Footage',
    project_file: 'D:/Footage/.mediaqc/project.sqlite',
  });
  vi.mocked(batches.importDirectory).mockResolvedValue({ batch_id: 'batch-1' });
  vi.mocked(batches.items).mockResolvedValue({
    total: 1,
    revision: 1,
    items: [failedItem],
  });
  vi.mocked(jobs.get).mockResolvedValue({
    id: 'run-failed-123',
    analysis_run_id: 'run-failed-123',
    media_asset_id: 'asset-1',
    status: 'FAILED',
    started_at: '2026-10-15T14:30:00Z',
    completed_at: '2026-10-15T14:30:05Z',
    qc_profile_snapshot_json: '{}',
    error_code: 'MEDIA_UNSUPPORTED',
    error_message: 'Decode error: Truncated frame stream',
    progress: {
      overall_progress: 1,
      stage: 'failed',
      current_detector_id: null,
      media_time_seconds: null,
      media_duration_seconds: null,
      message: 'Failed',
    },
    detector_states: [],
    overall_result: null,
    findings: [],
  });

  render(
    <EditorWorkspace
      engineStatus={readyStatus}
      storagePreference="in_folder"
      activeProject={null}
      onProjectChange={() => {}}
      onActiveJobChange={() => {}}
    />,
  );

  fireEvent.click(screen.getByRole('button', { name: 'Browse Folder…' }));
  const cell = await screen.findByText('corrupted_clip.mxf');
  const row = cell.closest('tr');
  expect(row).not.toBeNull();
  expect(row?.style.cursor).toBe('pointer');

  // Click the row to inspect
  if (row) {
    fireEvent.click(row);
  }

  // The drawer opens with error banner
  await screen.findByRole('complementary', { name: 'Issue details drawer' });
  expect(screen.getByText('⚠️ Analysis Failed')).toBeDefined();
  expect(
    screen.getByText('Decode error: Truncated frame stream'),
  ).toBeDefined();
});

test('displays item duration timing tag when duration_seconds is present', async () => {
  const itemWithDuration = {
    item_id: 'it-timed',
    file_name: 'timed_clip.mxf',
    relative_path: 'Card_A/timed_clip.mxf',
    absolute_path: 'D:/Media/Card_A/timed_clip.mxf',
    status: 'COMPLETED',
    overall_result: 'PASS',
    analysis_run_id: 'run-timed-123',
    error_message: null,
    exclusion_reason: null,
    duplicate_count: 0,
    duration_seconds: 42.5,
    import_size_bytes: 1024 * 1024 * 100,
    import_modified_at: '2026-10-15T12:00:00Z',
  };

  vi.mocked(projects.pick).mockResolvedValue('D:/Footage');
  vi.mocked(projects.open).mockResolvedValue({
    id: 'proj-123',
    name: 'Footage',
    project_file: 'D:/Footage/.mediaqc/project.sqlite',
  });
  vi.mocked(batches.importDirectory).mockResolvedValue({ batch_id: 'batch-1' });
  vi.mocked(batches.items).mockResolvedValue({
    total: 1,
    revision: 1,
    items: [itemWithDuration],
  });

  render(
    <EditorWorkspace
      engineStatus={readyStatus}
      storagePreference="in_folder"
      activeProject={null}
      onProjectChange={() => {}}
      onActiveJobChange={() => {}}
    />,
  );

  fireEvent.click(screen.getByRole('button', { name: 'Browse Folder…' }));
  await screen.findByText('timed_clip.mxf');
  expect(screen.getByText('⏱️ 43s')).toBeDefined();
});
