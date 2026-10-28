import { browser } from 'wxt/browser';
import { SITES } from '@/src/sites';

/** The sites from SITES you've allowed. */
export async function allowedSites(): Promise<string[]> {
  const { origins = [] } = await browser.permissions.getAll();
  return origins.filter((o) => (SITES as readonly string[]).includes(o));
}

/** Asks Chrome for every site at once. Call it straight from a click: Chrome needs the gesture. */
export function requestSites(): Promise<boolean> {
  return browser.permissions.request({ origins: [...SITES] });
}
