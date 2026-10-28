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

const AnyCell = z.object({ cell_type: z.string(), source: Source.optional() });

const CodeCell = z.object({
  cell_type: z.literal('code'),
  id: z.string().optional(),
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
  /** The notebook line that led to it, as IPython names it: "Cell In[14], line 3". */
  where: string | null;
  /** The source line IPython marked in that frame, e.g. "x = a @ b". */
  line: string | null;
  /** The library frame that raised it, when that's not the notebook: "File h5py/h5f.pyx:106, in open()". */
  raisedIn: string | null;
  /** The cell's source when it ran (what a fix starts from). */
  source: string;
}

/** Every cell's kind and source, in order: the context a fix is asked with. */
export interface CellText {
  kind: string;
  source: string;
}

export interface NotebookSummary {
  cellCount: number;
  codeCellCount: number;
  errors: CellError[];
  cells: CellText[];
}

const sourceText = (s: string | string[] | undefined) =>
  Array.isArray(s) ? s.join('') : (s ?? '');

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

interface Frame {
  where: string;
  line: string | null;
}

/**
 * IPython 8+ tracebacks list frames as `Cell In[14], line 3` or
 * `File ~/lib/x.py:12, in f(a)`, each followed by numbered source lines with
 * `---->` on the one that ran.
 */
export function frames(traceback: string): Frame[] {
  const out: Frame[] = [];
  for (const raw of traceback.split('\n')) {
    const frame = FRAME.exec(raw.trim());
    if (frame?.[1] !== undefined) {
      out.push({ where: frame[1], line: null });
      continue;
    }
    const arrow = ARROW.exec(raw);
    const last = out.at(-1);
    if (arrow?.[1] !== undefined && last !== undefined) last.line = arrow[1].trim() || null;
  }
  return out;
}

/**
 * Where to look: the last frame in the notebook (that's the line you can change), and the
 * library frame that raised, if the last frame isn't yours.
 */
export function locate(traceback: string): {
  where: string | null;
  line: string | null;
  raisedIn: string | null;
} {
  const all = frames(traceback);
  const last = all.at(-1);
  const mine = all.filter((f) => f.where.startsWith('Cell In')).at(-1) ?? last;
  return {
    where: mine?.where ?? null,
    line: mine?.line ?? null,
    raisedIn: last !== undefined && last !== mine ? last.where : null,
  };
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
  const texts: CellText[] = [];
  let codeCellCount = 0;
  cells.forEach((raw, index) => {
    const any = AnyCell.safeParse(raw);
    texts.push(
      any.success
        ? { kind: any.data.cell_type, source: sourceText(any.data.source) }
        : { kind: 'unknown', source: '' },
    );
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
      source: sourceText(code.data.source),
    });
  });
  return { cellCount: cells.length, codeCellCount, errors, cells: texts };
}
