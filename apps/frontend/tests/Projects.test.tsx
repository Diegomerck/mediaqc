import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, expect, test, vi } from 'vitest';
import ProjectView from '../src/ProjectView';
import { projects, type Project } from '../src/projects';

vi.mock('../src/projects', () => ({
  projects: {
    pick: vi.fn(),
    create: vi.fn(),
    open: vi.fn(),
    get: vi.fn(),
    inspect: vi.fn(),
  },
}));
const project: Project = {
  id: 'project-id',
  name: 'Episode',
  project_file: "C:/QC/音楽 & O'Brien/project.sqlite",
  media_assets: [],
};
beforeEach(() => {
  vi.resetAllMocks();
  localStorage.clear();
});

test('create project uses chosen directory and entered name', async () => {
  vi.mocked(projects.pick).mockResolvedValue('C:/QC/episode');
  vi.mocked(projects.create).mockResolvedValue(project);
  render(<ProjectView />);
  fireEvent.change(screen.getByLabelText('Project name'), {
    target: { value: 'Episode' },
  });
  fireEvent.click(
    screen.getByRole('button', { name: 'Choose project directory' }),
  );
  await screen.findByText('C:/QC/episode');
  fireEvent.click(screen.getByRole('button', { name: 'Create project' }));
  await screen.findByRole('heading', { name: 'Episode' });
  expect(projects.create).toHaveBeenCalledWith('C:/QC/episode', 'Episode');
});

test('open and inspect renders engine metadata without losing source path', async () => {
  vi.mocked(projects.pick)
    .mockResolvedValueOnce(project.project_file)
    .mockResolvedValueOnce('D:/audio.wav');
  vi.mocked(projects.open).mockResolvedValue(project);
  vi.mocked(projects.inspect).mockResolvedValue({});
  vi.mocked(projects.get).mockResolvedValue({
    ...project,
    media_assets: [
      {
        id: 'asset',
        absolute_path: 'D:/audio.wav',
        file_name: 'audio.wav',
        file_size_bytes: 192044,
        modified_at: '2026-09-10T00:00:00+00:00',
        duration_seconds: 1,
        container_format: 'wav',
        fast_fingerprint_sha256: 'fingerprint',
        inspection_status: 'COMPLETED',
        inspection_error_code: null,
        inspection_error_message: null,
        source_status: 'UNCHANGED',
        streams: [
          {
            stream_index: 0,
            stream_type: 'audio',
            codec_name: 'pcm_s16le',
            width: null,
            height: null,
            avg_frame_rate: null,
            real_frame_rate: null,
            sample_rate_hz: 48000,
            channel_count: 2,
            channel_layout: 'stereo',
          },
        ],
      },
    ],
  });
  render(<ProjectView />);
  fireEvent.click(screen.getByRole('button', { name: 'Open project' }));
  await screen.findByRole('heading', { name: 'Episode' });
  fireEvent.click(
    screen.getByRole('button', { name: 'Choose media and inspect' }),
  );
  await screen.findByText('audio.wav — COMPLETED');
  expect(screen.getByText('D:/audio.wav')).toBeDefined();
  expect(screen.getByText(/48000 Hz/)).toBeDefined();
  expect(projects.inspect).toHaveBeenCalledWith('project-id', 'D:/audio.wav');
});

test('failed inspection retains open project and exposes an actionable code', async () => {
  vi.mocked(projects.pick)
    .mockResolvedValueOnce(project.project_file)
    .mockResolvedValueOnce('D:/bad.wav');
  vi.mocked(projects.open).mockResolvedValue(project);
  vi.mocked(projects.get).mockResolvedValue(project);
  vi.mocked(projects.inspect).mockRejectedValue(
    Object.assign(new Error('Bad media'), { code: 'MEDIA_INSPECTION_FAILED' }),
  );
  render(<ProjectView />);
  fireEvent.click(screen.getByRole('button', { name: 'Open project' }));
  await screen.findByRole('heading', { name: 'Episode' });
  fireEvent.click(
    screen.getByRole('button', { name: 'Choose media and inspect' }),
  );
  expect((await screen.findByRole('alert')).textContent).toContain(
    'MEDIA_INSPECTION_FAILED',
  );
  expect(screen.getByRole('heading', { name: 'Episode' })).toBeDefined();
});

test('cancelled file chooser does not send an IPC request', async () => {
  vi.mocked(projects.pick).mockResolvedValue(null);
  render(<ProjectView />);
  fireEvent.click(screen.getByRole('button', { name: 'Open project' }));
  await vi.waitFor(() => {
    expect(projects.pick).toHaveBeenCalled();
  });
  expect(projects.open).not.toHaveBeenCalled();
});
