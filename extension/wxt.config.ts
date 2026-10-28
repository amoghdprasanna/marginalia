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
    description: 'Reads the Jupyter notebook in this tab and shows which cells raised errors.',
    minimum_chrome_version: '116',
    permissions: ['sidePanel', 'storage', 'scripting'],
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
