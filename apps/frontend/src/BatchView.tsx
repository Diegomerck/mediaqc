import { useEffect, useState } from 'react';
import {
  batches,
  type Batch,
  type BatchPage,
  type HistoricalRun,
} from './batches';
import { jobs, type Profile } from './jobs';
import { projects, type CompactProject } from './projects';
import { engineError } from './engine';
import FileResults from './FileResults';

const activeStates = ['IMPORTING', 'RUNNING', 'PAUSING', 'STOPPING'];
export default function BatchView({
  project,
  onActive,
}: {
  project: CompactProject;
  onActive: (value: boolean) => void;
}) {
  const [selected, setSelected] = useState('');
  const [batch, setBatch] = useState<Batch | null>(null);
  const [history, setHistory] = useState<Batch[]>([]);
  const [historyTotal, setHistoryTotal] = useState(0);
  const [historyOffset, setHistoryOffset] = useState(0);
  const [profiles, setProfiles] = useState<Profile[]>([]);
  const [profileKey, setProfileKey] = useState('');
  const [aiMode, setAiMode] = useState<'OFF' | 'LOCAL'>('OFF');
  const [localAvailable, setLocalAvailable] = useState(false);
  const [recursive, setRecursive] = useState(false);
  const [name, setName] = useState('');
  const [filter, setFilter] = useState('ALL');
  const [offset, setOffset] = useState(0);
  const [page, setPage] = useState<BatchPage>({
    items: [],
    total: 0,
    revision: 0,
  });
  const [runId, setRunId] = useState('');
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState('');
  const [reportPath, setReportPath] = useState('');
  const [refreshKey, setRefreshKey] = useState(0);
  const [oldRuns, setOldRuns] = useState<HistoricalRun[] | null>(null);
  const [runOffset, setRunOffset] = useState(0);
  const [runTotal, setRunTotal] = useState(0);
  const active = !!batch && activeStates.includes(batch.status);
  useEffect(() => {
    onActive(active || busy);
    return () => {
      onActive(false);
    };
  }, [active, busy, onActive]);
  useEffect(() => {
    let current = true;
    void jobs
      .profiles()
      .then((value) => {
        if (current) setProfiles(value.profiles);
      })
      .catch((error: unknown) => {
        if (current) setFailure(engineError(error).message);
      });
    void jobs
      .capabilities()
      .then((value) => {
        if (current) setLocalAvailable(value.ai.local_available);
      })
      .catch(() => {});
    return () => {
      current = false;
    };
  }, []);
  useEffect(() => {
    let current = true;
    void batches
      .list(project.id, historyOffset)
      .then((value) => {
        if (current) {
          setHistory(value.batches);
          setHistoryTotal(value.total);
        }
      })
      .catch((error: unknown) => {
        if (current) setFailure(engineError(error).message);
      });
    return () => {
      current = false;
    };
  }, [project.id, historyOffset, refreshKey]);
  useEffect(() => {
    if (!selected) return;
    const lifetime = { disposed: false };
    const isDisposed = () => lifetime.disposed;
    let pending = false;
    let lastRevision = -1;
    let lastSession = '';
    let lastSequence = -1;
    let dirty = true;
    let polling = true;
    let invalidation = 0;
    async function refresh() {
      if (pending || isDisposed()) return;
      pending = true;
      const requestVersion = invalidation;
      try {
        const value = await batches.get(selected);
        if (isDisposed()) return;
        if (
          value.engine_session_id === lastSession &&
          value.progress_sequence < lastSequence
        )
          return;
        lastSession = value.engine_session_id;
        lastSequence = value.progress_sequence;
        setBatch(value);
        polling = activeStates.includes(value.status);
        if (dirty || value.revision !== lastRevision) {
          const rows = await batches.items(selected, filter, offset);
          if (isDisposed()) return;
          setPage(rows);
          if (offset && offset >= rows.total)
            setOffset(Math.max(0, Math.floor((rows.total - 1) / 50) * 50));
          lastRevision = rows.revision;
          dirty = requestVersion !== invalidation;
        }
      } catch (error: unknown) {
        if (!isDisposed()) setFailure(engineError(error).message);
      } finally {
        pending = false;
      }
    }
    void refresh();
    const subscription = batches.listen((id, revision, error) => {
      if (id !== selected || isDisposed()) return;
      if (revision !== undefined && revision < lastRevision) return;
      if (revision !== lastRevision) {
        invalidation += 1;
        dirty = true;
      }
      if (error) setFailure(error);
      void refresh();
    });
    void subscription.catch(() => {});
    const timer = setInterval(() => {
      if (polling || dirty) void refresh();
    }, 500);
    return () => {
      lifetime.disposed = true;
      clearInterval(timer);
      void subscription
        .then((unlisten) => {
          unlisten();
        })
        .catch(() => {});
    };
  }, [selected, filter, offset, refreshKey]);
  async function perform(action: () => Promise<unknown>) {
    setBusy(true);
    setFailure('');
    try {
      await action();
      setRefreshKey((key) => key + 1);
    } catch (error: unknown) {
      setFailure(engineError(error).message);
    } finally {
      setBusy(false);
    }
  }
  function select(id: string) {
    setSelected(id);
    setBatch(null);
    setRunId('');
    setOffset(0);
    setFilter('ALL');
    setReportPath('');
  }
  async function choose(kind: 'FILE' | 'FOLDER') {
    const path = await projects.pick(
      kind === 'FILE' ? 'media' : 'media_directory',
    );
    if (!path) return;
    const label = path.split(/[\\/]/).filter(Boolean).at(-1) ?? 'Media batch';
    const created = await batches.create(
      project.id,
      name.trim() || label,
      kind,
      path,
      kind === 'FOLDER' && recursive,
    );
    select(created.batch_id);
  }
  const profile =
    batch?.profile ??
    profiles.find(
      (item) => `${item.profile_key}@${item.version}` === profileKey,
    );
  const canExport =
    batch &&
    ['PAUSED', 'COMPLETED', 'STOPPED', 'FAILED', 'INTERRUPTED'].includes(
      batch.status,
    );
  return (
    <section aria-label="Batch workflow">
      <p className="workflow-steps">
        1. Select Media / Folder → 2. Run QC Analysis → 3. Review Results
      </p>
      {failure && <p role="alert">{failure}</p>}
      {!runId && (
        <>
          <div className="actions">
            <label>
              Batch name{' '}
              <input
                value={name}
                maxLength={200}
                disabled={active || busy}
                onChange={(event) => {
                  setName(event.target.value);
                }}
                placeholder="Defaults to source name"
              />
            </label>
            <label>
              <input
                type="checkbox"
                checked={recursive}
                disabled={active || busy}
                onChange={(event) => {
                  setRecursive(event.target.checked);
                }}
              />{' '}
              Include subfolders
            </label>
            <button
              disabled={active || busy}
              onClick={() => {
                void perform(() => choose('FILE'));
              }}
            >
              Select Media
            </button>
            <button
              disabled={active || busy}
              onClick={() => {
                void perform(() => choose('FOLDER'));
              }}
            >
              Select Folder
            </button>
          </div>
          <p className="muted">
            Folder discovery: WAV, MP3, MP4, MXF. Source media stays in place.
          </p>
          <label>
            QC profile{' '}
            <select
              disabled={active || busy || !!batch?.profile}
              value={
                batch?.profile
                  ? `${batch.profile.profile_key}@${batch.profile.version}`
                  : profileKey
              }
              onChange={(event) => {
                setProfileKey(event.target.value);
              }}
            >
              <option value="">Choose a profile</option>
              {batch?.profile &&
                !profiles.some(
                  (item) =>
                    item.profile_key === batch.profile?.profile_key &&
                    item.version === batch.profile.version,
                ) && (
                  <option
                    value={`${batch.profile.profile_key}@${batch.profile.version}`}
                  >
                    {batch.profile.name} {batch.profile.version}
                  </option>
                )}
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
          <label>
            AI mode{' '}
            <select
              disabled={active || busy || !!batch?.profile}
              value={batch?.profile ? batch.ai_mode : aiMode}
              onChange={(event) => {
                setAiMode(event.target.value === 'LOCAL' ? 'LOCAL' : 'OFF');
              }}
            >
              <option>OFF</option>
              <option disabled={!localAvailable}>LOCAL</option>
            </select>
          </label>
          {!localAvailable && (
            <small>
              Local AI unavailable. Full deterministic QC is available with AI
              OFF.
            </small>
          )}
        </>
      )}
      {batch && (
        <section aria-label="Batch dashboard">
          <h3>Batch: {batch.name}</h3>
          <p role="status">
            {batch.status === 'PAUSING'
              ? 'Pausing after current file...'
              : batch.status === 'STOPPING'
                ? 'Stopping...'
                : batch.status === 'COMPLETED' && batch.counts.error
                  ? 'Completed with errors'
                  : batch.status}
          </p>
          <p>
            {batch.counts.processed} of {batch.counts.total} processed ·
            Overall: approximately {Math.floor(batch.overall_progress * 100)}%
            (file-weighted)
          </p>
          <progress
            aria-label="Overall batch progress"
            max={1}
            value={batch.overall_progress}
          />
          {batch.current && (
            <div>
              <p>
                Current: <strong>{batch.current.file_name}</strong>
              </p>
              <progress
                aria-label="Current file progress"
                max={1}
                value={batch.current.file_progress ?? undefined}
              />
              <span>
                {batch.current.file_progress === null
                  ? 'Inspecting…'
                  : `${String(Math.floor(batch.current.file_progress * 100))}%`}
              </span>
            </div>
          )}
          {batch.error_message && <p role="alert">{batch.error_message}</p>}
          {batch.import_summary.partial && (
            <p role="alert">
              Import incomplete: {batch.import_summary.directory_errors}{' '}
              directories could not be read.
            </p>
          )}
          {batch.status === 'READY' && !batch.counts.total && (
            <p>No supported media found.</p>
          )}
          {batch.status === 'INTERRUPTED' && !batch.import_summary.complete && (
            <p>
              Discovery was interrupted. Select the source again to reimport.
            </p>
          )}
          <div className="actions">
            <button
              disabled={
                busy ||
                batch.status !== 'READY' ||
                !profile ||
                !batch.counts.total
              }
              onClick={() => {
                if (profile)
                  void perform(() =>
                    batches.start(
                      batch.batch_id,
                      profile,
                      batch.profile ? batch.ai_mode : aiMode,
                    ),
                  );
              }}
            >
              Run QC Analysis
            </button>
            <button
              disabled={busy || batch.status !== 'RUNNING'}
              onClick={() => {
                void perform(() => batches.control(batch.batch_id, 'pause'));
              }}
            >
              Pause
            </button>
            <button
              disabled={
                busy ||
                !(batch.status === 'PAUSED' || batch.can_continue_pending)
              }
              onClick={() => {
                void perform(() => batches.control(batch.batch_id, 'resume'));
              }}
            >
              {batch.can_continue_pending ? 'Continue pending files' : 'Resume'}
            </button>
            <button
              disabled={
                busy ||
                ['COMPLETED', 'FAILED', 'STOPPED', 'STOPPING'].includes(
                  batch.status,
                )
              }
              onClick={() => {
                void perform(() => batches.control(batch.batch_id, 'stop'));
              }}
            >
              Stop
            </button>
          </div>
          <div className="batch-counts">
            {(
              [
                'pass',
                'warn',
                'fail',
                'error',
                'processing',
                'pending',
                'cancelled',
              ] as const
            ).map((key) => (
              <span key={key} className={`status-${key}`}>
                {key.toUpperCase()} <strong>{batch.counts[key]}</strong>
              </span>
            ))}
          </div>
          {!runId && (
            <>
              <label>
                Filter files{' '}
                <select
                  value={filter}
                  onChange={(event) => {
                    setFilter(event.target.value);
                    setOffset(0);
                  }}
                >
                  {[
                    'ALL',
                    'NEEDS_ATTENTION',
                    'FAIL',
                    'WARN',
                    'PASS',
                    'ERROR',
                    'PROCESSING',
                    'PENDING',
                    'CANCELLED',
                    'IMPORT_RESULTS',
                  ].map((value) => (
                    <option key={value} value={value}>
                      {value.replaceAll('_', ' ')}
                    </option>
                  ))}
                </select>
              </label>
              <p>
                {batch.import_summary.excluded} excluded ·{' '}
                {batch.import_summary.duplicate_encounters} duplicate paths
              </p>
              <table className="batch-table">
                <caption>Files — select a completed file to review</caption>
                <thead>
                  <tr>
                    <th>Status</th>
                    <th>File</th>
                    <th>Details</th>
                  </tr>
                </thead>
                <tbody>
                  {page.items.map((item) => (
                    <tr key={item.item_id}>
                      <td>{item.overall_result ?? item.status}</td>
                      <td>
                        <button
                          disabled={
                            !item.analysis_run_id ||
                            ['RUNNING', 'INSPECTING'].includes(item.status)
                          }
                          title={item.absolute_path}
                          onClick={() => {
                            if (item.analysis_run_id)
                              setRunId(item.analysis_run_id);
                          }}
                        >
                          {item.relative_path}
                        </button>
                      </td>
                      <td>
                        {item.error_message ?? item.exclusion_reason}
                        {item.duplicate_count > 0 &&
                          ` · ${String(item.duplicate_count)} duplicate paths`}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {!page.items.length && <p>No files match this filter.</p>}
              <div className="actions">
                <button
                  disabled={!offset}
                  onClick={() => {
                    setOffset((value) => Math.max(0, value - 50));
                  }}
                >
                  Previous files
                </button>
                <span>
                  {page.total ? offset + 1 : 0}–
                  {Math.min(offset + 50, page.total)} of {page.total}
                </span>
                <button
                  disabled={offset + 50 >= page.total}
                  onClick={() => {
                    setOffset((value) => value + 50);
                  }}
                >
                  Next files
                </button>
              </div>
              {canExport && (
                <div className="actions">
                  <button
                    disabled={
                      busy ||
                      !batch.profile ||
                      !(
                        batch.counts.error ||
                        batch.counts.cancelled ||
                        (batch.status === 'FAILED' && batch.counts.pending)
                      )
                    }
                    onClick={() => {
                      void perform(async () => {
                        select((await batches.retry(batch.batch_id)).batch_id);
                      });
                    }}
                  >
                    Retry unsuccessful files in new batch
                  </button>
                  {(['HTML', 'PDF'] as const).map((format) => (
                    <button
                      key={format}
                      disabled={busy}
                      onClick={() => {
                        void perform(async () => {
                          setReportPath(
                            (await batches.report(batch.batch_id, format))
                              .absolute_path,
                          );
                        });
                      }}
                    >
                      Export batch {format}
                    </button>
                  ))}
                </div>
              )}
              {reportPath && (
                <p role="status">Batch report saved: {reportPath}</p>
              )}
            </>
          )}
        </section>
      )}
      {runId && (
        <FileResults
          key={runId}
          runId={runId}
          busy={active}
          back={() => {
            setRunId('');
            setRefreshKey((key) => key + 1);
          }}
        />
      )}
      {!runId && (
        <details>
          <summary>Previous batches and analyses</summary>
          {history.map((item) => (
            <p key={item.batch_id}>
              <button
                disabled={active || busy}
                onClick={() => {
                  select(item.batch_id);
                }}
              >
                {item.name}
              </button>{' '}
              {item.status}
            </p>
          ))}
          <button
            disabled={active || !historyOffset}
            onClick={() => {
              setHistoryOffset((value) => value - 50);
            }}
          >
            Previous batches
          </button>
          <button
            disabled={active || historyOffset + 50 >= historyTotal}
            onClick={() => {
              setHistoryOffset((value) => value + 50);
            }}
          >
            Next batches
          </button>
          <button
            disabled={busy}
            onClick={() => {
              void perform(async () => {
                const value = await batches.history(project.id, runOffset);
                setOldRuns(value.runs);
                setRunTotal(value.total);
              });
            }}
          >
            Load analysis history
          </button>
          {oldRuns?.map((item) => (
            <p key={item.id}>
              <button
                onClick={() => {
                  setRunId(item.id);
                }}
              >
                {item.file_name}
              </button>{' '}
              {item.overall_result ?? item.status}
            </p>
          ))}
          <button
            disabled={!runOffset}
            onClick={() => {
              void perform(async () => {
                const next = runOffset - 50;
                const value = await batches.history(project.id, next);
                setOldRuns(value.runs);
                setRunTotal(value.total);
                setRunOffset(next);
              });
            }}
          >
            Previous analyses
          </button>
          <button
            disabled={runOffset + 50 >= runTotal}
            onClick={() => {
              void perform(async () => {
                const next = runOffset + 50;
                const value = await batches.history(project.id, next);
                setOldRuns(value.runs);
                setRunTotal(value.total);
                setRunOffset(next);
              });
            }}
          >
            Next analyses
          </button>
        </details>
      )}
    </section>
  );
}
