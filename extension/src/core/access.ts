import { z } from 'zod';

/**
 * What a page's `#jupyter-config-data` says about reaching its notebook
 * (docs/adr/0029). Jupyter writes this JSON into every page it serves;
 * Notebook 7 and JupyterLab 4 both include `exposeAppInBrowser`.
 */
const PageConfig = z.object({
  appName: z.string().optional(),
  appVersion: z.string().optional(),
  exposeAppInBrowser: z.union([z.boolean(), z.string()]).optional(),
});

export interface JupyterPage {
  /** "Jupyter Notebook" or "JupyterLab", as the page names itself. */
  appName: string;
  appVersion: string | null;
  /** True when the server sets expose_app_in_browser, so `window.jupyterapp` will exist. */
  exposesApp: boolean;
}

/** Reads the page config text; null when this isn't a Jupyter page. */
export function readPageConfig(text: string | null): JupyterPage | null {
  if (text === null) return null;
  let json: unknown;
  try {
    json = JSON.parse(text);
  } catch {
    return null;
  }
  const parsed = PageConfig.safeParse(json);
  if (!parsed.success) return null;
  const { appName, appVersion, exposeAppInBrowser } = parsed.data;
  return {
    appName: appName ?? 'Jupyter',
    appVersion: appVersion ?? null,
    // The server writes the Python bool, which older templates render as a string.
    exposesApp: exposeAppInBrowser === true || String(exposeAppInBrowser).toLowerCase() === 'true',
  };
}

/** The lines that turn access on, for `~/.jupyter/jupyter_server_config.py` on the server. */
export const SERVER_CONFIG_LINES = [
  'c.JupyterNotebookApp.expose_app_in_browser = True',
  'c.LabApp.expose_app_in_browser = True',
] as const;
