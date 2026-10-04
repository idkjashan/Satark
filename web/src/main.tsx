// Entry point. Applying prefs happens before render() so <html lang> and the `simple`/
// `text-large` classes are correct before Preact paints anything (LLD §21.3). The service
// worker is registered from here, not an inline <script> - CSP is `default-src 'self'`.
import { render } from 'preact';
import { applyPrefsToDocument } from './lib/signals';
import { App } from './app';
import './styles.css';

applyPrefsToDocument();

const root = document.getElementById('app');
if (root) render(<App />, root);

if ('serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/sw.js').catch(() => {
      // No SW this session (older browser, blocked, etc.) - the app still works online.
    });
  });
}
