import { browser } from 'wxt/browser';
import { defineContentScript } from 'wxt/utils/define-content-script';
import { startBridge } from '@/src/adapters/jupyter/bridge';
import { windowTransport } from '@/src/adapters/jupyter/page';
import { readPageConfig } from '@/src/core/access';
import { makeMessage, NOTEBOOK_PORT } from '@/src/messaging/protocol';

/**
 * Isolated world, on the sites you allowed (registered by the background,
 * docs/adr/0029). Answers the side panel on every such page, so the panel can
 * tell "not a Jupyter page" from "Marginalia can't reach this tab".
 */
export default defineContentScript({
  registration: 'runtime',
  noScriptStartedPostMessage: true,
  main() {
    // The background also injects into tabs that were open before you allowed
    // the site; a page that already has us keeps the first copy.
    const flags = globalThis as { __marginaliaBridge?: true };
    if (flags.__marginaliaBridge) return;
    flags.__marginaliaBridge = true;

    const jupyter = readPageConfig(
      document.getElementById('jupyter-config-data')?.textContent ?? null,
    );
    const bridge = jupyter ? startBridge({ page: windowTransport(window), jupyter }) : null;

    browser.runtime.onConnect.addListener((port) => {
      if (port.name !== NOTEBOOK_PORT || port.sender?.id !== browser.runtime.id) return;
      if (bridge) bridge.connect(port);
      else port.postMessage(makeMessage('tab/other', {}));
    });
  },
});
