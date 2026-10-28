import { defineConfig } from 'vitest/config';
import { WxtVitest } from 'wxt/testing/vitest-plugin';

export default defineConfig({
  plugins: [WxtVitest()],
  test: {
    include: ['src/**/*.test.{ts,tsx}', 'entrypoints/**/*.test.{ts,tsx}'],
    environment: 'node',
    coverage: {
      provider: 'v8',
      // Coverage targets the pure core and the adapters' pure helpers, not the UI.
      include: [
        'src/core/**/*.ts',
        'src/messaging/**/*.ts',
        'src/adapters/jupyter/**/*.ts',
        'src/mascot/**/*.ts',
        'src/ui/view.ts',
      ],
      exclude: ['**/*.test.*', '**/*.d.ts'],
      // Set just below current coverage so regressions fail CI.
      thresholds: { lines: 84, statements: 84, functions: 80, branches: 78 },
    },
  },
});
