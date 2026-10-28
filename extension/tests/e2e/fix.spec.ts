import type { Page } from '@playwright/test';
import { expect, test } from './fixtures';
import { EXPOSED } from './servers';

type App = {
  shell: {
    currentWidget: {
      content: {
        model: {
          cells: {
            length: number;
            get(i: number): { sharedModel: { getSource(): string; setSource(s: string): void } };
          };
        };
      };
    };
  };
};

async function openNotebook(page: Page, name: string) {
  await page.goto(`${EXPOSED}/notebooks/${name}`);
  await expect(page.locator('.jp-Notebook .jp-Cell').first()).toBeVisible({ timeout: 30_000 });
}

/** Every cell's source, read from Jupyter's own model: what's really in the notebook. */
function sources(page: Page): Promise<string[]> {
  return page.evaluate(() => {
    const cells = (window as unknown as { jupyterapp: App }).jupyterapp.shell.currentWidget.content
      .model.cells;
    return Array.from({ length: cells.length }, (_, i) => cells.get(i).sharedModel.getSource());
  });
}

test('Fix with Claude proposes a diff, Apply changes the cell, Undo puts it back', async ({
  context,
  openPanel,
}) => {
  const page = await context.newPage();
  await openNotebook(page, 'control.ipynb');
  const panel = await openPanel(page);
  await expect(panel.getByRole('combobox', { name: 'Model for fixes' })).toHaveValue('claude-test');
  const before = await sources(page);

  await panel.getByRole('button', { name: 'Fix with Claude' }).click();
  await expect(panel.getByText(/Claude is reading 4 cells/)).toBeVisible();
  await expect(panel.getByText('psi has 3 rows but h is 4 by 4.')).toBeVisible();
  const diff = panel.locator('.diff');
  await expect(diff.locator('figcaption')).toHaveText('Change to cell 4');
  await expect(diff.locator('.diff-remove')).toContainText('psi = np.ones((3, 1))');
  await expect(diff.locator('.diff-add')).toContainText('psi = np.ones((4, 1))');
  // Nothing changes until Apply.
  expect(await sources(page)).toEqual(before);

  await panel.getByRole('button', { name: 'Apply' }).click();
  await expect(panel.getByText('Changed cell 4. Run it to check.')).toBeVisible();
  expect((await sources(page))[3]).toContain('np.ones((4, 1))');

  await panel.getByRole('button', { name: 'Undo' }).click();
  await expect(panel.getByRole('button', { name: 'Apply' })).toBeVisible();
  expect(await sources(page)).toEqual(before);
});

test('a missing module gets a %pip cell before it, which Undo removes', async ({
  context,
  openPanel,
}) => {
  const page = await context.newPage();
  await openNotebook(page, 'missing.ipynb');
  const panel = await openPanel(page);

  await panel.getByRole('button', { name: 'Fix with Claude' }).click();
  await expect(panel.locator('.diff figcaption')).toHaveText('New cell before cell 2');
  await panel.getByRole('button', { name: 'Apply' }).click();
  await expect(panel.getByText('Added a cell before cell 2.')).toBeVisible();
  expect(await sources(page)).toEqual([
    '# Jaynes–Cummings control\n',
    '%pip install qutip',
    'import numpy as np\nimport qutip as qt',
  ]);

  await panel.getByRole('button', { name: 'Undo' }).click();
  await expect(panel.getByRole('button', { name: 'Apply' })).toBeVisible();
  expect(await sources(page)).toHaveLength(2);
});

test('an edit to the cell after Claude looked makes Apply refuse', async ({
  context,
  openPanel,
}) => {
  const page = await context.newPage();
  await openNotebook(page, 'control.ipynb');
  const panel = await openPanel(page);
  await panel.getByRole('button', { name: 'Fix with Claude' }).click();
  await expect(panel.getByRole('button', { name: 'Apply' })).toBeVisible();

  await page.evaluate(() => {
    const cells = (window as unknown as { jupyterapp: App }).jupyterapp.shell.currentWidget.content
      .model.cells;
    cells.get(3).sharedModel.setSource('# I rewrote this myself');
  });
  await panel.getByRole('button', { name: 'Apply' }).click();
  await expect(panel.getByText('The cell changed since Claude looked at it.')).toBeVisible();
  expect((await sources(page))[3]).toBe('# I rewrote this myself');
});

test('the model menu picks who answers, and the proposal says who did', async ({
  context,
  openPanel,
}) => {
  const page = await context.newPage();
  await openNotebook(page, 'control.ipynb');
  const panel = await openPanel(page);
  const menu = panel.getByRole('combobox', { name: 'Model for fixes' });
  await expect(menu).toHaveValue('claude-test');
  await menu.selectOption({ label: 'Claude Fast' });

  await panel.getByRole('button', { name: 'Fix with Claude' }).click();
  await expect(panel.getByText('Claude Fast suggests')).toBeVisible();

  // Remembered: a new panel starts on the same model.
  await panel.reload();
  await expect(panel.getByRole('combobox', { name: 'Model for fixes' })).toHaveValue('claude-fast');
});

test.describe('without the helper installed', () => {
  test.use({ helper: false });

  test('a Connect Claude card says how, and Fix waits for it', async ({ context, openPanel }) => {
    const page = await context.newPage();
    await openNotebook(page, 'control.ipynb');
    const panel = await openPanel(page);
    await expect(panel.getByText('Claude not connected')).toBeVisible();

    const card = panel.locator('.connect');
    await expect(card.getByRole('heading', { name: 'Connect Claude' })).toBeVisible();
    await expect(card.locator('.codeblock pre')).toHaveText('marginalia-browser-host install');
    await expect(card).toContainText('Chrome said:');
    await expect(card.getByRole('button', { name: 'Check again' })).toBeVisible();
    await expect(panel.getByRole('button', { name: 'Fix with Claude' })).toBeDisabled();
  });
});

test.describe('with a helper set up for another extension', () => {
  test.use({ helper: 'other-id' });

  test('says to set the helper up again', async ({ context, openPanel }) => {
    const page = await context.newPage();
    await openNotebook(page, 'control.ipynb');
    const panel = await openPanel(page);
    const card = panel.locator('.connect');
    await expect(card).toContainText('set up for another copy of Marginalia');
    await expect(card.locator('.codeblock pre')).toHaveText('marginalia-browser-host install');
  });
});
