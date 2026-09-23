import { useEffect, useState } from 'react';
import ProjectView from './ProjectView';
import {
  engine,
  engineError,
  type EngineError,
  type EngineStatus,
} from './engine';

export default function App() {
  const [status, setStatus] = useState<EngineStatus | null>(null);
  const [error, setError] = useState<EngineError | null>(null);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState(
    'Start the local engine to check the desktop connection.',
  );

  useEffect(() => {
    let active = true;
    let timer: ReturnType<typeof setTimeout> | undefined;
    async function refresh() {
      try {
        const next = await engine.status();
        if (active) setStatus(next);
      } catch (value: unknown) {
        if (active) setError(engineError(value));
      }
      if (active)
        timer = setTimeout(() => {
          void refresh();
        }, 500);
    }
    void refresh();
    return () => {
      active = false;
      clearTimeout(timer);
    };
  }, []);

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
        setNotice('Engine is ready. Send a ping to verify the connection.');
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
      setStatus(await engine.status());
    } catch (value: unknown) {
      setError(engineError(value));
      setNotice('The engine operation failed.');
    } finally {
      setBusy(false);
    }
  }

  const failure = error ?? status?.error;
  const phase = status?.phase ?? 'connecting';
  const working = busy || phase === 'starting' || phase === 'stopping';
  const capabilities = status?.capabilities;

  return (
    <main className="shell">
      <header>
        <p className="eyebrow">LOCAL MEDIA QUALITY CONTROL</p>
        <h1>MediaQC</h1>
        <p className="muted">Offline batch quality control</p>
      </header>
      {phase === 'ready' && <ProjectView key={status?.pid} />}
      <details open={phase !== 'ready'}>
        <summary>Engine diagnostics</summary>
        <section
          className="panel"
          aria-labelledby="engine-heading"
          aria-busy={working}
        >
          <div className="row">
            <h2 id="engine-heading">Engine diagnostics</h2>
            <span className={`badge ${phase}`}>Engine: {phase}</span>
          </div>
          <p>
            Start the bundled local engine to open projects and inspect media.
          </p>
          <div className="actions">
            <button
              disabled={working || phase === 'ready' || phase === 'connecting'}
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
          <p role="status" className="notice">
            {phase === 'error'
              ? 'Engine unavailable. Restart it to continue connection checks.'
              : notice}
          </p>
          {failure && (
            <div role="alert" className="error-box">
              <h3>Engine connection failed</h3>
              <p>{failure.message}</p>
              <p>
                Connection checks cannot continue until the engine is available.
                Restart the engine; if the problem persists, relaunch or
                reinstall MediaQC.
              </p>
              <p>
                <strong>Code:</strong> {failure.code}
              </p>
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
              <dt>Schema contract version</dt>
              <dd>
                {capabilities?.schema_version ?? '—'}{' '}
                <span className="muted">(SQLite project schema)</span>
              </dd>
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
              <dt>Detectors / local AI</dt>
              <dd>
                {capabilities
                  ? `${String(capabilities.detectors.length)} detectors · AI optional`
                  : '—'}
              </dd>
            </div>
            <div>
              <dt>Engine process</dt>
              <dd>{status?.pid ?? '—'}</dd>
            </div>
            <div className="wide">
              <dt>Diagnostic log</dt>
              <dd>{status?.log_path ?? 'Connecting to desktop…'}</dd>
            </div>
          </dl>
        </section>
      </details>
      <footer>Offline desktop · Source media stays untouched</footer>
    </main>
  );
}
