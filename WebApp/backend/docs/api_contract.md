# Model → Backend API Contract — v2

Endpoint: `POST /sessions/{session_id}/bullets`

The detection model calls this endpoint once per confirmed Bullet Hole.

A Session spans every enabled camera, one board each, so a posted hole names
the board it was seen on with `camera` (the camera's alias). That is the change
from `v1`, which named no camera because a Session watched a single camera.

## Request body

```json
{
  "version": "v2",
  "camera": "lane1",
  "first_seen_at": "2026-10-08T14:32:07.412Z",
  "position": {
    "x": 774.8,
    "y": 560.3
  },
  "target_index": 0,
  "x_mm": -12.3,
  "y_mm": 4.1,
  "source": "model",
  "idempotency_key": "8c4b7d1e-3f0a-5b6c-9d2e-1a7f4e8b0c35"
}
```

## Field reference

| Field | Type | Required | Description |
|---|---|---|---|
| `version` | string | yes | Must be `"v2"`. Any other version, `"v1"` included, is rejected with `422`. |
| `camera` | string | no | The board the hole is on: the camera's alias, as the Session's Run watched it. `null` or absent is a hole on no board — a manual one in a Session with no camera. |
| `first_seen_at` | string (ISO 8601, timezone required) | yes | Absolute UTC time of the frame in which the model first detected the Bullet Hole, not of its confirmation. Naive timestamps (no `Z` or offset) are rejected with `422`. |
| `position.x` | float | yes | Template-space X coordinate in px, any finite number. The largest Target's artwork spans 0–1405; a Bullet Hole off that artwork (a Miss, or a Bullet Hole on another Target) lies outside it. |
| `position.y` | float | yes | Template-space Y coordinate in px, any finite number. The artwork spans 0–1120, and a Bullet Hole off it lies outside it, as for `position.x`. |
| `target_index` | integer | no | Index of the Target the hole landed on, when the model can determine it. `null` or absent means Miss or undetermined. |
| `x_mm` | float | no | Horizontal offset from Target centre in millimetres. Requires a calibrated print scale. `null` if unavailable. |
| `y_mm` | float | no | Vertical offset from Target centre in millimetres. Requires a calibrated print scale. `null` if unavailable. |
| `source` | string | no | `"model"` (default). |
| `idempotency_key` | string | no | Makes a retry safe. A key the Session already holds stores nothing new: the response is the existing row, with `201`. The `404` and `409` checks come first, so a retry into a completed Session still gets `409`. The model derives the key from the Session, the **camera**, the Bullet Hole's first frame and its template coordinates rounded to whole px — the camera because boards share Template space and each Stream counts frames from its own start, so two holes on different boards can otherwise share a key. A retry, or a rerun of the same Recording, sends the same key. |

## Responses

| Status | Meaning |
|---|---|
| `201` | Bullet hole stored. Response body is the created row, or the existing row when the Session already holds the `idempotency_key`. |
| `404` | Session not found. |
| `409` | Session is completed and `source` is `"model"`. |
| `422` | Payload validation failed (wrong `version`, missing field, bad type, NaN or infinity, naive timestamp). |
