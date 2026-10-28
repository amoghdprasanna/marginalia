/**
 * Where Marginalia may run (docs/adr/0029). Asked for once, from the panel's
 * Allow button; the content scripts are registered only for these.
 */
export const SITES = ['https://*.umd.edu/*', 'http://localhost/*', 'http://127.0.0.1/*'] as const;
