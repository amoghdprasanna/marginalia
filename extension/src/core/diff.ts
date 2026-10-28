/** One line of a preview: unchanged, removed or added. */
export interface DiffLine {
  kind: 'same' | 'remove' | 'add';
  text: string;
}

/** A line diff by longest common subsequence: cells are short, so O(n·m) is fine. */
export function diffLines(before: string, after: string): DiffLine[] {
  const a = before === '' ? [] : before.split('\n');
  const b = after === '' ? [] : after.split('\n');
  const lcs: number[][] = Array.from({ length: a.length + 1 }, () =>
    new Array<number>(b.length + 1).fill(0),
  );
  for (let i = a.length - 1; i >= 0; i--)
    for (let j = b.length - 1; j >= 0; j--) {
      const row = lcs[i] ?? [];
      row[j] =
        a[i] === b[j]
          ? (lcs[i + 1]?.[j + 1] ?? 0) + 1
          : Math.max(lcs[i + 1]?.[j] ?? 0, row[j + 1] ?? 0);
    }
  const out: DiffLine[] = [];
  let i = 0;
  let j = 0;
  while (i < a.length || j < b.length) {
    if (i < a.length && j < b.length && a[i] === b[j]) {
      out.push({ kind: 'same', text: a[i] ?? '' });
      i++;
      j++;
    } else if (
      i < a.length &&
      (j >= b.length || (lcs[i + 1]?.[j] ?? 0) >= (lcs[i]?.[j + 1] ?? 0))
    ) {
      out.push({ kind: 'remove', text: a[i] ?? '' });
      i++;
    } else {
      out.push({ kind: 'add', text: b[j] ?? '' });
      j++;
    }
  }
  return out;
}

/**
 * The lines worth showing: every change with `context` unchanged lines around it, and a
 * `skipped` count where the rest is folded away.
 */
export function hunks(
  lines: DiffLine[],
  context = 2,
): (DiffLine | { kind: 'skip'; count: number })[] {
  const keep = lines.map((_line, i) =>
    lines.slice(Math.max(0, i - context), i + context + 1).some((m) => m.kind !== 'same'),
  );
  const out: (DiffLine | { kind: 'skip'; count: number })[] = [];
  let skipped = 0;
  lines.forEach((l, i) => {
    if (keep[i]) {
      if (skipped > 0) out.push({ kind: 'skip', count: skipped });
      skipped = 0;
      out.push(l);
    } else skipped++;
  });
  if (skipped > 0) out.push({ kind: 'skip', count: skipped });
  return out;
}
