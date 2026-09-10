import { useState } from 'react';
import { projects, type Project } from './projects';
import { engineError, type EngineError } from './engine';

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
  const [project, setProject] = useState<Project | null>(null);
  const [name, setName] = useState('');
  const [directory, setDirectory] = useState('');
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<EngineError | null>(null);
  const [recent, setRecent] = useState(loadRecent);

  function remember(next: Project) {
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
    action: 'create' | 'open' | 'inspect' | 'refresh',
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
      if (action === 'inspect' && project) {
        const path = await projects.pick('media');
        if (path) {
          try {
            await projects.inspect(project.id, path);
          } finally {
            setProject(await projects.get());
          }
        }
      }
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
      <h2 id="projects-heading">Projects and media inspection</h2>
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
          disabled={busy}
          maxLength={200}
        />
      </label>
      <div className="actions">
        <button
          disabled={busy}
          onClick={() => {
            void chooseDirectory();
          }}
        >
          Choose project directory
        </button>
        <button
          disabled={busy || !directory || !name.trim()}
          onClick={() => {
            void perform('create');
          }}
        >
          Create project
        </button>
        <button
          disabled={busy}
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
                disabled={busy}
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
      {busy && (
        <p role="status">
          Working locally… Inspection may take up to 30 seconds.
        </p>
      )}
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
          <div className="actions">
            <button
              disabled={busy}
              onClick={() => {
                void perform('inspect');
              }}
            >
              Choose media and inspect
            </button>
            <button
              disabled={busy}
              onClick={() => {
                void perform('refresh');
              }}
            >
              Refresh project
            </button>
          </div>
          {project.media_assets.length === 0 && <p>No media inspected yet.</p>}
          {project.media_assets.map((asset) => (
            <article key={asset.id} className="media-card">
              <h3>
                {asset.file_name} — {asset.inspection_status}
              </h3>
              <p className="path">{asset.absolute_path}</p>
              {asset.source_status !== 'UNCHANGED' && (
                <p role="alert">
                  Source warning: {asset.source_status}. Locate the source and
                  inspect again.
                </p>
              )}
              {asset.inspection_error_code && (
                <p>
                  {asset.inspection_error_code}:{' '}
                  {asset.inspection_error_message}
                </p>
              )}
              <dl className="diagnostics">
                <div>
                  <dt>Size</dt>
                  <dd>{asset.file_size_bytes} bytes</dd>
                </div>
                <div>
                  <dt>Modified (UTC)</dt>
                  <dd>{asset.modified_at ?? 'Unavailable'}</dd>
                </div>
                <div>
                  <dt>Duration</dt>
                  <dd>{asset.duration_seconds ?? 'Unavailable'} seconds</dd>
                </div>
                <div>
                  <dt>Container</dt>
                  <dd>{asset.container_format ?? 'Unavailable'}</dd>
                </div>
                <div>
                  <dt>Stream count</dt>
                  <dd>{asset.streams.length}</dd>
                </div>
                <div className="wide">
                  <dt>Source fingerprint (SHA-256)</dt>
                  <dd>{asset.fast_fingerprint_sha256}</dd>
                </div>
              </dl>
              {asset.streams.map((stream) => (
                <p key={stream.stream_index}>
                  Stream {stream.stream_index}: {stream.stream_type}, codec{' '}
                  {stream.codec_name ?? 'unknown'}.
                  {stream.stream_type === 'video' && (
                    <>
                      {' '}
                      {stream.width} × {stream.height}; average frame rate{' '}
                      {stream.avg_frame_rate ?? 'unknown'}; real frame rate{' '}
                      {stream.real_frame_rate ?? 'unknown'}.
                    </>
                  )}
                  {stream.stream_type === 'audio' && (
                    <>
                      {' '}
                      {stream.sample_rate_hz ?? 'unknown'} Hz;{' '}
                      {stream.channel_count ?? 'unknown'} channels; layout{' '}
                      {stream.channel_layout ?? 'unknown'}.
                    </>
                  )}
                </p>
              ))}
            </article>
          ))}
        </>
      )}
    </section>
  );
}
