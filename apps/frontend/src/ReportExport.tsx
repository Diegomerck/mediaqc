import { useState } from 'react';
import { jobs } from './jobs';
import { engineError } from './engine';

export default function ReportExport({ runId }: { runId: string }) {
  const [busy, setBusy] = useState(false);
  const [path, setPath] = useState('');
  const [error, setError] = useState('');
  async function exportReport(format: 'HTML' | 'PDF') {
    setBusy(true);
    setPath('');
    setError('');
    try {
      setPath((await jobs.report(runId, format)).absolute_path);
    } catch (failure: unknown) {
      const detail = engineError(failure);
      setError(`${detail.code}: ${detail.message}`);
    } finally {
      setBusy(false);
    }
  }
  return (
    <section aria-label="Report export">
      <h4>Export saved run</h4>
      <p>
        Includes current saved dispositions. Reports are saved in the project’s
        reports folder.
      </p>
      {(['HTML', 'PDF'] as const).map((format) => (
        <button
          key={format}
          disabled={busy}
          onClick={() => {
            void exportReport(format);
          }}
        >
          Export {format}
        </button>
      ))}
      {busy && <p role="status">Generating report…</p>}
      {path && (
        <p role="status">
          Report saved: <output>{path}</output>
        </p>
      )}
      {error && <p role="alert">{error}</p>}
    </section>
  );
}
