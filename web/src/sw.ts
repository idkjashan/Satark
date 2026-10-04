/// <reference lib="webworker" />
// Satark service worker (LLD §22.2, CONTRACTS §6 `POST /share`).
//
// Responsibilities, in order of how often they matter:
//  1. Precache the app shell (JS/CSS/HTML) that Vite built - i18n/lesson/sim content is bundled
//     into those JS chunks via `import.meta.glob`, so precaching the shell is precaching content too.
//  2. Fall back to the precached app shell for any other navigation (offline, or a deep link like
//     /run/<id> opened directly) via Workbox's own NavigationRoute - no hand-rolled fetch/catch.
//  3. Serve the share target: the Android share sheet POSTs here; we stash the payload in
//     IndexedDB and redirect to /check, which reads and deletes it.
//  4. Never touch /v1/*, /healthz, /readyz, /share: denylisted from the navigation fallback, and
//     nothing here ever calls respondWith() for them, so the browser's normal network path applies.
import { precacheAndRoute, createHandlerBoundToURL } from 'workbox-precaching';
import { registerRoute, NavigationRoute } from 'workbox-routing';
import { set } from 'idb-keyval';

declare const self: ServiceWorkerGlobalScope;

precacheAndRoute(self.__WB_MANIFEST);

registerRoute(
  new NavigationRoute(createHandlerBoundToURL('/index.html'), {
    denylist: [/^\/v1\//, /^\/share$/, /^\/healthz$/, /^\/readyz$/],
  }),
);

self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', (event) => event.waitUntil(self.clients.claim()));

self.addEventListener('fetch', (event: FetchEvent) => {
  const { request } = event;
  if (request.method === 'POST' && new URL(request.url).pathname === '/share') {
    event.respondWith(handleShareTarget(request));
  }
});

/** Stash the shared text/url/images and hand off to /check (LLD §22.2 sequence diagram). */
async function handleShareTarget(request: Request): Promise<Response> {
  const id = crypto.randomUUID();
  try {
    const form = await request.formData();
    const files: Blob[] = [];
    for (const value of form.getAll('media')) {
      if (value instanceof File && value.size > 0) files.push(value);
    }
    await set(`share:${id}`, {
      title: String(form.get('title') ?? ''),
      text: String(form.get('text') ?? ''),
      url: String(form.get('url') ?? ''),
      files,
    });
  } catch {
    // Malformed share payload: still land on /check so the user isn't stuck on a blank redirect.
  }
  return Response.redirect('/check?share=' + id, 303);
}
