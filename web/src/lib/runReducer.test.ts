import { describe, it, expect } from 'vitest';
import {
  applyRunEvent,
  initialRunState,
  familyRowStatus,
  familiesInPlan,
  agentStepRows,
  type VerdictEvent,
  type PlanEvent,
} from './runReducer';

const sourceRef = { id: 'sebi_registers', as_on: '2026-10-03' };

function verdict(revision: number, level: VerdictEvent['level'] = 'HIGH_RISK'): VerdictEvent {
  return {
    revision,
    level,
    confidence: 'SURE',
    reasons: [{ code: 'REG_NOT_FOUND', weight: 'high', title: 'Not registered', source: sourceRef }],
    worth_noting: [],
    assurances: [],
    actions: ['report_1930'],
    checked: [],
    scoring_version: '1',
  };
}

describe('applyRunEvent: idempotency', () => {
  it('ignores a replayed event with the same id', () => {
    let state = initialRunState();
    state = applyRunEvent(state, 1, 'stage', { stage: 'received', t_ms: 0 });
    const afterFirst = state;
    state = applyRunEvent(state, 1, 'stage', { stage: 'executing', t_ms: 500 }); // same id, different payload
    expect(state).toBe(afterFirst); // untouched: same object reference, not just equal value
    expect(state.stage).toBe('received');
  });

  it('applies a new id normally', () => {
    let state = initialRunState();
    state = applyRunEvent(state, 1, 'stage', { stage: 'received', t_ms: 0 });
    state = applyRunEvent(state, 2, 'stage', { stage: 'executing', t_ms: 500 });
    expect(state.stage).toBe('executing');
    expect(state.appliedIds.has(1)).toBe(true);
    expect(state.appliedIds.has(2)).toBe(true);
  });
});

describe('applyRunEvent: verdict revisions', () => {
  it('keeps the newer revision when events arrive in order', () => {
    let state = initialRunState();
    state = applyRunEvent(state, 1, 'verdict', verdict(1, 'SUSPICIOUS'));
    state = applyRunEvent(state, 2, 'verdict', verdict(2, 'HIGH_RISK'));
    expect(state.verdict?.revision).toBe(2);
    expect(state.verdict?.level).toBe('HIGH_RISK');
  });

  it('does not regress to an older revision that arrives late (out-of-order replay)', () => {
    let state = initialRunState();
    state = applyRunEvent(state, 2, 'verdict', verdict(2, 'HIGH_RISK'));
    state = applyRunEvent(state, 1, 'verdict', verdict(1, 'SUSPICIOUS')); // arrives after, but older revision
    expect(state.verdict?.revision).toBe(2);
    expect(state.verdict?.level).toBe('HIGH_RISK');
  });
});

describe('applyRunEvent: plan revisions and the checklist', () => {
  const plan1: PlanEvent = {
    revision: 1,
    steps: [
      { id: 's1', checker_id: 'sebi.reg', family: 'registry', status: 'running' },
      { id: 's2', checker_id: 'upi.valid', family: 'payment', status: 'pending' },
    ],
  };

  it('does not let an older plan revision overwrite a newer one', () => {
    let state = initialRunState();
    state = applyRunEvent(state, 1, 'plan', { ...plan1, revision: 2 });
    state = applyRunEvent(state, 2, 'plan', { ...plan1, revision: 1 });
    expect(state.plan?.revision).toBe(2);
  });

  it('builds the checklist from plan steps grouped by family, in first-seen order', () => {
    let state = initialRunState();
    state = applyRunEvent(state, 1, 'plan', plan1);
    expect(familiesInPlan(state)).toEqual(['registry', 'payment']);
    expect(familyRowStatus('registry', state)).toBe('checking'); // step s1 is "running"
    expect(familyRowStatus('payment', state)).toBe('checking'); // step s2 is "pending"

    state = applyRunEvent(state, 2, 'check_result', {
      step_id: 's1',
      checker_id: 'sebi.reg',
      family: 'registry',
      status: 'unknown',
      signals: [],
      source: sourceRef,
      stale: false,
      cached: false,
    });
    expect(familyRowStatus('registry', state)).toBe('unknown'); // "could not check"

    state = applyRunEvent(state, 3, 'check_result', {
      step_id: 's2',
      checker_id: 'upi.valid',
      family: 'payment',
      status: 'clear',
      signals: ['UPI_VALID_HANDLE'],
      source: sourceRef,
      stale: false,
      cached: false,
    });
    expect(familyRowStatus('payment', state)).toBe('done');
  });

  it('marks a row skipped only when every step in that family was skipped', () => {
    let state = initialRunState();
    state = applyRunEvent(state, 1, 'plan', {
      revision: 1,
      steps: [{ id: 's1', checker_id: 'x', family: 'social', status: 'skipped' }],
    });
    expect(familyRowStatus('social', state)).toBe('skipped');
  });
});

describe('applyRunEvent: ask_user', () => {
  it('records the question and its options', () => {
    let state = initialRunState();
    state = applyRunEvent(state, 1, 'ask_user', {
      question_id: 'which_candidate',
      text: 'Which of these did the message mean?',
      options: [{ id: 'a', label: 'Broker A' }],
    });
    expect(state.askUser?.question_id).toBe('which_candidate');
    expect(state.askUser?.options).toHaveLength(1);
  });
});

describe('applyRunEvent: image_reading', () => {
  it('records what the vision model saw, with its cues', () => {
    let state = initialRunState();
    state = applyRunEvent(state, 1, 'image_reading', {
      screen: 'WhatsApp chat',
      description: 'A group admin asks you to pay a 15% fee to withdraw',
      cues: ['profit chart', 'countdown timer'],
    });
    expect(state.imageReading).toEqual({
      screen: 'WhatsApp chat',
      description: 'A group admin asks you to pay a 15% fee to withdraw',
      cues: ['profit chart', 'countdown timer'],
    });
  });
});

describe('applyRunEvent: agent_step + tool_status, and agentStepRows', () => {
  it('shows an action as "checking" as soon as its step arrives, before any tool_status', () => {
    let state = initialRunState();
    state = applyRunEvent(state, 1, 'agent_step', {
      step: 1,
      thought: 'This looks like a guaranteed-return pitch.',
      actions: [{ tool: 'satark.search_sebi_register', label: 'Checking the SEBI register: Suresh Mehta' }],
    });
    const rows = agentStepRows(state);
    expect(rows).toHaveLength(1);
    expect(rows[0].thought).toBe('This looks like a guaranteed-return pitch.');
    expect(rows[0].actions).toEqual([
      { tool: 'satark.search_sebi_register', label: 'Checking the SEBI register: Suresh Mehta', status: 'checking' },
    ]);
  });

  it('joins a tool_status start/end pair by call_id (parallel calls in one step) to "done" or "unknown"', () => {
    let state = initialRunState();
    state = applyRunEvent(state, 1, 'agent_step', {
      step: 1,
      thought: '',
      actions: [
        { tool: 'web.search', label: 'Searching the web: profitking-trade.in' },
        { tool: 'satark.check_identifiers', label: 'Checking the payment handle' },
      ],
    });
    state = applyRunEvent(state, 2, 'tool_status', {
      tool: 'web.search',
      status: 'start',
      label: 'Searching the web: profitking-trade.in',
      call_id: 'c1',
    });
    state = applyRunEvent(state, 3, 'tool_status', {
      tool: 'satark.check_identifiers',
      status: 'start',
      label: 'Checking the payment handle',
      call_id: 'c2',
    });
    let rows = agentStepRows(state);
    expect(rows[0].actions.map((a) => a.status)).toEqual(['checking', 'checking']);

    // The two parallel calls end independently and with different outcomes.
    state = applyRunEvent(state, 4, 'tool_status', {
      tool: 'web.search',
      status: 'end',
      label: 'Searching the web: profitking-trade.in',
      call_id: 'c1',
      ok: true,
    });
    state = applyRunEvent(state, 5, 'tool_status', {
      tool: 'satark.check_identifiers',
      status: 'end',
      label: 'Checking the payment handle',
      call_id: 'c2',
      ok: false,
    });
    rows = agentStepRows(state);
    expect(rows[0].actions[0].status).toBe('done'); // ok: true
    expect(rows[0].actions[1].status).toBe('unknown'); // ok: false -> "could not check"
  });

  it('is a no-op the second time the same agent_step id is replayed (idempotency)', () => {
    let state = initialRunState();
    state = applyRunEvent(state, 1, 'agent_step', { step: 1, thought: '', actions: [{ tool: 'web.search', label: 'x' }] });
    const afterFirst = state;
    state = applyRunEvent(state, 1, 'agent_step', { step: 2, thought: 'different payload', actions: [] });
    expect(state).toBe(afterFirst);
    expect(agentStepRows(state)).toHaveLength(1);
  });

  it('still updates the legacy toolStatus singleton for an old-style event with no label or call_id', () => {
    let state = initialRunState();
    state = applyRunEvent(state, 1, 'tool_status', { tool: 'check_entities', status: 'start' });
    expect(state.toolStatus).toEqual({ tool: 'check_entities', status: 'start' });
    state = applyRunEvent(state, 2, 'tool_status', { tool: 'check_entities', status: 'end' });
    expect(state.toolStatus?.status).toBe('end');
  });
});
