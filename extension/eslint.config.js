// @ts-check
import js from '@eslint/js';
import reactHooks from 'eslint-plugin-react-hooks';
import globals from 'globals';
import { defineConfig } from 'eslint/config';
import tseslint from 'typescript-eslint';

/** The extension makes no network requests; the desktop app is where models are called. */
const NETWORK_GLOBALS = ['fetch', 'XMLHttpRequest', 'WebSocket', 'EventSource', 'WebTransport'].map(
  (name) => ({ name, message: 'The extension makes no network requests (docs/adr/0029).' }),
);

/** Globals the pure core must not touch. */
const BROWSER_GLOBALS = [
  'window',
  'document',
  'navigator',
  'location',
  'localStorage',
  'sessionStorage',
  'indexedDB',
  'chrome',
  'browser',
].map((name) => ({ name, message: 'src/core and src/mascot are pure: no browser APIs.' }));

export default defineConfig(
  { ignores: ['.output/', '.wxt/', 'coverage/', 'playwright-report/', 'test-results/'] },
  js.configs.recommended,
  ...tseslint.configs.strictTypeChecked,
  {
    languageOptions: {
      parserOptions: { projectService: true, tsconfigRootDir: import.meta.dirname },
      globals: { ...globals.browser },
    },
  },
  {
    files: ['**/*.js', '**/*.config.ts'],
    extends: [tseslint.configs.disableTypeChecked],
    languageOptions: { globals: { ...globals.node } },
  },
  {
    files: ['src/**/*.{ts,tsx}', 'entrypoints/**/*.{ts,tsx}'],
    plugins: { 'react-hooks': reactHooks },
    rules: {
      ...reactHooks.configs.recommended.rules,
      '@typescript-eslint/no-confusing-void-expression': ['error', { ignoreArrowShorthand: true }],
      '@typescript-eslint/no-unused-vars': [
        'error',
        { varsIgnorePattern: '^_', argsIgnorePattern: '^_', destructuredArrayIgnorePattern: '^_' },
      ],
      'no-restricted-globals': ['error', ...NETWORK_GLOBALS],
      'no-restricted-properties': [
        'error',
        { object: 'navigator', property: 'sendBeacon', message: 'No network requests.' },
      ],
    },
  },
  {
    files: ['src/core/**/*.ts', 'src/mascot/**/*.ts'],
    rules: {
      'no-restricted-globals': ['error', ...NETWORK_GLOBALS, ...BROWSER_GLOBALS],
      'no-restricted-imports': [
        'error',
        {
          patterns: [
            {
              group: ['@/src/adapters/*', '@/src/ui/*', '@/entrypoints/*'],
              message: 'The core is pure.',
            },
            {
              group: ['wxt', 'wxt/*', 'react', 'react-dom'],
              message: 'The core is framework-free.',
            },
          ],
        },
      ],
    },
  },
);
