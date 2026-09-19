import { useState } from 'react';
import type { Finding } from './jobs';

import { timelinePosition } from './timeline';

export default function ResultsTimeline({
  findings,
  duration,
  selected,
  select,
}: {
  findings: Finding[];
  duration: number;
  selected: Finding | undefined;
  select: (finding: Finding) => void;
}) {
  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState<{
    position: number;
    finding: string | undefined;
  } | null>(null);
  const span = Math.max(0.001, duration) / zoom;
  const start = Math.min(
    Math.max(0, duration - span),
    pan && pan.finding === selected?.id
      ? pan.position
      : Math.max(0, (selected?.start_time_seconds ?? 0) - span / 2),
  );
  // At most 80 keyboard targets regardless of the number of loaded findings.
  const groups = new Map<number, Finding[]>();
  for (const finding of findings) {
    const time = finding.start_time_seconds;
    if (
      time === null ||
      time > start + span ||
      (finding.end_time_seconds ?? time) < start
    )
      continue;
    const bucket = Math.min(
      79,
      Math.floor(timelinePosition(time, start, span) * 0.8),
    );
    const group = groups.get(bucket);
    if (group) group.push(finding);
    else groups.set(bucket, [finding]);
  }
  const [cluster, setCluster] = useState<Finding[]>([]);
  const [clusterPage, setClusterPage] = useState(0);
  return (
    <section aria-label="Finding timeline">
      <label>
        Timeline zoom{' '}
        <input
          type="range"
          min="1"
          max="100"
          value={zoom}
          onChange={(event) => {
            setZoom(Number(event.target.value));
            setPan(null);
          }}
        />
      </label>
      <label>
        Timeline pan{' '}
        <input
          type="range"
          min="0"
          max={Math.max(0, duration - span)}
          step="0.01"
          value={start}
          onChange={(event) => {
            setPan({
              position: Number(event.target.value),
              finding: selected?.id,
            });
          }}
        />
      </label>
      <p>
        {start.toFixed(3)} s — {(start + span).toFixed(3)} s. Whole-stream
        findings appear in the list.
      </p>
      <p>
        Selected position:{' '}
        {selected?.start_time_seconds?.toFixed(3) ?? 'Whole stream'} s
      </p>
      <svg
        className="timeline"
        viewBox="0 0 1000 30"
        role="img"
        aria-label="Finding ranges on media time axis"
      >
        <line x1="0" x2="1000" y1="25" y2="25" stroke="currentColor" />
        {[...groups].map(([bucket, items]) => (
          <rect
            key={bucket}
            x={bucket * 12.5}
            y="5"
            width={Math.max(
              4,
              timelinePosition(
                items[0]?.end_time_seconds ?? items[0]?.start_time_seconds ?? 0,
                start,
                span,
              ) *
                10 -
                bucket * 12.5,
            )}
            height="15"
            fill={
              items.some((item) => item.severity === 'FAIL')
                ? '#ff9999'
                : '#ffe49a'
            }
          />
        ))}
      </svg>
      <div className="timeline-targets">
        {[...groups].map(([bucket, items]) => (
          <button
            key={bucket}
            onClick={() => {
              if (items.length === 1 && items[0]) {
                select(items[0]);
                setPan(null);
              } else {
                setCluster(items);
                setClusterPage(0);
              }
            }}
          >
            {items[0]?.severity} · {items[0]?.start_time_seconds?.toFixed(3)} s
            {items.length > 1 ? ` · ${String(items.length)} findings` : ''}
          </button>
        ))}
      </div>
      {cluster.length > 0 && (
        <div aria-label="Timeline cluster">
          {cluster
            .slice(clusterPage * 50, (clusterPage + 1) * 50)
            .map((item) => (
              <button
                key={item.id}
                onClick={() => {
                  select(item);
                  setPan(null);
                  setCluster([]);
                }}
              >
                {item.severity}: {item.title}
              </button>
            ))}
          <button
            disabled={clusterPage === 0}
            onClick={() => {
              setClusterPage(clusterPage - 1);
            }}
          >
            Previous cluster page
          </button>
          <button
            disabled={(clusterPage + 1) * 50 >= cluster.length}
            onClick={() => {
              setClusterPage(clusterPage + 1);
            }}
          >
            Next cluster page
          </button>
          <button
            onClick={() => {
              setCluster([]);
            }}
          >
            Close cluster
          </button>
        </div>
      )}
    </section>
  );
}
