import {
  chromium,
  test as base,
  type BrowserContext,
  type Page,
  type Worker,
} from '@playwright/test';
import path from 'node:path';

const EXTENSION_PATH = path.resolve(import.meta.dirname, '../../.output/e2e/chrome-mv3');

/** A Chromium context with the e2e build loaded (`npm run build:e2e` first). */
export const test = base.extend<{
  context: BrowserContext;
  serviceWorker: Worker;
  extensionId: string;
  /** Opens the side panel as a page, pinned to the tab showing `page`. */
  openPanel: (page: Page) => Promise<Page>;
}>({
  // eslint-disable-next-line no-empty-pattern -- Playwright fixture signature
  context: async ({}, use) => {
    const context = await chromium.launchPersistentContext('', {
      channel: 'chromium',
      args: [`--disable-extensions-except=${EXTENSION_PATH}`, `--load-extension=${EXTENSION_PATH}`],
    });
    await use(context);
    await context.close();
  },
  serviceWorker: async ({ context }, use) => {
    const worker = context.serviceWorkers()[0] ?? (await context.waitForEvent('serviceworker'));
    await use(worker);
  },
  extensionId: async ({ serviceWorker }, use) => {
    await use(new URL(serviceWorker.url()).host);
  },
  openPanel: async ({ context, serviceWorker, extensionId }, use) => {
    await use(async (page) => {
      const url = page.url();
      const tabId = await serviceWorker.evaluate(async (u) => {
        const { chrome } = globalThis as unknown as {
          chrome: { tabs: { query(q: object): Promise<{ id?: number; url?: string }[]> } };
        };
        const tabs = await chrome.tabs.query({});
        return tabs.find((t) => t.url === u)?.id;
      }, url);
      if (tabId === undefined) throw new Error(`no tab for ${url}`);
      const panel = await context.newPage();
      await panel.goto(`chrome-extension://${extensionId}/sidepanel.html?tab=${String(tabId)}`);
      return panel;
    });
  },
});

export const expect = test.expect;
