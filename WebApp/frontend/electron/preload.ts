import { contextBridge, ipcRenderer } from 'electron'
import { GET_CONFIG, OPEN_LOG_FOLDER, WRITE_LOG } from './channels'
import type { KanatConfig } from './config'
import type { LogEntry } from './logs'

contextBridge.exposeInMainWorld('versions', {
  node: () => process.versions.node,
  electron: () => process.versions.electron,
})

contextBridge.exposeInMainWorld('kanat', ipcRenderer.sendSync(GET_CONFIG) as KanatConfig)

// What the pages may do with the log: hand it a line, and open its folder.
// Nothing else of the file system reaches them.
contextBridge.exposeInMainWorld('kanatLog', {
  write: (entry: LogEntry) => ipcRenderer.send(WRITE_LOG, entry),
  openFolder: (): Promise<string> => ipcRenderer.invoke(OPEN_LOG_FOLDER),
})
