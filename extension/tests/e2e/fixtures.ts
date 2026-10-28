import {
  chromium,
  test as base,
  type BrowserContext,
  type Page,
  type Worker,
} from '@playwright/test';
import { chmodSync, mkdirSync, mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';

const EXTENSION_PATH = path.resolve(import.meta.dirname, '../../.output/e2e/chrome-mv3');
/** Fixed by the manifest key (wxt.config.ts), so the helper manifest can name it. */
export const EXTENSION_ID = 'behgmlfpdfdjcbiogfngmghpbfgaagpa';

/**
 * Chromium reads helper manifests from <user data dir>/NativeMessagingHosts. With `helper`
 * on, the fake helper is registered there, as `marginalia-browser-host install` would.
 */
function registerFakeHelper(userDataDir: string, allowedId: string): void {
  const dir = path.join(userDataDir, 'NativeMessagingHosts');
  mkdirSync(dir, { recursive: true });
  const launcher = path.join(userDataDir, 'fake-helper.sh');
  const script = path.join(import.meta.dirname, 'fake-helper.js');
  writeFileSync(launcher, `#!/bin/sh\nexec "${process.execPath}" "${script}" "$@"\n`);
  chmodSync(launcher, 0o755);
  writeFileSync(
    path.join(dir, 'marginalia.browser.json'),
    JSON.stringify({
      name: 'marginalia.browser',
      description: 'fake helper for tests',
      path: launcher,
      type: 'stdio',
      allowed_origins: [`chrome-extension://${allowedId}/`],
    }),
  );
}

/** A Chromium context with the e2e build loaded (`npm run build:e2e` first). */
export const test = base.extend<{
  /** true: the fake helper, for our id; 'other-id': installed for another extension; false: none. */
  helper: boolean | 'other-id';
  context: BrowserContext;
  serviceWorker: Worker;
  extensionId: string;
  /** Opens the side panel as a page, pinned to the tab showing `page`. */
  openPanel: (page: Page) => Promise<Page>;
}>({
  helper: [true, { option: true }],
  context: async ({ helper }, use) => {
    const userDataDir = mkdtempSync(path.join(tmpdir(), 'marginalia-chrome-'));
    if (helper !== false)
      registerFakeHelper(userDataDir, helper === 'other-id' ? 'a'.repeat(32) : EXTENSION_ID);
    const context = await chromium.launchPersistentContext(userDataDir, {
      channel: 'chromium',
      args: [`--disable-extensions-except=${EXTENSION_PATH}`, `--load-extension=${EXTENSION_PATH}`],
    });
    await use(context);
    await context.close();
    rmSync(userDataDir, { recursive: true, force: true });
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
