import { useEffect, useState, useRef } from 'react';
import {
  engine,
  engineError,
  type EngineError,
  type EngineStatus,
} from './engine';
import { type CompactProject } from './projects';
import EditorWorkspace from './EditorWorkspace';
import SettingsModal from './SettingsModal';

function loadStoragePreference(): 'in_folder' | 'appdata' {
  try {
    const val = localStorage.getItem('mediaqc.storage_preference');
    return val === 'appdata' ? 'appdata' : 'in_folder';
  } catch {
    return 'in_folder';
  }
}

export default function App() {
  const [status, setStatus] = useState<EngineStatus | null>(null);
  const [error, setError] = useState<EngineError | null>(null);
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);
  const [activeProject, setActiveProject] = useState<CompactProject | null>(
    null,
  );
  const [, setHasActiveJob] = useState(false);
  const [storagePreference, setStoragePreference] = useState<
    'in_folder' | 'appdata'
  >(loadStoragePreference);

  const autoStartTriggered = useRef(false);

  // Monitor engine status and auto-start on mount if stopped
  useEffect(() => {
    const lifetime = { active: true };
    const isComponentActive = () => lifetime.active;
    let timer: ReturnType<typeof setTimeout> | undefined;

    async function refresh() {
      try {
        const next = await engine.status();
        if (!isComponentActive()) return;
        setStatus(next);

        if (next.phase === 'ready') {
          setError(null);
        }

        // Auto-start engine on initial mount if stopped
        if (!autoStartTriggered.current && next.phase === 'stopped') {
          autoStartTriggered.current = true;
          try {
            await engine.start();
            if (isComponentActive()) {
              const started = await engine.status();
              setStatus(started);
              if (started.phase === 'ready') {
                setError(null);
              }
            }
          } catch (startErr: unknown) {
            if (isComponentActive()) setError(engineError(startErr));
          }
        }
      } catch (value: unknown) {
        if (isComponentActive()) setError(engineError(value));
      }

      if (isComponentActive()) {
        timer = setTimeout(() => {
          void refresh();
        }, 500);
      }
    }

    void refresh();

    return () => {
      lifetime.active = false;
      clearTimeout(timer);
    };
  }, []);

  function handleStoragePreferenceChange(pref: 'in_folder' | 'appdata') {
    setStoragePreference(pref);
    try {
      localStorage.setItem('mediaqc.storage_preference', pref);
    } catch {
      // Storage errors are non-fatal
    }
  }

  async function handleRestartEngine() {
    setError(null);
    try {
      await engine.start();
      const next = await engine.status();
      setStatus(next);
      if (next.phase === 'ready') {
        setError(null);
      }
    } catch (err: unknown) {
      setError(engineError(err));
    }
  }

  const failure = error ?? status?.error;
  const phase = status?.phase ?? (error ? 'error' : 'connecting');

  const isPhaseBlocked =
    phase === 'starting' ||
    phase === 'connecting' ||
    phase === 'ready';

  const isEligiblePhase =
    phase === 'error' || (phase === 'stopped' && autoStartTriggered.current);

  const isEngineNotRunningWhenReady =
    failure?.code === 'ENGINE_NOT_RUNNING' && (phase as string) === 'ready';

  const showFailure = Boolean(
    failure && !isPhaseBlocked && isEligiblePhase && !isEngineNotRunningWhenReady,
  );

  return (
    <main className="shell">
      {/* Clean Editor Top Bar */}
      <header className="top-bar">
        <div className="top-bar-left">
          <div className="brand-group">
            <h1>MediaQC</h1>
            <span className="brand-tagline muted">Offline Quality Control</span>
          </div>
        </div>

        <div className="top-bar-right">
          {activeProject && (
            <span className="workspace-pill" title={activeProject.project_file}>
              📁 {activeProject.name}
            </span>
          )}

          <div
            className={`engine-status-pill ${phase}`}
            title={
              status?.log_path ? `Log: ${status.log_path}` : 'Engine status'
            }
          >
            <span className={`status-dot ${phase}`} />
            <span className="status-label">
              {phase === 'ready'
                ? 'Ready'
                : phase === 'starting'
                  ? 'Starting…'
                  : phase === 'error'
                    ? 'Error'
                    : 'Offline'}
            </span>
          </div>

          <button
            className="secondary settings-btn"
            onClick={() => {
              setIsSettingsOpen(true);
            }}
            aria-label="Settings"
          >
            ⚙️ Settings
          </button>
        </div>
      </header>

      {/* Startup / Fatal Error Alert */}
      {showFailure && failure && (
        <div role="alert" className="error-box" style={{ margin: '16px 0' }}>
          <div className="row">
            <div>
              <h3>Engine connection notice</h3>
              <p>{failure.message}</p>
              <p className="muted small">
                Code: <strong>{failure.code}</strong>
              </p>
            </div>
            <button
              onClick={() => {
                void handleRestartEngine();
              }}
            >
              Retry startup
            </button>
          </div>
        </div>
      )}

      {/* Main Single-Window Editor Workspace */}
      <section className="main-content-area" aria-label="Editor workspace">
        <EditorWorkspace
          engineStatus={status}
          storagePreference={storagePreference}
          activeProject={activeProject}
          onProjectChange={setActiveProject}
          onActiveJobChange={setHasActiveJob}
        />
      </section>

      {/* Settings & Engine Diagnostics Modal */}
      <SettingsModal
        status={status}
        isOpen={isSettingsOpen}
        onClose={() => {
          setIsSettingsOpen(false);
        }}
        storagePreference={storagePreference}
        onStoragePreferenceChange={handleStoragePreferenceChange}
        activeProject={activeProject}
        onProjectChange={setActiveProject}
      />

      <footer className="shell-footer muted small">
        MediaQC · Deterministic Offline Video Post-Production QC · Source media
        stays untouched
      </footer>
    </main>
  );
}
