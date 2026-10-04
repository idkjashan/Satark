// Live checklist (LLD §22.1), now "How Satark checked this" (agent harness, Oct 2026): the rule
// checks (one row per family in the plan) plus, once the model's tool-use loop starts, one row
// per `agent_step` action. Status is icon + word, never colour alone. aria-live="polite" so
// screen readers announce each row as it settles. Wrapped in <details> so it is collapsible once
// finished - a native disclosure widget, so no extra JS state is needed for that.
import { t } from '../lib/i18n';
import { familiesInPlan, familyRowStatus, familyProofs, agentStepRows, type Proof, type RunState } from '../lib/runReducer';
import { Icon, type IconName } from './Icon';

const ICON: Record<string, IconName> = { checking: 'loader', done: 'checkCircle', unknown: 'helpCircle', skipped: 'close' };

// Older servers narrate a single tool call at a time with no `label` (product update, Oct 2026:
// a check run, not only chat, could already narrate its own tool use before agent_step existed).
// Any tool not listed here (future additions) simply shows no activity line rather than a raw,
// untranslated tool id. Superseded by the per-step rows below once a run sends any agent_step.
const TOOL_LABEL: Record<string, string> = {
  check_entities: 'ui.tool.check_entities',
  search_registry: 'ui.tool.search_registry',
  load_skill: 'ui.tool.load_skill',
  add_entity: 'ui.tool.add_entity',
};

// A row may read as a pass only when its check ran: an unknown result says "Could not check" and why.
function ProofItem({ proof }: { proof: Proof }) {
  return (
    <li class={`proof-item outcome-${proof.outcome}`} data-testid="proof-item">
      <p class="proof-outcome">{t(`ui.proof.${proof.outcome}`)}</p>
      <p>
        <span class="proof-key">{t('ui.proof.checked')}</span> {proof.checked}
      </p>
      <p>
        <span class="proof-key">{t('ui.proof.source')}</span> {proof.source_name},{' '}
        {proof.live ? t('ui.proof.live') : proof.as_on ?? ''}
      </p>
      <p>
        <span class="proof-key">{t('ui.proof.result')}</span> {proof.result}
        {proof.why ? ` (${proof.why})` : ''}
      </p>
      {proof.items?.map((it) => (
        <p key={it.url}>
          <a href={it.url} target="_blank" rel="noopener noreferrer">{it.title}</a>
        </p>
      ))}
      {proof.url && (
        <a class="proof-verify" href={proof.url} target="_blank" rel="noopener noreferrer">{t('ui.proof.verify')}</a>
      )}
    </li>
  );
}

export function Checklist({ run }: { run: RunState }) {
  const families = familiesInPlan(run);
  const steps = agentStepRows(run);
  // Only fall back to the single-row legacy display when this run never sent an agent_step at
  // all - once it does, the per-step rows below already cover every tool call it narrates.
  const legacyToolLabel =
    steps.length === 0 && run.toolStatus?.status === 'start'
      ? run.toolStatus.label ?? (TOOL_LABEL[run.toolStatus.tool] ? t(TOOL_LABEL[run.toolStatus.tool]) : undefined)
      : undefined;
  if (!families.length && !legacyToolLabel && !steps.length) return null;

  return (
    <details class="activity-timeline" data-testid="activity-timeline" open>
      <summary>{t('ui.how_checked_title')}</summary>
      <ul class="checklist" data-testid="checklist" aria-live="polite">
        {families.map((family) => {
          const status = familyRowStatus(family, run);
          return (
            <li key={family} class={`checklist-row checklist-row-proof status-${status}`} data-testid={`checklist-row-${family}`}>
              <details>
                <summary class="checklist-row-main">
                  <span class="checklist-icon" aria-hidden="true">
                    <Icon name={ICON[status]} size={18} spin={status === 'checking'} />
                  </span>
                  <span class="checklist-label">{t(`family.${family}`)}</span>
                  <span class="checklist-status">{t(`ui.checklist.${status}`)}</span>
                </summary>
                <ul class="proof-list">
                  {familyProofs(family, run).map((p, i) => <ProofItem key={i} proof={p} />)}
                </ul>
              </details>
            </li>
          );
        })}
        {legacyToolLabel && (
          <li class="checklist-row checklist-row-tool" data-testid="checklist-row-tool">
            <span class="checklist-icon" aria-hidden="true">
              <Icon name="loader" size={18} spin />
            </span>
            <span class="checklist-label">{legacyToolLabel}</span>
          </li>
        )}
      </ul>

      {steps.map((step) => (
        <div key={step.step} class="agent-step" data-testid={`agent-step-${step.step}`}>
          {step.thought && <p class="agent-step-thought">{step.thought}</p>}
          <ul class="checklist" aria-live="polite">
            {step.actions.map((action, i) => (
              <li key={i} class={`checklist-row status-${action.status}`} data-testid={`agent-action-${step.step}-${i}`}>
                <span class="checklist-icon" aria-hidden="true">
                  <Icon name={ICON[action.status]} size={18} spin={action.status === 'checking'} />
                </span>
                <span class="checklist-label">{action.label}</span>
                <span class="checklist-status">{t(`ui.checklist.${action.status}`)}</span>
                {run.toolCalls[action.label]?.proof && (
                  <details class="proof-inline"><summary>{t('ui.proof.show')}</summary>
                    <ul class="proof-list"><ProofItem proof={run.toolCalls[action.label].proof!} /></ul>
                  </details>
                )}
              </li>
            ))}
          </ul>
        </div>
      ))}
    </details>
  );
}
