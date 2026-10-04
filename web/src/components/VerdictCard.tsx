// The verdict card (CONTRACTS §6.1, LLD §22.1): colour band + icon + headline + confidence,
// <=3 reasons with source chips, "what we could not check", <=3 action buttons, and the links
// into a simulator or lesson. Reason titles come from the event itself (already translated and
// unmasked server-side) - the PWA never re-derives wording from a signal code here.
import { useEffect, useRef } from 'preact/hooks';
import { t } from '../lib/i18n';
import { prefs } from '../lib/signals';
import { getLesson, pick } from '../lib/lessons';
import { speak } from '../lib/voice';
import { SourceChip } from './SourceChip';
import { ActionButtons } from './ActionButtons';
import { SpeakerButton } from './SpeakerButton';
import { FeedbackRow } from './FeedbackRow';
import { Icon, type IconName } from './Icon';
import type { VerdictEvent } from '../lib/runReducer';

const LEVEL_ICON: Record<string, IconName> = {
  HIGH_RISK: 'warningTriangle',
  SUSPICIOUS: 'alertCircle',
  NO_SIGNS: 'checkCircle',
  UNKNOWN: 'helpCircle',
};

export function VerdictCard({ verdict, caseId }: { verdict: VerdictEvent; caseId?: string }) {
  const headingRef = useRef<HTMLHeadingElement>(null);
  const isHigh = verdict.level === 'HIGH_RISK';
  const say = t(`level.${verdict.level}.say`);
  const spokenLevelRef = useRef<string | null>(null);

  // HIGH_RISK moves focus to the heading (role="alert" needs it to actually be announced).
  useEffect(() => {
    if (isHigh) headingRef.current?.focus();
  }, [isHigh, verdict.revision]);

  // Auto-speak in Simple mode; a speaker button covers everyone else. The first verdict speaks
  // its full "say" sentence; a later AI-reviewed revision speaks only a short update, and only
  // when the level actually changed - an unchanged verdict (rules and the AI review agree) is
  // never repeated.
  useEffect(() => {
    if (!prefs.value.simple) return;
    if (spokenLevelRef.current === null) {
      spokenLevelRef.current = verdict.level;
      void speak(say);
    } else if (spokenLevelRef.current !== verdict.level) {
      spokenLevelRef.current = verdict.level;
      void speak(t('ui.ai_review_update', { headline: t(`level.${verdict.level}.headline`) }));
    }
  }, [verdict.level, verdict.revision]);

  // A story or awareness post about a scam: say so instead of "no strong risk signs" (level stays NO_SIGNS).
  const about = !!verdict.about_scam && verdict.level === 'NO_SIGNS';
  const scamType = (verdict.scam_type && t(`scam_type.${verdict.scam_type}`)) || t('ui.about_scam_generic');
  const headline = about ? t('ui.about_scam_title', { type: scamType }) : t(`level.${verdict.level}.headline`);
  // The one-line "why/what now" under the headline. A news story gets its own sentence.
  const why = about ? t('ui.about_scam_headline', { type: scamType }) : say;
  const couldNotCheck = verdict.checked.filter((c) => c.status === 'unknown');

  return (
    <section
      class={`verdict-card level-${verdict.level}${about ? ' is-about' : ''}`}
      data-testid="verdict-card"
      data-level={verdict.level}
      role={isHigh ? 'alert' : undefined}
    >
      <header class="verdict-head">
        <span class="verdict-icon" aria-hidden="true">
          <Icon name={about ? 'news' : LEVEL_ICON[verdict.level]} size={34} />
        </span>
        <div class="verdict-title">
          <h2 class="verdict-headline" data-testid="verdict-headline" tabIndex={-1} ref={headingRef}>
            {headline}
          </h2>
          <p class="verdict-why">{why}</p>
        </div>
      </header>

      <div class="verdict-meta">
        <span class="pill verdict-confidence">{t(`confidence.${verdict.confidence}`)}</span>
        {verdict.ai_reviewed && (
          <span class="pill ai-reviewed-badge">
            <Icon name="checkCircle" size={14} />
            {t('ui.ai_reviewed_badge')}
          </span>
        )}
        <SpeakerButton text={say} />
      </div>

      {verdict.reasons.length > 0 && (
        <>
          <h3 class="section-label">{t('ui.why_title')}</h3>
          <ol class="reasons" data-testid="reasons">
            {verdict.reasons.map((reason) => (
              <li key={reason.code} class="reason" data-testid={`reason-${reason.code}`}>
                <p>{reason.title}</p>
                <SourceChip id={reason.source.id} asOn={reason.source.as_on} />
              </li>
            ))}
          </ol>
        </>
      )}

      {couldNotCheck.length > 0 && (
        <p class="could-not-check">
          {t('explain.could_not_check', {
            families: couldNotCheck.map((c) => t(`family.${c.family}`)).join(', '),
          })}
        </p>
      )}

      {verdict.actions.length > 0 && <h3 class="section-label">{t('ui.what_to_do')}</h3>}
      {/* The generic "learn" action (-> /learn) duplicates the specific lesson link below. */}
      <ActionButtons ids={verdict.lesson ? verdict.actions.filter((a) => a !== 'learn') : verdict.actions} />

      <div class="verdict-links">
        {verdict.simulator && (
          <a class="btn btn-link" href={`/sim/${verdict.simulator}${verdict.sim_params ? `?rate=${verdict.sim_params.rate}&period=${verdict.sim_params.period}` : ''}`}>
            {t('ui.see_how_this_trap_works')} <Icon name="chevronRight" size={16} />
          </a>
        )}
        {verdict.lesson && (
          <a class="btn btn-link" href={`/learn/${verdict.lesson}`}>
            {t('ui.learn_more')}
            {getLesson(verdict.lesson) ? `: ${pick(getLesson(verdict.lesson)!.title, prefs.value.lang)}` : ''}{' '}
            <Icon name="chevronRight" size={16} />
          </a>
        )}
        {/* Bug fix (QA, Oct 2026): neither default_actions nor any signal's actions list ever
            include draft_complaint (config/scoring.yaml, config/signals.yaml are contract files
            this role doesn't own), so someone who already paid had no in-app way to reach
            /help-paid from a HIGH_RISK/SUSPICIOUS verdict with this case's evidence still
            attached (lastCaseId is memory-only - a typed/bookmarked URL loses it). This is the
            one link that matters most right after a bad verdict, so it is always shown here. */}
        {(verdict.level === 'HIGH_RISK' || verdict.level === 'SUSPICIOUS') && (
          <a class="btn btn-link" href="/help-paid">
            {t('action.draft_complaint')}
          </a>
        )}
      </div>

      <FeedbackRow caseId={caseId} level={verdict.level} reasonCodes={verdict.reasons.map((r) => r.code)} />
    </section>
  );
}
