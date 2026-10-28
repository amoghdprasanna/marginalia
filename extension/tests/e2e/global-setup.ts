import { spawn, type ChildProcess } from 'node:child_process';
import { cpSync, mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { EXPOSED, NOTEBOOK_VERSION, PLAIN } from './servers';

/**
 * Starts real Jupyter Notebook servers with `uvx` (docs/adr/0029): one with
 * expose_app_in_browser, one without. Each serves a copy of the fixtures and
 * reads config from an empty folder, so your own ~/.jupyter can't leak in.
 */
function start(url: string, expose: boolean, root: string): ChildProcess {
  const port = new URL(url).port;
  const home = mkdtempSync(path.join(tmpdir(), 'marginalia-jupyter-'));
  return spawn(
    'uvx',
    [
      '--from',
      `notebook==${NOTEBOOK_VERSION}`,
      '--with',
      'ipykernel',
      'jupyter-notebook',
      '--no-browser',
      `--port=${port}`,
      '--ServerApp.ip=127.0.0.1',
      '--ServerApp.port_retries=0',
      '--IdentityProvider.token=',
      '--ServerApp.password=',
      `--ServerApp.root_dir=${root}`,
      `--JupyterNotebookApp.expose_app_in_browser=${expose ? 'True' : 'False'}`,
    ],
    {
      env: {
        ...process.env,
        JUPYTER_CONFIG_DIR: path.join(home, 'config'),
        JUPYTER_RUNTIME_DIR: path.join(home, 'runtime'),
        JUPYTER_PLATFORM_DIRS: '1',
      },
      stdio: process.env.MARGINALIA_E2E_LOG ? 'inherit' : 'ignore',
    },
  );
}

async function ready(url: string, server: ChildProcess, timeoutMs = 180_000): Promise<void> {
  const until = Date.now() + timeoutMs;
  while (Date.now() < until) {
    if (server.exitCode !== null)
      throw new Error(
        `Jupyter at ${url} exited (${String(server.exitCode)}). Set MARGINALIA_E2E_LOG=1 to see why.`,
      );
    try {
      if ((await fetch(`${url}/api/status`)).ok) return;
    } catch {
      // not listening yet
    }
    await new Promise((r) => setTimeout(r, 500));
  }
  throw new Error(`Jupyter at ${url} didn't start in ${String(timeoutMs / 1000)} s`);
}

export default async function globalSetup(): Promise<() => void> {
  const root = mkdtempSync(path.join(tmpdir(), 'marginalia-notebooks-'));
  cpSync(path.join(import.meta.dirname, 'fixtures'), root, { recursive: true });
  const exposed = start(EXPOSED, true, root);
  const plain = start(PLAIN, false, root);
  const servers = [exposed, plain];
  try {
    await Promise.all([ready(EXPOSED, exposed), ready(PLAIN, plain)]);
  } catch (e) {
    for (const s of servers) s.kill();
    throw e;
  }
  return () => {
    for (const s of servers) s.kill();
    rmSync(root, { recursive: true, force: true });
  };
}
