import { useEffect, useState } from 'react';
import { jobs, type Run } from './jobs';
import { engineError } from './engine';
import AudioResults from './AudioResults';
import ReportExport from './ReportExport';

export default function FileResults({
  runId,
  busy,
  back,
}: {
  runId: string;
  busy: boolean;
  back: () => void;
}) {
  const [run, setRun] = useState<Run | null>(null);
  const [error, setError] = useState('');
  useEffect(() => {
    let current = true;
    void jobs
      .get(runId)
      .then((value) => {
        if (current) setRun(value);
      })
      .catch((failure: unknown) => {
        if (current) setError(engineError(failure).message);
      });
    return () => {
      current = false;
    };
  }, [runId]);
  return (
    <section aria-label="File results">
      <button onClick={back}>Back to batch</button>
      {error && <p role="alert">{error}</p>}
      {!run && !error && <p role="status">Loading file results…</p>}
      {run && (
        <>
          <h3>{run.media?.file_name ?? 'Selected file'}</h3>
          <p className="path">{run.media?.absolute_path}</p>
          {run.error_message && (
            <p role="alert">
              Analysis {run.status.toLowerCase()}: {run.error_message}
            </p>
          )}
          <AudioResults key={run.id} run={run} />
          {run.status === 'COMPLETED' && !busy && (
            <ReportExport runId={run.id} />
          )}
          {busy && (
            <p>Pause or finish the batch to export a detailed report.</p>
          )}
        </>
      )}
    </section>
  );
}
