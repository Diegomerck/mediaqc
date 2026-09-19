import { useState } from 'react';
import { jobs, type Finding, type Run } from './jobs';
import { engineError } from './engine';

export default function AudioResults({ run }: { run: Run }) {
  const mediaLabel = run.detector_states.some(
    (detector) =>
      detector.detector_id.startsWith('video.') &&
      detector.status !== 'SKIPPED',
  )
    ? 'Audio / Video'
    : 'Audio';
  const [additional, setAdditional] = useState<Finding[]>([]);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const findings = [...(run.findings ?? []), ...additional];
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
  return (
    <section aria-label={`${mediaLabel} QC results`}>
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
        Run date: {run.started_at ?? 'Not started'}. Measurement evidence is
        saved in this project.
      </p>
      {findings.map((finding) => (
        <details key={finding.id}>
          <summary>
            {finding.severity} ·{' '}
            {finding.start_time_seconds === null
              ? 'Whole stream'
              : `${finding.start_time_seconds.toFixed(3)}–${(finding.end_time_seconds ?? finding.start_time_seconds).toFixed(3)} s`}{' '}
            · {finding.title}
          </summary>
          <p>{finding.description}</p>
          <p>
            {finding.detector_id} v{finding.detector_version} · Stream:{' '}
            {finding.stream_id} · {finding.disposition}
          </p>
          <p>
            Duration: {finding.duration_seconds ?? 'Whole stream'} · Confidence:{' '}
            {finding.confidence ?? 'Deterministic measurement'}
          </p>
          <h5>Measurements</h5>
          <pre>{JSON.stringify(finding.measurements, null, 2)}</pre>
          <h5>Profile thresholds</h5>
          <pre>{JSON.stringify(finding.threshold, null, 2)}</pre>
          <h5>Evidence in project</h5>
          {finding.evidence.map((evidence) => (
            <p key={evidence.id}>
              {evidence.evidence_type}: {evidence.relative_path}
            </p>
          ))}
          {finding.evidence.length === 0 && (
            <p role="alert">
              Evidence unavailable:{' '}
              {JSON.stringify(
                finding.metadata.evidence_error ??
                  'No evidence reference saved',
              )}
            </p>
          )}
        </details>
      ))}
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
      {error && <p role="alert">{error}</p>}
      {run.detector_states.map((detector) => (
        <details key={detector.id}>
          <summary>
            {detector.detector_id} measurements · {detector.status} · Findings:{' '}
            {detector.finding_count ?? 0} · Worst severity:{' '}
            {detector.worst_severity ?? 'None'}
          </summary>
          {detector.error_message && (
            <p role="alert">{detector.error_message}</p>
          )}
          <pre>{detector.metrics_json ?? 'No measurements available'}</pre>
        </details>
      ))}
    </section>
  );
}
