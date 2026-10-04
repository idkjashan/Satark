// S2 engine: the "guaranteed return" calculator (CONTRACTS §7.3). value = P*(1+r)^n,
// n = trading days/weeks/months per year * years. No LLM; plain compounding maths.

export type Period = 'day' | 'week' | 'month';

const PERIODS_PER_YEAR: Record<Period, number> = { day: 250, week: 52, month: 12 };

/** `ratePercent` is the promised rate per period, e.g. 1 for "1% a day". */
export function compoundValue(principal: number, ratePercent: number, period: Period, years: number): number {
  const n = PERIODS_PER_YEAR[period] * years;
  const r = ratePercent / 100;
  return principal * Math.pow(1 + r, n);
}

export interface S2Projection {
  afterOneMonth: number;
  afterSixMonths: number;
  afterOneYear: number;
}

export function s2Project(principal: number, ratePercent: number, period: Period): S2Projection {
  return {
    afterOneMonth: compoundValue(principal, ratePercent, period, 1 / 12),
    afterSixMonths: compoundValue(principal, ratePercent, period, 0.5),
    afterOneYear: compoundValue(principal, ratePercent, period, 1),
  };
}
