import { describe, expect, it } from 'vitest';
import { siteHost, sitePattern } from './site';

describe('sitePattern', () => {
  it('turns what people paste into a pattern for the host', () => {
    expect(sitePattern('jupyter.example.edu')).toEqual({
      pattern: 'https://jupyter.example.edu/*',
      host: 'jupyter.example.edu',
    });
    expect(sitePattern(' https://hub.example.org:8443/user/me/tree?x=1 ')?.pattern).toBe(
      'https://hub.example.org/*',
    );
    expect(sitePattern('http://10.0.0.5:8888')?.pattern).toBe('http://10.0.0.5/*');
    expect(sitePattern('localhost:8080')?.pattern).toBe('https://localhost/*');
  });

  it('refuses what is not a web address', () => {
    for (const bad of ['', 'not a url', 'ftp://x.org', 'chrome://extensions', 'jupyter'])
      expect(sitePattern(bad)).toBeNull();
  });

  it('names a pattern by its host', () => {
    expect(siteHost('https://jupyter.example.edu/*')).toBe('jupyter.example.edu');
  });
});
