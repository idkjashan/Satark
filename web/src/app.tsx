// Router (preact-iso, LLD §21.1/§21.2). First launch (prefs.onboarded === false) always renders
// Onboarding, for any path - reactive because @preact/signals auto-subscribes any component that
// reads `.value` during render, no extra wiring needed.
import { LocationProvider, Router, Route, lazy, ErrorBoundary } from 'preact-iso';
import { prefs } from './lib/signals';
import { Shell } from './components/Shell';

const Onboarding = lazy(() => import('./routes/Onboarding').then((m) => m.Onboarding));
const Home = lazy(() => import('./routes/Home').then((m) => m.Home));
const Check = lazy(() => import('./routes/Check').then((m) => m.Check));
const Run = lazy(() => import('./routes/Run').then((m) => m.Run));
const Chat = lazy(() => import('./routes/Chat').then((m) => m.Chat));
const Learn = lazy(() => import('./routes/Learn').then((m) => m.Learn));
const LessonPlayer = lazy(() => import('./routes/LessonPlayer').then((m) => m.LessonPlayer));
const Practice = lazy(() => import('./routes/Practice').then((m) => m.Practice));
const Quiz = lazy(() => import('./routes/Quiz').then((m) => m.Quiz));
const SimPlayer = lazy(() => import('./routes/SimPlayer').then((m) => m.SimPlayer));
const HelpPaid = lazy(() => import('./routes/HelpPaid').then((m) => m.HelpPaid));
const Settings = lazy(() => import('./routes/Settings').then((m) => m.Settings));
const AboutData = lazy(() => import('./routes/AboutData').then((m) => m.AboutData));
const History = lazy(() => import('./routes/History').then((m) => m.History));

function NotFound() {
  return (
    <main class="screen">
      <p>{'Not found.'}</p>
      <a href="/">Home</a>
    </main>
  );
}

/** Moves focus to the new screen's <main> once its (possibly lazy) content has actually loaded -
 * otherwise a screen reader never announces anything after a client-side route change.
 * preventScroll: true - the page is already at the top of a fresh screen; a default .focus()
 * also scrolls the element into view, which with the shell's sticky header tucks the first
 * heading up underneath it (visible as the heading clipping behind the header). */
function focusMain() {
  const main = document.querySelector('main');
  if (main instanceof HTMLElement) {
    if (!main.hasAttribute('tabindex')) main.tabIndex = -1;
    main.focus({ preventScroll: true });
  }
}

function Root() {
  if (!prefs.value.onboarded) return <Onboarding />;
  return (
    <Shell>
      <Router onLoadEnd={focusMain}>
        <Route path="/onboarding" component={Onboarding} />
        <Route path="/" component={Home} />
        <Route path="/check" component={Check} />
        <Route path="/run/:runId" component={Run} />
        {/* content/portals.json's "ask" action routes here with no id - content/i18n/content.<lang>.json
            are G's files, so the route alias lives here rather than asking for a contract change. */}
        <Route path="/chat" component={Chat} />
        <Route path="/chat/:caseId" component={Chat} />
        <Route path="/learn" component={Learn} />
        <Route path="/learn/:id" component={LessonPlayer} />
        <Route path="/practice" component={Practice} />
        <Route path="/quiz" component={Quiz} />
        <Route path="/sim/:id" component={SimPlayer} />
        <Route path="/help-paid" component={HelpPaid} />
        <Route path="/settings" component={Settings} />
        <Route path="/about-data" component={AboutData} />
        <Route path="/history" component={History} />
        <Route default component={NotFound} />
      </Router>
    </Shell>
  );
}

export function App() {
  return (
    <LocationProvider>
      <ErrorBoundary>
        <Root />
      </ErrorBoundary>
    </LocationProvider>
  );
}
