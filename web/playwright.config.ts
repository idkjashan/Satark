// E2E config (QA, Oct 2026). Hits the REAL FastAPI server (CONTRACTS §6) on two ports:
// 8100 deterministic (no network, no LLM) and 8101 with the mock LLM on 9101 for the chat/
// refusal journeys. Both serve the built PWA from web/dist (satark/api/static.py), so there is
// no Vite dev server in this setup - baseURL points straight at uvicorn.
import { defineConfig, devices } from '@playwright/test';
import { fileURLToPath } from 'node:url';

const ROOT = fileURLToPath(new URL('..', import.meta.url)); // repo root (~/hackathon/satark)
const PORT_DETERMINISTIC = 8100;
const PORT_AI = 8101;
const PORT_MOCK_LLM = 9101;

export default defineConfig({
  testDir: './e2e',
  fullyParallel: true,
  retries: 0,
  // Default output folder (playwright-report/) - already in .gitignore, so no new ignore entry needed.
  reporter: [['list'], ['html', { open: 'never' }]],
  timeout: 30_000,
  expect: { timeout: 20_000 },
  globalSetup: './e2e/global-setup.ts',
  use: {
    trace: 'retain-on-failure',
    video: 'retain-on-failure',
  },
  projects: [
    {
      name: 'mobile',
      testIgnore: /ai-model\.spec\.ts/,
      use: { ...devices['Pixel 5'], baseURL: `http://127.0.0.1:${PORT_DETERMINISTIC}` },
    },
    {
      name: 'mobile-ai',
      testMatch: /ai-model\.spec\.ts/,
      use: { ...devices['Pixel 5'], baseURL: `http://127.0.0.1:${PORT_AI}` },
    },
  ],
  webServer: [
    {
      command: `${ROOT}/.venv/bin/uvicorn satark.app:create_app --factory --host 127.0.0.1 --port ${PORT_DETERMINISTIC}`,
      cwd: ROOT,
      port: PORT_DETERMINISTIC,
      reuseExistingServer: true,
      timeout: 60_000,
      env: { SATARK_RATE_LIMIT_SCALE: '0', SATARK_OFFLINE: '1' },
    },
    {
      command: `${ROOT}/.venv/bin/python scripts/mock_llm.py --port ${PORT_MOCK_LLM}`,
      cwd: ROOT,
      port: PORT_MOCK_LLM,
      reuseExistingServer: true,
      timeout: 30_000,
    },
    {
      command: `${ROOT}/.venv/bin/uvicorn satark.app:create_app --factory --host 127.0.0.1 --port ${PORT_AI}`,
      cwd: ROOT,
      port: PORT_AI,
      reuseExistingServer: true,
      timeout: 60_000,
      env: {
        SATARK_RATE_LIMIT_SCALE: '0',
        SATARK_OFFLINE: '1',
        SATARK_LLM: 'local:satark-mock',
        SATARK_LLM_BASE_URL: `http://127.0.0.1:${PORT_MOCK_LLM}/v1`,
      },
    },
  ],
});
