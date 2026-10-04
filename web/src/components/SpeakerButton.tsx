// A reusable "listen" button (LLD §24 voice out). If this phone has no speechSynthesis voice for
// the language, says so instead of just staying silent - there is no server TTS in this build.
import { useState } from 'preact/hooks';
import { t } from '../lib/i18n';
import { speak } from '../lib/voice';
import { Icon } from './Icon';

export function SpeakerButton({ text, lang }: { text: string; lang?: string }) {
  const [unavailable, setUnavailable] = useState(false);

  return (
    <>
      <button
        type="button"
        class="btn-speaker"
        aria-label={t('ui.listen')}
        onClick={async () => {
          const { spoken } = await speak(text, lang);
          setUnavailable(!spoken);
        }}
      >
        <Icon name="speaker" size={18} /> {t('ui.listen')}
      </button>
      {unavailable && <p class="voice-unavailable">{t('ui.voice_unavailable')}</p>}
    </>
  );
}
