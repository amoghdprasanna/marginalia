import { describe, expect, it } from 'vitest';
import { readPageConfig } from './access';

describe('readPageConfig', () => {
  it('reads what Notebook 7 writes', () => {
    const text = JSON.stringify({
      appName: 'Jupyter Notebook',
      appVersion: '7.6.3',
      exposeAppInBrowser: true,
      baseUrl: '/node/x/',
    });
    expect(readPageConfig(text)).toEqual({
      appName: 'Jupyter Notebook',
      appVersion: '7.6.3',
      exposesApp: true,
    });
  });

  it('treats a missing or "False" setting as off', () => {
    expect(readPageConfig('{"appName":"JupyterLab"}')?.exposesApp).toBe(false);
    expect(readPageConfig('{"exposeAppInBrowser":"False"}')?.exposesApp).toBe(false);
    expect(readPageConfig('{"exposeAppInBrowser":"True"}')?.exposesApp).toBe(true);
  });

  it('says a page without Jupyter config is not Jupyter', () => {
    expect(readPageConfig(null)).toBeNull();
    expect(readPageConfig('not json')).toBeNull();
    expect(readPageConfig('[1,2]')).toBeNull();
  });
});
