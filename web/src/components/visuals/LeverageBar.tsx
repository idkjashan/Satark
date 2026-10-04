// Illustrative only. Two bars: a small real price move next to the much bigger leveraged move -
// labelled, not colour-coded, since this is the whole point being taught.
export function LeverageBar() {
  return (
    <svg viewBox="0 0 100 60" class="visual" role="img" aria-hidden="true">
      <line x1="8" y1="30" x2="92" y2="30" stroke="currentColor" stroke-opacity="0.3" />
      <rect x="22" y="25" width="16" height="10" fill="currentColor" fill-opacity="0.5" />
      <rect x="62" y="6" width="16" height="48" fill="currentColor" />
      <text x="30" y="46" font-size="9" text-anchor="middle" fill="currentColor">
        1x
      </text>
      <text x="70" y="58" font-size="9" text-anchor="middle" fill="currentColor">
        8x
      </text>
    </svg>
  );
}
