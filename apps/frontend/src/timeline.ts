export function timelinePosition(time: number, start: number, span: number) {
  return Math.max(
    0,
    Math.min(100, ((time - start) / Math.max(span, 0.001)) * 100),
  );
}
