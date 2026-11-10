import { test } from 'node:test'
import assert from 'node:assert/strict'
import { mkdtempSync, writeFileSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { readLogs } from './logreader.ts'

function withDir(fn: (dir: string) => Promise<void> | void) {
  const dir = mkdtempSync(join(tmpdir(), 'kanat-logs-'))
  return Promise.resolve(fn(dir)).finally(() => rmSync(dir, { recursive: true, force: true }))
}

const line = (time: string, over: object = {}) =>
  JSON.stringify({ time, level: 'info', service: 'backend', message: time, ...over }) + '\n'

test('readLogs merges the files newest first and handles both time suffixes', () =>
  withDir(async (dir) => {
    writeFileSync(join(dir, 'backend.log'), line('2026-10-22T10:00:01.000+00:00') + line('2026-10-22T10:00:03.000+00:00'))
    writeFileSync(join(dir, 'frontend.log'), line('2026-10-22T10:00:02.000Z'))  // app writes "Z"
    const lines = await readLogs(dir)
    assert.deepEqual(lines.map((l) => l.message), [
      '2026-10-22T10:00:03.000+00:00',
      '2026-10-22T10:00:02.000Z',
      '2026-10-22T10:00:01.000+00:00',
    ])
  }))

test('readLogs skips blank and unparseable lines and defaults missing fields', () =>
  withDir(async (dir) => {
    writeFileSync(join(dir, 'backend.log'),
      '\n' +
      'not json at all\n' +
      JSON.stringify({ message: 'bare' }) + '\n' +       // no time/level/service
      '{"not":"a message"}\n')                            // no message field -> dropped
    const lines = await readLogs(dir)
    assert.equal(lines.length, 1)
    assert.deepEqual(
      { message: lines[0].message, level: lines[0].level, service: lines[0].service, time: lines[0].time },
      { message: 'bare', level: 'info', service: 'unknown', time: '' },
    )
  }))

test('readLogs honours the limit, keeping the newest', () =>
  withDir(async (dir) => {
    writeFileSync(join(dir, 'backend.log'),
      line('2026-10-22T10:00:01.000Z') + line('2026-10-22T10:00:02.000Z') + line('2026-10-22T10:00:03.000Z'))
    const lines = await readLogs(dir, 2)
    assert.deepEqual(lines.map((l) => l.message), ['2026-10-22T10:00:03.000Z', '2026-10-22T10:00:02.000Z'])
  }))

test('readLogs drops the partial first line when a big file is tailed', () =>
  withDir(async (dir) => {
    // A file larger than the 512 KB tail, so the read starts mid-file: the
    // first (partial) line must not appear
    const filler = Array.from({ length: 6000 }, (_, i) => line(`2026-10-22T10:00:${String(i % 60).padStart(2, '0')}.000Z`, { n: i })).join('')
    writeFileSync(join(dir, 'backend.log'), line('2026-10-22T09:00:00.000Z', { message: 'OLDEST_SENTINEL' }) + filler)
    const lines = await readLogs(dir, 100000)
    assert.ok(!lines.some((l) => l.message === 'OLDEST_SENTINEL'), 'the cut-off first line should be gone')
  }))

test('readLogs on a missing folder is empty', () =>
  withDir(async (dir) => {
    assert.deepEqual(await readLogs(join(dir, 'nope')), [])
    assert.deepEqual(await readLogs(undefined), [])
  }))
