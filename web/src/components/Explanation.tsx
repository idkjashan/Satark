// The `explanation` event (CONTRACTS §6.1): a short summary, fuller reason sentences, and
// follow-up chips. Text is already translated server-side. Each chip is a plain link into
// /chat/:caseId with the question pre-filled via `?q=` (Chat.tsx sends it once on mount).
import { t } from '../lib/i18n';
import type { ExplanationEvent } from '../lib/runReducer';

interface ExplanationProps {
  explanation: ExplanationEvent;
  caseId: string;
}

export function Explanation({ explanation, caseId }: ExplanationProps) {
  return (
    <section class="explanation card" data-testid="explanation">
      <h3 class="section-label">{t('ui.plain_words')}</h3>
      <p class="explanation-summary">{explanation.summary}</p>
      {explanation.reasons.length > 0 && (
        <ul class="explanation-reasons">
          {explanation.reasons.map((r) => (
            <li key={r.code}>{r.text}</li>
          ))}
        </ul>
      )}
      {explanation.chips.length > 0 && (
        <div class="chips chips-followup">
          {explanation.chips.map((chip) => (
            <a key={chip} class="chip" href={`/chat/${caseId}?q=${encodeURIComponent(chip)}`}>
              {chip}
            </a>
          ))}
        </div>
      )}
    </section>
  );
}
