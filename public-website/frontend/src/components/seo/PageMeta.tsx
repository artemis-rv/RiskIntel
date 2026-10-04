/**
 * components/seo/PageMeta.tsx
 * ───────────────────────────
 * Per-route document metadata: title, description, canonical URL, Open Graph
 * and robots directives.
 *
 * Written against the DOM directly rather than pulling in a helmet library —
 * the requirement is a handful of tags per route, and this keeps the dependency
 * list short.
 *
 * The `noIndex` flag defaults to false for public pages. Every authenticated and
 * administrative route passes `noIndex`, which pairs with the Disallow rules in
 * public/robots.txt so private areas stay out of search results even if a URL
 * leaks into a link somewhere.
 */

import { useEffect } from 'react';
import { config } from '@/constants/config';
import { PRODUCT } from '@/constants/content';

/**
 * The social card. Absolute URLs are required — a relative og:image is ignored
 * by every scraper — so this is only emitted when a site URL is configured.
 * The same file is referenced by the static tags in index.html.
 */
const SOCIAL_IMAGE_PATH = '/og-image.png';

export interface PageMetaProps {
  /** Page-specific part of the title. The product name is appended. */
  title: string;
  description?: string;
  /** Path for the canonical URL, e.g. "/features". Ignored when noIndex. */
  canonicalPath?: string;
  noIndex?: boolean;
  /** Open Graph type; "website" for most pages, "article" for docs. */
  ogType?: 'website' | 'article';
}

function upsertMeta(selector: string, attribute: 'name' | 'property', key: string, content: string) {
  let element = document.head.querySelector<HTMLMetaElement>(selector);
  if (!element) {
    element = document.createElement('meta');
    element.setAttribute(attribute, key);
    document.head.appendChild(element);
  }
  element.setAttribute('content', content);
}

function upsertCanonical(href: string | null) {
  let element = document.head.querySelector<HTMLLinkElement>('link[rel="canonical"]');
  if (!href) {
    element?.remove();
    return;
  }
  if (!element) {
    element = document.createElement('link');
    element.setAttribute('rel', 'canonical');
    document.head.appendChild(element);
  }
  element.setAttribute('href', href);
}

export function PageMeta({
  title,
  description,
  canonicalPath,
  noIndex = false,
  ogType = 'website',
}: PageMetaProps) {
  useEffect(() => {
    const fullTitle = `${title} — ${PRODUCT.name}`;
    document.title = fullTitle;

    const resolvedDescription = description ?? PRODUCT.summary;
    upsertMeta('meta[name="description"]', 'name', 'description', resolvedDescription);

    // Private routes are excluded from indexing and from link previews.
    upsertMeta(
      'meta[name="robots"]',
      'name',
      'robots',
      noIndex ? 'noindex, nofollow' : 'index, follow',
    );

    const canonical =
      !noIndex && canonicalPath && config.siteUrl ? `${config.siteUrl}${canonicalPath}` : null;
    upsertCanonical(canonical);

    upsertMeta('meta[property="og:title"]', 'property', 'og:title', fullTitle);
    upsertMeta(
      'meta[property="og:description"]',
      'property',
      'og:description',
      resolvedDescription,
    );
    upsertMeta('meta[property="og:type"]', 'property', 'og:type', ogType);
    upsertMeta('meta[property="og:site_name"]', 'property', 'og:site_name', PRODUCT.name);
    if (canonical) {
      upsertMeta('meta[property="og:url"]', 'property', 'og:url', canonical);
    }
    // A card type of summary_large_image promises an image. Declaring it
    // without one is what makes a shared link render as a blank rectangle, so
    // the image travels with the declaration rather than being assumed to be
    // inherited from the static head.
    if (config.siteUrl) {
      const image = `${config.siteUrl}${SOCIAL_IMAGE_PATH}`;
      upsertMeta('meta[property="og:image"]', 'property', 'og:image', image);
      upsertMeta('meta[name="twitter:image"]', 'name', 'twitter:image', image);
    }

    upsertMeta('meta[name="twitter:card"]', 'name', 'twitter:card', 'summary_large_image');
    // Twitter falls back to the og:* tags, but only when its own are absent —
    // being explicit costs two lines and removes the ambiguity.
    upsertMeta('meta[name="twitter:title"]', 'name', 'twitter:title', fullTitle);
    upsertMeta(
      'meta[name="twitter:description"]',
      'name',
      'twitter:description',
      resolvedDescription,
    );
  }, [title, description, canonicalPath, noIndex, ogType]);

  return null;
}
