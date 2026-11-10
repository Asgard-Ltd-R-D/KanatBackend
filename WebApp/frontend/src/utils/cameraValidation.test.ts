import { test } from 'node:test'
import assert from 'node:assert/strict'
import { validateCamera, toInput, toForm, type CameraForm } from './cameraValidation.ts'

const VALID: CameraForm = { alias: 'lane1', mcast_ip: '226.226.226.112', mcast_port: '50000', iface: 'eth1', enabled: true }
const form = (over: Partial<CameraForm>): CameraForm => ({ ...VALID, ...over })
const keys = (f: CameraForm) => Object.keys(validateCamera(f)).sort()

test('a well-formed camera has no errors', () => {
  assert.deepEqual(validateCamera(VALID), {})
})

test('the multicast group must be in 224.0.0.0 – 239.255.255.255', () => {
  assert.deepEqual(keys(form({ mcast_ip: '192.168.1.10' })), ['mcast_ip'])  // unicast
  assert.deepEqual(keys(form({ mcast_ip: '223.1.1.1' })), ['mcast_ip'])     // just below the range
  assert.deepEqual(keys(form({ mcast_ip: '240.1.1.1' })), ['mcast_ip'])     // just above
  assert.deepEqual(keys(form({ mcast_ip: '226.226.226' })), ['mcast_ip'])   // malformed
  assert.deepEqual(validateCamera(form({ mcast_ip: '239.255.255.255' })), {})  // top of the range
})

test('the alias must start alphanumeric and hold only letters, digits, - and _', () => {
  assert.deepEqual(keys(form({ alias: 'lane 1' })), ['alias'])  // space
  assert.deepEqual(keys(form({ alias: '-cam' })), ['alias'])    // leading hyphen
  assert.deepEqual(keys(form({ alias: 'a' })), ['alias'])       // too short (min 2)
})

test('the port must be an integer from 1 to 65535', () => {
  assert.deepEqual(keys(form({ mcast_port: '0' })), ['mcast_port'])
  assert.deepEqual(keys(form({ mcast_port: '70000' })), ['mcast_port'])
  assert.deepEqual(keys(form({ mcast_port: '12.5' })), ['mcast_port'])
  assert.deepEqual(keys(form({ mcast_port: '' })), ['mcast_port'])
})

test('a Windows interface name with a space is accepted (matches the backend)', () => {
  // The backend allows friendly names like "Ethernet 2"; the form must too
  assert.deepEqual(validateCamera(form({ iface: 'Ethernet 2' })), {})
})

test('an interface name with shell/url-unsafe characters is rejected', () => {
  assert.deepEqual(keys(form({ iface: 'eth0"; reboot' })), ['iface'])
})

test('a blank interface is allowed and becomes null in the input', () => {
  assert.deepEqual(validateCamera(form({ iface: '   ' })), {})
  assert.equal(toInput(form({ iface: '   ' })).iface, null)
})

test('toForm and toInput round-trip a camera', () => {
  const input = { alias: 'lane2', mcast_ip: '226.1.2.3', mcast_port: 50002, iface: 'eth1', enabled: false }
  assert.deepEqual(toInput(toForm(input)), input)
})
