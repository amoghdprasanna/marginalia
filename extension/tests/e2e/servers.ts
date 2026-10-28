/** The two Jupyter servers the e2e suite runs (tests/e2e/global-setup.ts). */
/** The pinned version; MARGINALIA_NOTEBOOK_VERSION tries another (UMD's hepcms ran 7.5.6 on 2026-10-27). */
export const NOTEBOOK_VERSION = process.env.MARGINALIA_NOTEBOOK_VERSION ?? '7.6.3';
/** expose_app_in_browser on: Marginalia can read notebooks. */
export const EXPOSED = 'http://127.0.0.1:18899';
/** The setting off, as on a cluster nobody has configured. */
export const PLAIN = 'http://127.0.0.1:18898';
