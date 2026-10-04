// Voice in: webkitSpeechRecognition dictation for the /check textarea and /chat input
// (LLD §24). Chrome on Android sends the audio to Google's servers for this - callers must
// disclose that before first use. No MediaRecorder/server-transcription fallback in this build.
import { speechTagFor } from './voice';

export function isDictationSupported(): boolean {
  return typeof window !== 'undefined' && !!window.webkitSpeechRecognition;
}

export interface Dictation {
  stop: () => void;
}

/**
 * Starts one dictation turn. `onResult` fires on every recognised chunk - interim ones as the
 * words are heard, then a final one with `isFinal: true` - so a caller can show live interim
 * text in an input field; `onEnd` fires once when the turn stops (silence, an error, or `stop()`).
 */
export function startDictation(
  lang: string,
  onResult: (text: string, isFinal: boolean) => void,
  onEnd?: () => void,
): Dictation | null {
  const Ctor = typeof window !== 'undefined' ? window.webkitSpeechRecognition : undefined;
  if (!Ctor) return null;
  const recognition = new Ctor();
  recognition.lang = speechTagFor(lang);
  recognition.interimResults = true;
  recognition.maxAlternatives = 1;
  recognition.onresult = (event) => {
    const results = Array.from(event.results);
    const text = results.map((r) => r[0].transcript).join(' ');
    const isFinal = results.length > 0 && !!results[results.length - 1].isFinal;
    onResult(text, isFinal);
  };
  recognition.onerror = () => onEnd?.();
  recognition.onend = () => onEnd?.();
  recognition.start();
  return { stop: () => recognition.stop() };
}
