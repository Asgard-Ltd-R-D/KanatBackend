import { test } from 'node:test'
import assert from 'node:assert/strict'
import { refusalToLog } from './refusals.ts'

test('a refusal repeated within a minute is counted, then logged with the count', () => {
  const key = 'GET /sessions/1 503 Database unavailable'
  assert.deepEqual(refusalToLog(key, 0), { log: true, repeats: 0 })
  assert.deepEqual(refusalToLog(key, 1_000), { log: false, repeats: 0 })
  assert.deepEqual(refusalToLog(key, 59_000), { log: false, repeats: 0 })
  assert.deepEqual(refusalToLog(key, 61_000), { log: true, repeats: 2 })
})

test('a different refusal is logged at once', () => {
  refusalToLog('GET /cameras 503 Database unavailable', 0)
  assert.deepEqual(refusalToLog('GET /recordings 503 Database unavailable', 1), { log: true, repeats: 0 })
})
