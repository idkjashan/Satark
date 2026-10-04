// /chat/:caseId (CONTRACTS §6, §6.1): one message exchange per POST /v1/chat, each with its own
// short SSE stream (tool_status -> "checking...", answer -> a bubble, an optional new verdict ->
// a compact banner linking to the full /run card). Off-topic refusals arrive as plain `answer`
// events (product scope guardrails, Oct 2026) - rendered exactly like any other answer.
import { useEffect, useRef } from 'preact/hooks';
import { useSignal } from '@preact/signals';
import { useLocation } from 'preact-iso';
import { t } from '../lib/i18n';
import { prefs } from '../lib/signals';
import { openRunEvents, postChat, lastCaseId, ApiError, type RunEventType, type RunSubscription } from '../lib/api';
import type { AnswerEvent, ToolStatusEvent, VerdictEvent } from '../lib/runReducer';
import { ActionButtons } from '../components/ActionButtons';
import { SpeakerButton } from '../components/SpeakerButton';
import { isDictationSupported, startDictation } from '../lib/speechInput';
import { speak, stopSpeaking } from '../lib/voice';
import { matchFaq } from '../lib/faq';
import { Icon } from '../components/Icon';
import { Shield } from '../components/Shield';
import { ChatArt } from '../components/Illustrations';
import { getLesson, pick } from '../lib/lessons';
import { getSim } from '../lib/sims';

// Same examples Home's "Ask or learn" chips use (content/i18n/content.<lang>.json, engineer G) -
// shown here too so a user who reached /chat/new straight from the Ask tab (no ?q= prefill) still
// has something to tap on instead of a blank screen.
const EMPTY_STATE_CHIPS = ['chip.what_is_sip', 'chip.is_rate_possible', 'chip.spot_fake_adviser'];

interface ChatProps {
  // Optional: bare /chat (content/portals.json's "ask" action) means "start a fresh case",
  // same as the NEW_CASE sentinel below.
  caseId?: string;
}

interface Bubble {
  id: number;
  role: 'user' | 'assistant';
  text: string;
  actions?: string[];
  chips?: string[];
  refused?: 'off_topic' | 'advice' | null;
  cites?: string[];
}

let nextBubbleId = 1;

/** Knowledge chunk ids ("lesson:<id>:<step>", "sim:<id>", "faq:<intent>") -> unique in-app links,
 * labelled with the lesson/sim title. FAQ chunks have no page of their own; unknown ids are dropped. */
export function citeLinks(cites: string[] = []): { href: string; label: string }[] {
  const lang = prefs.value.lang;
  const out = new Map<string, string>();
  for (const c of cites) {
    const [kind, ref] = c.split(':');
    const title = kind === 'lesson' ? getLesson(ref)?.title : kind === 'sim' ? getSim(ref)?.title : undefined;
    if (title) out.set(`/${kind === 'lesson' ? 'learn' : 'sim'}/${ref}`, pick(title, lang));
  }
  return [...out].slice(0, 2).map(([href, label]) => ({ href, label }));
}

/** Home's mic has no prior case to attach to; it links here with this sentinel instead of a
 * real id, and we ask /v1/chat to start a fresh one (CONTRACTS: `case_id` is optional there). */
export const NEW_CASE = 'new';

export function Chat({ caseId = NEW_CASE }: ChatProps) {
  const { query, route } = useLocation();
  const bubbles = useSignal<Bubble[]>([]);
  const draft = useSignal('');
  const busy = useSignal(false);
  const expired = useSignal(false);
  const errorMsg = useSignal<string | null>(null);
  const toolStatus = useSignal<ToolStatusEvent | null>(null);
  const banner = useSignal<{ verdict: VerdictEvent; runId: string } | null>(null);
  const realCaseId = useSignal<string | null>(caseId === NEW_CASE ? null : caseId);
  // Hands-free (voice, live - Oct 2026): a self-contained voice conversation toggle, independent
  // of Simple mode - once on, every answer is spoken and the mic re-opens automatically after.
  const handsFree = useSignal(false);
  const listening = useSignal(false);
  const listRef = useRef<HTMLDivElement>(null);
  const dictationRef = useRef<ReturnType<typeof startDictation>>(null);
  const autoSent = useRef(false);
  const silentTurns = useRef(0);

  useEffect(() => {
    listRef.current?.scrollTo(0, listRef.current.scrollHeight);
  }, [bubbles.value.length, busy.value]);

  // The `?q=` hand-off (from a /run chip, or Home's mic) is sent exactly once per case,
  // regardless of how many times this effect re-runs as the URL settles onto a real case id.
  useEffect(() => {
    if (query.q && !autoSent.current) {
      autoSent.current = true;
      void send(query.q);
    }
  }, [caseId]);

  // Hands-free: stop the loop if the tab goes to the background, and always release the
  // mic/voice on unmount so neither lingers after the user navigates away.
  useEffect(() => {
    function onVisibility() {
      if (document.hidden && handsFree.value) {
        handsFree.value = false;
        stopSpeaking();
        dictationRef.current?.stop();
        dictationRef.current = null;
        listening.value = false;
      }
    }
    document.addEventListener('visibilitychange', onVisibility);
    return () => {
      document.removeEventListener('visibilitychange', onVisibility);
      stopSpeaking();
      dictationRef.current?.stop();
    };
  }, []);

  async function send(message: string) {
    if (!message.trim() || busy.value) return;
    bubbles.value = [...bubbles.value, { id: nextBubbleId++, role: 'user', text: message }];
    draft.value = '';
    busy.value = true;
    toolStatus.value = null;
    try {
      const handle = await postChat({
        case_id: realCaseId.value ?? undefined,
        message,
        lang: prefs.value.lang,
        simple: prefs.value.simple,
      });
      if (!realCaseId.value) {
        realCaseId.value = handle.case_id;
        route(`/chat/${handle.case_id}`, true);
      }
      lastCaseId.value = handle.case_id;
      await new Promise<void>((resolve) => {
        const sub: RunSubscription = openRunEvents(handle.events_url, {
          onEvent: (type: RunEventType, _id, data) => {
            if (type === 'tool_status') toolStatus.value = data as ToolStatusEvent;
            if (type === 'answer') {
              const answer = data as AnswerEvent;
              toolStatus.value = null;
              bubbles.value = [
                ...bubbles.value,
                {
                  id: nextBubbleId++,
                  role: 'assistant',
                  text: answer.text,
                  actions: answer.actions,
                  chips: answer.chips,
                  refused: answer.refused,
                  cites: answer.cites,
                },
              ];
              // Voice-first explainer: in Simple mode (and always in hands-free, which IS a voice
              // conversation) the answer is read aloud as it lands; everyone else gets the
              // per-bubble speaker button below. Hands-free only starts listening again once the
              // speaking has actually finished (speak() now waits for playback) - never while the
              // mic is about to go live.
              if (prefs.value.simple || handsFree.value) {
                void speak(answer.text, prefs.value.lang).then(() => {
                  if (handsFree.value) startHandsFreeTurn();
                });
              }
            }
            if (type === 'verdict') banner.value = { verdict: data as VerdictEvent, runId: handle.run_id };
            if (type === 'error') errorMsg.value = t(`error.${(data as { code: string }).code}`);
            if (type === 'done' || type === 'error') {
              sub.close();
              resolve();
            }
          },
          onConnectionFailed: () => {
            sub.close();
            resolve();
          },
        });
      });
    } catch (err) {
      if (err instanceof ApiError) {
        if (err.code === 'case_expired') expired.value = true;
        else errorMsg.value = t(`error.${err.code}`);
      } else {
        // No network at all: content/faq.json (CONTRACTS §7.4) answers common questions offline.
        const offline = matchFaq(message, prefs.value.lang);
        if (offline) {
          bubbles.value = [
            ...bubbles.value,
            { id: nextBubbleId++, role: 'assistant', text: offline.answer, actions: offline.actions, chips: offline.chips },
          ];
        } else {
          errorMsg.value = t('error.internal');
        }
      }
    } finally {
      busy.value = false;
    }
  }

  function toggleMic() {
    if (dictationRef.current) {
      dictationRef.current.stop();
      dictationRef.current = null;
      return;
    }
    stopSpeaking(); // never speak while the mic is listening
    dictationRef.current = startDictation(
      prefs.value.lang,
      (text) => {
        draft.value = text;
      },
      () => {
        dictationRef.current = null;
      },
    );
  }

  /** One hands-free turn: listen, then either send what was heard or count a silent turn. Stops
   * itself after 2 silent turns in a row (assume the user stepped away). */
  function startHandsFreeTurn() {
    if (!handsFree.value || document.hidden || busy.value) return;
    stopSpeaking();
    let heardFinal = false;
    listening.value = true;
    dictationRef.current = startDictation(
      prefs.value.lang,
      (heard, isFinal) => {
        if (isFinal && heard.trim()) {
          heardFinal = true;
          silentTurns.current = 0;
          listening.value = false;
          dictationRef.current = null;
          void send(heard.trim());
        }
      },
      () => {
        dictationRef.current = null;
        listening.value = false;
        if (!handsFree.value || heardFinal) return;
        silentTurns.current += 1;
        if (silentTurns.current >= 2) {
          handsFree.value = false; // 2 silent turns - assume the user stepped away
        } else {
          startHandsFreeTurn();
        }
      },
    );
  }

  function toggleHandsFree() {
    if (handsFree.value) {
      handsFree.value = false;
      stopSpeaking();
      dictationRef.current?.stop();
      dictationRef.current = null;
      listening.value = false;
      return;
    }
    handsFree.value = true;
    silentTurns.current = 0;
    if (!busy.value) startHandsFreeTurn();
  }

  if (expired.value) {
    return (
      <main class="screen">
        <p role="alert">{t('ui.case_expired')}</p>
        <a class="btn btn-primary" href="/check">
          {t('ui.check_another')}
        </a>
      </main>
    );
  }

  const typing = busy.value && (toolStatus.value?.status === 'start' || bubbles.value[bubbles.value.length - 1]?.role === 'user');

  return (
    <main class="screen chat-screen" data-testid="chat-screen">
      {errorMsg.value && (
        <p role="alert" class="error-banner">
          <Icon name="alertCircle" size={18} /> {errorMsg.value}
        </p>
      )}

      {banner.value && (
        <p class={`chat-level-banner level-${banner.value.verdict.level}`}>
          {t(`level.${banner.value.verdict.level}.headline`)}{' '}
          <a class="btn-link" href={`/run/${banner.value.runId}?case=${realCaseId.value ?? ''}`}>
            {t('ui.view_full_result')}
          </a>
        </p>
      )}

      <div class="chat-messages" ref={listRef}>
        {bubbles.value.length === 0 && !busy.value && (
          <div class="chat-empty-state">
            <ChatArt size={200} />
            <h1>{t('ui.chat_empty_title')}</h1>
            <p>{t('ui.ask_hint')}</p>
            <div class="prompt-list">
              {EMPTY_STATE_CHIPS.map((key) => (
                <button key={key} type="button" class="chip chip-prompt" onClick={() => void send(t(key))}>
                  <span>{t(key)}</span>
                  <Icon name="arrowRight" size={16} />
                </button>
              ))}
            </div>
          </div>
        )}
        {bubbles.value.map((b) => (
          <div key={b.id} class={`chat-row chat-row-${b.role}`}>
            {b.role === 'assistant' && (
              <span class="chat-avatar" aria-hidden="true">
                <Shield size={32} />
              </span>
            )}
            <div class={`chat-bubble chat-${b.role}`} data-testid={b.role === 'assistant' ? 'chat-answer' : undefined}>
              <p>{b.text}</p>
              {b.role === 'assistant' && <SpeakerButton text={b.text} />}
              {b.refused && <p class="scope-hint">{t('ui.scope_hint')}</p>}
              {b.actions && b.actions.length > 0 && <ActionButtons ids={b.actions} />}
              {citeLinks(b.cites).length > 0 && (
                <div class="chips cite-chips">
                  {citeLinks(b.cites).map(({ href, label }) => (
                    <a key={href} class="chip chip-cite" href={href} data-testid="chat-cite">
                      <Icon name="learn" size={14} /> {t('ui.learn_more')}: {label}
                    </a>
                  ))}
                </div>
              )}
              {b.chips && b.chips.length > 0 && (
                <div class="chips chips-followup">
                  {b.chips.map((chip) => (
                    <button key={chip} type="button" class="chip" onClick={() => void send(chip)}>
                      {chip}
                    </button>
                  ))}
                </div>
              )}
            </div>
          </div>
        ))}
        {typing && (
          <div class="chat-row chat-row-assistant" aria-live="polite">
            <span class="chat-avatar" aria-hidden="true">
              <Shield size={32} />
            </span>
            <div class="chat-bubble chat-assistant chat-typing">
              <span class="typing-dots" aria-hidden="true">
                <i />
                <i />
                <i />
              </span>
              <span class="chat-tool-status">{t('ui.stage.answering')}</span>
            </div>
          </div>
        )}
      </div>

      <div class="chat-dock">
        {isDictationSupported() && (
          <div class="mic-row">
            <button type="button" class="tool-btn" data-testid="hands-free-toggle" aria-pressed={handsFree.value} onClick={toggleHandsFree}>
              <Icon name={handsFree.value ? 'close' : 'mic'} size={16} /> {handsFree.value ? t('ui.hands_free_stop') : t('ui.hands_free_on')}
            </button>
            {listening.value && <p class="listening" aria-live="polite">{t('ui.listening')}</p>}
          </div>
        )}
        <form
          class="chat-compose"
          onSubmit={(e) => {
            e.preventDefault();
            void send(draft.value);
          }}
        >
          {isDictationSupported() && (
            <button type="button" class="btn-mic" aria-label={t('ui.mic')} onClick={toggleMic}>
              <Icon name="mic" size={20} />
            </button>
          )}
          <input
            class="text-input"
            data-testid="chat-input"
            value={draft.value}
            disabled={busy.value}
            aria-label={t('ui.ask_hint')}
            placeholder={t('ui.ask_hint')}
            onInput={(e) => (draft.value = (e.target as HTMLInputElement).value)}
          />
          <button type="submit" class="btn btn-primary btn-send" data-testid="chat-send" disabled={busy.value || !draft.value.trim()}>
            <Icon name="send" size={18} />
            <span class="send-label">{t('ui.send')}</span>
          </button>
        </form>
        {isDictationSupported() && <p class="mic-disclosure">{t('ui.mic_disclosure')}</p>}
      </div>
    </main>
  );
}
