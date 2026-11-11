import { useState } from 'react';
import type { EngineError, EngineStatus } from './engine';
import { engine, engineError } from './engine';
import { projects, type CompactProject } from './projects';

export interface SettingsModalProps {
  status: EngineStatus | null;
  isOpen: boolean;
  onClose: () => void;
  storagePreference: 'in_folder' | 'appdata';
  onStoragePreferenceChange: (pref: 'in_folder' | 'appdata') => void;
  activeProject: CompactProject | null;
  onProjectChange?: (project: CompactProject) => void;
}

export default function SettingsModal({
  status,
  isOpen,
  onClose,
  storagePreference,
  onStoragePreferenceChange,
  activeProject,
  onProjectChange,
}: SettingsModalProps) {
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState('');
  const [error, setError] = useState<EngineError | null>(null);
  const [diagOpen, setDiagOpen] = useState(false);

  const phase = status?.phase ?? 'connecting';
  const capabilities = status?.capabilities;
  const working = busy || phase === 'starting' || phase === 'stopping';

  async function perform(action: 'start' | 'ping' | 'stop') {
    setBusy(true);
    setError(null);
    setNotice(
      action === 'start'
        ? 'Starting engine and checking capabilities…'
        : action === 'stop'
          ? 'Shutting down engine…'
          : 'Waiting for system.ping…',
    );
    try {
      if (action === 'start') {
        await engine.start();
        setNotice('Engine is ready.');
      } else if (action === 'ping') {
        const result = await engine.ping();
        setNotice(`system.ping → ${JSON.stringify(result)}`);
      } else {
        const result = await engine.stop();
        setNotice(
          result.forced
            ? 'Engine stopped after the graceful shutdown deadline.'
            : 'Engine shut down cleanly.',
        );
      }
    } catch (value: unknown) {
      setError(engineError(value));
      setNotice('The engine operation failed.');
    } finally {
      setBusy(false);
    }
  }

  async function handleOpenExistingProject() {
    try {
      const path = await projects.pick('project');
      if (path) {
        const opened = await projects.open(path);
        onProjectChange?.(opened);
        onClose();
      }
    } catch (err: unknown) {
      setError(engineError(err));
    }
  }

  if (!isOpen) return null;

  return (
    <div
      className="modal-backdrop open"
      onClick={onClose}
      role="dialog"
      aria-modal="true"
      aria-labelledby="settings-title"
    >
      <div
        className="modal-content"
        onClick={(e) => {
          e.stopPropagation();
        }}
      >
        <div className="modal-header">
          <h2 id="settings-title">Settings & Diagnostics</h2>
          <button
            className="modal-close"
            onClick={onClose}
            aria-label="Close settings"
          >
            ✕
          </button>
        </div>

        <div className="modal-body">
          <section className="settings-section">
            <h3>Project Storage Preference</h3>
            <p className="muted">
              Choose where MediaQC stores project databases (`project.sqlite`)
              and analysis metadata:
            </p>
            <div className="radio-group">
              <label className="radio-card">
                <input
                  type="radio"
                  name="storage"
                  value="in_folder"
                  checked={storagePreference === 'in_folder'}
                  onChange={() => {
                    onStoragePreferenceChange('in_folder');
                  }}
                />
                <div>
                  <strong>In-Folder (`.mediaqc` inside scanned folder)</strong>
                  <p className="muted small">
                    Creates a `.mediaqc/` subfolder alongside the media. Highly
                    portable across edit suites and shared NAS volumes.
                  </p>
                </div>
              </label>

              <label className="radio-card">
                <input
                  type="radio"
                  name="storage"
                  value="appdata"
                  checked={storagePreference === 'appdata'}
                  onChange={() => {
                    onStoragePreferenceChange('appdata');
                  }}
                />
                <div>
                  <strong>Central AppData Workspace</strong>
                  <p className="muted small">
                    Stores all QC databases in your local user profile
                    (`AppData`). Leaves source directories completely untouched.
                  </p>
                </div>
              </label>
            </div>
          </section>

          <section className="settings-section">
            <h3>Active Workspace</h3>
            {activeProject ? (
              <p>
                Current project: <strong>{activeProject.name}</strong>
                <br />
                <span className="path small muted">
                  {activeProject.project_file}
                </span>
              </p>
            ) : (
              <p className="muted">
                No project currently active. Drop a folder to automatically
                create one.
              </p>
            )}
            <div className="actions">
              <button
                className="secondary"
                onClick={() => {
                  void handleOpenExistingProject();
                }}
              >
                Open Existing Project (.sqlite)…
              </button>
            </div>
          </section>

          <details
            className="diagnostics-accordion"
            open={diagOpen}
            onToggle={(e) => {
              setDiagOpen(e.currentTarget.open);
            }}
          >
            <summary>
              <strong>Technical Engine Diagnostics</strong>
              <span className={`badge ${phase}`} style={{ marginLeft: 8 }}>
                Engine: {phase}
              </span>
            </summary>

            <div className="diagnostics-panel">
              <div className="actions" style={{ marginBottom: 12 }}>
                <button
                  disabled={
                    working || phase === 'ready' || phase === 'connecting'
                  }
                  onClick={() => {
                    void perform('start');
                  }}
                >
                  {phase === 'error' ? 'Restart engine' : 'Start engine'}
                </button>
                <button
                  disabled={working || phase !== 'ready'}
                  onClick={() => {
                    void perform('ping');
                  }}
                >
                  Send system.ping
                </button>
                <button
                  className="secondary"
                  disabled={working || phase !== 'ready'}
                  onClick={() => {
                    void perform('stop');
                  }}
                >
                  Stop engine
                </button>
              </div>

              {notice && (
                <p role="status" className="notice">
                  {notice}
                </p>
              )}

              {error && (
                <div role="alert" className="error-box">
                  <strong>{error.code}</strong>
                  <p>{error.message}</p>
                </div>
              )}

              <dl className="diagnostics">
                <div>
                  <dt>Desktop version</dt>
                  <dd>{status?.desktop_version ?? '—'}</dd>
                </div>
                <div>
                  <dt>Engine version</dt>
                  <dd>{capabilities?.engine_version ?? '—'}</dd>
                </div>
                <div>
                  <dt>Protocol version</dt>
                  <dd>{capabilities?.protocol_version ?? '—'}</dd>
                </div>
                <div>
                  <dt>Schema version</dt>
                  <dd>{capabilities?.schema_version ?? '—'}</dd>
                </div>
                <div>
                  <dt>FFmpeg / ffprobe</dt>
                  <dd>
                    {capabilities
                      ? `${capabilities.ffmpeg.version ?? 'Unavailable'} / ${capabilities.ffprobe.version ?? 'Unavailable'}`
                      : '—'}
                  </dd>
                </div>
                <div>
                  <dt>Detectors</dt>
                  <dd>
                    {capabilities
                      ? `${String(capabilities.detectors.length)} detectors loaded`
                      : '—'}
                  </dd>
                </div>
                <div>
                  <dt>Process PID</dt>
                  <dd>{status?.pid ?? '—'}</dd>
                </div>
                <div className="wide">
                  <dt>Diagnostic log</dt>
                  <dd className="path small">{status?.log_path ?? '—'}</dd>
                </div>
              </dl>
            </div>
          </details>
        </div>

        <div className="modal-footer">
          <button onClick={onClose}>Done</button>
        </div>
      </div>
    </div>
  );
}
