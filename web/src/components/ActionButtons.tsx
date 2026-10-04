// Renders verdict.actions / answer.actions (<=3 ids) as buttons, per content/portals.json
// (CONTRACTS §9, LLD §21.2): call -> tel: link, portal -> new tab, route -> in-app navigation,
// share -> navigator.share with clipboard fallback, info -> expands its own label text in full.
// `route` and `call` are plain <a> - preact-iso's LocationProvider intercepts same-origin link
// clicks itself, so an in-app link needs no onClick/useLocation plumbing.
import { useState } from 'preact/hooks';
import { t } from '../lib/i18n';
import { resolveAction, resolvePortal } from '../lib/portals';
import { Icon } from './Icon';

export function ActionButtons({ ids }: { ids: string[] }) {
  if (!ids.length) return null;
  return (
    <div class="actions" data-testid="actions">
      {ids.map((id) => (
        <ActionButton key={id} id={id} />
      ))}
    </div>
  );
}

function ActionButton({ id }: { id: string }) {
  const [expanded, setExpanded] = useState(false);
  const [copied, setCopied] = useState(false);
  const action = resolveAction(id);
  const label = t(`action.${id}`);
  const testId = `action-${id}`;

  if (!action) return null;

  if (action.kind === 'call') {
    const phone = action.phone ?? resolvePortal(action.portal)?.phone ?? '';
    return (
      <a class="btn btn-action" data-testid={testId} href={`tel:${phone}`}>
        <Icon name="phone" size={18} /> {label}
      </a>
    );
  }

  if (action.kind === 'portal') {
    const url = resolvePortal(action.portal)?.url ?? '#';
    return (
      <a class="btn btn-action" data-testid={testId} href={url} target="_blank" rel="noopener noreferrer">
        <Icon name="globe" size={18} /> {label}
      </a>
    );
  }

  if (action.kind === 'route') {
    return (
      <a class="btn btn-action" data-testid={testId} href={action.route ?? '#'}>
        {label} <Icon name="chevronRight" size={18} />
      </a>
    );
  }

  if (action.kind === 'share') {
    return (
      <button
        type="button"
        class="btn btn-action"
        data-testid={testId}
        onClick={async () => {
          const text = t('ui.share_warning_text');
          if (navigator.share) {
            try {
              await navigator.share({ text });
              return;
            } catch {
              // user cancelled, or the platform doesn't support it - fall through to clipboard
            }
          }
          try {
            await navigator.clipboard.writeText(text);
            setCopied(true);
            setTimeout(() => setCopied(false), 2000);
          } catch {
            // no clipboard access either; the label stays as-is
          }
        }}
      >
        <Icon name="share" size={18} /> {copied ? t('ui.copied') : label}
      </button>
    );
  }

  // info: a short, always-visible explanation; collapsed view just clips it with CSS.
  return (
    <button
      type="button"
      class="btn btn-action btn-info"
      data-testid={testId}
      aria-expanded={expanded}
      onClick={() => setExpanded((e) => !e)}
    >
      <span class={expanded ? undefined : 'truncate'}>{label}</span>
    </button>
  );
}
