import { describe, it, expect } from 'vitest';
import { compoundValue, s2Project } from './s2';

describe('S2: compounding maths (value = P * (1+r)^n)', () => {
  it('1% a day over a year (250 trading days) is about 12.0x (LLD §23.3)', () => {
    const multiple = compoundValue(1, 1, 'day', 1);
    expect(multiple).toBeCloseTo(12.03, 1); // 1.01^250
    expect(multiple).toBeGreaterThan(11.9);
    expect(multiple).toBeLessThan(12.2);
  });

  it('matches content/sims/S2.json\'s own example: ₹10,000 at 1%/day for a year', () => {
    const value = compoundValue(10000, 1, 'day', 1);
    expect(value).toBeGreaterThan(119_000);
    expect(value).toBeLessThan(121_000);
  });

  it('uses 52 weeks and 12 months per year for the other periods', () => {
    expect(compoundValue(100, 10, 'week', 1)).toBeCloseTo(100 * Math.pow(1.1, 52), 0);
    expect(compoundValue(100, 10, 'month', 1)).toBeCloseTo(100 * Math.pow(1.1, 12), 0);
  });

  it('a zero rate never grows the principal', () => {
    expect(compoundValue(5000, 0, 'day', 1)).toBe(5000);
  });

  it('s2Project gives three horizons from the same principal and rate', () => {
    const projection = s2Project(10000, 1, 'day');
    expect(projection.afterOneMonth).toBeLessThan(projection.afterSixMonths);
    expect(projection.afterSixMonths).toBeLessThan(projection.afterOneYear);
    expect(projection.afterOneYear).toBeCloseTo(compoundValue(10000, 1, 'day', 1), 0);
  });
});
