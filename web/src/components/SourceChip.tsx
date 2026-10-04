// "SEBI register · 3 Oct" (LLD §22.1). `id` is a config/sources.yaml id; its display name is
// content `source.<id>` (engineer G). Renders nothing when there's no source to cite.
import { t } from '../lib/i18n';
import { formatAsOn } from '../lib/format';
import { prefs } from '../lib/signals';
import { Icon } from './Icon';

interface SourceChipProps {
  id: string | null;
  asOn: string | null;
}

export function SourceChip({ id, asOn }: SourceChipProps) {
  if (!id) return null;
  const date = formatAsOn(asOn, prefs.value.lang);
  return (
    <span class="source-chip">
      <Icon name="landmark" size={13} />
      {t(`source.${id}`)}
      {date ? ` · ${date}` : ''}
    </span>
  );
}
