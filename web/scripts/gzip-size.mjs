#!/usr/bin/env node
// Enforces the 150 KB gzipped JS+CSS budget (LLD §24). Run after `vite build`.
import { readdirSync, readFileSync, statSync } from 'node:fs';
import { gzipSync } from 'node:zlib';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const BUDGET_BYTES = 150 * 1024;
const assetsDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', 'dist', 'assets');

let files;
try {
  files = readdirSync(assetsDir).filter((f) => f.endsWith('.js') || f.endsWith('.css'));
} catch {
  console.error(`No build output at ${assetsDir}. Run "npm run build" first.`);
  process.exit(1);
}

let total = 0;
for (const file of files.sort()) {
  const full = path.join(assetsDir, file);
  const gzipped = gzipSync(readFileSync(full)).length;
  total += gzipped;
  console.log(`${file}\t${(statSync(full).size / 1024).toFixed(1)} KB raw\t${(gzipped / 1024).toFixed(1)} KB gzip`);
}

const totalKB = (total / 1024).toFixed(1);
const budgetKB = (BUDGET_BYTES / 1024).toFixed(0);
console.log(`\nTotal gzipped: ${totalKB} KB (budget ${budgetKB} KB)`);

if (total > BUDGET_BYTES) {
  console.error(`OVER BUDGET by ${((total - BUDGET_BYTES) / 1024).toFixed(1)} KB`);
  process.exit(1);
}
console.log('Within budget.');
