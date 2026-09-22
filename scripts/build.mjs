import { mkdirSync, copyFileSync, writeFileSync } from 'node:fs';
import { spawnSync } from 'node:child_process';

const raw = (process.env.PUBLIC_API_BASE_URL || '').trim();
let apiBase = '';
if (raw) {
  const url = new URL(raw);
  if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password ||
      url.pathname !== '/' || url.search || url.hash) {
    throw new Error('PUBLIC_API_BASE_URL must be an HTTP(S) origin, without credentials or a path');
  }
  if (process.env.VERCEL && url.protocol !== 'https:') throw new Error('Vercel requires an HTTPS API origin');
  apiBase = url.origin;
}
if (process.env.VERCEL && !apiBase) throw new Error('Set PUBLIC_API_BASE_URL to the Render backend origin');
mkdirSync('dist', { recursive: true });
for (const name of ['index.html', 'app.js']) copyFileSync(`frontend/${name}`, `dist/${name}`);
// Only this explicitly public setting is emitted. Never copy .env into dist.
writeFileSync('dist/config.js', `window.APP_CONFIG = ${JSON.stringify({ apiBaseUrl: apiBase })};\n`);
const css = spawnSync(process.execPath, ['node_modules/tailwindcss/lib/cli.js',
  '-i', 'frontend/styles.css', '-o', 'dist/styles.css', '--minify'], { stdio: 'inherit' });
if (css.status !== 0) process.exit(css.status || 1);
