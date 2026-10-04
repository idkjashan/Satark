// Illustrative only - not real data. Decorative alongside lesson text, which carries the meaning.
export function CompoundingChart() {
  const points = Array.from({ length: 20 }, (_, i) => {
    const ratio = i / 19;
    const x = (ratio * 100).toFixed(1);
    const y = (100 - 95 * Math.pow(ratio, 2.2)).toFixed(1);
    return `${x},${y}`;
  }).join(' ');
  return (
    <svg viewBox="0 0 100 100" class="visual" role="img" aria-hidden="true">
      <polyline points={points} fill="none" stroke="currentColor" stroke-width="4" stroke-linecap="round" />
    </svg>
  );
}
