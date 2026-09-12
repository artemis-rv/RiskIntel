/**
 * scripts/check-deploy-env.mjs
 * ────────────────────────────
 * Refuse to build a deployment whose environment is quietly wrong.
 *
 * WHY THESE TWO CHECKS ARE A BUILD STEP
 * Both failures below produce a site that deploys successfully, loads
 * successfully, and is broken — the sort of fault that reaches users rather
 * than the person who caused it.
 *
 *   VITE_API_BASE_URL vs. CSP connect-src
 *       The bundle calls one origin; the browser enforces a list from
 *       vercel.json. They live in different files, edited at different times.
 *       When they disagree every API call is blocked and the only symptom is a
 *       console message on the client.
 *
 *   VITE_SITE_URL
 *       PageMeta emits a canonical URL and og:url only when this is set, and
 *       silently emits neither when it is not. A site that launches without it
 *       has no canonical tags at all, and nobody finds out from the build.
 *
 * Local and same-origin builds are still allowed through: an empty
 * VITE_API_BASE_URL means "same origin", which 'self' already covers, and
 * VITE_SITE_URL is only required for a deployed build.
 */

import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';

const here = dirname(fileURLToPath(import.meta.url));
const configPath = resolve(here, '..', 'vercel.json');

const problems = [];
const notes = [];

const read = (name) => (process.env[name] ?? '').trim().replace(/\/+$/, '');
const apiBase = read('VITE_API_BASE_URL');
const siteUrl = read('VITE_SITE_URL');

/** A deployed build is one that targets a cross-origin API. */
const isDeployBuild = apiBase !== '';

// ── VITE_API_BASE_URL must be reachable under the site's own CSP ────────────
if (!isDeployBuild) {
  notes.push('VITE_API_BASE_URL is empty (same-origin); CSP check skipped.');
} else {
  let origin;
  try {
    origin = new URL(apiBase).origin;
  } catch {
    problems.push(`VITE_API_BASE_URL is not a valid absolute URL: ${apiBase}`);
  }

  if (origin) {
    if (!origin.startsWith('https://')) {
      problems.push(`VITE_API_BASE_URL must be https in a deployed build: ${origin}`);
    }

    const config = JSON.parse(readFileSync(configPath, 'utf8'));
    const csp = (config.headers ?? [])
      .flatMap((entry) => entry.headers ?? [])
      .find((header) => header.key.toLowerCase() === 'content-security-policy')?.value;

    if (!csp) {
      problems.push('No Content-Security-Policy header found in vercel.json.');
    } else {
      const connectSrc = csp
        .split(';')
        .map((directive) => directive.trim())
        .find((directive) => directive.startsWith('connect-src'));

      if (!connectSrc || !connectSrc.split(/\s+/).slice(1).includes(origin)) {
        problems.push(
          `The CSP in vercel.json does not permit calls to ${origin}. ` +
            `Add it to connect-src, or correct VITE_API_BASE_URL. ` +
            `connect-src is currently: ${connectSrc ?? '(absent)'}`,
        );
      } else {
        notes.push(`connect-src permits ${origin}`);
      }
    }
  }
}

// ── VITE_SITE_URL is what makes canonical URLs and og:url exist ─────────────
if (siteUrl === '') {
  if (isDeployBuild) {
    problems.push(
      'VITE_SITE_URL is not set. Without it no canonical URL, no og:url and no ' +
        'sitemap can be emitted, and the omission is silent at runtime.',
    );
  } else {
    notes.push('VITE_SITE_URL is unset (local build); canonical URLs will be omitted.');
  }
} else {
  try {
    const parsed = new URL(siteUrl);
    if (isDeployBuild && parsed.protocol !== 'https:') {
      problems.push(`VITE_SITE_URL must be https in a deployed build: ${siteUrl}`);
    } else {
      notes.push(`canonical base is ${parsed.origin}`);
    }
  } catch {
    problems.push(`VITE_SITE_URL is not a valid absolute URL: ${siteUrl}`);
  }
}

for (const note of notes) console.log(`[check-env] ${note}`);

if (problems.length > 0) {
  console.error('\n[check-env] Build refused:');
  for (const problem of problems) console.error(`  • ${problem}`);
  process.exit(1);
}

console.log('[check-env] OK');
