/// <reference types="vitest/config" />
import { defineConfig, loadEnv, type Plugin } from 'vite';
import react from '@vitejs/plugin-react';
import { readFileSync } from 'node:fs';
import { fileURLToPath, URL } from 'node:url';

/**
 * Public routes that belong in a sitemap.
 *
 * Authenticated and administrative routes are deliberately absent: they are
 * `noindex` in PageMeta and Disallowed in robots.txt, and listing them here
 * would contradict both.
 */
const PUBLIC_ROUTES = [
  { path: '/', changefreq: 'weekly', priority: '1.0' },
  { path: '/features', changefreq: 'monthly', priority: '0.8' },
  { path: '/download', changefreq: 'daily', priority: '0.9' },
  { path: '/docs', changefreq: 'weekly', priority: '0.7' },
  { path: '/faq', changefreq: 'monthly', priority: '0.6' },
  { path: '/contact', changefreq: 'monthly', priority: '0.6' },
  { path: '/privacy', changefreq: 'yearly', priority: '0.3' },
  { path: '/terms', changefreq: 'yearly', priority: '0.3' },
];

const DISALLOWED = [
  '/admin',
  '/admin/',
  '/profile',
  '/my-downloads',
  '/my-feedback',
  '/my-requests',
  '/reset-password',
  '/verify-email',
  '/forgot-password',
];

const escapeXml = (value: string) =>
  value.replace(/[<>&'"]/g, (c) =>
    ({ '<': '&lt;', '>': '&gt;', '&': '&amp;', "'": '&apos;', '"': '&quot;' })[c]!,
  );

const escapeHtml = (value: string) =>
  value.replace(/[<>&"]/g, (c) => ({ '<': '&lt;', '>': '&gt;', '&': '&amp;', '"': '&quot;' })[c]!);

/** Documentation article slugs, read from the content module at build time. */
function docSlugs(): string[] {
  const source = readFileSync(
    fileURLToPath(new URL('./src/constants/content.ts', import.meta.url)),
    'utf8',
  );
  return [...source.matchAll(/slug:\s*'([^']+)'/g)].map((match) => match[1]);
}

/**
 * Emits robots.txt and sitemap.xml, and writes the social/canonical tags into
 * the static head.
 *
 * WHY THESE ARE GENERATED RATHER THAN CHECKED IN
 * Both files require absolute URLs — the sitemap protocol rejects a relative
 * `<loc>`, and Google and Bing ignore a relative `Sitemap:` line. The site's
 * own origin is not known until it is deployed, so a checked-in copy is either
 * wrong or hardcodes one environment's domain. Generating them from
 * VITE_SITE_URL means the deployed origin is the only place the domain lives.
 *
 * The sitemap is also derived from the route table rather than maintained by
 * hand, so a new docs article cannot be added and then forgotten — which is
 * what had happened to all four of them.
 *
 * The head tags matter for a different reason: no major link scraper runs
 * JavaScript. Whatever this plugin writes here is the entirety of what Slack,
 * LinkedIn, Discord, WhatsApp and X will ever see, no matter what the runtime
 * PageMeta component does afterwards.
 */
function seoAssets(rawSiteUrl: string): Plugin {
  const siteUrl = rawSiteUrl.trim().replace(/\/+$/, '');

  return {
    name: 'riskintel-seo-assets',
    apply: 'build',

    transformIndexHtml(html) {
      if (!siteUrl) {
        // Without an origin, absolute tags cannot be written. Emitting relative
        // ones would be worse than emitting none: scrapers ignore them, so the
        // tags would look present while doing nothing.
        this.warn?.(
          'VITE_SITE_URL is not set — og:url, og:image and canonical are omitted from index.html.',
        );
        return html;
      }

      const title = 'RiskIntel — Endpoint Risk Analysis';
      const description =
        'RiskIntel scans your endpoints, scores the risk it finds, and tells you what to fix first.';
      const image = `${siteUrl}/og-image.png`;

      const tags = [
        `<link rel="canonical" href="${escapeHtml(siteUrl)}/" />`,
        `<meta property="og:type" content="website" />`,
        `<meta property="og:site_name" content="RiskIntel" />`,
        `<meta property="og:title" content="${escapeHtml(title)}" />`,
        `<meta property="og:description" content="${escapeHtml(description)}" />`,
        `<meta property="og:url" content="${escapeHtml(siteUrl)}/" />`,
        `<meta property="og:image" content="${escapeHtml(image)}" />`,
        `<meta property="og:image:width" content="1200" />`,
        `<meta property="og:image:height" content="630" />`,
        `<meta property="og:image:alt" content="RiskIntel — endpoint risk analysis" />`,
        `<meta property="og:locale" content="en_US" />`,
        `<meta name="twitter:card" content="summary_large_image" />`,
        `<meta name="twitter:title" content="${escapeHtml(title)}" />`,
        `<meta name="twitter:description" content="${escapeHtml(description)}" />`,
        `<meta name="twitter:image" content="${escapeHtml(image)}" />`,
      ].join('\n    ');

      return html.replace('</head>', `  ${tags}\n  </head>`);
    },

    generateBundle() {
      const routes = [
        ...PUBLIC_ROUTES,
        ...docSlugs().map((slug) => ({
          path: `/docs/${slug}`,
          changefreq: 'monthly',
          priority: '0.7',
        })),
      ];

      const robots = [
        '# RiskIntel Public Website — robots policy',
        '# Private and administrative areas are never exposed to search engines.',
        '# Generated at build time; edit vite.config.ts, not this file.',
        'User-agent: *',
        'Allow: /',
        ...DISALLOWED.map((path) => `Disallow: ${path}`),
        '',
        // A relative Sitemap: line is ignored by every major crawler, so it is
        // written only when there is an origin to make it absolute.
        ...(siteUrl ? [`Sitemap: ${siteUrl}/sitemap.xml`] : []),
        '',
      ].join('\n');

      this.emitFile({ type: 'asset', fileName: 'robots.txt', source: robots });

      if (!siteUrl) {
        this.warn(
          'VITE_SITE_URL is not set — sitemap.xml is not emitted, because a ' +
            'sitemap with relative <loc> values is invalid and would be rejected.',
        );
        return;
      }

      const lastmod = new Date().toISOString().slice(0, 10);
      const urls = routes
        .map(
          (route) =>
            `  <url><loc>${escapeXml(siteUrl + route.path)}</loc>` +
            `<lastmod>${lastmod}</lastmod>` +
            `<changefreq>${route.changefreq}</changefreq>` +
            `<priority>${route.priority}</priority></url>`,
        )
        .join('\n');

      this.emitFile({
        type: 'asset',
        fileName: 'sitemap.xml',
        source: `<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n${urls}\n</urlset>\n`,
      });
    },
  };
}

/**
 * Vite configuration.
 *
 * Notes:
 * - Dev server is pinned to port 3000 because the FastAPI backend's
 *   CORS_ORIGINS allowlist contains http://localhost:3000. Changing this port
 *   requires a matching backend CORS change.
 * - No API base URL is hardcoded anywhere; it comes from VITE_API_BASE_URL.
 * - Source maps are disabled for production builds so internal module paths are
 *   not shipped to browsers (A05: security misconfiguration).
 */
export default defineConfig(({ mode }) => ({
  plugins: [react(), seoAssets(loadEnv(mode, process.cwd(), 'VITE_').VITE_SITE_URL ?? '')],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  server: {
    port: 3000,
    strictPort: true,
  },
  preview: {
    port: 3000,
    strictPort: true,
  },
  build: {
    outDir: 'dist',
    sourcemap: false,
    target: 'es2020',
    rollupOptions: {
      output: {
        // Split vendor code so the public marketing pages do not pay for the
        // full router/query runtime on first paint more than once.
        manualChunks(id: string) {
          if (!id.includes('node_modules')) return undefined;
          if (id.includes('react-router')) return 'router-vendor';
          if (id.includes('@tanstack')) return 'query-vendor';
          if (id.includes('react-dom') || id.includes('/react/')) return 'react-vendor';
          return undefined;
        },
      },
    },
  },
  define: {
    __APP_MODE__: JSON.stringify(mode),
  },
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    css: false,
    include: ['src/**/*.{test,spec}.{ts,tsx}'],
    coverage: {
      provider: 'v8',
      reporter: ['text', 'html'],
      exclude: ['src/test/**', '**/*.d.ts', 'src/main.tsx'],
    },
  },
}));
