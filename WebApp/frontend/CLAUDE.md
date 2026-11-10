# WebApp frontend

Electron 33 + React + Vite + Tailwind, TypeScript. Read `WebApp/CONTEXT.md` for the domain words before changing behaviour.

## Layout

| Folder | Holds | Rule |
|---|---|---|
| `src/api/` | every backend and MediaMTX (WHEP) call, and the Logs tab's log read | Components never call `fetch` directly; they import from here. `client.ts` has `apiFetch` and `ApiError`. |
| `src/pages/` | one component per route (Session list, Session detail, Settings, Logs) | |
| `src/components/{Session,Camera,Settings,UI}/` | the pieces pages use | `UI/` is generic, the rest are domain parts. |
| `src/hooks/`, `src/utils/`, `src/types/` | shared hooks, formatting helpers, API types | Types mirror the backend's schemas; change both together. |
| `electron/` | the main process | `main.ts` starts it; `window.ts` the window and its link rules; `protocol.ts` the `app://kanat` origin and the CSP; `config.ts` `kanat-config.json`; `preload.ts` + `ipc.ts` + `channels.ts` the bridge; `logs.ts` `frontend.log`. |

## Commands

```bash
npm run dev          # Vite + Electron, against the backend on 127.0.0.1:8000
npx tsc --noEmit     # type check
npm test             # node --test 'src/**/*.test.ts'
npm run dist:win     # Windows installer (NSIS) into release/, buildable on the Mac
```

## Rules

- **Electron security stays on:** context isolation, the preload as the only bridge, and the window never navigates away from its own pages (`will-navigate`). A new IPC channel goes in `channels.ts`, `ipc.ts` and `preload.ts` together.
- **Links to the backend open with `target="_blank"`**: `window.ts` turns them into downloads with a Save dialog. A plain or `download` link is a navigation, which the app blocks (that broke the CSV and Excel exports once).
- **A new origin** (another service URL) goes in the CSP in `protocol.ts`, and in `config.ts` if it's configurable.
- **Config:** defaults use `127.0.0.1`. Installed on Windows, `C:\ProgramData\Kanat\kanat-config.json` overrides them; its byte order mark is stripped.
- **One instance only** (`requestSingleInstanceLock` in `main.ts`).
- **Dependencies:** exact versions, and `package-lock.json` committed with them. `npm ci` in CI and in the bundle build.
- **The installed app is not the dev app:** check anything touching URLs, files, downloads or the window in a packaged build (`npm run dist:win`, or `electron-builder --dir` on the Mac).
