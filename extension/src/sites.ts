/**
 * Where Marginalia may read notebooks: only sites you allow, each one asked for in Chrome's
 * own prompt (docs/adr/0031).
 */

/** Jupyter on this computer, or through an SSH tunnel: allowed with one click. */
export const LOCAL_SITES = ['http://localhost/*', 'http://127.0.0.1/*'] as const;

/** Lets Chrome ask for any one address you type; nothing is granted until you allow it. */
export const ANY_SITE = ['http://*/*', 'https://*/*'] as const;
