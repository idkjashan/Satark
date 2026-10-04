// /help-paid (CONTRACTS §6 `POST /v1/report-draft`, LLD §21.2): urgent action first - call 1930,
// call the bank, report online - all client-side and work offline. Only the complaint-text draft
// needs the network; it falls back to a local template when there's no case or no connection.
import { useState } from 'preact/hooks';
import { t } from '../lib/i18n';
import { prefs } from '../lib/signals';
import { postReportDraft, lastCaseId } from '../lib/api';
import { Icon } from '../components/Icon';

type When = 'within_1h' | 'today' | 'earlier';
type HowPaid = 'upi' | 'bank' | 'card' | 'crypto' | 'cash';
type AmountBand = 'below_10000' | '10000_100000' | '100000_1000000' | 'above_1000000';

export function HelpPaid() {
  const [when, setWhen] = useState<When>('today');
  const [howPaid, setHowPaid] = useState<HowPaid>('upi');
  const [amountBand, setAmountBand] = useState<AmountBand>('10000_100000');
  const [draftText, setDraftText] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [loading, setLoading] = useState(false);

  async function generateDraft() {
    setLoading(true);
    setCopied(false);
    const caseId = lastCaseId.value;
    if (caseId) {
      try {
        const draft = await postReportDraft({
          case_id: caseId,
          lang: prefs.value.lang,
          answers: { when, how_paid: howPaid, amount_band: amountBand },
        });
        setDraftText(draft.text_lang || draft.text_en);
        setLoading(false);
        return;
      } catch {
        // offline, expired case, or the server is busy - fall through to the local template
      }
    }
    // No case (or the server didn't answer): compose the same template the server would from
    // content.<lang>.json `report.*` (G's keys), just without evidence-based reasons/identifiers.
    setDraftText(
      [
        t('report.intro'),
        t('report.when', { when: t(`ui.when_${when}`) }),
        t('report.how_paid', { how_paid: t(`ui.pay_${howPaid}`) }),
        t('report.closing'),
      ].join(' '),
    );
    setLoading(false);
  }

  async function copyDraft() {
    if (!draftText) return;
    try {
      await navigator.clipboard.writeText(draftText);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // no clipboard access - the text is still visible to select and copy by hand
    }
  }

  return (
    <main class="screen help-paid-screen">
      <h1>{t('ui.already_paid')}</h1>

      <ol class="help-steps">
        <li data-testid="help-step-1">
          <a class="btn btn-primary btn-huge" href="tel:1930">
            <Icon name="phone" size={26} /> {t('ui.call_1930_now')}
          </a>
        </li>
        <li data-testid="help-step-2">{t('ui.call_your_bank')}</li>
        <li data-testid="help-step-3">
          <a class="btn btn-link" href="https://cybercrime.gov.in" target="_blank" rel="noopener noreferrer">
            {t('ui.report_online')}
          </a>
        </li>
        <li data-testid="help-step-4">
          <p>{t('ui.complaint_text_intro')}</p>

          <fieldset>
            <legend>{t('ui.when_question')}</legend>
            {(['within_1h', 'today', 'earlier'] as When[]).map((v) => (
              <label key={v} class="radio-row">
                <input type="radio" name="when" checked={when === v} onChange={() => setWhen(v)} />
                {t(`ui.when_${v}`)}
              </label>
            ))}
          </fieldset>

          <fieldset>
            <legend>{t('ui.how_paid_question')}</legend>
            {(['upi', 'bank', 'card', 'crypto', 'cash'] as HowPaid[]).map((v) => (
              <label key={v} class="radio-row">
                <input type="radio" name="how_paid" checked={howPaid === v} onChange={() => setHowPaid(v)} />
                {t(`ui.pay_${v}`)}
              </label>
            ))}
          </fieldset>

          <fieldset>
            <legend>{t('ui.amount_question')}</legend>
            {(['below_10000', '10000_100000', '100000_1000000', 'above_1000000'] as AmountBand[]).map((v) => (
              <label key={v} class="radio-row">
                <input type="radio" name="amount_band" checked={amountBand === v} onChange={() => setAmountBand(v)} />
                {t(`ui.band_${v}`)}
              </label>
            ))}
          </fieldset>

          <button type="button" class="btn btn-primary" onClick={() => void generateDraft()} disabled={loading}>
            {t('ui.generate_complaint_text')}
          </button>

          {draftText && (
            <div class="report-draft">
              <textarea readOnly rows={6} value={draftText} />
              <button type="button" class="btn" onClick={() => void copyDraft()}>
                {copied ? t('ui.copied') : t('ui.copy')}
              </button>
            </div>
          )}
        </li>
      </ol>

      <p class="warning-banner" role="alert">
        <Icon name="warningTriangle" size={20} /> {t('ui.recovery_agent_warning')}
      </p>
    </main>
  );
}
