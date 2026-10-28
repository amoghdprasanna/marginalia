// A stand-in for marginalia-browser-host (docs/adr/0030): Chrome's native messaging framing,
// canned fixes, no network. Started by Chromium through the manifest tests/e2e/fixtures.ts writes.
import process from 'node:process';

let buffer = Buffer.alloc(0);

function send(message) {
  const body = Buffer.from(JSON.stringify(message), 'utf8');
  const header = Buffer.alloc(4);
  header.writeUInt32LE(body.length, 0);
  process.stdout.write(Buffer.concat([header, body]));
}

function fixFor(request) {
  const cell = request.cells[request.failing]?.source ?? '';
  if (request.ename === 'ModuleNotFoundError')
    return {
      summary: "qutip isn't installed in this kernel.",
      explanation: 'Install it into the running kernel, then run the import again.',
      fix: { kind: 'insert_before', source: '%pip install qutip' },
    };
  if (cell.includes('np.ones((3, 1))'))
    return {
      summary: 'psi has 3 rows but h is 4 by 4.',
      explanation: 'Make psi a 4-component column so h @ psi lines up.',
      fix: { kind: 'replace', source: cell.replace('np.ones((3, 1))', 'np.ones((4, 1))') },
    };
  return {
    summary: 'Nothing to change here.',
    explanation: 'The fix is outside the notebook.',
    fix: { kind: 'none', source: '' },
  };
}

function handle(message) {
  if (message.type === 'hello')
    return {
      id: message.id,
      type: 'hello',
      model: 'claude-test',
      modelName: 'Claude Test',
      hasKey: true,
    };
  if (message.type === 'fix')
    return { id: message.id, type: 'fix', model: 'claude-test', ...fixFor(message.request) };
  return { id: message.id, type: 'error', message: 'unknown request' };
}

process.stdin.on('data', (chunk) => {
  buffer = Buffer.concat([buffer, chunk]);
  while (buffer.length >= 4) {
    const length = buffer.readUInt32LE(0);
    if (buffer.length < 4 + length) return;
    const message = JSON.parse(buffer.subarray(4, 4 + length).toString('utf8'));
    buffer = buffer.subarray(4 + length);
    // A short pause, so the panel's "reading" state is visible to the tests.
    setTimeout(() => send(handle(message)), 300);
  }
});
process.stdin.on('end', () => process.exit(0));
