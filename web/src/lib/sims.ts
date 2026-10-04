// Simulator content (CONTRACTS §7.3): content/sims/S1.json, S4-S6.json (fsm), S2.json (returns),
// S3.json (leverage). Loaded eagerly, raw - each player casts to its own engine's shape, since
// the kinds share nothing but an `id`/`kind`/`title`/optional `quiz` (lib/lessons.ts QuizQuestion).
import type { QuizQuestion } from './lessons';

export interface SimMeta {
  id: string;
  kind: 'fsm' | 'returns' | 'leverage';
  title?: Record<string, string>;
  quiz?: QuizQuestion | QuizQuestion[];
}

const modules = import.meta.glob<SimMeta>('@content/sims/*.json', { eager: true, import: 'default' });
export const sims: SimMeta[] = Object.values(modules);

export function getSim<T extends SimMeta>(id: string): T | undefined {
  return sims.find((s) => s.id === id) as T | undefined;
}
