# Kanat Video Server — Sim Paths & Playback API

> 🧩 **Stack**: MediaMTX (record + playback) • RTSP/WebRTC readers • Control API
> 🔌 **Ports** in this setup: **9996 = Playback API**, **9997 = Control API**

We run two simulated paths:

- 🎞️ **`loopdemo`** — publishes an MP4 on an endless loop to RTSP and mirrors it to multicast (single GStreamer pipeline with a `tee`).
- 📼 **`recorddemo`** — subscribes to that multicast, republishes to RTSP, and **records** to disk as fMP4 with short **parts** (e.g., 2 s) and **segments** (e.g., 10 min). MediaMTX’s **Playback server** stitches parts/segments into a single stream/file for any time window you ask. ([GitHub][1])

> ℹ️ The Playback server exposes HTTP endpoints like **`/list`** and **`/get`** for recorded content (enabled by `playback: yes`). The Control API (v3) exposes endpoints such as **`/v3/paths/list`** to inspect active paths. ([GitHub][1])

---

## ✅ Quick sanity checks (sim)

- Trigger `loopdemo`:

  ```bash
  ffplay -rtsp_transport tcp "rtsp://127.0.0.1:8554/loopdemo"
  ```

- Read/verify `recorddemo`:

  ```bash
  ffplay -rtsp_transport tcp "rtsp://127.0.0.1:8554/recorddemo"
  ```

> Make sure `playback: yes` and `playbackAddress: :9996` are set in your config. ([GitHub][1])

---

## 🎛️ Control API (port **9997**)

### 🔎 List **active runtime paths**

```bash
curl "http://127.0.0.1:9997/v3/paths/list"
```

Returns JSON with paths, their sources, and connected readers/writers. (Enable with `api: yes`; by default it binds to localhost.) ([Go Packages][2])

### 🧾 List **configured** paths (from YAML)

```bash
curl "http://127.0.0.1:9997/v3/config/paths/list"
```

Helps correlate declared paths with active ones. ([GitHub][3])

> 🔐 If you see `401`, ensure API auth is set as required in your config; many setups prompt for auth by default. ([GitHub][4])

---

## ▶️ Playback API (port **9996**) — cookbook

> Base URL (dev): `http://127.0.0.1:9996`
> Required: `path=...`
> Times must be **RFC 3339** (e.g., `2025-09-29T10:00:00Z` or `…+03:00`). ([IETF Tools][5])

### 1) ⏲️ Get **1-minute video** by **start date/time**

**Path:** `recorddemo` • **Start:** `2025-09-29T10:00:00Z` • **Duration:** `60s`

```bash
curl -L \
  "http://127.0.0.1:9996/get?path=recorddemo&start=2025-09-29T10:00:00Z&duration=60&format=mp4" \
  -o recorddemo_2025-09-29T100000Z_60s.mp4
```

- `/get` takes `path`, `start` (RFC3339), `duration` (seconds), with optional `format=mp4|fmp4`. MP4 is broadly compatible. ([GitHub][1])

### 2) 🧭 Discover spans first, then play or save

List **last 10 minutes**, then open the returned `url`:

```bash
# macOS (BSD date)
START="$(date -u -v-10M +"%Y-%m-%dT%H:%M:%SZ")"
END="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
curl "http://127.0.0.1:9996/list?path=recorddemo&start=${START}&end=${END}"

# Linux (GNU date)
START="$(date -u -d '10 minutes ago' '+%Y-%m-%dT%H:%M:%SZ')"
END="$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
curl "http://127.0.0.1:9996/list?path=recorddemo&start=${START}&end=${END}"
```

Each item includes `start`, `duration`, and a ready-to-use `/get` URL. For big archives, favor windowed `/list` queries for responsiveness. ([GitHub][1])

### 3) 🎯 Play or download a span you found via `/list`

```bash
ffplay "http://127.0.0.1:9996/get?path=recorddemo&start=2025-09-28T16%3A55%3A53.297738%2B03%3A00&duration=67.538&format=mp4"

curl -L "http://127.0.0.1:9996/get?path=recorddemo&start=2025-09-28T16%3A55%3A53.297738%2B03%3A00&duration=67.538&format=mp4" \
  -o clip.mp4
```

(Example uses a local-time offset `+03:00` which is valid RFC 3339.) ([IETF Tools][5])

### 4) 🕒 “From local time” (Asia/Jerusalem, **UTC+03:00**)

```bash
# List a half-hour window at local noon
curl "http://127.0.0.1:9996/list?path=recorddemo&start=2025-09-28T12:00:00%2B03:00&end=2025-09-28T12:30:00%2B03:00"

# Play a 5-minute clip starting at 12:15 local
ffplay "http://127.0.0.1:9996/get?path=recorddemo&start=2025-09-28T12%3A15%3A00%2B03%3A00&duration=300&format=mp4"
```

`Z` means UTC; `+03:00` means “UTC plus 3 hours.” Both are accepted. ([Stack Overflow][6])

### 5) 🧪 Play the **last 60 seconds** (rolling)

```bash
START="$(date -u -v-60S +"%Y-%m-%dT%H:%M:%SZ")"  # macOS
ffplay "http://127.0.0.1:9996/get?path=recorddemo&start=${START}&duration=60&format=mp4"
```

(Use GNU `date` equivalents on Linux.) ([Unix & Linux Stack Exchange][7])

---

## 🧩 Minimal config knobs you’ll care about

```yaml
# Playback server (HTTP, /list and /get) — you’re using 9996
playback: yes
playbackAddress: :9996

# Control API (v3) — you’re using 9997
api: yes
apiAddress: :9997
```

These are defined in the stock `mediamtx.yml` with inline docs. Defaults bind to localhost unless changed. ([GitHub][1])

---

## 🛠️ Troubleshooting notes

- **`/list` slow on huge archives** → query with a **time window** (start/end) rather than a full-history scan. ([GitHub][8])
- **Control API prompts 401** → enable API and ensure auth as per your security posture; many examples expect credentials by default. ([GitHub][4])

---

## 📚 References

- **`mediamtx.yml` (official, up-to-date options: playback, addresses, etc.)**. ([GitHub][1])
- **Control API usage (`/v3/paths/list`)** with localhost binding note. ([Go Packages][2])
- **OpenAPI for API v3** (endpoint catalog). ([GitHub][3])
- **RFC 3339** time format spec & usage. ([IETF Tools][5])

---

### TL;DR (copy/paste)

- **1-minute clip from a date/time**

  ```bash
  curl -L "http://127.0.0.1:9996/get?path=recorddemo&start=2025-09-29T10:00:00Z&duration=60&format=mp4" -o clip.mp4
  ```

- **List active paths (9997)**

  ```bash
  curl "http://127.0.0.1:9997/v3/paths/list"
  ```

- **List a 10-min window**

  ```bash
  START="$(date -u -v-10M +"%Y-%m-%dT%H:%M:%SZ")"; END="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
  curl "http://127.0.0.1:9996/list?path=recorddemo&start=${START}&end=${END}"
  ```

[1]: https://raw.githubusercontent.com/bluenviron/mediamtx/main/mediamtx.yml?utm_source=chatgpt.com "configuration file - GitHub"
[2]: https://pkg.go.dev/github.com/xaionaro-go/mediamtx?utm_source=chatgpt.com "mediamtx command - github.com/xaionaro ..."
[3]: https://raw.githubusercontent.com/bluenviron/mediamtx/main/api/openapi.yaml?utm_source=chatgpt.com "https://raw.githubusercontent.com/bluenviron/media..."
[4]: https://github.com/bluenviron/mediamtx/discussions/3841?utm_source=chatgpt.com "Control and Metrics APIs asking for authentication despite ..."
[5]: https://tools.ietf.org/html/rfc3339?utm_source=chatgpt.com "RFC 3339 timestamp - tools.ietf.org"
[6]: https://stackoverflow.com/questions/33721073/how-to-interpret-rfc3339-utc-timestamp?utm_source=chatgpt.com "How to interpret RFC3339 UTC timestamp"
[7]: https://unix.stackexchange.com/questions/120484/what-is-a-standard-command-for-printing-a-date-in-rfc-3339-format?utm_source=chatgpt.com "What is a standard command for printing a date in RFC- ..."
[8]: https://github.com/bluenviron/mediamtx/issues/3637?utm_source=chatgpt.com "playback list is very slow and not all files shown · Issue #3637"
