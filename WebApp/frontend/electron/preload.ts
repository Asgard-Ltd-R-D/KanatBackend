import { contextBridge, ipcRenderer } from 'electron'
import { GET_CONFIG } from './channels'
import type { KanatConfig } from './config'

contextBridge.exposeInMainWorld('versions', {
  node: () => process.versions.node,
  electron: () => process.versions.electron,
})

contextBridge.exposeInMainWorld('kanat', ipcRenderer.sendSync(GET_CONFIG) as KanatConfig)
