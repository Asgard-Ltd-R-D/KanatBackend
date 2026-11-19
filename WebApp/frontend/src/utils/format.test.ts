import { test } from 'node:test'
import assert from 'node:assert/strict'
import { formatLength, formatDuration } from './format.ts'

test('formatLength rounds before dividing, so 119.6s is 2:00 not 1:60', () => {
  assert.equal(formatLength(119.6), '2:00')
  assert.equal(formatLength(0), '0:00')
  assert.equal(formatLength(5), '0:05')
  assert.equal(formatLength(65), '1:05')
  assert.equal(formatLength(600), '10:00')
})

test('formatDuration is whole minutes and seconds between two moments', () => {
  assert.equal(formatDuration('2026-10-22T10:00:00.000Z', '2026-10-22T10:12:04.000Z'), '12m 4s')
  assert.equal(formatDuration('2026-10-22T10:00:00.000Z', '2026-10-22T10:00:00.000Z'), '0m 0s')
})

test('formatDuration shows hours from the first hour on, not minutes past 59', () => {
  assert.equal(formatDuration('2026-10-22T10:00:00.000Z', '2026-10-22T10:59:59.000Z'), '59m 59s')
  assert.equal(formatDuration('2026-10-22T10:00:00.000Z', '2026-10-22T11:00:00.000Z'), '1h 0m 0s')
  assert.equal(formatDuration('2026-10-22T10:00:00.000Z', '2026-10-22T12:05:09.000Z'), '2h 5m 9s')
})

test('formatDuration never goes below zero when the clocks disagree', () => {
  assert.equal(formatDuration('2026-10-22T10:00:05.000Z', '2026-10-22T10:00:00.000Z'), '0m 0s')
})
