/**
 * A traceback as IPython 8 writes it into an nbformat error output: SGR
 * colour codes included, one frame in the notebook and one in a library.
 */
export const MATMUL_TRACEBACK = [
  '\u001b[0;31m---------------------------------------------------------------------------\u001b[0m',
  '\u001b[0;31mValueError\u001b[0m                                Traceback (most recent call last)',
  'Cell \u001b[0;32mIn[14], line 3\u001b[0m\n\u001b[1;32m      1\u001b[0m a \u001b[38;5;241m=\u001b[39m np\u001b[38;5;241m.\u001b[39mones((\u001b[38;5;241m4\u001b[39m, \u001b[38;5;241m4\u001b[39m))\n\u001b[1;32m      2\u001b[0m b \u001b[38;5;241m=\u001b[39m np\u001b[38;5;241m.\u001b[39mones((\u001b[38;5;241m3\u001b[39m, \u001b[38;5;241m1\u001b[39m))\n\u001b[0;32m----> 3\u001b[0m c \u001b[38;5;241m=\u001b[39m \u001b[43mevolve\u001b[49m\u001b[43m(\u001b[49m\u001b[43ma\u001b[49m\u001b[43m,\u001b[49m\u001b[43m \u001b[49m\u001b[43mb\u001b[49m\u001b[43m)\u001b[49m\n',
  'File \u001b[0;32m~/work/control.py:12\u001b[0m, in \u001b[0;36mevolve\u001b[0;34m(h, psi)\u001b[0m\n\u001b[1;32m     11\u001b[0m \u001b[38;5;28;01mdef\u001b[39;00m \u001b[38;5;21mevolve\u001b[39m(h, psi):\n\u001b[0;32m---> 12\u001b[0m     \u001b[38;5;28;01mreturn\u001b[39;00m h \u001b[38;5;241m@\u001b[39m psi\n',
  '\u001b[0;31mValueError\u001b[0m: matmul: Input operand 1 has a mismatch in its core dimension 0 (size 3 is different from 4)',
];

export function codeCell(
  id: string,
  count: number | null,
  outputs: unknown[] = [],
): Record<string, unknown> {
  return { cell_type: 'code', id, source: 'x = 1', execution_count: count, metadata: {}, outputs };
}

export function errorOutput(ename = 'ValueError', evalue = 'shapes differ'): unknown {
  return { output_type: 'error', ename, evalue, traceback: MATMUL_TRACEBACK };
}
