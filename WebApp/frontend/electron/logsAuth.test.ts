import { test } from 'node:test'
import assert from 'node:assert/strict'
import { randomBytes, scryptSync } from 'node:crypto'
import { passwordMatches } from './logsAuth.ts'

// A "saltHex:hashHex" for a known password, made exactly as the installer does
// (keylen 64), so this exercises the real scrypt verify, not a stand-in
const salt = randomBytes(16)
const STORED = `${salt.toString('hex')}:${scryptSync('correct horse', salt, 64).toString('hex')}`

test('the right password matches', () => {
  assert.equal(passwordMatches('correct horse', STORED), true)
})

test('a wrong password does not match', () => {
  assert.equal(passwordMatches('correct horse ', STORED), false)
  assert.equal(passwordMatches('battery staple', STORED), false)
  assert.equal(passwordMatches('', STORED), false)
})

test('a malformed stored value fails closed', () => {
  assert.equal(passwordMatches('correct horse', 'not-a-salt-hash'), false)
  assert.equal(passwordMatches('correct horse', ':'), false)
  assert.equal(passwordMatches('correct horse', 'zz:zz'), false)  // bad hex
})

test('a non-string password fails closed', () => {
  assert.equal(passwordMatches(undefined, STORED), false)
  assert.equal(passwordMatches(1234, STORED), false)
  assert.equal(passwordMatches(null, STORED), false)
})
