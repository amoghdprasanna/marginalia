import { defineConfig } from 'wxt';
import { SITES } from './src/sites';

// Extension-page CSP (side panel, background): no remote code, no outbound
// connections. Applied to builds only, because `wxt dev` talks to its server.
const EXTENSION_PAGES_CSP = [
  "default-src 'self'",
  "script-src 'self'",
  "object-src 'none'",
  "connect-src 'self'",
  "base-uri 'none'",
  "form-action 'none'",
].join('; ');

/**
 * The public half of the extension's key: it fixes the extension id at
 * behgmlfpdfdjcbiogfngmghpbfgaagpa wherever it's loaded from, so the desktop
 * helper can name it (docs/adr/0030, src/marginalia/browser/install.py).
 */
const PUBLIC_KEY =
  'MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAmOqXgGY/xBFjEhNRPojdnUJEXZ5jHDw5k7BR1ohbF8uF7UTqFBZqCBnojXeH8rvjUyxNYZTcpy3VHbxtBObFcBdTeayvIsGdtQSAkk+9owSvflAXV3gvaqi6uJQkqRIFt8FfTS/To5oFJTDUefTBvGYPZVa5bu1G0paIYEZ3Bxn6txVpGIrQbKQUbPyyVUAKE3O0MNpfahsWv/spo0XcXC5P895cHPmvnI9BB5urC3wA+UN/4yxh3Yv+ZeWNl78D2/Ry9iltOMPYHWQ0ZP2ObnOS5xbsUjjyMFYEKU2EWZabuOI6chogOV94lgj8GrZyQcWGUN8bolhtv3pia0SLLQIDAQAB';

/**
 * The e2e build grants local Jupyter up front: a test can't click Chrome's
 * permission prompt (docs/adr/0029). Never shipped.
 */
const e2e = process.env.MARGINALIA_E2E === '1';

export default defineConfig({
  modules: ['@wxt-dev/module-react'],
  // Explicit imports only, as in Lemma: the dependency graph stays readable.
  imports: false,
  // Kept apart from the real build, so the e2e grant can't be zipped by mistake.
  ...(e2e ? { outDirTemplate: 'e2e/{{browser}}-mv{{manifestVersion}}' } : {}),
  manifest: ({ command }) => ({
    name: 'Marginalia',
    description:
      'Shows which cells in your Jupyter notebook raised an error, and fixes them with Claude when you say so.',
    key: PUBLIC_KEY,
    minimum_chrome_version: '116',
    // nativeMessaging: the desktop helper that asks Claude (docs/adr/0030).
    permissions: ['sidePanel', 'storage', 'scripting', 'nativeMessaging'],
    host_permissions: e2e ? ['http://127.0.0.1/*'] : [],
    optional_host_permissions: [...SITES],
    action: {
      default_title: 'Open Marginalia',
      default_icon: { 16: 'icon/16.png', 32: 'icon/32.png' },
    },
    ...(command === 'build'
      ? { content_security_policy: { extension_pages: EXTENSION_PAGES_CSP } }
      : {}),
  }),
});
