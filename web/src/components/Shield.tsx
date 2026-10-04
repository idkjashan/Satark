// The Satark mark: a shield with a check on a brand-colour tile. Colours come from CSS tokens, so it
// follows light/dark mode (the tile stays the brand colour, the glyph stays white).
interface ShieldProps {
  size?: number;
  className?: string;
}

export function Shield({ size = 32, className }: ShieldProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" class={className} role="img" aria-label="Satark">
      <rect width="32" height="32" rx="9" fill="var(--brand)" />
      <path
        d="M16 6.5l7.5 2.8v5.6c0 4.6-3.1 7.9-7.5 9.6-4.4-1.7-7.5-5-7.5-9.6V9.3L16 6.5z"
        fill="#fff"
        fill-opacity="0.18"
        stroke="#fff"
        stroke-width="1.7"
        stroke-linejoin="round"
      />
      <path d="M12.6 15.6l2.6 2.6 4.4-4.9" fill="none" stroke="#fff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" />
    </svg>
  );
}
