import { describe, it, expect } from 'vitest';
import { mulberry32, s3Equity, s3Status, s3IndexPath, s3Run } from './s3';

describe('mulberry32: deterministic PRNG', () => {
  it('the same seed always produces the same sequence', () => {
    const a = mulberry32(42);
    const b = mulberry32(42);
    const seqA = [a(), a(), a()];
    const seqB = [b(), b(), b()];
    expect(seqA).toEqual(seqB);
  });

  it('stays within [0, 1)', () => {
    const rand = mulberry32(1);
    for (let i = 0; i < 50; i++) {
      const n = rand();
      expect(n).toBeGreaterThanOrEqual(0);
      expect(n).toBeLessThan(1);
    }
  });
});

describe('s3Status: wipe-out and margin-call detection', () => {
  it('flags wiped_out at or below zero equity', () => {
    expect(s3Status(10000, 0)).toBe('wiped_out');
    expect(s3Status(10000, -500)).toBe('wiped_out');
  });

  it('flags margin_call below 50% of margin but still positive', () => {
    expect(s3Status(10000, 4999)).toBe('margin_call');
    expect(s3Status(10000, 5000)).toBe('ok'); // exactly 50% is not yet a margin call
  });

  it('is ok comfortably above the margin-call line', () => {
    expect(s3Status(10000, 12000)).toBe('ok');
  });
});

describe('s3Equity', () => {
  it('equity = margin * (1 + leverage * index return)', () => {
    expect(s3Equity(10000, 8, 0)).toBe(10000);
    expect(s3Equity(10000, 8, 0.1)).toBeCloseTo(18000, 5); // +10% index move, 8x leverage
    expect(s3Equity(10000, 8, -0.1)).toBeCloseTo(2000, 5); // -10% index move, 8x leverage
    expect(s3Equity(10000, 8, -0.125)).toBeCloseTo(0, 5); // -12.5% wipes out 8x leverage exactly
  });
});

describe('s3Run: the full stepped, reproducible walk', () => {
  it('path[0] is always the starting point (zero cumulative return)', () => {
    const path = s3IndexPath(42, 30);
    expect(path).toHaveLength(31);
    expect(path[0]).toBe(0);
  });

  it('is fully reproducible for the same (margin, leverage, seed)', () => {
    const a = s3Run(10000, 8, 42, 30);
    const b = s3Run(10000, 8, 42, 30);
    expect(a).toEqual(b);
  });

  it('detects a wipe-out whenever the walk pushes equity to zero or below', () => {
    // A high enough leverage over enough steps, at +-2% per step, will cross the wipe-out line
    // for at least one seed - search a small range instead of pinning one magic seed.
    let foundWipeOut = false;
    for (let seed = 0; seed < 20 && !foundWipeOut; seed++) {
      const steps = s3Run(10000, 10, seed, 30);
      if (steps.some((s) => s.status === 'wiped_out')) {
        foundWipeOut = true;
        // every step from the first wipe-out onward must be classified consistently (equity <= 0)
        const firstWipeOut = steps.find((s) => s.status === 'wiped_out')!;
        expect(firstWipeOut.equity).toBeLessThanOrEqual(0);
      }
    }
    expect(foundWipeOut).toBe(true);
  });
});
