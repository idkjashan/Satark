// Waits for both uvicorn instances' lifespan startup (config + registry DB load) to finish, not
// just for their ports to accept TCP connections (webServer's own port-wait fires earlier, since
// uvicorn binds the socket before running the ASGI lifespan). Polling /readyz is the documented
// way to know the server is actually answering (CONTRACTS §6), so this is a bounded wait-for-
// condition, not a blind sleep.
async function waitReady(url: string, timeoutMs = 60_000): Promise<void> {
  const deadline = Date.now() + timeoutMs;
  let lastErr: unknown = null;
  while (Date.now() < deadline) {
    try {
      const res = await fetch(url);
      if (res.status === 200) return;
      lastErr = new Error(`${url} -> HTTP ${res.status}`);
    } catch (err) {
      lastErr = err;
    }
    await new Promise((r) => setTimeout(r, 300));
  }
  throw new Error(`${url} never became ready: ${String(lastErr)}`);
}

export default async function globalSetup(): Promise<void> {
  await Promise.all([waitReady('http://127.0.0.1:8100/readyz'), waitReady('http://127.0.0.1:8101/readyz')]);
}
