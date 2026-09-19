import { useEffect, useState } from 'react';
import { jobs, type Finding } from './jobs';
import { engineError } from './engine';

function Artifact({ item }: { item: Finding['evidence'][number] }) {
  const [result, setResult] =
    useState<Awaited<ReturnType<typeof jobs.evidence>>>();
  const [error, setError] = useState('');
  useEffect(() => {
    let current = true;
    void jobs
      .evidence(item.id)
      .then((value) => {
        if (current) setResult(value);
      })
      .catch((failure: unknown) => {
        if (current) {
          const detail = engineError(failure);
          setError(`${detail.code}: ${detail.message}`);
        }
      });
    return () => {
      current = false;
    };
  }, [item.id]);
  return (
    <figure>
      <figcaption>
        {item.evidence_type}: {item.relative_path}
      </figcaption>
      {error ? (
        <p role="alert">
          Evidence unavailable: {error}. Analysis measurements remain available;
          restore evidence or rerun analysis.
        </p>
      ) : !result ? (
        <p role="status">Loading evidence…</p>
      ) : (
        <>
          {result.data_url && (
            <>
              <img
                src={result.data_url}
                alt={item.evidence_type.replaceAll('_', ' ')}
                onError={() => {
                  setError(
                    'EVIDENCE_UNAVAILABLE: Image could not be displayed',
                  );
                }}
              />
              <p>
                Time ruler: {result.start_time_seconds?.toFixed(3)}–
                {result.end_time_seconds?.toFixed(3)} s
              </p>
              {item.evidence_type.startsWith('AUDIO_') && (
                <>
                  <svg
                    viewBox="0 0 640 30"
                    role="img"
                    aria-label="Highlighted finding region on evidence time ruler"
                  >
                    <line
                      x1="0"
                      x2="640"
                      y1="20"
                      y2="20"
                      stroke="currentColor"
                    />
                    <rect
                      x={Math.max(
                        0,
                        Math.min(
                          640,
                          ((Number(
                            result.metadata?.finding_start_seconds ??
                              result.start_time_seconds,
                          ) -
                            (result.start_time_seconds ?? 0)) /
                            Math.max(
                              0.001,
                              (result.end_time_seconds ?? 0) -
                                (result.start_time_seconds ?? 0),
                            )) *
                            640,
                        ),
                      )}
                      y="4"
                      width={Math.max(
                        2,
                        Math.min(
                          640,
                          ((Number(
                            result.metadata?.finding_end_seconds ??
                              result.end_time_seconds,
                          ) -
                            Number(
                              result.metadata?.finding_start_seconds ??
                                result.start_time_seconds,
                            )) /
                            Math.max(
                              0.001,
                              (result.end_time_seconds ?? 0) -
                                (result.start_time_seconds ?? 0),
                            )) *
                            640,
                        ),
                      )}
                      height="16"
                      fill="#ffe49a"
                    />
                  </svg>
                  <p>
                    Audio preview: mono mixdown, 16 kHz; up to 8 seconds of
                    context.
                  </p>
                </>
              )}
              {result.metadata?.finding_start_seconds != null && (
                <p>
                  Finding region:{' '}
                  {String(result.metadata.finding_start_seconds)}–
                  {String(result.metadata.finding_end_seconds)} s
                </p>
              )}
            </>
          )}
          {result.text && <pre>{result.text}</pre>}
          {!result.data_url && !result.text && (
            <p role="alert">Evidence unavailable: empty artifact response</p>
          )}
        </>
      )}
    </figure>
  );
}

export default function EvidenceView({ finding }: { finding: Finding }) {
  const expected = finding.detector_id.startsWith('video.')
    ? ['VIDEO_FRAME_BEFORE', 'VIDEO_FRAME', 'VIDEO_FRAME_AFTER']
    : ['AUDIO_WAVEFORM', 'AUDIO_SPECTROGRAM'];
  const missing = expected.filter(
    (kind) => !finding.evidence.some((item) => item.evidence_type === kind),
  );
  return (
    <section aria-label="Finding evidence">
      {missing.length > 0 && (
        <p role="alert">
          Evidence unavailable: {missing.join(', ')}.{' '}
          {JSON.stringify(
            finding.metadata.visual_evidence_errors ??
              finding.metadata.evidence_error ??
              'No visual evidence saved; rerun analysis',
          )}
          . Measurements remain available.
        </p>
      )}
      {finding.metadata.evidence_error != null && missing.length === 0 && (
        <p role="alert">
          Evidence generation error:{' '}
          {JSON.stringify(finding.metadata.evidence_error)}
        </p>
      )}
      <div className="evidence-grid">
        {finding.evidence.map((item) => (
          <Artifact key={item.id} item={item} />
        ))}
      </div>
    </section>
  );
}
