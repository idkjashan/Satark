// ask_user (CONTRACTS §6.1): the harness needs one more answer before it can plan or verdict.
// Special case (product requirement, Oct 2026 scope guardrails): question_id "off_topic" means
// the input wasn't an investment message at all (a coding question, homework, a poem, ...) - show
// its text with one big "Check another message" button instead of options or free text.
import { useState } from 'preact/hooks';
import { t } from '../lib/i18n';
import type { AskUserEvent } from '../lib/runReducer';

interface AskUserProps {
  askUser: AskUserEvent;
  busy?: boolean;
  onChoice: (optionId: string) => void;
  onText: (text: string) => void;
}

export function AskUser({ askUser, busy, onChoice, onText }: AskUserProps) {
  const [text, setText] = useState('');

  if (askUser.question_id === 'off_topic') {
    return (
      <div class="ask-user" data-testid="ask-user">
        <p>{askUser.text}</p>
        <a class="btn btn-primary btn-big" href="/check">
          {t('ui.check_another')}
        </a>
      </div>
    );
  }

  return (
    <div class="ask-user" data-testid="ask-user">
      <p>{askUser.text}</p>
      {askUser.options.length > 0 ? (
        <div class="ask-user-options">
          {askUser.options.map((opt) => (
            <button key={opt.id} type="button" class="btn" disabled={busy} onClick={() => onChoice(opt.id)}>
              {opt.label}
            </button>
          ))}
        </div>
      ) : (
        <form
          onSubmit={(e) => {
            e.preventDefault();
            if (text.trim()) onText(text.trim());
          }}
        >
          <input
            class="text-input"
            value={text}
            disabled={busy}
            placeholder={t('ui.ask_hint')}
            onInput={(e) => setText((e.target as HTMLInputElement).value)}
          />
          <button type="submit" class="btn btn-primary" disabled={busy || !text.trim()}>
            {t('ui.send')}
          </button>
        </form>
      )}
    </div>
  );
}
