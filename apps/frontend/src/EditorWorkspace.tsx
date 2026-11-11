import { useEffect, useState, useMemo } from 'react';
import { getCurrentWebview } from '@tauri-apps/api/webview';
import { batches, type Batch, type BatchItem, type BatchPage } from './batches';
import { jobs, type Profile } from './jobs';
import { projects, type CompactProject } from './projects';
import { engineError, type EngineStatus } from './engine';
import { formatFileSize, formatDate, getMediaBadge, formatDuration } from './formatters';
import IssueDrawer from './IssueDrawer';

export interface EditorWorkspaceProps {
  engineStatus: EngineStatus | null;
  storagePreference: 'in_folder' | 'appdata';
  activeProject: CompactProject | null;
  onProjectChange: (project: CompactProject) => void;
  onActiveJobChange: (active: boolean) => void;
}

const activeStates = ['IMPORTING', 'RUNNING', 'PAUSING', 'STOPPING'];

export default function EditorWorkspace({
  engineStatus,
  storagePreference,
  activeProject,
  onProjectChange,
  onActiveJobChange,
}: EditorWorkspaceProps) {
  const [batchId, setBatchId] = useState<string>('');
  const [batch, setBatch] = useState<Batch | null>(null);
  const [itemsPage, setItemsPage] = useState<BatchPage>({
    items: [],
    total: 0,
    revision: 0,
  });
  const [selectedItemIds, setSelectedItemIds] = useState<Set<string>>(
    new Set(),
  );
  const [filter, setFilter] = useState<string>('ALL');
  const [offset, setOffset] = useState<number>(0);
  const [recursive, setRecursive] = useState<boolean>(true);
  const [profiles, setProfiles] = useState<Profile[]>([]);
  const [selectedProfileKey, setSelectedProfileKey] = useState<string>('');
  const [aiMode, setAiMode] = useState<'OFF' | 'LOCAL'>('OFF');
  const [localAiAvailable, setLocalAiAvailable] = useState<boolean>(false);
  const [busy, setBusy] = useState<boolean>(false);
  const [errorMessage, setErrorMessage] = useState<string>('');
  const [reportNotice, setReportNotice] = useState<string>('');
  const [inspectingItem, setInspectingItem] = useState<BatchItem | null>(null);
  const [isDragOver, setIsDragOver] = useState<boolean>(false);
  const [refreshTrigger, setRefreshTrigger] = useState<number>(0);

  const isActive = Boolean(batch && activeStates.includes(batch.status));

  useEffect(() => {
    onActiveJobChange(isActive || busy);
    return () => {
      onActiveJobChange(false);
    };
  }, [isActive, busy, onActiveJobChange]);

  // Load profiles and AI capabilities when engine is ready or in tests
  useEffect(() => {
    if (!engineStatus || engineStatus.phase !== 'ready') return;
    let current = true;
    jobs
      .profiles()
      .then((res) => {
        if (!current) return;
        setErrorMessage('');
        setProfiles(res.profiles);
        const first = res.profiles[0];
        if (first && !selectedProfileKey) {
          setSelectedProfileKey(`${first.profile_key}@${first.version}`);
        }
      })
      .catch((err: unknown) => {
        if (current) setErrorMessage(engineError(err).message);
      });

    jobs
      .capabilities()
      .then((cap) => {
        if (current) setLocalAiAvailable(cap.ai.local_available);
      })
      .catch(() => {});

    return () => {
      current = false;
    };
  }, [engineStatus, selectedProfileKey]);

  // Automatically clear startup notice when engine becomes ready
  useEffect(() => {
    if (engineStatus?.phase === 'ready') {
      if (
        errorMessage.includes('Start the local engine first') ||
        errorMessage.includes('ENGINE_NOT_RUNNING')
      ) {
        setErrorMessage('');
      }
    }
  }, [engineStatus?.phase, errorMessage]);

  // Listen to native Tauri OS drag-drop events (from Windows Explorer)
  useEffect(() => {
    let unlisten: (() => void) | undefined;
    try {
      void getCurrentWebview()
        .onDragDropEvent((event) => {
          if (event.payload.type === 'enter' || event.payload.type === 'over') {
            setIsDragOver(true);
          } else if (event.payload.type === 'leave') {
            setIsDragOver(false);
          } else if (event.payload.type === 'drop') {
            setIsDragOver(false);
            const first = event.payload.paths[0];
            if (first) {
              void handleScanFolder(first);
            }
          }
        })
        .then((fn) => {
          unlisten = fn;
        })
        .catch(() => {});
    } catch {
      // In non-Tauri or test environment, ignore
    }

    return () => {
      if (unlisten) unlisten();
    };
  }, []);

  // Poll & subscribe to batch updates
  useEffect(() => {
    if (!batchId) return;

    const lifetime = { disposed: false };
    const isDisposed = () => lifetime.disposed;
    let pending = false;
    let lastRevision = -1;

    async function refresh() {
      if (pending || isDisposed()) return;
      pending = true;
      try {
        const nextBatch = await batches.get(batchId);
        if (isDisposed()) return;
        setBatch(nextBatch);

        const rows = await batches.items(batchId, filter, offset);
        if (isDisposed()) return;
        setItemsPage(rows);
        lastRevision = rows.revision;

        setSelectedItemIds((prev) =>
          prev.size === 0 && rows.items.length > 0
            ? new Set(rows.items.map((it) => it.item_id))
            : prev,
        );
      } catch (err: unknown) {
        if (!isDisposed()) setErrorMessage(engineError(err).message);
      } finally {
        pending = false;
      }
    }

    void refresh();

    const subscription = batches.listen((id, revision, err) => {
      if (id !== batchId || lifetime.disposed) return;
      if (err) setErrorMessage(err);
      if (revision === undefined || revision !== lastRevision) {
        void refresh();
      }
    });

    const timer = setInterval(() => {
      void refresh();
    }, 500);

    return () => {
      lifetime.disposed = true;
      clearInterval(timer);
      void subscription
        .then((unlisten) => {
          if (typeof unlisten === 'function') unlisten();
        })
        .catch(() => {});
    };
  }, [batchId, filter, offset, refreshTrigger]);

  // Ensure an active project exists, or auto-create one
  async function ensureProject(folderPath: string): Promise<CompactProject> {
    if (activeProject) return activeProject;

    const folderName =
      folderPath.split(/[\\/]/).filter(Boolean).at(-1) || 'Workspace';

    if (storagePreference === 'in_folder') {
      const projectDir = `${folderPath}/.mediaqc`;
      const projectFile = `${projectDir}/project.sqlite`;
      try {
        const opened = await projects.open(projectFile);
        onProjectChange(opened);
        return opened;
      } catch {
        const created = await projects.create(projectDir, folderName);
        onProjectChange(created);
        return created;
      }
    } else {
      const baseDir = engineStatus?.log_path
        ? engineStatus.log_path.replace(/[\\/]logs[\\/]engine\.log$/, '')
        : 'C:/ProgramData/MediaQC';
      const cleanName = folderName.replace(/[^a-zA-Z0-9_-]/g, '_');
      const projectDir = `${baseDir}/projects/${cleanName}`;
      const projectFile = `${projectDir}/project.sqlite`;
      try {
        const opened = await projects.open(projectFile);
        onProjectChange(opened);
        return opened;
      } catch {
        const created = await projects.create(projectDir, folderName);
        onProjectChange(created);
        return created;
      }
    }
  }

  // Handle folder scan / import
  async function handleScanFolder(targetPath?: string) {
    setBusy(true);
    setErrorMessage('');
    setReportNotice('');
    try {
      const path = targetPath || (await projects.pick('media_directory'));
      if (!path) {
        setBusy(false);
        return;
      }

      const proj = await ensureProject(path);
      const folderName =
        path.split(/[\\/]/).filter(Boolean).at(-1) || 'Media Batch';

      const res = await batches.importDirectory(
        proj.id,
        path,
        recursive,
        folderName,
      );
      setBatchId(res.batch_id);
      setOffset(0);
      setFilter('ALL');
      setSelectedItemIds(new Set());
    } catch (err: unknown) {
      setErrorMessage(engineError(err).message);
    } finally {
      setBusy(false);
    }
  }

  // Handle single file scan
  async function handleScanFile() {
    setBusy(true);
    setErrorMessage('');
    setReportNotice('');
    try {
      const path = await projects.pick('media');
      if (!path) {
        setBusy(false);
        return;
      }

      const fileName =
        path.split(/[\\/]/).filter(Boolean).at(-1) || 'Media File';
      const folderPath = path.substring(
        0,
        Math.max(path.lastIndexOf('/'), path.lastIndexOf('\\')),
      );

      const proj = await ensureProject(folderPath);
      const res = await batches.create(proj.id, fileName, 'FILE', path, false);
      setBatchId(res.batch_id);
      setOffset(0);
      setFilter('ALL');
      setSelectedItemIds(new Set());
    } catch (err: unknown) {
      setErrorMessage(engineError(err).message);
    } finally {
      setBusy(false);
    }
  }

  const activeProfile = useMemo(() => {
    return (
      batch?.profile ??
      profiles.find(
        (p) => `${p.profile_key}@${p.version}` === selectedProfileKey,
      ) ??
      profiles[0]
    );
  }, [batch?.profile, profiles, selectedProfileKey]);

  async function handleStartAnalysis() {
    if (!batch || !activeProfile) return;
    setBusy(true);
    setErrorMessage('');
    try {
      await batches.start(
        batch.batch_id,
        activeProfile,
        batch.profile ? batch.ai_mode : aiMode,
      );
      setRefreshTrigger((k) => k + 1);
    } catch (err: unknown) {
      setErrorMessage(engineError(err).message);
    } finally {
      setBusy(false);
    }
  }

  async function handleControl(action: 'pause' | 'resume' | 'stop') {
    if (!batch) return;
    setBusy(true);
    try {
      await batches.control(batch.batch_id, action);
      setRefreshTrigger((k) => k + 1);
    } catch (err: unknown) {
      setErrorMessage(engineError(err).message);
    } finally {
      setBusy(false);
    }
  }

  async function handleExportReport(format: 'HTML' | 'PDF') {
    if (!batch) return;
    setBusy(true);
    try {
      const res = await batches.report(batch.batch_id, format);
      setReportNotice(`Report generated: ${res.absolute_path}`);
    } catch (err: unknown) {
      setErrorMessage(engineError(err).message);
    } finally {
      setBusy(false);
    }
  }

  // Toggle selection
  function toggleSelectItem(id: string) {
    setSelectedItemIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function toggleSelectAll() {
    if (selectedItemIds.size === itemsPage.items.length) {
      setSelectedItemIds(new Set());
    } else {
      setSelectedItemIds(new Set(itemsPage.items.map((it) => it.item_id)));
    }
  }

  // Determine row status badge
  function renderBadgeOnly(item: BatchItem) {
    if (item.status === 'ERROR') {
      return (
        <span
          className="badge badge-error"
          title={item.error_message ?? 'Error'}
        >
          ⚠️ Error
        </span>
      );
    }
    if (item.status === 'EXCLUDED') {
      return (
        <span
          className="badge badge-excluded"
          title={item.exclusion_reason ?? 'Excluded'}
        >
          ⚪ Excluded
        </span>
      );
    }
    if (item.status === 'RUNNING' || item.status === 'INSPECTING') {
      const isCur = batch?.current?.item_id === item.item_id;
      const progressVal = batch?.current?.file_progress;
      const pct =
        isCur && progressVal !== null && progressVal !== undefined
          ? `${String(Math.floor(progressVal * 100))}%`
          : '...';
      return (
        <span className="badge badge-analyzing">🟡 Analyzing ({pct})</span>
      );
    }
    if (batch?.status === 'PAUSED' && item.status === 'PENDING') {
      return <span className="badge badge-paused">⏸️ Paused</span>;
    }
    if (item.status === 'PENDING') {
      return <span className="badge badge-ready">⚪ Ready</span>;
    }
    if (item.status === 'COMPLETED') {
      if (item.overall_result === 'FAIL' || item.overall_result === 'WARN') {
        const failCount = item.issue_counts?.FAIL ?? 0;
        const warnCount = item.issue_counts?.WARN ?? 0;
        const count = failCount + warnCount || 1;
        return (
          <button
            className="badge badge-issues badge-btn"
            onClick={(e) => {
              e.stopPropagation();
              setInspectingItem(item);
            }}
            title="Click to inspect issues"
          >
            🔴 {String(count)} {count === 1 ? 'Issue' : 'Issues'} Detected
          </button>
        );
      }
      if (item.overall_result === 'PASS') {
        if (
          item.total_findings &&
          item.total_findings > 0 &&
          item.waived_findings === item.total_findings
        ) {
          return (
            <button
              className="badge badge-approved badge-btn"
              onClick={(e) => {
                e.stopPropagation();
                setInspectingItem(item);
              }}
              title="All issues reviewed and marked OK"
            >
              🔵 Approved
            </button>
          );
        }
        return <span className="badge badge-passed">🟢 Passed</span>;
      }
    }
    if (item.status === 'CANCELLED') {
      return <span className="badge badge-cancelled">⚪ Cancelled</span>;
    }
    return <span className="badge">{item.status}</span>;
  }

  function renderStatusBadge(item: BatchItem) {
    const badge = renderBadgeOnly(item);
    if (item.duration_seconds && item.duration_seconds > 0) {
      return (
        <span className="status-cell-wrapper">
          {badge}
          <span
            className="file-duration muted small"
            title={`Analysis completed in ${item.duration_seconds}s`}
          >
            ⏱️ {formatDuration(item.duration_seconds)}
          </span>
        </span>
      );
    }
    return badge;
  }

  const isAllSelected =
    itemsPage.items.length > 0 &&
    selectedItemIds.size === itemsPage.items.length;

  return (
    <div className="editor-workspace">
      {errorMessage && (
        <div className="error-box" role="status">
          <strong>Notice: </strong>
          {errorMessage}
        </div>
      )}

      {reportNotice && (
        <div className="notice-banner" role="status">
          ✓ {reportNotice}
        </div>
      )}

      {/* Drop Zone or Empty State */}
      {!batch ? (
        <div
          className={`dropzone ${isDragOver ? 'drag-over' : ''}`}
          onDragOver={(e) => {
            e.preventDefault();
            setIsDragOver(true);
          }}
          onDragLeave={() => {
            setIsDragOver(false);
          }}
          onDrop={(e) => {
            e.preventDefault();
            setIsDragOver(false);
            void handleScanFolder();
          }}
        >
          <div className="dropzone-content">
            <div className="dropzone-icon">📁</div>
            <h2>Drag & Drop Media Folder Here</h2>
            <p className="muted">
              Fast, deterministic offline QC for video & audio post-production.
            </p>
            <div className="dropzone-actions">
              <button
                className="primary-btn"
                disabled={busy}
                onClick={() => {
                  void handleScanFolder();
                }}
              >
                Browse Folder…
              </button>
              <button
                className="secondary"
                disabled={busy}
                onClick={() => {
                  void handleScanFile();
                }}
              >
                Browse File…
              </button>
            </div>
            <label className="checkbox-label" style={{ marginTop: 16 }}>
              <input
                type="checkbox"
                checked={recursive}
                onChange={(e) => {
                  setRecursive(e.target.checked);
                }}
              />
              Include subfolders (recursive scan)
            </label>
          </div>
        </div>
      ) : (
        /* Active Batch Workspace */
        <div className="batch-content-layout">
          <div className="batch-header-bar">
            <div className="batch-info">
              <h2>{batch.name}</h2>
              <span className="muted small">
                {String(batch.counts.total)} files · {String(batch.counts.pass)}{' '}
                passed · {String(batch.counts.fail + batch.counts.warn)} issues
                · {String(batch.counts.processed)} of{' '}
                {String(batch.counts.total)} processed
              </span>
            </div>

            <div className="batch-header-controls">
              <label className="select-label">
                Profile:
                <select
                  disabled={isActive || Boolean(batch.profile)}
                  value={
                    batch.profile
                      ? `${batch.profile.profile_key}@${batch.profile.version}`
                      : selectedProfileKey
                  }
                  onChange={(e) => {
                    setSelectedProfileKey(e.target.value);
                  }}
                >
                  {profiles.map((p) => (
                    <option
                      key={`${p.profile_key}@${p.version}`}
                      value={`${p.profile_key}@${p.version}`}
                    >
                      {p.name} v{p.version}
                    </option>
                  ))}
                </select>
              </label>

              <label className="select-label">
                AI Mode:
                <select
                  disabled={
                    isActive || !localAiAvailable || Boolean(batch.profile)
                  }
                  value={batch.profile ? batch.ai_mode : aiMode}
                  onChange={(e) => {
                    setAiMode(e.target.value as 'OFF' | 'LOCAL');
                  }}
                >
                  <option value="OFF">OFF</option>
                  <option value="LOCAL" disabled={!localAiAvailable}>
                    LOCAL
                  </option>
                </select>
              </label>

              <button
                className="secondary small-btn"
                disabled={isActive || busy}
                onClick={() => {
                  void handleScanFolder();
                }}
              >
                + Scan Another Folder…
              </button>
            </div>
          </div>

          {/* Filter pills */}
          <div className="filter-bar">
            {[
              { id: 'ALL', label: 'All Files' },
              { id: 'NEEDS_ATTENTION', label: 'Issues Detected' },
              { id: 'PASS', label: 'Passed' },
              { id: 'PROCESSING', label: 'Analyzing' },
              { id: 'PENDING', label: 'Ready' },
            ].map((f) => (
              <button
                key={f.id}
                className={`filter-pill ${filter === f.id ? 'active' : ''}`}
                onClick={() => {
                  setFilter(f.id);
                  setOffset(0);
                }}
              >
                {f.label}
              </button>
            ))}
          </div>

          {/* File Table */}
          <div className="table-container">
            <table className="editor-file-table" aria-label="Media QC files">
              <thead>
                <tr>
                  <th style={{ width: 40 }}>
                    <input
                      type="checkbox"
                      aria-label="Select all files"
                      checked={isAllSelected}
                      onChange={toggleSelectAll}
                    />
                  </th>
                  <th>File Name & Path</th>
                  <th style={{ width: 140 }}>Format / Codec</th>
                  <th style={{ width: 180 }}>Size & Date</th>
                  <th style={{ width: 170 }}>Status</th>
                </tr>
              </thead>
              <tbody>
                {itemsPage.items.length === 0 ? (
                  <tr>
                    <td colSpan={5} className="empty-table-cell">
                      No files match the selected filter.
                    </td>
                  </tr>
                ) : (
                  itemsPage.items.map((item) => {
                    const badge = getMediaBadge(item.file_name);
                    const isSelected = selectedItemIds.has(item.item_id);
                    const isInspected =
                      inspectingItem?.item_id === item.item_id;

                    const isClickable = Boolean(item.analysis_run_id);

                    return (
                      <tr
                        key={item.item_id}
                        className={`${isSelected ? 'row-selected' : ''} ${isInspected ? 'row-inspecting' : ''} ${isClickable ? 'clickable' : ''}`}
                        style={{ cursor: isClickable ? 'pointer' : undefined }}
                        onClick={() => {
                          if (item.analysis_run_id) {
                            setInspectingItem(item);
                          }
                        }}
                      >
                        <td
                          onClick={(e) => {
                            e.stopPropagation();
                          }}
                        >
                          <input
                            type="checkbox"
                            checked={isSelected}
                            onChange={() => {
                              toggleSelectItem(item.item_id);
                            }}
                            aria-label={`Select ${item.file_name}`}
                          />
                        </td>
                        <td>
                          <div className="file-name-cell">
                            <span className="file-name-title">
                              {item.file_name}
                            </span>
                            <span className="file-rel-path muted">
                              {item.relative_path}
                            </span>
                          </div>
                        </td>
                        <td>
                          <span
                            className={`media-badge ${badge.type.toLowerCase()}`}
                          >
                            {badge.badge}
                          </span>
                        </td>
                        <td>
                          <div className="file-meta-cell">
                            <span>
                              {formatFileSize(item.import_size_bytes)}
                            </span>
                            <span className="muted small">
                              {formatDate(item.import_modified_at)}
                            </span>
                          </div>
                        </td>
                        <td>{renderStatusBadge(item)}</td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>

          {/* Pagination Controls */}
          {itemsPage.total > 50 && (
            <div className="pagination-bar">
              <button
                disabled={offset === 0}
                onClick={() => {
                  setOffset((o) => Math.max(0, o - 50));
                }}
              >
                Previous 50
              </button>
              <span>
                {String(offset + 1)}–
                {String(Math.min(offset + 50, itemsPage.total))} of{' '}
                {String(itemsPage.total)} files
              </span>
              <button
                disabled={offset + 50 >= itemsPage.total}
                onClick={() => {
                  setOffset((o) => o + 50);
                }}
              >
                Next 50
              </button>
            </div>
          )}

          {/* Bottom Action Bar */}
          <footer className="editor-bottom-bar" aria-label="Editor action bar">
            <div className="action-bar-left">
              <span className="selection-count">
                {String(selectedItemIds.size)} of{' '}
                {String(itemsPage.items.length)} files selected
              </span>
            </div>

            <div className="action-bar-center">
              {isActive && (
                <div className="active-progress-box">
                  <div className="progress-labels">
                    <span>
                      Analyzing:{' '}
                      {String(Math.floor(batch.overall_progress * 100))}%
                    </span>
                    {batch.current && (
                      <span className="muted small">
                        Current: <strong>{batch.current.file_name}</strong>
                      </span>
                    )}
                  </div>
                  <progress
                    className="editor-progress-bar"
                    value={batch.overall_progress}
                    max={1}
                  />
                </div>
              )}
            </div>

            <div className="action-bar-right">
              {isActive ? (
                <div className="control-btn-group">
                  {batch.status === 'RUNNING' && (
                    <button
                      className="secondary"
                      disabled={busy}
                      onClick={() => {
                        void handleControl('pause');
                      }}
                    >
                      Pause
                    </button>
                  )}
                  {batch.status === 'PAUSED' && (
                    <button
                      className="primary-btn"
                      disabled={busy}
                      onClick={() => {
                        void handleControl('resume');
                      }}
                    >
                      Resume
                    </button>
                  )}
                  <button
                    className="danger-btn"
                    disabled={busy || batch.status === 'STOPPING'}
                    onClick={() => {
                      void handleControl('stop');
                    }}
                  >
                    Stop
                  </button>
                </div>
              ) : (
                <div className="idle-btn-group">
                  {['COMPLETED', 'PAUSED', 'STOPPED'].includes(
                    batch.status,
                  ) && (
                    <>
                      <button
                        className="secondary small-btn"
                        disabled={busy}
                        onClick={() => {
                          void handleExportReport('HTML');
                        }}
                      >
                        Export HTML
                      </button>
                      <button
                        className="secondary small-btn"
                        disabled={busy}
                        onClick={() => {
                          void handleExportReport('PDF');
                        }}
                      >
                        Export PDF
                      </button>
                    </>
                  )}
                  <button
                    className="primary-btn analyze-btn"
                    disabled={
                      busy ||
                      !activeProfile ||
                      selectedItemIds.size === 0 ||
                      batch.counts.total === 0 ||
                      (batch.status !== 'READY' &&
                        batch.status !== 'COMPLETED' &&
                        batch.status !== 'PAUSED')
                    }
                    onClick={() => {
                      void handleStartAnalysis();
                    }}
                  >
                    {batch.status === 'COMPLETED'
                      ? 'Re-Analyze Selected'
                      : `Analyze Selected (${String(selectedItemIds.size)})`}
                  </button>
                </div>
              )}
            </div>
          </footer>

          {/* Issue Details Drawer */}
          {inspectingItem && (
            <IssueDrawer
              item={inspectingItem}
              onClose={() => {
                setInspectingItem(null);
              }}
              onUpdated={() => {
                setRefreshTrigger((k) => k + 1);
              }}
            />
          )}
        </div>
      )}
    </div>
  );
}
