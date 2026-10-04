import { fileURLToPath, URL } from 'node:url';
import { defineConfig } from 'vitest/config';
import preact from '@preact/preset-vite';
import { VitePWA } from 'vite-plugin-pwa';

const repoRoot = fileURLToPath(new URL('..', import.meta.url));
const contentDir = fileURLToPath(new URL('../content', import.meta.url));

// Satark PWA. See docs/CONTRACTS.md and docs/reference/Satark-LLD.md Part D.
export default defineConfig({
  root: fileURLToPath(new URL('.', import.meta.url)),
  resolve: {
    alias: {
      '@content': contentDir,
    },
  },
  plugins: [
    preact(),
    VitePWA({
      strategies: 'injectManifest',
      srcDir: 'src',
      filename: 'sw.ts',
      injectRegister: false, // we register the SW ourselves from src/main.tsx (CSP: no inline scripts)
      injectManifest: {
        // Content packs are fetched by the app at runtime via @content; precache only the app shell here.
        globPatterns: ['**/*.{js,css,html,woff2}'], // woff2: self-hosted Inter + Noto Sans Devanagari must work offline,
      },
      manifest: {
        name: 'Satark',
        short_name: 'Satark',
        description: 'Check a suspicious investment message against official Indian registries.',
        start_url: '/',
        display: 'standalone',
        theme_color: '#0F6E8C',
        background_color: '#FFFFFF',
        icons: [
          { src: '/icons/icon-192.png', sizes: '192x192', type: 'image/png', purpose: 'any' },
          { src: '/icons/icon-512.png', sizes: '512x512', type: 'image/png', purpose: 'any' },
          { src: '/icons/icon-maskable-192.png', sizes: '192x192', type: 'image/png', purpose: 'maskable' },
          { src: '/icons/icon-maskable-512.png', sizes: '512x512', type: 'image/png', purpose: 'maskable' },
        ],
        // LLD lines 2036-2039, exact shape.
        share_target: {
          action: '/share',
          method: 'POST',
          enctype: 'multipart/form-data',
          params: {
            title: 'title',
            text: 'text',
            url: 'url',
            files: [{ name: 'media', accept: ['image/*', '.jpg', '.png'] }],
          },
        } as never, // share_target isn't in the upstream ManifestOptions type yet
      },
    }),
  ],
  server: {
    fs: { allow: [repoRoot] },
    proxy: {
      '/v1': 'http://127.0.0.1:8000',
      '/healthz': 'http://127.0.0.1:8000',
      '/readyz': 'http://127.0.0.1:8000',
      '/share': 'http://127.0.0.1:8000',
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: false,
  },
  test: {
    environment: 'happy-dom',
    include: ['src/**/*.test.{ts,tsx}'],
  },
});
