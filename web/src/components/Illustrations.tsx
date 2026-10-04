// Small original inline-SVG illustrations (flat style, a few hundred bytes each, no raster images),
// drawn for Satark in the brand palette so they work offline and on slow networks. They are purely
// decorative (aria-hidden). Colours come from CSS tokens so they follow dark mode.
interface Art {
  size?: number;
  class?: string;
}

/** Hero: a phone showing a chat with a flagged message, a shield-check badge and a rupee coin. */
export function HeroArt({ size = 300, class: cls }: Art) {
  return (
    <svg width={size} height={size * 0.9} viewBox="0 0 300 270" class={cls} aria-hidden="true" focusable="false">
      <circle cx="150" cy="135" r="118" fill="#fff" fill-opacity="0.12" />
      <circle cx="150" cy="135" r="84" fill="#fff" fill-opacity="0.12" />
      <rect x="92" y="24" width="116" height="214" rx="20" fill="#fff" />
      <rect x="100" y="40" width="100" height="182" rx="10" fill="#e6f3f6" />
      <rect x="132" y="29" width="36" height="5" rx="2.5" fill="#d0d5dd" />
      <rect x="108" y="52" width="62" height="22" rx="9" fill="#fff" />
      <rect x="116" y="60" width="38" height="5" rx="2.5" fill="#d0d5dd" />
      <rect x="120" y="84" width="72" height="34" rx="9" fill="#fef3f2" stroke="#d92d20" stroke-width="2" />
      <rect x="128" y="94" width="46" height="5" rx="2.5" fill="#fda29b" />
      <rect x="128" y="105" width="30" height="5" rx="2.5" fill="#fda29b" />
      <path d="M190 82l-8 14h16z" fill="#d92d20" />
      <rect x="108" y="128" width="62" height="22" rx="9" fill="#fff" />
      <rect x="116" y="136" width="30" height="5" rx="2.5" fill="#d0d5dd" />
      <rect x="120" y="160" width="72" height="26" rx="9" fill="#0a6577" />
      <rect x="128" y="170" width="40" height="5" rx="2.5" fill="#fff" fill-opacity="0.8" />
      <path d="M222 138l40 15v30c0 26-17 43-40 51-23-8-40-25-40-51v-30z" fill="#067647" stroke="#fff" stroke-width="5" stroke-linejoin="round" />
      <path d="M203 188l13 13 24-28" fill="none" stroke="#fff" stroke-width="9" stroke-linecap="round" stroke-linejoin="round" />
      <circle cx="58" cy="82" r="22" fill="#fec84b" />
      <circle cx="58" cy="82" r="16" fill="none" stroke="#b54708" stroke-width="2.5" />
      <path d="M51 76h14M51 82h14M52 76c8 0 8 12-1 12l8 7" fill="none" stroke="#b54708" stroke-width="2.5" stroke-linecap="round" />
      <circle cx="262" cy="64" r="7" fill="#fff" fill-opacity="0.5" />
      <circle cx="40" cy="190" r="5" fill="#fff" fill-opacity="0.5" />
    </svg>
  );
}

/** Check empty state: a message bubble with a magnifier. */
export function CheckArt({ size = 160, class: cls }: Art) {
  return (
    <svg width={size} height={size * 0.75} viewBox="0 0 160 120" class={cls} aria-hidden="true" focusable="false">
      <circle cx="80" cy="60" r="54" fill="var(--brand-soft)" />
      <rect x="32" y="26" width="76" height="50" rx="12" fill="var(--card)" stroke="var(--link)" stroke-width="2.5" />
      <path d="M48 76l-4 14 18-14z" fill="var(--card)" stroke="var(--link)" stroke-width="2.5" stroke-linejoin="round" />
      <rect x="44" y="40" width="40" height="5" rx="2.5" fill="var(--border-strong)" />
      <rect x="44" y="52" width="26" height="5" rx="2.5" fill="var(--border-strong)" />
      <circle cx="108" cy="68" r="20" fill="var(--card)" stroke="var(--link)" stroke-width="4" />
      <path d="M100 68l6 6 11-12" fill="none" stroke="var(--ok-solid)" stroke-width="4" stroke-linecap="round" stroke-linejoin="round" />
      <path d="M123 83l16 16" stroke="var(--link)" stroke-width="7" stroke-linecap="round" />
    </svg>
  );
}

/** Chat empty state: two speech bubbles with a mic. */
export function ChatArt({ size = 160, class: cls }: Art) {
  return (
    <svg width={size} height={size * 0.75} viewBox="0 0 160 120" class={cls} aria-hidden="true" focusable="false">
      <circle cx="80" cy="60" r="54" fill="var(--brand-soft)" />
      <rect x="26" y="26" width="70" height="42" rx="12" fill="var(--card)" stroke="var(--link)" stroke-width="2.5" />
      <path d="M40 68l-2 14 16-14z" fill="var(--card)" stroke="var(--link)" stroke-width="2.5" stroke-linejoin="round" />
      <circle cx="46" cy="47" r="4" fill="var(--link)" />
      <circle cx="61" cy="47" r="4" fill="var(--link)" />
      <circle cx="76" cy="47" r="4" fill="var(--link)" />
      <rect x="84" y="56" width="52" height="36" rx="12" fill="var(--link)" />
      <rect x="104" y="64" width="12" height="18" rx="6" fill="#fff" />
      <path d="M100 76a10 10 0 0 0 20 0M110 86v4" fill="none" stroke="#fff" stroke-width="2.5" stroke-linecap="round" />
    </svg>
  );
}

/** Learn header: an open book with a light bulb. */
export function LearnArt({ size = 160, class: cls }: Art) {
  return (
    <svg width={size} height={size * 0.75} viewBox="0 0 160 120" class={cls} aria-hidden="true" focusable="false">
      <circle cx="80" cy="60" r="54" fill="var(--brand-soft)" />
      <path d="M80 54c-14-8-32-9-48-5v42c16-4 34-3 48 5 14-8 32-9 48-5V49c-16-4-34-3-48 5z" fill="var(--card)" stroke="var(--link)" stroke-width="2.5" stroke-linejoin="round" />
      <path d="M80 54v42" stroke="var(--link)" stroke-width="2.5" />
      <rect x="42" y="62" width="26" height="4" rx="2" fill="var(--border-strong)" />
      <rect x="42" y="72" width="20" height="4" rx="2" fill="var(--border-strong)" />
      <rect x="92" y="62" width="26" height="4" rx="2" fill="var(--border-strong)" />
      <circle cx="80" cy="28" r="12" fill="#fec84b" />
      <path d="M75 40h10M76 44h8" stroke="var(--link)" stroke-width="3" stroke-linecap="round" />
      <path d="M80 8v5M62 15l4 4M98 15l-4 4" stroke="#fec84b" stroke-width="3" stroke-linecap="round" />
    </svg>
  );
}
