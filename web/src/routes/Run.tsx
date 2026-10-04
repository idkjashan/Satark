// /run/:runId (CONTRACTS §6.1, LLD §22.1): subscribes to the run's SSE stream, drives the live
// checklist, then the verdict card and explanation. case_id travels as a `?case=` query param
// from Check.tsx (the POST /v1/checks response has it before any SSE event does); `done` is the
// only event that also carries it, so a direct/bookmarked open still recovers it eventually.
import { useEffect, useRef } from 'preact/hooks';
import { useSignal } from '@preact/signals';
import { useLocation } from 'preact-iso';
import { t } from '../lib/i18n';
import { prefs } from '../lib/signals';
import {
  openRunEvents,
  postChat,
  postCheck,
  lastCheckInput,
  lastCaseId,
  type RunEventType,
  type RunSubscription,
} from '../lib/api';
import { applyRunEvent, initialRunState, type RunState } from '../lib/runReducer';
import { addHistory } from '../lib/idb';
import { Checklist } from '../components/Checklist';
import { VerdictCard } from '../components/VerdictCard';
import { Explanation } from '../components/Explanation';
import { AskUser } from '../components/AskUser';
import { ActionButtons } from '../components/ActionButtons';
import { Icon } from '../components/Icon';

interface RunProps {
  runId: string;
}

export function Run({ runId }: RunProps) {
  const { route, query } = useLocation();
  const state = useSignal<RunState>(initialRunState());
  const slow = useSignal(false);
  const expired = useSignal(false);
  const busy = useSignal(false);
  const caseId = query.case ?? state.value.done?.case_id ?? '';
  const subRef = useRef<RunSubscription | null>(null);

  useEffect(() => {
    if (caseId) lastCaseId.value = caseId;
  }, [caseId]);

  useEffect(() => {
    state.value = initialRunState();
    slow.value = false;
    expired.value = false;
    let restarted = false;

    const sub = openRunEvents(`/v1/runs/${runId}/events`, {
      onEvent: (type: RunEventType, id, data) => {
        const prev = state.value;
        const isNew = !prev.appliedIds.has(id);
        const next = applyRunEvent(prev, id, type, data);
        state.value = next;
        slow.value = false;
        if (isNew && type === 'done' && next.verdict && next.askUser?.question_id !== 'off_topic') {
          void addHistory({
            date: new Date().toISOString(),
            level: next.verdict.level,
            scam_type: next.verdict.scam_type ?? undefined,
            lesson: next.verdict.lesson ?? undefined,
            lang: prefs.value.lang,
          });
        }
      },
      onSlow: () => {
        slow.value = true;
      },
      onConnectionFailed: () => {
        const input = lastCheckInput.value;
        if (!restarted && input) {
          restarted = true;
          postCheck(input)
            .then((handle) => route(`/run/${handle.run_id}?case=${handle.case_id}`, true))
            .catch(() => {
              expired.value = true;
            });
        } else {
          expired.value = true;
        }
      },
    });
    subRef.current = sub;
    return () => sub.close();
  }, [runId]);

  async function answerChoice(optionId: string) {
    const askUser = state.value.askUser;
    if (!askUser) return;
    busy.value = true;
    try {
      const handle = await postChat({
        case_id: caseId,
        choice: { question_id: askUser.question_id, option_id: optionId },
        lang: prefs.value.lang,
        simple: prefs.value.simple,
      });
      route(`/run/${handle.run_id}?case=${handle.case_id}`);
    } finally {
      busy.value = false;
    }
  }

  async function answerText(message: string) {
    busy.value = true;
    try {
      const handle = await postChat({ case_id: caseId, message, lang: prefs.value.lang, simple: prefs.value.simple });
      route(`/run/${handle.run_id}?case=${handle.case_id}`);
    } finally {
      busy.value = false;
    }
  }

  if (expired.value) {
    return (
      <main class="screen">
        <p role="alert">{t('ui.run_expired')}</p>
        <a class="btn btn-primary" href="/check">
          {t('ui.check_another')}
        </a>
      </main>
    );
  }

  const run = state.value;
  // Still reviewing (product update, Oct 2026): the AI-review stage sits between the instant
  // rule-based verdict (revision 1) and a possible reviewed one (revision 2, `ai_reviewed`).
  // Without a model this stage never arrives, so the line never shows - exactly today's behaviour.
  const reviewing = !!run.verdict && run.stage === 'reasoning' && !run.verdict.ai_reviewed;

  return (
    <main class="screen screen-wide" data-testid="run-screen">
      {run.error && (
        <p role="alert" class="error-banner">
          {t(`error.${run.error.code}`)}
        </p>
      )}

      {slow.value && (
        <p class="slow-banner">
          {t('ui.slow_network')}{' '}
          <button
            type="button"
            class="btn"
            onClick={() => {
              slow.value = false;
              subRef.current?.retry();
            }}
          >
            {t('ui.retry')}
          </button>
        </p>
      )}

      {!run.verdict && !run.answer && (
        <>
          <p class="stage-label" role="status">
            <Icon name="loader" size={18} spin /> {t(`ui.stage.${run.stage ?? 'received'}`)}
          </p>
          {!run.plan && (
            <ul class="skeleton-list" aria-hidden="true">
              <li class="skeleton-row" />
              <li class="skeleton-row" />
              <li class="skeleton-row" />
            </ul>
          )}
        </>
      )}

      {run.imageReading && (
        <section class="image-reading-card" data-testid="image-reading-card" aria-live="polite">
          <h2>{t('ui.image_reading_title')}</h2>
          <p>
            <strong>{run.imageReading.screen}</strong>
          </p>
          <p>{run.imageReading.description}</p>
          {run.imageReading.cues.length > 0 && (
            <div class="chips">
              {run.imageReading.cues.map((cue) => (
                <span key={cue} class="chip chip-static">
                  {cue}
                </span>
              ))}
            </div>
          )}
        </section>
      )}

      {run.askUser && !run.verdict && <AskUser askUser={run.askUser} busy={busy.value} onChoice={answerChoice} onText={answerText} />}

      <div class={`run-grid ${run.verdict || run.explanation ? 'has-result' : 'is-running'}`}>
        {(run.verdict || run.explanation) && (
          <div class="run-main">
            {run.verdict && (
              <div class="run-verdict-col">
                <VerdictCard verdict={run.verdict} caseId={caseId} />
                {reviewing && (
                  <p class="ai-reviewing" aria-live="polite">
                    <Icon name="loader" spin />
                    {t('ui.stage.reasoning')}
                  </p>
                )}
              </div>
            )}
            {run.explanation && <Explanation explanation={run.explanation} caseId={caseId} />}
          </div>
        )}
        <div class="run-side">
          <Checklist run={run} />
        </div>
      </div>

      {run.askUser && run.verdict && <AskUser askUser={run.askUser} busy={busy.value} onChoice={answerChoice} onText={answerText} />}

      {/* The model decided this input was a question, not something to verdict (Track C, Oct 2026). */}
      {run.answer && !run.verdict && (
        <section class="answer-card" data-testid="chat-answer">
          <p>{run.answer.text}</p>
          {run.answer.refused && <p class="scope-hint">{t('ui.scope_hint')}</p>}
          <ActionButtons ids={run.answer.actions} />
          {run.answer.chips.length > 0 && (
            <div class="chips">
              {run.answer.chips.map((chip) => (
                <a key={chip} class="chip" href={`/chat/${caseId}?q=${encodeURIComponent(chip)}`}>
                  {chip}
                </a>
              ))}
            </div>
          )}
          <a class="btn btn-primary btn-huge" href={`/chat/${caseId}`}>
            {t('ui.continue_in_chat')}
          </a>
        </section>
      )}
    </main>
  );
}
