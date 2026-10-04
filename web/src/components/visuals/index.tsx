// Built-in lesson visuals, named by content/lessons/<id>.json `visual` (CONTRACTS §7.2).
// An unknown or missing name renders nothing - new visuals are additive, not breaking.
import type { JSX } from 'preact';
import { CompoundingChart } from './CompoundingChart';
import { LeverageBar } from './LeverageBar';

const VISUALS: Record<string, () => JSX.Element> = {
  'compounding-chart': CompoundingChart,
  'leverage-bar': LeverageBar,
};

export function Visual({ name }: { name?: string }) {
  const Component = name ? VISUALS[name] : undefined;
  return Component ? <Component /> : null;
}
