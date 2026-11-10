import { test } from 'node:test'
import assert from 'node:assert/strict'
import { existsSync, mkdtempSync, readdirSync, rmSync, utimesSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { fromPage, rotateIfNewDay, utcDay } from './logs.ts'

function withDir(fn: (dir: string) => void) {
  const dir = mkdtempSync(join(tmpdir(), 'kanat-logs-'))
  try {
    fn(dir)
  } finally {
    rmSync(dir, { recursive: true, force: true })
  }
}

// --- fromPage: the untrusted-renderer input check ---

test('fromPage rejects anything that is not a log line', () => {
  assert.equal(fromPage(null), null)
  assert.equal(fromPage('nope'), null)
  assert.equal(fromPage({ level: 'info' }), null)                 // no message
  assert.equal(fromPage({ level: 'shout', message: 'hi' }), null) // bad level
  assert.equal(fromPage({ level: 'info', message: 42 }), null)    // non-string message
})

test('fromPage caps message, context, page and time so a page cannot flood the log', () => {
  const line = fromPage({
    level: 'info',
    message: 'm'.repeat(5000),
    page: 'p'.repeat(500),
    time: 't'.repeat(100),
    context: { blob: 'x'.repeat(20000) },
  })!
  assert.equal(line.message.length, 2000)
  assert.equal(line.page!.length, 200)
  assert.equal(line.time!.length, 40)
  // oversized context is replaced by a truncated marker
  assert.equal((line.context as { context_cut: string }).context_cut.length, 8000)
})

test('fromPage keeps a well-formed line', () => {
  const line = fromPage({ level: 'warning', message: 'lost', page: '/sessions', context: { camera: 'lane1' } })!
  assert.equal(line.level, 'warning')
  assert.deepEqual(line.context, { camera: 'lane1' })
})

// --- rotation ---

test('utcDay is the UTC calendar day', () => {
  assert.equal(utcDay(new Date('2026-10-22T23:30:00.000Z')), '2026-10-22')
})

const stamp = (path: string, day: string) => utimesSync(path, new Date(`${day}T12:00:00Z`), new Date(`${day}T12:00:00Z`))

test('rotateIfNewDay rolls a stale file to its day and keeps only BACKUP_DAYS', () =>
  withDir((dir) => {
    const active = join(dir, 'frontend.log')
    // Seven old rotated days already present
    for (const d of ['2020-01-01', '2020-01-02', '2020-01-03', '2020-01-04', '2020-01-05', '2020-01-06', '2020-01-07']) {
      writeFileSync(`${active}.${d}`, 'old\n')
    }
    writeFileSync(active, 'from an earlier day\n')
    stamp(active, '2020-06-01')  // last written on a day that is not today

    rotateIfNewDay(active)

    assert.ok(!existsSync(active), 'the active file rolled away')
    assert.ok(existsSync(`${active}.2020-06-01`), 'it was labelled with its own day')
    const rotated = readdirSync(dir).filter((f) => /frontend\.log\.\d{4}-\d{2}-\d{2}$/.test(f)).sort()
    assert.equal(rotated.length, 7, 'only a week of rotated files is kept')
    assert.equal(rotated[0], 'frontend.log.2020-01-02', 'the oldest day was dropped')
  }))

test('rotateIfNewDay does not roll a file written today', () =>
  withDir((dir) => {
    const active = join(dir, 'frontend.log')
    writeFileSync(active, 'today\n')  // mtime is now, i.e. today
    rotateIfNewDay(active)
    assert.ok(existsSync(active) && readdirSync(dir).length === 1, 'nothing rotated')
  }))

test('rotateIfNewDay keeps appending when that day was already rolled', () =>
  withDir((dir) => {
    const active = join(dir, 'frontend.log')
    writeFileSync(active, 'stale\n')
    stamp(active, '2020-06-01')
    writeFileSync(`${active}.2020-06-01`, 'already rolled\n')  // its target already exists

    rotateIfNewDay(active)

    assert.ok(existsSync(active), 'the active file is left to be appended to, not clobbered')
  }))
