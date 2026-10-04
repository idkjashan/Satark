// Number and date formatting. Amounts always use en-IN grouping (1,00,000), per LLD §24,
// even when the UI language is Hindi - only the words around the number translate.

const GROUPED = new Intl.NumberFormat('en-IN', { maximumFractionDigits: 0 });

/** Grouped integer, e.g. 100000 -> "1,00,000". */
export function formatNumber(n: number): string {
  return GROUPED.format(Math.round(n));
}

/** Rupee amount with the sign, e.g. "₹1,00,000". */
export function formatINR(n: number): string {
  return `₹${formatNumber(n)}`;
}

const LAKH = 100_000;
const CRORE = 1_00_00_000; // 10,000,000

/** Trim to <=2 decimals with no trailing zeros: 12 -> "12", 12.3 -> "12.3". */
function trimDecimals(n: number): string {
  return (Math.round(n * 100) / 100).toString();
}

/**
 * Big rupee amounts in lakh/crore words for the simulators, e.g. 19800000 -> "₹1.98 crore".
 * Falls back to a plain grouped amount below one lakh.
 */
export function formatINRWords(n: number): string {
  const sign = n < 0 ? '-' : '';
  const abs = Math.abs(n);
  if (abs >= CRORE) return `${sign}₹${trimDecimals(abs / CRORE)} crore`;
  if (abs >= LAKH) return `${sign}₹${trimDecimals(abs / LAKH)} lakh`;
  return formatINR(n);
}

/** Short "as on" date for a source chip, e.g. "2026-10-03" -> "3 Oct". Falls back to the raw string. */
export function formatAsOn(iso: string | null | undefined, lang: string): string {
  if (!iso) return '';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  try {
    return new Intl.DateTimeFormat(lang === 'hi' ? 'hi-IN' : 'en-IN', { day: 'numeric', month: 'short' }).format(d);
  } catch {
    return iso;
  }
}
