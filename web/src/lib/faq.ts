// Offline chat fallback (CONTRACTS §7.4, content/faq.json). Used only when POST /v1/chat can't
// be reached at all (no network) - Chat.tsx still answers common questions from this local copy
// instead of just failing. Pattern matching is a simple case-insensitive substring test: good
// enough for a fixed, short list of canned intents, and avoids pulling in a matching library.
export type LangText = Record<string, string>;

interface FaqIntent {
  id: string;
  patterns: string[];
  answer: LangText;
  actions?: string[];
  chips?: Record<string, string[]>;
}
interface FaqData {
  intents: FaqIntent[];
  fallback: { answer: LangText; chips?: Record<string, string[]> };
}

const modules = import.meta.glob<FaqData>('@content/faq.json', { eager: true, import: 'default' });
const faq: FaqData | null = Object.values(modules)[0] ?? null;

export interface FaqMatch {
  answer: string;
  actions: string[];
  chips: string[];
}

export function matchFaq(message: string, lang: string): FaqMatch | null {
  if (!faq) return null;
  const text = message.toLowerCase();
  const intent = faq.intents.find((i) => i.patterns.some((p) => text.includes(p.toLowerCase())));
  const answer = intent?.answer ?? faq.fallback.answer;
  const chips = intent?.chips ?? faq.fallback.chips ?? {};
  return {
    answer: answer[lang] ?? answer.en ?? '',
    actions: intent?.actions ?? [],
    chips: chips[lang] ?? chips.en ?? [],
  };
}
