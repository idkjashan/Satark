// Voice out (LLD §24). speechSynthesis only in this build - no server TTS.
import { prefs } from './signals';

// Mirrors config/languages.yaml `speech` tags; the PWA has no YAML loader so this is a small
// static mirror, not a second source of truth for which languages are enabled.
const SPEECH_TAGS: Record<string, string> = {
  en: 'en-IN',
  hi: 'hi-IN',
  mr: 'mr-IN',
  bn: 'bn-IN',
  ta: 'ta-IN',
  te: 'te-IN',
};

export function speechTagFor(lang: string): string {
  return SPEECH_TAGS[lang] ?? 'en-IN';
}

let voicesReady: Promise<SpeechSynthesisVoice[]> | null = null;

function waitForVoices(): Promise<SpeechSynthesisVoice[]> {
  if (typeof speechSynthesis === 'undefined') return Promise.resolve([]);
  const existing = speechSynthesis.getVoices();
  if (existing.length) return Promise.resolve(existing);
  voicesReady ??= new Promise((resolve) => {
    const timer = setTimeout(() => resolve(speechSynthesis.getVoices()), 1000);
    speechSynthesis.addEventListener(
      'voiceschanged',
      () => {
        clearTimeout(timer);
        resolve(speechSynthesis.getVoices());
      },
      { once: true },
    );
  });
  return voicesReady;
}

/** Speaks `text` in `lang`. Returns {spoken:false} when no voice exists for that language. */
export async function speak(text: string, lang: string = prefs.value.lang): Promise<{ spoken: boolean }> {
  if (typeof speechSynthesis === 'undefined' || !text.trim()) return { spoken: false };
  const tag = speechTagFor(lang);
  const voices = await waitForVoices();
  const voice =
    voices.find((v) => v.lang === tag) ?? voices.find((v) => v.lang.toLowerCase().startsWith(lang.toLowerCase()));
  if (!voice) return { spoken: false };
  speechSynthesis.cancel(); // one utterance at a time
  const utterance = new SpeechSynthesisUtterance(text);
  utterance.lang = tag;
  utterance.voice = voice;
  utterance.rate = prefs.value.rate || 1;
  // Waits for playback to actually finish (not just for the call to speechSynthesis.speak to
  // return) so a caller can safely sequence "speak, then start listening" - hands-free chat
  // needs that to never have the mic and the voice live at the same time.
  await new Promise<void>((resolve) => {
    utterance.onend = () => resolve();
    utterance.onerror = () => resolve();
    speechSynthesis.speak(utterance);
  });
  return { spoken: true };
}

export function stopSpeaking(): void {
  if (typeof speechSynthesis !== 'undefined') speechSynthesis.cancel();
}
