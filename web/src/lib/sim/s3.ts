// S3 engine: leverage wipe-out (CONTRACTS §7.3). A seeded PRNG drives an illustrative index path
// (explicitly labelled "not real prices" in the UI); equity = margin * (1 + leverage * cumulative
// index return). No network, no real market data - this is a fixed, reproducible demonstration.

/** mulberry32: a tiny deterministic PRNG. Same seed -> same sequence, every time, every device. */
export function mulberry32(seed: number): () => number {
  let a = seed >>> 0;
  return function next(): number {
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

export const S3_STEPS = 30;
export const STEP_VOLATILITY = 0.02; // +/-2% per step - illustrative only, not a real market figure

/** Cumulative index return after each step, path[0] = 0. Length = steps + 1. */
export function s3IndexPath(seed: number, steps = S3_STEPS): number[] {
  const rand = mulberry32(seed);
  const path = [0];
  let cumulative = 0;
  for (let i = 0; i < steps; i++) {
    cumulative += (rand() * 2 - 1) * STEP_VOLATILITY;
    path.push(cumulative);
  }
  return path;
}

export function s3Equity(margin: number, leverage: number, cumulativeReturn: number): number {
  return margin * (1 + leverage * cumulativeReturn);
}

export type S3Status = 'ok' | 'margin_call' | 'wiped_out';

/** equity <= 0 -> wiped_out; equity below 50% of margin -> margin_call; else ok. */
export function s3Status(margin: number, equity: number): S3Status {
  if (equity <= 0) return 'wiped_out';
  if (equity < margin * 0.5) return 'margin_call';
  return 'ok';
}

export interface S3StepResult {
  step: number;
  indexReturn: number;
  equity: number;
  status: S3Status;
}

/** The full deterministic walk for one (margin, leverage, seed) combination, stepped through by the UI. */
export function s3Run(margin: number, leverage: number, seed: number, steps = S3_STEPS): S3StepResult[] {
  return s3IndexPath(seed, steps).map((indexReturn, step) => {
    const equity = s3Equity(margin, leverage, indexReturn);
    return { step, indexReturn, equity, status: s3Status(margin, equity) };
  });
}
