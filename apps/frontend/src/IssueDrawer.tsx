import { useEffect, useState } from 'react';
import type { BatchItem } from './batches';
import { jobs, type Finding } from './jobs';
import { engineError } from './engine';
import { formatTimeRange, humanFriendlyTitle, formatDuration } from './formatters';
import EvidenceView from './EvidenceView';

export interface IssueDrawerProps {
  item: BatchItem | null;
  onClose: () => void;
  onUpdated?: () => void;
}

export default function IssueDrawer({
  item,
  onClose,
  onUpdated,
}: IssueDrawerProps) {
  const [findings, setFindings] = useState<Finding[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [notes, setNotes] = useState<Record<string, string>>({});
  const [waivingId, setWaivingId] = useState<string | null>(null);
  const [userToggledAudio, setUserToggledAudio] = useState<boolean | null>(null);
  const [techOpen, setTechOpen] = useState<Record<string, boolean>>({});

  const runId = item?.analysis_run_id;

  useEffect(() => {
    if (!runId) return;

    const lifetime = { active: true };
    void jobs
      .get(runId)
      .then((data) => {
        if (!lifetime.active) return;
        const list = data.findings ?? [];
        setFindings(list);
        setLoading(false);
      })
      .catch((err: unknown) => {
        if (!lifetime.active) return;
        setError(engineError(err).message);
        setLoading(false);
      });

    return () => {
      lifetime.active = false;
    };
  }, [runId]);

  if (!item) return null;

  async function handleSetDisposition(finding: Finding, disposition: string) {
    setWaivingId(finding.id);
    setError('');
    const note =
      notes[finding.id]?.trim() ||
      (disposition === 'WAIVED' ? 'Approved by editor' : 'Reopened');
    try {
      const updated = await jobs.disposition(finding.id, disposition, note);
      setFindings((prev) =>
        prev.map((f) => (f.id === updated.id ? { ...f, ...updated } : f)),
      );
      onUpdated?.();
    } catch (err: unknown) {
      setError(engineError(err).message);
    } finally {
      setWaivingId(null);
    }
  }

  const isWaived = (f: Finding) =>
    ['WAIVED', 'FALSE_POSITIVE', 'IGNORED'].includes(f.disposition);

  const toggleTech = (id: string) => {
    setTechOpen((prev) => ({ ...prev, [id]: !prev[id] }));
  };

  const totalFindings = findings.length;
  const waivedCount = findings.filter(isWaived).length;
  const allWaived = totalFindings > 0 && waivedCount === totalFindings;
  const openCount = totalFindings - waivedCount;

  const videoFindings = findings.filter((f) =>
    f.detector_id.startsWith('video.'),
  );
  const audioFindings = findings.filter(
    (f) => !f.detector_id.startsWith('video.'),
  );

  const audioOpen =
    userToggledAudio !== null ? userToggledAudio : videoFindings.length === 0;

  const isFailedOrError =
    item.status === 'FAILED' ||
    item.status === 'ERROR' ||
    Boolean(item.error_message);

  function renderFindingCard(finding: Finding, isVideo: boolean) {
    const waived = isWaived(finding);
    const busyThis = waivingId === finding.id;
    const comparisons = finding.explanation?.comparisons;
    const showTech = Boolean(techOpen[finding.id]);

    return (
      <article
        key={finding.id}
        className={`finding-card ${waived ? 'waived' : finding.severity.toLowerCase()}`}
      >
        <div className="finding-card-header">
          <span className={`severity-tag ${finding.severity.toLowerCase()}`}>
            {finding.severity}
          </span>
          <span className="finding-title">
            {isVideo ? humanFriendlyTitle(finding) : finding.title}
          </span>
          <span className="finding-time">
            ⏱️{' '}
            {formatTimeRange(
              finding.start_time_seconds,
              finding.end_time_seconds,
            )}
          </span>
        </div>

        <p className="finding-desc">
          {finding.explanation?.summary ?? finding.description}
        </p>

        {isVideo && finding.evidence.length > 0 && (
          <div className="finding-evidence prominent-visual">
            <EvidenceView finding={finding} technical={false} />
          </div>
        )}

        <div className="finding-actions">
          {waived ? (
            <div className="waived-badge-row">
              <span className="waived-label">✓ Marked OK (False Alarm)</span>
              <button
                className="secondary small-btn"
                disabled={busyThis}
                onClick={() => {
                  void handleSetDisposition(finding, 'OPEN');
                }}
              >
                {busyThis ? 'Reopening…' : 'Reopen'}
              </button>
            </div>
          ) : (
            <div className="waive-controls">
              <input
                type="text"
                className="waive-note-input"
                placeholder="Optional note / rationale"
                value={notes[finding.id] ?? ''}
                onChange={(e) => {
                  setNotes({ ...notes, [finding.id]: e.target.value });
                }}
                disabled={busyThis}
              />
              <button
                className="waive-btn"
                disabled={busyThis}
                onClick={() => {
                  void handleSetDisposition(finding, 'WAIVED');
                }}
              >
                {busyThis ? 'Saving…' : 'Mark OK / False Alarm'}
              </button>
            </div>
          )}
        </div>

        <div className="technical-details-section">
          <button
            type="button"
            className="toggle-tech-btn text-btn"
            onClick={() => {
              toggleTech(finding.id);
            }}
            aria-expanded={showTech}
          >
            {showTech ? '▲ Hide technical details' : '▼ Show technical details'}
          </button>
          {showTech && (
            <div className="technical-details-content">
              {comparisons && comparisons.length > 0 && (
                <div className="finding-comparisons">
                  {comparisons.map((c, i) => (
                    <div key={i} className="comparison-row">
                      <span className="comp-label">{c.label}:</span>
                      <span className="comp-measured">
                        Measured:{' '}
                        <strong>
                          {c.measured !== null ? String(c.measured) : '—'}{' '}
                          {c.unit}
                        </strong>
                      </span>
                      {c.target !== null && (
                        <span className="comp-target">
                          (Target: {String(c.target)} {c.unit}
                          {c.difference_from_limit !== null &&
                            `, Diff: ${c.difference_from_limit > 0 ? '+' : ''}${c.difference_from_limit.toFixed(2)}`}
                          )
                        </span>
                      )}
                    </div>
                  ))}
                </div>
              )}

              {!isVideo && finding.evidence.length > 0 && (
                <div className="finding-evidence-tech">
                  <EvidenceView finding={finding} technical={false} />
                </div>
              )}

              {Object.keys(finding.measurements).length > 0 && (
                <div className="raw-measurements">
                  <span className="comp-label">Measurements:</span>
                  <pre className="measurements-json">
                    {JSON.stringify(finding.measurements, null, 2)}
                  </pre>
                </div>
              )}

              {Object.keys(finding.threshold).length > 0 && (
                <div className="raw-threshold">
                  <span className="comp-label">Threshold Gate:</span>
                  <pre className="measurements-json">
                    {JSON.stringify(finding.threshold, null, 2)}
                  </pre>
                </div>
              )}

              {finding.evidence.length > 0 && (
                <div className="raw-tech-artifacts">
                  <EvidenceView finding={finding} technical={true} />
                </div>
              )}
            </div>
          )}
        </div>
      </article>
    );
  }

  return (
    <aside className="issue-drawer" aria-label="Issue details drawer">
      <div className="drawer-header">
        <div className="drawer-title-area">
          <h3>{item.file_name}</h3>
          <p className="drawer-path">{item.relative_path}</p>
        </div>
        <button
          className="drawer-close"
          onClick={onClose}
          aria-label="Close drawer"
        >
          ✕
        </button>
      </div>

      {isFailedOrError && (
        <div className="drawer-error-banner" role="alert">
          <strong>⚠️ Analysis Failed</strong>
          <p>
            {item.error_message ||
              'The analysis process encountered an error while inspecting this file.'}
          </p>
        </div>
      )}

      <div className="drawer-summary-bar">
        {allWaived ? (
          <span className="badge badge-approved">
            🔵 Approved (All issues waived)
          </span>
        ) : openCount > 0 ? (
          <span className="badge badge-issues">
            🔴 {String(openCount)} {openCount === 1 ? 'Issue' : 'Issues'}{' '}
            Detected
          </span>
        ) : (
          <span className="badge badge-passed">🟢 Clean File (Passed)</span>
        )}
        {item.duration_seconds && item.duration_seconds > 0 ? (
          <span className="drawer-duration-pill">
            ⏱️ Analyzed in {formatDuration(item.duration_seconds)}
          </span>
        ) : null}
        <span className="muted">
          {String(totalFindings)} total findings · {String(waivedCount)} waived
        </span>
      </div>

      {error && (
        <div className="error-box" role="alert">
          <p>{error}</p>
        </div>
      )}

      {loading && <p role="status">Loading inspection details…</p>}

      {!loading && findings.length === 0 && !error && (
        <p className="muted">No issues found for this file.</p>
      )}

      {/* Video Section (Top & Prominent) */}
      {videoFindings.length > 0 && (
        <section
          className="drawer-section video-section"
          aria-label="Video Issues"
        >
          <h4 className="drawer-section-title">
            🎬 Video Issues ({String(videoFindings.length)})
          </h4>
          <div className="drawer-findings-list">
            {videoFindings.map((f) => renderFindingCard(f, true))}
          </div>
        </section>
      )}

      {/* Audio Section (Grouped & Collapsible) */}
      {audioFindings.length > 0 && (
        <details
          className="audio-checks-accordion"
          open={audioOpen}
          onToggle={(e) => {
            setUserToggledAudio(e.currentTarget.open);
          }}
        >
          <summary className="audio-accordion-summary">
            <span>
              🔊 Audio Checks ({String(audioFindings.length)}{' '}
              {audioFindings.length === 1 ? 'finding' : 'findings'})
            </span>
            <span className="accordion-chevron">{audioOpen ? '▲' : '▼'}</span>
          </summary>
          <div className="audio-accordion-content drawer-findings-list">
            {audioFindings.map((f) => renderFindingCard(f, false))}
          </div>
        </details>
      )}
    </aside>
  );
}
