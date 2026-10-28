import { browser } from 'wxt/browser';
import { LOCAL_SITES } from '@/src/sites';

const SITE = /^https?:\/\/[^/]+\/\*$/;

/** The sites you've allowed, as match patterns. */
export async function allowedSites(): Promise<string[]> {
  const { origins = [] } = await browser.permissions.getAll();
  return origins.filter((o) => SITE.test(o));
}

/** Call these straight from a click or a form submit: Chrome needs the gesture. */
export function requestLocal(): Promise<boolean> {
  return browser.permissions.request({ origins: [...LOCAL_SITES] });
}

export function requestSite(pattern: string): Promise<boolean> {
  return browser.permissions.request({ origins: [pattern] });
}
