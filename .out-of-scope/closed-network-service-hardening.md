# Service hardening on the closed range network

Kanat does not add authentication, authorisation or interface restrictions to
its own services while it runs on a closed range network with no internet
exposure.

## Why this is out of scope

Everyone who can reach a Kanat port is already inside the closed network. No
SOW item asks for authentication or a security review, and the system has
never had either: none of its services authenticate callers beyond the
defaults in the checked-in configs.

| Service | As checked in |
|---|---|
| PacketProcessingService | all interfaces, no authentication |
| WebApp backend | no authentication, CORS `*` |
| Postgres, QuestDB, Seq | default credentials from `docker-compose.*.yml` |
| MediaMTX (`VideoService/mediamtx.yml`) | anonymous `publish`, `read`, `playback` and `api` from any IP |

Hardening one of them does not change what someone inside the network can do
with the others. When hardening is needed, it is one piece of work across all
of them.

It is also not cheap for MediaMTX alone. KanatFrontend calls the Control API
(:9997) directly, with no credentials, at a configurable host
(`src/models/mediamtx.ts`), so stations other than the MediaMTX host use it.
Binding the API to localhost breaks them, and any authentication needs a
KanatFrontend release with credential storage, plus a new way for a range day
to fail.

## Rules that still apply

These cost nothing and are what actually limit exposure:

- **The camera account MediaMTX pulls with can view only and belongs to
  Kanat alone**: no PTZ, configuration or admin rights, not shared with other
  systems. A camera path's `source` holds that account's credentials, and
  MediaMTX's config endpoints return it. With a view-only account they give
  no more than reading the stream from MediaMTX already does.
- **No credentials in Git, documentation, issue text, logs or CLI output.**
  Example configs use placeholders, and the pipeline strips URL credentials
  from its output (`_redacted`, #83).

## When to reopen

- The customer's approval of the range network requires authentication or a
  security review of the system.
- Kanat is connected to anything beyond the closed range network.
- The camera account cannot be view-only or dedicated to Kanat.

Reopen it as one ticket covering every service in the table. #89 has the
MediaMTX details: which endpoints return the camera credentials (verified on
MediaMTX v1.21.1), which callers use the Control API, and that RTSPS/SRTP
between the camera and MediaMTX is a separate decision.

## Prior requests

- #89: "VideoService MediaMTX: authenticate the Control API and keep camera
  credentials out of reach"
