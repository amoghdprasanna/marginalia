import { defineContentScript } from 'wxt/utils/define-content-script';
import { claimPage, startPage, windowTransport } from '@/src/adapters/jupyter/page';

/** MAIN world: reads Jupyter's app object for the bridge (docs/adr/0029, 0031). */
export default defineContentScript({
  registration: 'runtime',
  world: 'MAIN',
  noScriptStartedPostMessage: true,
  main() {
    if (document.getElementById('jupyter-config-data') === null) return;
    claimPage(window, () => startPage({ win: window, transport: windowTransport(window) }));
  },
});
