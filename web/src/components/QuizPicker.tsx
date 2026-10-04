// "Make me a quiz on..." - a lesson dropdown plus Start; goes to /quiz (model-written, static fallback).
import { useState } from 'preact/hooks';
import { t } from '../lib/i18n';
import { prefs } from '../lib/signals';
import { lessons, pick } from '../lib/lessons';

export function QuizPicker() {
  const [topic, setTopic] = useState(lessons[0]?.id ?? '');
  if (!lessons.length) return null;
  return (
    <section class="quiz-picker card">
      <label class="eyebrow" for="quiz-topic">
        {t('ui.make_quiz')}
      </label>
      <div class="quiz-picker-row">
        <select id="quiz-topic" class="text-input" data-testid="quiz-topic" value={topic} onChange={(e) => setTopic((e.target as HTMLSelectElement).value)}>
          {lessons.map((l) => (
            <option key={l.id} value={l.id}>
              {pick(l.title, prefs.value.lang)}
            </option>
          ))}
        </select>
        <a class="btn btn-primary" data-testid="quiz-start" href={`/quiz?topic=${encodeURIComponent(topic)}`}>
          {t('ui.start_quiz')}
        </a>
      </div>
    </section>
  );
}
