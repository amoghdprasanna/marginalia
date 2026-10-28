import { z } from 'zod';

/**
 * The open notebook as nbformat (https://nbformat.readthedocs.io), which is
 * what each Jupyter cell model's `toJSON()` returns. The page hands us these
 * objects, so everything is validated and anything unknown is ignored
 * (docs/adr/0029).
 */
const ErrorOutput = z.object({
  output_type: z.literal('error'),
  ename: z.string(),
  evalue: z.string(),
  traceback: z.array(z.string()),
});

const Source = z.union([z.string(), z.array(z.string())]);

const CodeCell = z.object({
  cell_type: z.literal('code'),
  id: z.string().optional(),
  // Optional: the page script leaves the source behind (src/adapters/jupyter/page.ts).
  source: Source.optional(),
  execution_count: z.number().int().nullable().optional(),
  outputs: z.array(z.unknown()),
});

/** One cell whose last run raised an exception. */
export interface CellError {
  /** Position in the notebook, from 0. */
  index: number;
  /** nbformat 4.5+ cell id; null on older notebooks. */
  cellId: string | null;
  /** The number Jupyter shows as `[14]:`; null if the cell has no count. */
  executionCount: number | null;
  ename: string;
  evalue: string;
  /** The traceback as plain text, colour codes removed. */
  traceback: string;
  /** Where it was raised, as IPython names it: "Cell In[14], line 3" or "File ~/x.py:12, in f()". */
  where: string | null;
  /** The source line IPython marked with an arrow in the last frame, e.g. "x = a @ b". */
  line: string | null;
}

export interface NotebookSummary {
  cellCount: number;
  codeCellCount: number;
  errors: CellError[];
}

// ESC [ ... final byte: covers the SGR colour codes IPython writes, and any other CSI.
// eslint-disable-next-line no-control-regex
const ANSI = /\u001b\[[0-?]*[ -/]*[@-~]/g;

export function stripAnsi(text: string): string {
  return text.replace(ANSI, '');
}

/**
 * IPython opens with a rule of dashes and pads the header ("ValueError
 * <40 spaces> Traceback (most recent call last)") for a wide terminal.
 */
export function tidy(traceback: string): string {
  return traceback
    .split('\n')
    .filter((line) => !/^-{10,}\s*$/.test(line))
    .map((line) => line.replace(/^(\S+) {3,}(Traceback \(most recent call last\))/, '$1  $2'))
    .join('\n')
    .trim();
}

const FRAME = /^(Cell In\s*\[\d*\],\s*line \d+|File \S.*?(?::\d+)?(?:, in .+)?)\s*$/;
const ARROW = /^\s*-+>\s*\d+\s(.*)$/;

/**
 * IPython 8+ tracebacks list frames as `Cell In[14], line 3` or
 * `File ~/lib/x.py:12, in f(a)`, each followed by numbered source lines with
 * `---->` on the one that ran. The last frame is where it was raised.
 */
export function locate(traceback: string): { where: string | null; line: string | null } {
  let where: string | null = null;
  let line: string | null = null;
  for (const raw of traceback.split('\n')) {
    const frame = FRAME.exec(raw.trim());
    if (frame?.[1] !== undefined) {
      where = frame[1];
      line = null;
      continue;
    }
    const arrow = ARROW.exec(raw);
    if (arrow?.[1] !== undefined && where !== null) line = arrow[1].trim() || null;
  }
  return { where, line };
}

/** The error that stopped the cell: a run raises at most once, so it is the last one. */
function errorOf(outputs: readonly unknown[]): z.infer<typeof ErrorOutput> | null {
  let found: z.infer<typeof ErrorOutput> | null = null;
  for (const out of outputs) {
    const parsed = ErrorOutput.safeParse(out);
    if (parsed.success) found = parsed.data;
  }
  return found;
}

/** Counts the cells and lists every code cell whose outputs hold an error. */
export function summarize(cells: readonly unknown[]): NotebookSummary {
  const errors: CellError[] = [];
  let codeCellCount = 0;
  cells.forEach((raw, index) => {
    const code = CodeCell.safeParse(raw);
    if (!code.success) return;
    codeCellCount += 1;
    const err = errorOf(code.data.outputs);
    if (err === null) return;
    const traceback = tidy(stripAnsi(err.traceback.join('\n')));
    errors.push({
      index,
      cellId: code.data.id ?? null,
      executionCount: code.data.execution_count ?? null,
      ename: err.ename,
      evalue: stripAnsi(err.evalue),
      traceback,
      ...locate(traceback),
    });
  });
  return { cellCount: cells.length, codeCellCount, errors };
}
