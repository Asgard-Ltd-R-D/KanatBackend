import { contextBridge, ipcRenderer } from 'electron'

contextBridge.exposeInMainWorld('versions', {
  node: () => process.versions.node,
  electron: () => process.versions.electron,
})

contextBridge.exposeInMainWorld('kanat', {
  apiUrl: ipcRenderer.sendSync('kanat-get-api-url') as string,
})
