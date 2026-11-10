import { scryptSync, timingSafeEqual } from 'crypto'

// Verifies the engineer password that unlocks the Logs tab against the stored
// "saltHex:hashHex" (scrypt). Pure (crypto only), so it is tested directly; the
// IPC gating that uses it lives in ipc.ts. Comparison is constant-time, and any
// malformed stored value or non-string input fails closed.
export function passwordMatches(password: unknown, stored: string): boolean {
  if (typeof password !== 'string') return false
  const [saltHex, hashHex] = stored.split(':')
  if (!saltHex || !hashHex) return false
  try {
    const expected = Buffer.from(hashHex, 'hex')
    // Invalid hex decodes to an empty buffer; a zero-length hash would make any
    // password "match" (scrypt keylen 0, then timingSafeEqual of two empties)
    if (expected.length === 0) return false
    const actual = scryptSync(password, Buffer.from(saltHex, 'hex'), expected.length)
    return expected.length === actual.length && timingSafeEqual(actual, expected)
  } catch {
    return false
  }
}
