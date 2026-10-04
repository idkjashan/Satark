// S1 engine: the fake-trading-app trap, a finite-state machine (CONTRACTS §7.3, LLD §23.1-23.2).
// No LLM touches the maths; `set` ops are a tiny fixed grammar (+N/-N/=N/*F), never eval.
// Also reused as-is by S4-S6 (content/sims/*.json kind "fsm") - this is a generic FSM engine, not
// specific to the trading-app scenario despite the filename.
import { formatNumber } from '../format';
import type { QuizQuestion } from '../lessons';

export type LangText = Record<string, string>;

export interface S1Choice {
  id: string;
  label: LangText;
  to: string;
  set?: Record<string, string>;
}

export interface S1State {
  say?: LangText;
  choices?: S1Choice[];
  end?: 'safe' | 'lost';
  reveal?: LangText;
  show?: string[];
}

export interface S1Scenario {
  id: string;
  kind: 'fsm';
  version: number;
  start: string;
  title?: LangText;
  vars: Record<string, number>;
  states: Record<string, S1State>;
  quiz?: QuizQuestion | QuizQuestion[];
}

export interface S1RunState {
  current: string;
  vars: Record<string, number>;
}

/** +N / -N / =N / *F only - a regex match, never `eval`. An op that doesn't match this is ignored. */
export function applySetOp(current: number, op: string): number {
  const m = /^([+\-=*])(\d+(?:\.\d+)?)$/.exec(op.trim());
  if (!m) return current;
  const n = Number(m[2]);
  switch (m[1]) {
    case '+':
      return current + n;
    case '-':
      return current - n;
    case '=':
      return n;
    case '*':
      return current * n;
    default:
      return current;
  }
}

export function s1Start(scenario: S1Scenario): S1RunState {
  return { current: scenario.start, vars: { ...scenario.vars } };
}

/** Unknown choice id or an unknown `to` target: no-op (stays on the current state) rather than crash. */
export function s1Choose(scenario: S1Scenario, state: S1RunState, choiceId: string): S1RunState {
  const node = scenario.states[state.current];
  const choice = node?.choices?.find((c) => c.id === choiceId);
  if (!choice) return state;
  const to = scenario.states[choice.to] ? choice.to : state.current;
  const vars = { ...state.vars };
  for (const [key, op] of Object.entries(choice.set ?? {})) {
    vars[key] = applySetOp(vars[key] ?? 0, op);
  }
  return { current: to, vars };
}

export function s1Node(scenario: S1Scenario, state: S1RunState): S1State | undefined {
  return scenario.states[state.current];
}

export function s1IsEnd(scenario: S1Scenario, state: S1RunState): boolean {
  return !!s1Node(scenario, state)?.end;
}

/** Renders a say/reveal text in `lang` (English fallback), substituting {balance}/{lost} etc. */
export function s1Text(text: LangText | undefined, lang: string, vars: Record<string, number>): string {
  const template = text?.[lang] ?? text?.en ?? '';
  return template.replace(/\{(\w+)\}/g, (whole, name: string) => (name in vars ? formatNumber(vars[name]) : whole));
}
