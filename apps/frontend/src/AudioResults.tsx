import { useState } from 'react';
import { jobs, type Finding, type Run } from './jobs';
import { engineError } from './engine';
import EvidenceView from './EvidenceView';
import ResultsTimeline from './ResultsTimeline';

function profileLabel(snapshot: string) {
  try {
    const profile = JSON.parse(snapshot) as { name?: string; version?: string };
    return `${profile.name ?? 'Unnamed profile'} v${profile.version ?? 'unknown'}`;
  } catch {
    return 'Profile snapshot unavailable';
  }
}

export default function AudioResults({ run: initial }: { run: Run }) {
  const [saved, setSaved] = useState<Run | null>(null);
  const run = saved ?? initial;
  const [additional, setAdditional] = useState<Finding[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [note, setNote] = useState('');
  const [filters, setFilters] = useState({
    severity: '',
    detector: '',
    disposition: '',
    kind: '',
    search: '',
  });
  const findings = [...(run.findings ?? []), ...additional];
  const selected =
    findings.find((item) => item.id === selectedId) ?? findings[0];
  const mediaLabel = run.detector_states.some(
    (detector) =>
      detector.detector_id.startsWith('video.') &&
      detector.status !== 'SKIPPED',
  )
    ? 'Audio / Video'
    : 'Audio';
  const visible = findings.filter(
    (item) =>
      (!filters.severity || item.severity === filters.severity) &&
      (!filters.detector || item.detector_id === filters.detector) &&
      (!filters.disposition || item.disposition === filters.disposition) &&
      item.detector_id.startsWith(filters.kind) &&
      `${item.title} ${item.description} ${item.detector_id}`
        .toLowerCase()
        .includes(filters.search.toLowerCase()),
  );
  function select(item: Finding) {
    setSelectedId(item.id);
    setNote('');
  }
  async function more() {
    setLoading(true);
    try {
      const page = await jobs.findings(run.id, findings.length);
      setAdditional((previous) => [...previous, ...page.findings]);
    } catch (failure: unknown) {
      setError(engineError(failure).message);
    } finally {
      setLoading(false);
    }
  }
  async function disposition(value: string) {
    if (!selected) return;
    setLoading(true);
    setError('');
    try {
      const updated = await jobs.disposition(selected.id, value, note);
      // Reflect the persisted finding even if the subsequent summary refresh fails.
      setSaved({
        ...run,
        findings: (run.findings ?? []).map((item) =>
          item.id === updated.id ? updated : item,
        ),
      });
      setAdditional((previous) =>
        previous.map((item) => (item.id === updated.id ? updated : item)),
      );
      setSaved(await jobs.get(run.id));
    } catch (failure: unknown) {
      const detail = engineError(failure);
      setError(
        `${detail.code}: ${detail.message}. Reload the run to verify saved state.`,
      );
    } finally {
      setLoading(false);
    }
  }
  return (
    <section aria-label={`${mediaLabel} QC results`}>
      <p>Profile: {profileLabel(run.qc_profile_snapshot_json)}</p>
      <h4>
        {mediaLabel} QC: {run.overall_result ?? 'Incomplete'}
      </h4>
      {run.summary && (
        <p>
          FAIL: {run.summary.counts.FAIL} · WARN: {run.summary.counts.WARN} ·
          INFO: {run.summary.counts.INFO}
        </p>
      )}
      <p>
        Dispositions:{' '}
        {['OPEN', 'CONFIRMED', 'FALSE_POSITIVE', 'IGNORED']
          .map(
            (value) =>
              `${value}: ${String(run.summary?.dispositions?.[value] ?? findings.filter((item) => item.disposition === value).length)}`,
          )
          .join(' · ')}
      </p>
      <p>
        Media: {run.media?.file_name ?? run.media_asset_id} · Run date:{' '}
        {run.started_at ?? 'Not started'}
      </p>
      <details>
        <summary>Run profile snapshot</summary>
        <pre>{run.qc_profile_snapshot_json}</pre>
      </details>
      <fieldset>
        <legend>
          Filter loaded findings ({findings.length} of{' '}
          {run.total ?? findings.length})
        </legend>
        {(['severity', 'detector', 'disposition', 'kind'] as const).map(
          (key) => (
            <label key={key}>
              {key}
              <select
                aria-label={`Filter ${key}`}
                value={filters[key]}
                onChange={(event) => {
                  setFilters({ ...filters, [key]: event.target.value });
                }}
              >
                <option value="">All</option>
                {(key === 'severity'
                  ? ['FAIL', 'WARN', 'INFO']
                  : key === 'disposition'
                    ? ['OPEN', 'CONFIRMED', 'FALSE_POSITIVE', 'IGNORED']
                    : key === 'kind'
                      ? ['audio.', 'video.']
                      : [...new Set(findings.map((item) => item.detector_id))]
                ).map((value) => (
                  <option key={value}>{value}</option>
                ))}
              </select>
            </label>
          ),
        )}
        <label>
          Search text
          <input
            value={filters.search}
            onChange={(event) => {
              setFilters({ ...filters, search: event.target.value });
            }}
          />
        </label>
      </fieldset>
      <ResultsTimeline
        findings={visible}
        duration={
          run.media?.duration_seconds ??
          run.progress.media_duration_seconds ??
          Math.max(1, ...findings.map((item) => item.end_time_seconds ?? 0))
        }
        selected={selected}
        select={select}
      />
      <div className="findings-table">
        <table>
          <caption>Findings — select an issue to inspect</caption>
          <thead>
            <tr>
              {[
                'Severity',
                'Time (s)',
                'Detector',
                'Title',
                'Duration (s)',
                'Confidence',
                'Disposition',
              ].map((label) => (
                <th key={label}>{label}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {visible.map((item) => (
              <tr key={item.id} aria-selected={selected?.id === item.id}>
                <td>{item.severity}</td>
                <td>{item.start_time_seconds?.toFixed(3) ?? 'Whole stream'}</td>
                <td>{item.detector_id}</td>
                <td>
                  <button
                    onClick={() => {
                      select(item);
                    }}
                  >
                    {item.title}
                  </button>
                </td>
                <td>{item.duration_seconds ?? 'Whole stream'}</td>
                <td>{item.confidence ?? 'Not applicable'}</td>
                <td>{item.disposition}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {visible.length === 0 && <p>No findings match these filters.</p>}
      {findings.length < (run.total ?? 0) && (
        <button
          disabled={loading}
          onClick={() => {
            void more();
          }}
        >
          Load more findings ({findings.length} of {run.total})
        </button>
      )}
      {selected && (
        <section aria-label="Issue inspector">
          <h4>
            {selected.severity} · {selected.title}
          </h4>
          <p>{selected.description}</p>
          <p>
            {selected.detector_id} v{selected.detector_version} · Stream:{' '}
            {selected.stream_id ?? 'Not applicable'} · {selected.disposition}
          </p>
          <p>
            Start: {selected.start_time_seconds ?? 'Whole stream'} · End:{' '}
            {selected.end_time_seconds ?? 'Whole stream'} · Duration:{' '}
            {selected.duration_seconds ?? 'Whole stream'} · Confidence:{' '}
            {selected.confidence ?? 'Not applicable'}
          </p>
          <h5>Measurements</h5>
          <pre>{JSON.stringify(selected.measurements, null, 2)}</pre>
          <h5>Profile thresholds</h5>
          <pre>{JSON.stringify(selected.threshold, null, 2)}</pre>
          <EvidenceView key={selected.id} finding={selected} />
          {run.ai_mode === 'LOCAL' && (
            <section aria-label="Optional local AI review">
              <h5>Local AI review — advisory</h5>
              {selected.ai_review?.status === 'COMPLETED' &&
              selected.ai_review.output ? (
                <>
                  <p>{selected.ai_review.output.summary}</p>
                  <p>
                    {selected.ai_review.output.classification} · Confidence:{' '}
                    {selected.ai_review.output.confidence} · Recommendation:{' '}
                    {selected.ai_review.output.recommended_action}
                  </p>
                  <p>
                    Model: {selected.ai_review.model_id}{' '}
                    {selected.ai_review.model_version} · Template:{' '}
                    {selected.ai_review.prompt_version} ·{' '}
                    {selected.ai_review.created_at}
                  </p>
                  <p>
                    Evidence references:{' '}
                    {selected.ai_review.output.evidence_refs.join(', ') ||
                      'Structured measurements only'}
                  </p>
                </>
              ) : (
                <p>
                  AI review unavailable (
                  {selected.ai_review?.error_code ??
                    'not reviewed or review budget exhausted'}
                  ). Deterministic QC remains authoritative. Check the local
                  model status or review the evidence manually.
                </p>
              )}
              <p>
                AI does not change measurements or disposition. Use the operator
                controls below to record your decision.
              </p>
            </section>
          )}
          <details>
            <summary>Disposition history</summary>
            {selected.feedback?.map((entry, index) => (
              <p key={index}>
                {entry.created_at}: {entry.previous_disposition} →{' '}
                {entry.new_disposition} · {entry.note ?? 'No note'}
              </p>
            ))}
          </details>
          <label>
            Disposition note
            <textarea
              maxLength={4000}
              value={note}
              onChange={(event) => {
                setNote(event.target.value);
              }}
            />
          </label>
          <div>
            {(
              [
                ['CONFIRMED', 'Confirm'],
                ['FALSE_POSITIVE', 'Mark False Positive'],
                ['IGNORED', 'Ignore'],
                ['OPEN', 'Reopen'],
              ] as const
            ).map(([value, label]) => (
              <button
                key={value}
                disabled={loading}
                onClick={() => {
                  void disposition(value);
                }}
              >
                {label}
              </button>
            ))}
          </div>
        </section>
      )}
      {error && <p role="alert">{error}</p>}
      {(['audio.', 'video.'] as const).map((kind) => (
        <section
          key={kind}
          aria-label={`${kind === 'audio.' ? 'Audio' : 'Video'} detector results`}
        >
          <h5>{kind === 'audio.' ? 'Audio' : 'Video'} detectors</h5>
          {run.detector_states
            .filter((detector) => detector.detector_id.startsWith(kind))
            .map((detector) => (
              <details key={detector.id}>
                <summary>
                  {detector.detector_id} measurements · {detector.status} ·
                  Findings: {detector.finding_count ?? 0} · Worst severity:{' '}
                  {detector.worst_severity ?? 'None'}
                </summary>
                {detector.error_message && (
                  <p role="alert">{detector.error_message}</p>
                )}
                <pre>
                  {detector.metrics_json ?? 'No measurements available'}
                </pre>
              </details>
            ))}
        </section>
      ))}
    </section>
  );
}
