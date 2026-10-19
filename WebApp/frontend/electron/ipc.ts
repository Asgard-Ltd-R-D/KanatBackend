import { ipcMain } from 'electron'
import { GET_CONFIG } from './channels'
import { KanatConfig } from './config'

export function registerIpcHandlers(config: KanatConfig) {
  ipcMain.on(GET_CONFIG, (event) => {
    event.returnValue = config
  })
}
