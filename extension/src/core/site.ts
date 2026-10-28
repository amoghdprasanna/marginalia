/**
 * An address you type ("jupyter.example.edu", "https://hub.example.org/user/me/tree") as the
 * Chrome match pattern for its whole host. Ports aren't part of a match pattern, so one
 * pattern covers every port on that host. Null when it isn't a web address.
 */
export function sitePattern(input: string): { pattern: string; host: string } | null {
  const text = input.trim();
  if (text === '' || /\s/.test(text)) return null;
  let url: URL;
  try {
    url = new URL(/^[a-z][a-z0-9+.-]*:\/\//i.test(text) ? text : `https://${text}`);
  } catch {
    return null;
  }
  if (url.protocol !== 'http:' && url.protocol !== 'https:') return null;
  const host = url.hostname;
  if (host === '' || (!host.includes('.') && host !== 'localhost')) return null;
  return { pattern: `${url.protocol}//${host}/*`, host };
}

/** "https://jupyter.example.edu/*" -> "jupyter.example.edu". */
export function siteHost(pattern: string): string {
  return pattern.replace(/^[a-z]+:\/\//, '').replace(/\/\*$/, '');
}
