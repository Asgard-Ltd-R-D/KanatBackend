import type { KanatConfig } from '../../electron/config'

declare global {
  interface Window {
    kanat: KanatConfig
  }
}

export {}
