// /sim/:id (CONTRACTS §7.3, LLD §23): three simulator kinds share this route. No LLM anywhere -
// S1 is a fixed-grammar state machine, S2 is plain compounding maths, S3 is a seeded,
// reproducible illustrative path. Content (text, defaults, the closing fact) comes from
// content/sims/<id>.json; the maths lives here in the PWA.
import { useMemo, useState } from 'preact/hooks';
import { t, interpolate } from '../lib/i18n';
import { prefs } from '../lib/signals';
import { pick, quizQuestions, type LangText, type QuizQuestion } from '../lib/lessons';
import { getSim } from '../lib/sims';
import { recordSimOutcome } from '../lib/idb';
import { formatINRWords, formatNumber } from '../lib/format';
import { SpeakerButton } from '../components/SpeakerButton';
import { QuizFlow } from '../components/QuizFlow';
import {
  s1Start,
  s1Choose,
  s1Node,
  s1IsEnd,
  s1Text,
  type S1Scenario,
  type S1RunState,
} from '../lib/sim/s1';
import { s2Project, type Period } from '../lib/sim/s2';
import { s3Run, S3_STEPS, type S3Status } from '../lib/sim/s3';

/** Fills a content template (e.g. "₹{amount} at {rate}%...") and falls back to "" cleanly. */
function render(text: LangText | undefined, lang: string, vars: Record<string, string | number>): string {
  return interpolate(pick(text, lang), vars);
}

interface SimPlayerProps {
  id: string;
}

export function SimPlayer({ id }: SimPlayerProps) {
  const sim = getSim(id);
  if (!sim) {
    return (
      <main class="screen">
        <p>{t('ui.sim_not_found')}</p>
        <a class="btn" href="/practice">
          {t('ui.practice')}
        </a>
      </main>
    );
  }
  if (sim.kind === 'fsm') return <S1Player scenario={sim as unknown as S1Scenario} />;
  if (sim.kind === 'returns') return <S2Player content={sim as S2Content} />;
  return <S3Player content={sim as S3Content} />;
}

// ---- S1: the fake trading-app trap (finite-state machine) -------------------------------------

function S1Player({ scenario }: { scenario: S1Scenario }) {
  const lang = prefs.value.lang;
  const [state, setState] = useState<S1RunState>(() => s1Start(scenario));
  const [showQuiz, setShowQuiz] = useState(false);
  const node = s1Node(scenario, state);
  const isEnd = s1IsEnd(scenario, state);

  if (!node) {
    return <p>{t('ui.sim_not_found')}</p>;
  }

  if (isEnd && showQuiz && scenario.quiz) {
    return (
      <main class="screen" data-testid="sim-quiz">
        <QuizFlow questions={quizQuestions(scenario.quiz)} doneHref="/practice" />
      </main>
    );
  }

  if (isEnd) {
    const text = s1Text(node.reveal, lang, state.vars);
    return (
      <main class="screen" data-testid="sim-end">
        <h1>{text}</h1>
        <p data-testid="sim-balance">{t('ui.lost_amount', { amount: formatNumber(state.vars.lost ?? 0) })}</p>
        <SpeakerButton text={text} lang={lang} />
        <button
          type="button"
          class="btn btn-primary btn-huge"
          onClick={() => {
            void recordSimOutcome(scenario.id, node.end ?? 'unknown');
            if (scenario.quiz) setShowQuiz(true);
          }}
        >
          {scenario.quiz ? t('ui.quiz') : t('ui.done')}
        </button>
      </main>
    );
  }

  const text = s1Text(node.say, lang, state.vars);

  return (
    <main class="screen">
      <h1>{pick(scenario.title, lang)}</h1>
      <p>{text}</p>
      <p data-testid="sim-balance">{formatINRWords(state.vars.balance ?? 0)}</p>
      <div class="sim-choices">
        {(node.choices ?? []).map((choice) => (
          <button
            key={choice.id}
            type="button"
            class="btn btn-primary btn-huge"
            data-testid={`sim-choice-${choice.id}`}
            onClick={() => setState(s1Choose(scenario, state, choice.id))}
          >
            {pick(choice.label, lang)}
          </button>
        ))}
      </div>
    </main>
  );
}

// ---- S2: the "guaranteed return" calculator ----------------------------------------------------
// content/sims/S2.json: {title, texts: {prompt, result, impossible, benchmark}, defaults}.

interface S2Content {
  id: string;
  title?: LangText;
  texts?: { prompt?: LangText; result?: LangText; impossible?: LangText; benchmark?: LangText };
  defaults?: { rate?: number; period?: Period; amount?: number };
  quiz?: QuizQuestion | QuizQuestion[];
}

/** Decorative only (aria-hidden) - the real numbers are the <li> list right next to it; this is
 * just a visual sense of how fast the bars grow, scaled by sqrt so month 1 stays visible next to
 * year 1. */
function ProjectionBars({ values }: { values: number[] }) {
  const scaled = values.map((v) => Math.sqrt(Math.max(v, 0)));
  const max = Math.max(...scaled, 1);
  return (
    <svg viewBox="0 0 120 70" class="visual s2-chart" role="img" aria-hidden="true">
      <line x1="4" y1="62" x2="116" y2="62" stroke="currentColor" stroke-opacity="0.25" />
      {scaled.map((v, i) => {
        const h = Math.max(3, (v / max) * 52);
        return <rect key={i} x={10 + i * 40} y={62 - h} width="26" height={h} rx="3" fill="currentColor" fill-opacity={0.4 + i * 0.25} />;
      })}
    </svg>
  );
}

function S2Player({ content }: { content: S2Content }) {
  const lang = prefs.value.lang;
  // A check that found "5% daily" opens /sim/S2?rate=5&period=day so the user plays with their own message's promise
  const q = new URLSearchParams(typeof location !== 'undefined' ? location.search : '');
  const qRate = Number(q.get('rate'));
  const qPeriod = q.get('period');
  const [rate, setRate] = useState(qRate > 0 && qRate <= 100 ? qRate : (content.defaults?.rate ?? 1));
  const [period, setPeriod] = useState<Period>(
    qPeriod === 'day' || qPeriod === 'week' || qPeriod === 'month' ? qPeriod : (content.defaults?.period ?? 'day'),
  );
  const [amount, setAmount] = useState(content.defaults?.amount ?? 10000);
  const [showQuiz, setShowQuiz] = useState(false);
  const projection = useMemo(() => s2Project(amount, rate, period), [amount, rate, period]);
  const periodWord = t(`ui.period_${period}`);

  return (
    <main class="screen">
      <h1>{pick(content.title, lang) || t('ui.practice')}</h1>
      {content.texts?.prompt && <p>{pick(content.texts.prompt, lang)}</p>}

      <label>
        {t('ui.promised_rate')}
        <input
          type="number"
          inputMode="decimal"
          value={rate}
          onInput={(e) => setRate(Number((e.target as HTMLInputElement).value) || 0)}
        />
      </label>
      <label>
        {t('ui.period')}
        <select value={period} onChange={(e) => setPeriod((e.target as HTMLSelectElement).value as Period)}>
          <option value="day">{t('ui.period_day')}</option>
          <option value="week">{t('ui.period_week')}</option>
          <option value="month">{t('ui.period_month')}</option>
        </select>
      </label>
      <label>
        {t('ui.amount')}
        <input
          type="number"
          inputMode="numeric"
          value={amount}
          onInput={(e) => setAmount(Number((e.target as HTMLInputElement).value) || 0)}
        />
      </label>

      <p class="s2-headline">
        {render(content.texts?.result, lang, {
          amount: formatNumber(amount),
          rate,
          period: periodWord,
          result: formatNumber(projection.afterOneYear),
        })}
      </p>

      <ProjectionBars values={[projection.afterOneMonth, projection.afterSixMonths, projection.afterOneYear]} />

      <ul class="s2-projection">
        <li>
          {t('ui.after_1_month')}: <strong>{formatINRWords(projection.afterOneMonth)}</strong>
        </li>
        <li>
          {t('ui.after_6_months')}: <strong>{formatINRWords(projection.afterSixMonths)}</strong>
        </li>
        <li>
          {t('ui.after_1_year')}: <strong>{formatINRWords(projection.afterOneYear)}</strong>
        </li>
      </ul>

      <p class="s2-warning">{pick(content.texts?.impossible, lang) || t('ui.no_one_can_promise_this')}</p>
      {content.texts?.benchmark && <p class="s2-benchmark">{pick(content.texts.benchmark, lang)}</p>}

      {content.quiz &&
        (showQuiz ? (
          <div data-testid="sim-quiz">
            <QuizFlow questions={quizQuestions(content.quiz)} doneHref="/practice" />
          </div>
        ) : (
          <button type="button" class="btn btn-primary" onClick={() => setShowQuiz(true)}>
            {t('ui.quiz')}
          </button>
        ))}
    </main>
  );
}

// ---- S3: leverage wipe-out --------------------------------------------------------------------
// content/sims/S3.json: {title, texts: {prompt, result, wiped_out, fact}, defaults: {margin,
// leverage, seed, steps}}. The seed and step count are content, not hardcoded, so content can
// retune the walk without a PWA change.

interface S3Content {
  id: string;
  title?: LangText;
  texts?: { prompt?: LangText; result?: LangText; wiped_out?: LangText; fact?: LangText };
  defaults?: { margin?: number; leverage?: number; seed?: number; steps?: number };
  quiz?: QuizQuestion | QuizQuestion[];
}

const STATUS_WORD: Record<S3Status, string> = { ok: 'ui.sim_ok', margin_call: 'ui.margin_call', wiped_out: 'ui.wiped_out' };

/** Decorative only (aria-hidden) - plots equity revealed so far against the starting margin
 * (dashed reference line), so the shrinking trend is visible, not just the current number. */
function EquityPath({ equities, margin }: { equities: number[]; margin: number }) {
  const max = Math.max(margin, ...equities, 1);
  const refY = 100 - (margin / max) * 92;
  const points = equities
    .map((e, i) => `${((i / Math.max(1, equities.length - 1)) * 100).toFixed(1)},${(100 - (Math.max(e, 0) / max) * 92).toFixed(1)}`)
    .join(' ');
  return (
    <svg viewBox="0 0 100 100" class="visual s3-chart" role="img" aria-hidden="true">
      <line x1="0" y1={refY} x2="100" y2={refY} stroke="currentColor" stroke-opacity="0.3" stroke-dasharray="3,3" />
      <polyline points={points} fill="none" stroke="currentColor" stroke-width="4" stroke-linecap="round" stroke-linejoin="round" />
    </svg>
  );
}

function S3Player({ content }: { content: S3Content }) {
  const lang = prefs.value.lang;
  const margin = content.defaults?.margin ?? 10000;
  const seed = content.defaults?.seed ?? 42;
  const steps = content.defaults?.steps ?? S3_STEPS;
  const [leverage, setLeverage] = useState(content.defaults?.leverage ?? 8);
  const [started, setStarted] = useState(false);
  const [stepIndex, setStepIndex] = useState(0);
  const [recorded, setRecorded] = useState(false);
  const [showQuiz, setShowQuiz] = useState(false);
  const path = useMemo(() => s3Run(margin, leverage, seed, steps), [margin, leverage, seed, steps]);

  if (!started) {
    return (
      <main class="screen">
        <h1>{pick(content.title, lang) || t('ui.practice')}</h1>
        <p>{render(content.texts?.prompt, lang, { margin: formatNumber(margin), leverage })}</p>
        <label>
          {t('ui.leverage')}: {leverage}x
          <input
            type="range"
            min={1}
            max={10}
            step={1}
            value={leverage}
            onInput={(e) => setLeverage(Number((e.target as HTMLInputElement).value))}
          />
        </label>
        <button type="button" class="btn btn-primary btn-huge" onClick={() => setStarted(true)}>
          {t('ui.start')}
        </button>
      </main>
    );
  }

  const current = path[stepIndex];
  const isFinal = current.status === 'wiped_out' || stepIndex === steps;

  if (isFinal && !recorded) {
    setRecorded(true);
    void recordSimOutcome(content.id, current.status);
  }

  if (isFinal && showQuiz && content.quiz) {
    return (
      <main class="screen" data-testid="sim-quiz">
        <QuizFlow questions={quizQuestions(content.quiz)} doneHref="/practice" />
      </main>
    );
  }

  const resultText =
    current.status === 'wiped_out'
      ? pick(content.texts?.wiped_out, lang)
      : // content/sims/S3.json's own `texts.result` already has a literal ₹ before {equity}
        // (same pairing as S2's ₹{amount}/₹{result} and S1's ₹{balance}/₹{lost} templates) - the
        // plain grouped number here, not formatINRWords (which prepends its own ₹), or the line
        // reads "₹₹10,000".
        render(content.texts?.result, lang, { equity: formatNumber(current.equity) });

  return (
    <main class="screen" data-testid={isFinal ? 'sim-end' : undefined}>
      <p class="sim-disclaimer">{t('ui.illustrative_not_real_prices')}</p>
      <EquityPath equities={path.slice(0, stepIndex + 1).map((s) => s.equity)} margin={margin} />
      <p data-testid="sim-balance">{formatINRWords(current.equity)}</p>
      <p class={`sim-status status-${current.status}`}>{t(STATUS_WORD[current.status])}</p>
      <p>{resultText}</p>

      {isFinal ? (
        <>
          <p class="s3-fact">{pick(content.texts?.fact, lang)}</p>
          {content.quiz ? (
            <button type="button" class="btn btn-primary btn-huge" onClick={() => setShowQuiz(true)}>
              {t('ui.quiz')}
            </button>
          ) : (
            <a class="btn btn-primary btn-huge" href="/practice">
              {t('ui.done')}
            </a>
          )}
        </>
      ) : (
        <button type="button" class="btn btn-primary btn-huge" onClick={() => setStepIndex((s) => s + 1)}>
          {t('ui.next')}
        </button>
      )}
    </main>
  );
}
