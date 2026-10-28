import { defineContentScript } from 'wxt/utils/define-content-script';
import { startPage, windowTransport } from '@/src/adapters/jupyter/page';

/** MAIN world: reads Jupyter's app object for the bridge (docs/adr/0029). */
export default defineContentScript({
  registration: 'runtime',
  world: 'MAIN',
  noScriptStartedPostMessage: true,
  main() {
    if (document.getElementById('jupyter-config-data') === null) return;
    const flag = Symbol.for('marginalia.page');
    const w = window as unknown as Record<symbol, true>;
    if (w[flag]) return;
    w[flag] = true;
    startPage({ win: window, transport: windowTransport(window) });
  },
});
