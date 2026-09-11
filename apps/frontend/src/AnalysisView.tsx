import { useEffect, useState } from 'react';
import { jobs, type Profile, type Run } from './jobs';
import { engineError, type EngineError } from './engine';
import type { Project } from './projects';
import AudioResults from './AudioResults';

const terminal = (status: string) =>
  ['COMPLETED', 'FAILED', 'CANCELLED'].includes(status);

function profileLabel(snapshot: string): string {
  try {
    const value: unknown = JSON.parse(snapshot);
    if (
      typeof value === 'object' &&
      value !== null &&
      'name' in value &&
      'version' in value &&
      typeof value.name === 'string' &&
      typeof value.version === 'string'
    )
      return `${value.name} ${value.version}`;
  } catch {
    /* Preserve access to a historical run even if its profile is invalid. */
  }
  return 'Unavailable profile';
}

export default function AnalysisView({
  project,
  onActive,
}: {
  project: Project;
  onActive: (active: boolean) => void;
}) {
  const [profiles, setProfiles] = useState<Profile[]>([]);
  const [selectedProfile, setSelectedProfile] = useState('');
  const [asset, setAsset] = useState('');
  const [runId, setRunId] = useState('');
  const [run, setRun] = useState<Run | null>(null);
  const [history, setHistory] = useState(project.analysis_runs ?? []);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<EngineError | null>(null);
  const [clock, setClock] = useState(Date.now);
  const active = !!runId && (!run || !terminal(run.status));
  useEffect(() => {
    onActive(active);
    return () => {
      onActive(false);
    };
  }, [active, onActive]);
  useEffect(() => {
    let disposed = false;
    void jobs
      .profiles()
      .then((value) => {
        if (!disposed) setProfiles(value.profiles);
      })
      .catch((error: unknown) => {
        if (!disposed) setFailure(engineError(error));
      });
    return () => {
      disposed = true;
    };
  }, []);
  useEffect(() => {
    if (!runId) return;
    let disposed = false;
    let pending = false;
    const refresh = async () => {
      if (pending) return;
      pending = true;
      try {
        const value = await jobs.get(runId);
        if (!disposed) {
          setRun(value);
          setClock(Date.now());
          setHistory((previous) => [
            value,
            ...previous.filter((item) => item.id !== value.id),
          ]);
        }
      } catch (error: unknown) {
        if (!disposed) setFailure(engineError(error));
      } finally {
        pending = false;
      }
    };
    void refresh();
    const subscription = jobs.listen((event) => {
      if (event.data.analysis_run_id === runId) void refresh();
    });
    void subscription.catch((error: unknown) => {
      if (!disposed) setFailure(engineError(error));
    });
    // Poll persisted state as a fallback for events emitted before subscription.
    const timer = setInterval(() => {
      void refresh();
    }, 500);
    return () => {
      disposed = true;
      clearInterval(timer);
      void subscription
        .then((unlisten) => {
          unlisten();
        })
        .catch(() => {});
    };
  }, [runId]);
  async function action(kind: 'start' | 'cancel' | 'retry') {
    setBusy(true);
    setFailure(null);
    try {
      if (kind === 'cancel') await jobs.cancel(runId);
      else {
        const profile = profiles.find(
          (item) => `${item.profile_key}@${item.version}` === selectedProfile,
        );
        if (kind === 'start' && !profile) return;
        const next =
          kind === 'retry'
            ? await jobs.retry(runId)
            : profile
              ? await jobs.start(project.id, asset, profile)
              : null;
        if (!next) return;
        setRun(null);
        setRunId(next.analysis_run_id);
      }
    } catch (error: unknown) {
      setFailure(engineError(error));
    } finally {
      setBusy(false);
    }
  }
  const filename = project.media_assets.find(
    (item) => item.id === (run?.media_asset_id ?? asset),
  )?.file_name;
  const elapsed = run?.started_at
    ? Math.max(
        0,
        ((run.completed_at ? Date.parse(run.completed_at) : clock) -
          Date.parse(run.started_at)) /
          1000,
      )
    : 0;
  return (
    <section aria-labelledby="analysis-heading">
      <h3 id="analysis-heading">Analysis jobs</h3>
      <p>
        Run deterministic audio QC locally using the selected profile. Source
        media remains read-only.
      </p>
      <label>
        Analysis media{' '}
        <select
          value={asset}
          disabled={active || busy}
          onChange={(event) => {
            setAsset(event.target.value);
          }}
        >
          <option value="">Choose inspected media</option>
          {project.media_assets
            .filter(
              (item) =>
                item.inspection_status === 'COMPLETED' &&
                item.source_status === 'UNCHANGED',
            )
            .map((item) => (
              <option key={item.id} value={item.id}>
                {item.file_name}
              </option>
            ))}
        </select>
      </label>
      <label>
        QC profile{' '}
        <select
          value={selectedProfile}
          disabled={active || busy}
          onChange={(event) => {
            setSelectedProfile(event.target.value);
          }}
        >
          <option value="">Choose valid profile</option>
          {profiles.map((item) => (
            <option
              key={`${item.profile_key}@${item.version}`}
              value={`${item.profile_key}@${item.version}`}
            >
              {item.name} {item.version}
            </option>
          ))}
        </select>
      </label>
      <p>AI: OFF · Project: {project.name}</p>
      <div className="actions">
        <button
          disabled={active || busy || !asset || !selectedProfile}
          onClick={() => {
            void action('start');
          }}
        >
          Start analysis
        </button>
        <button
          disabled={!active || busy}
          onClick={() => {
            void action('cancel');
          }}
        >
          Cancel run
        </button>
        <button
          disabled={!run || active || busy}
          onClick={() => {
            void action('retry');
          }}
        >
          Retry run
        </button>
      </div>
      {failure && (
        <p role="alert">
          {failure.code}: {failure.message} Retry or reopen the project.
        </p>
      )}
      {run && (
        <div aria-live="polite">
          <h4>
            {filename} — {run.status}
          </h4>
          <progress
            aria-label="Analysis progress"
            max={1}
            value={run.progress.overall_progress}
          />
          <p>
            Stage: {run.progress.stage} · Detector:{' '}
            {run.progress.current_detector_id ?? 'None'} · Elapsed:{' '}
            {elapsed.toFixed(1)} seconds
          </p>
          <p>
            Media position: {run.progress.media_time_seconds ?? 'Unavailable'} /{' '}
            {run.progress.media_duration_seconds ?? 'Unavailable'} seconds
          </p>
          <p>{run.progress.message}</p>
          <p>Profile: {profileLabel(run.qc_profile_snapshot_json)}</p>
          {run.error_code && (
            <p role="alert">
              {run.error_code}: {run.error_message}
            </p>
          )}
          <ul aria-label="Detector checklist">
            {run.detector_states.map((item) => (
              <li key={item.id}>
                {item.detector_id}: {item.status}
              </li>
            ))}
          </ul>
        </div>
      )}
      {run && terminal(run.status) && <AudioResults key={run.id} run={run} />}
      <details>
        <summary>Previous runs</summary>
        {history.map((item) => (
          <p key={item.id}>
            <button
              disabled={active || busy}
              onClick={() => {
                setRun(null);
                setRunId(item.id);
              }}
            >
              {item.id}
            </button>{' '}
            {item.status} · Profile:{' '}
            {profileLabel(item.qc_profile_snapshot_json)}
          </p>
        ))}
      </details>
    </section>
  );
}
