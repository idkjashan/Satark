import { describe, it, expect } from 'vitest';
import { applySetOp, s1Start, s1Choose, s1Node, s1IsEnd, s1Text, type S1Scenario } from './s1';

describe('applySetOp: +N / -N / =N / *F only, never eval', () => {
  it('adds, subtracts, sets and multiplies', () => {
    expect(applySetOp(100, '+50')).toBe(150);
    expect(applySetOp(100, '-30')).toBe(70);
    expect(applySetOp(100, '=0')).toBe(0);
    expect(applySetOp(100, '*2')).toBe(200);
    expect(applySetOp(10000, '=70000')).toBe(70000); // S1.json's real "pay" choice
  });

  it('ignores anything that is not the fixed grammar (no eval, ever)', () => {
    expect(applySetOp(100, '100+1')).toBe(100); // not a valid op string: no-op
    expect(applySetOp(100, 'balance*2')).toBe(100);
    expect(applySetOp(100, '')).toBe(100);
  });
});

const scenario: S1Scenario = {
  id: 'S1',
  kind: 'fsm',
  version: 1,
  start: 'invite',
  vars: { balance: 0, lost: 0 },
  states: {
    invite: {
      say: { en: 'Join a VIP group?' },
      choices: [
        { id: 'check', label: { en: 'Check first' }, to: 'checked' },
        { id: 'join', label: { en: 'Join' }, to: 'deposit' },
        { id: 'nowhere', label: { en: 'A broken choice' }, to: 'does_not_exist' },
      ],
    },
    deposit: {
      say: { en: 'Pay {lost} to start' },
      choices: [{ id: 'pay', label: { en: 'Pay' }, to: 'profits', set: { lost: '+10000', balance: '+10000' } }],
    },
    profits: { say: { en: 'Balance: {balance}' }, choices: [] },
    checked: { end: 'safe', reveal: { en: 'You lost {lost}, which was the right call' } },
  },
};

describe('S1 engine against a scenario shaped like content/sims/S1.json', () => {
  it('starts at the declared start state with the declared vars', () => {
    const state = s1Start(scenario);
    expect(state.current).toBe('invite');
    expect(state.vars).toEqual({ balance: 0, lost: 0 });
  });

  it('applies a choice\'s `set` ops and moves to `to`', () => {
    let state = s1Start(scenario);
    state = s1Choose(scenario, state, 'join');
    expect(state.current).toBe('deposit');
    state = s1Choose(scenario, state, 'pay');
    expect(state.current).toBe('profits');
    expect(state.vars).toEqual({ balance: 10000, lost: 10000 });
  });

  it('reaches an end state and exposes its reveal text', () => {
    let state = s1Start(scenario);
    state = s1Choose(scenario, state, 'check');
    expect(s1IsEnd(scenario, state)).toBe(true);
    expect(s1Node(scenario, state)?.end).toBe('safe');
    expect(s1Text(s1Node(scenario, state)?.reveal, 'en', state.vars)).toBe('You lost 0, which was the right call');
  });

  it('guards an unknown `to`: stays on the current state instead of crashing', () => {
    let state = s1Start(scenario);
    state = s1Choose(scenario, state, 'nowhere');
    expect(state.current).toBe('invite'); // unchanged
  });

  it('guards an unknown choice id the same way', () => {
    let state = s1Start(scenario);
    state = s1Choose(scenario, state, 'not_a_real_choice');
    expect(state.current).toBe('invite');
  });

  it('formats {placeholders} with en-IN grouping', () => {
    let state = s1Start(scenario);
    state = s1Choose(scenario, state, 'join');
    state = s1Choose(scenario, state, 'pay');
    expect(s1Text(scenario.states.profits.say, 'en', state.vars)).toBe('Balance: 10,000');
  });

  it('falls back to English when the requested language is missing', () => {
    const state = s1Start(scenario);
    expect(s1Text(scenario.states.invite.say, 'hi', state.vars)).toBe('Join a VIP group?');
  });
});
