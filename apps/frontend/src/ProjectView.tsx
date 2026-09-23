import { useState } from 'react';
import { projects, type CompactProject } from './projects';
import { engineError, type EngineError } from './engine';
import BatchView from './BatchView';

interface Recent {
  path: string;
  opened: string;
}
function loadRecent(): Recent[] {
  try {
    const value: unknown = JSON.parse(
      localStorage.getItem('mediaqc.recent') ?? '[]',
    );
    if (!Array.isArray(value)) return [];
    return value.filter(
      (item: unknown): item is Recent =>
        typeof item === 'object' &&
        item !== null &&
        'path' in item &&
        typeof item.path === 'string' &&
        'opened' in item &&
        typeof item.opened === 'string',
    );
  } catch {
    return [];
  }
}

export default function ProjectView() {
  const [project, setProject] = useState<CompactProject | null>(null);
  const [name, setName] = useState('');
  const [directory, setDirectory] = useState('');
  const [busy, setBusy] = useState(false);
  const [activeRun, setActiveRun] = useState(false);
  const [failure, setFailure] = useState<EngineError | null>(null);
  const [recent, setRecent] = useState(loadRecent);

  function remember(next: CompactProject) {
    setProject(next);
    const updated = [
      { path: next.project_file, opened: new Date().toISOString() },
      ...recent.filter((item) => item.path !== next.project_file),
    ].slice(0, 10);
    setRecent(updated);
    try {
      localStorage.setItem('mediaqc.recent', JSON.stringify(updated));
    } catch {
      /* Project data remains authoritative in SQLite. */
    }
  }
  async function perform(
    action: 'create' | 'open' | 'refresh',
    savedPath?: string,
  ) {
    setBusy(true);
    setFailure(null);
    try {
      if (action === 'create') remember(await projects.create(directory, name));
      if (action === 'open') {
        const path = savedPath ?? (await projects.pick('project'));
        if (path) remember(await projects.open(path));
      }
      if (action === 'refresh') setProject(await projects.get());
    } catch (error: unknown) {
      setFailure(engineError(error));
    } finally {
      setBusy(false);
    }
  }
  async function chooseDirectory() {
    try {
      const path = await projects.pick('directory');
      if (path) setDirectory(path);
    } catch (error: unknown) {
      setFailure(engineError(error));
    }
  }
  return (
    <section
      className="panel"
      aria-labelledby="projects-heading"
      aria-busy={busy}
    >
      <h2 id="projects-heading">Projects</h2>
      <p>
        Each local project folder stores its database and inspection metadata.
        Source media stays at its original location.
      </p>
      <label>
        Project name{' '}
        <input
          value={name}
          onChange={(event) => {
            setName(event.target.value);
          }}
          disabled={busy || activeRun}
          maxLength={200}
        />
      </label>
      <div className="actions">
        <button
          disabled={busy || activeRun}
          onClick={() => {
            void chooseDirectory();
          }}
        >
          Choose project directory
        </button>
        <button
          disabled={busy || activeRun || !directory || !name.trim()}
          onClick={() => {
            void perform('create');
          }}
        >
          Create project
        </button>
        <button
          disabled={busy || activeRun}
          onClick={() => {
            void perform('open');
          }}
        >
          Open project
        </button>
      </div>
      {directory && <p className="path">{directory}</p>}
      {recent.length > 0 && (
        <details>
          <summary>Recent projects</summary>
          {recent.map((item) => (
            <p key={item.path}>
              <button
                disabled={busy || activeRun}
                onClick={() => {
                  void perform('open', item.path);
                }}
              >
                {item.path}
              </button>{' '}
              <small>Last opened: {item.opened}</small>
            </p>
          ))}
        </details>
      )}
      {busy && <p role="status">Working locally…</p>}
      {failure && (
        <div className="error-box" role="alert">
          <strong>Operation failed: {failure.code}</strong>
          <p>{failure.message}</p>
          <p>Your open project is retained. Choose another file or retry.</p>
        </div>
      )}
      {project && (
        <>
          <h3>{project.name}</h3>
          <p className="path">{project.project_file}</p>
          <BatchView
            key={project.id}
            project={project}
            onActive={setActiveRun}
          />
        </>
      )}
    </section>
  );
}
