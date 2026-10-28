import { browser } from 'wxt/browser';
import { defineBackground } from 'wxt/utils/define-background';
import { allowedSites } from '@/src/adapters/permissions';

/**
 * Registers the content scripts for the sites you allowed, and only those
 * (docs/adr/0029). Keeps no state of its own: Chrome stops an idle worker,
 * and the registrations and the panel's per-tab answers live elsewhere.
 */
const SCRIPTS = [
  { id: 'marginalia-bridge', js: ['/content-scripts/jupyter.js'], world: 'ISOLATED' },
  { id: 'marginalia-page', js: ['/content-scripts/jupyter-main.js'], world: 'MAIN' },
] as const;

async function syncScripts(): Promise<string[]> {
  const sites = await allowedSites();
  const ids = SCRIPTS.map((s) => s.id);
  const registered = await browser.scripting.getRegisteredContentScripts({ ids });
  if (registered.length > 0)
    await browser.scripting.unregisterContentScripts({ ids: registered.map((r) => r.id) });
  if (sites.length > 0)
    await browser.scripting.registerContentScripts(
      SCRIPTS.map((s) => ({
        ...s,
        js: [...s.js],
        matches: sites,
        runAt: 'document_idle' as const,
      })),
    );
  return sites;
}

/** Tabs that were open before you allowed a site get the scripts now, no reload needed. */
async function injectIntoOpenTabs(sites: string[]): Promise<void> {
  if (sites.length === 0) return;
  const tabs = await browser.tabs.query({ url: sites });
  await Promise.allSettled(
    tabs.flatMap((tab) =>
      tab.id === undefined
        ? []
        : SCRIPTS.map((s) =>
            browser.scripting.executeScript({
              target: { tabId: tab.id as number },
              files: [...s.js],
              world: s.world,
            }),
          ),
    ),
  );
}

export default defineBackground(() => {
  void browser.sidePanel.setPanelBehavior({ openPanelOnActionClick: true });
  browser.runtime.onInstalled.addListener(() => {
    void syncScripts().then(injectIntoOpenTabs);
  });
  browser.runtime.onStartup.addListener(() => void syncScripts());
  browser.permissions.onAdded.addListener(() => {
    void syncScripts().then(injectIntoOpenTabs);
  });
  browser.permissions.onRemoved.addListener(() => void syncScripts());
});
