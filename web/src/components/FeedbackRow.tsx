// "Was this helpful? / Report a mistake" (product spec, Oct 2026) -> POST /v1/feedback
// {case_id, kind, level, reason_codes}. Anonymous and fire-and-forget (CONTRACTS §6: 204, no
// body) - a network failure just leaves the row as it was, since this is feedback, not a task the
// user is blocked on.
import { useState } from 'preact/hooks';
import { t } from '../lib/i18n';
import { postFeedback } from '../lib/api';
import { Icon } from './Icon';

interface FeedbackRowProps {
  caseId?: string;
  level: string;
  reasonCodes: string[];
}

export function FeedbackRow({ caseId, level, reasonCodes }: FeedbackRowProps) {
  const [sent, setSent] = useState(false);
  const [busy, setBusy] = useState(false);

  async function send(kind: 'helpful' | 'mistake') {
    if (busy || sent) return;
    setBusy(true);
    try {
      await postFeedback({ case_id: caseId, kind, level, reason_codes: reasonCodes });
    } catch {
      // offline or rate-limited - there is nothing actionable to tell the user about feedback
    } finally {
      setBusy(false);
      setSent(true);
    }
  }

  if (sent) return <p class="feedback-row feedback-sent">{t('ui.feedback_thanks')}</p>;

  return (
    <div class="feedback-row">
      <span class="feedback-question">{t('ui.feedback_question')}</span>
      <button type="button" class="btn btn-action" disabled={busy} onClick={() => void send('helpful')}>
        <Icon name="thumbUp" size={18} />
        {t('ui.feedback_helpful')}
      </button>
      <button type="button" class="btn btn-action" disabled={busy} onClick={() => void send('mistake')}>
        <Icon name="flag" size={18} />
        {t('ui.feedback_mistake')}
      </button>
    </div>
  );
}
