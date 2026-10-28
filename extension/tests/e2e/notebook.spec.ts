import type { Page } from '@playwright/test';
import { expect, test } from './fixtures';
import { EXPOSED, PLAIN } from './servers';

/** Opens a notebook and waits until Jupyter has loaded it. */
async function openNotebook(page: Page, base: string, name: string) {
  await page.goto(`${base}/notebooks/${name}`);
  await expect(page.locator('.jp-Notebook .jp-Cell').first()).toBeVisible({ timeout: 30_000 });
}

test('lists the cell that raised, with where and why', async ({ context, openPanel }) => {
  const page = await context.newPage();
  await openNotebook(page, EXPOSED, 'control.ipynb');
  const panel = await openPanel(page);

  await expect(panel.getByRole('heading', { name: '1 error' })).toBeVisible();
  await expect(panel.locator('.notebook')).toHaveText('control.ipynb');
  const card = panel.locator('.note');
  await expect(card.locator('.ename')).toHaveText('ValueError');
  await expect(card).toContainText('size 3 is different from 4');
  await expect(card).toContainText('Cell In[3], line 3');
  await expect(card.locator('.source-line')).toHaveText('h @ psi');
  await expect(card.getByRole('button', { name: 'Go to cell 4' })).toHaveText('4');
  // The traceback stays folded until you ask for it.
  await expect(card.locator('.details')).toBeHidden();
  await card.getByRole('button', { name: 'Details' }).click();
  await expect(card.locator('.details pre')).toContainText('Traceback (most recent call last)');
});

test('Go to cell selects that cell in the notebook', async ({ context, openPanel }) => {
  const page = await context.newPage();
  await openNotebook(page, EXPOSED, 'control.ipynb');
  const panel = await openPanel(page);

  await panel.getByRole('button', { name: 'Go to cell', exact: true }).click();
  await expect
    .poll(() =>
      page.evaluate(
        () =>
          (
            window as unknown as {
              jupyterapp: { shell: { currentWidget: { content: { activeCellIndex: number } } } };
            }
          ).jupyterapp.shell.currentWidget.content.activeCellIndex,
      ),
    )
    .toBe(3);
});

test('a new error shows up as soon as the cell runs', async ({ context, openPanel }) => {
  const page = await context.newPage();
  await openNotebook(page, EXPOSED, 'clean.ipynb');
  const panel = await openPanel(page);
  await expect(panel.getByRole('heading', { name: 'No cell has an error' })).toBeVisible();

  await page.evaluate(async () => {
    type App = {
      shell: {
        currentWidget: {
          content: {
            activeCellIndex: number;
            activeCell: { model: { sharedModel: { setSource(s: string): void } } };
          };
          sessionContext: { ready: Promise<void> };
        };
      };
      commands: { execute(id: string): Promise<unknown> };
    };
    const app = (window as unknown as { jupyterapp: App }).jupyterapp;
    const panel = app.shell.currentWidget;
    await panel.sessionContext.ready;
    panel.content.activeCellIndex = 2;
    await app.commands.execute('notebook:insert-cell-below');
    panel.content.activeCell.model.sharedModel.setSource('1 / 0');
    await app.commands.execute('notebook:run-cell');
  });

  await expect(panel.getByRole('heading', { name: '1 error' })).toBeVisible({
    timeout: 30_000,
  });
  await expect(panel.locator('.note')).toContainText('ZeroDivisionError');
});

test('reconnects after the notebook tab reloads', async ({ context, openPanel }) => {
  const page = await context.newPage();
  await openNotebook(page, EXPOSED, 'control.ipynb');
  const panel = await openPanel(page);
  await expect(panel.getByRole('heading', { name: '1 error' })).toBeVisible();

  await page.reload();
  await expect(page.locator('.jp-Notebook .jp-Cell').first()).toBeVisible({ timeout: 30_000 });
  await expect(panel.getByRole('heading', { name: '1 error' })).toBeVisible();
  await expect(panel.getByText('Reload to connect')).toHaveCount(0);
});

test('asks for the server setting when Jupyter keeps the app to itself', async ({
  context,
  openPanel,
}) => {
  const page = await context.newPage();
  await openNotebook(page, PLAIN, 'control.ipynb');
  const panel = await openPanel(page);

  await expect(panel.getByRole('heading', { name: 'One setting on the server' })).toBeVisible();
  await expect(panel.locator('.codeblock pre')).toContainText(
    'c.JupyterNotebookApp.expose_app_in_browser = True',
  );
});

test('says so on a page that is not Jupyter', async ({ context, openPanel }) => {
  const page = await context.newPage();
  await page.goto(`${EXPOSED}/api/status`);
  const panel = await openPanel(page);
  await expect(panel.getByRole('heading', { name: 'This page isn’t Jupyter' })).toBeVisible();
});

test('Ket answers a click with a measurement', async ({ context, openPanel }) => {
  const page = await context.newPage();
  await openNotebook(page, EXPOSED, 'clean.ipynb');
  const panel = await openPanel(page);
  await expect(panel.getByRole('heading', { name: 'No cell has an error' })).toBeVisible();

  await panel.getByRole('button', { name: /Ket, Marginalia's lamb/ }).click();
  // The bell sits at |0⟩ when the notebook is clean, so the Born rule says |0⟩.
  await expect(panel.locator('.ket-said')).toHaveText('|0⟩');
});
