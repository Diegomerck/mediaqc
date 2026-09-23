import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, expect, test, vi } from 'vitest';
import ProjectView from '../src/ProjectView';
import { projects, type Project } from '../src/projects';
vi.mock('../src/BatchView', () => ({
  default: () => <p>Batch workflow ready</p>,
}));

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

test('opening a project shows compact batch workflow without inspecting media', async () => {
  vi.mocked(projects.pick).mockResolvedValue(project.project_file);
  vi.mocked(projects.open).mockResolvedValue(project);
  render(<ProjectView />);
  fireEvent.click(screen.getByRole('button', { name: 'Open project' }));
  await screen.findByText('Batch workflow ready');
  expect(screen.getAllByText(project.project_file)).toHaveLength(2);
  expect(projects.inspect).not.toHaveBeenCalled();
});

test('failed project opening retains the current project', async () => {
  vi.mocked(projects.pick).mockResolvedValue(project.project_file);
  vi.mocked(projects.open)
    .mockResolvedValueOnce(project)
    .mockRejectedValueOnce(new Error('Cannot open project'));
  render(<ProjectView />);
  fireEvent.click(screen.getByRole('button', { name: 'Open project' }));
  await screen.findByText('Batch workflow ready');
  fireEvent.click(screen.getByRole('button', { name: 'Open project' }));
  await screen.findByRole('alert');
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
