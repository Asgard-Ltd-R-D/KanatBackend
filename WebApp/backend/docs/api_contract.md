# Model → Backend API Contract — v1

Endpoint: `POST /sessions/{session_id}/bullets`

The detection model calls this endpoint once per confirmed Bullet Hole.

## Request body

```json
{
  "version": "v1",
  "first_seen_at": "2026-10-08T14:32:07.412Z",
  "position": {
    "x": 774.8,
    "y": 1417.7
  },
  "target_index": 0,
  "x_mm": -12.3,
  "y_mm": 4.1,
  "source": "model"
}
```

## Field reference

| Field | Type | Required | Description |
|---|---|---|---|
| `version` | string | yes | Must be `"v1"`. Unknown versions are rejected with `422`. |
| `first_seen_at` | string (ISO 8601, timezone required) | yes | Absolute UTC timestamp when the Bullet Hole was first confirmed by the model. Naive timestamps (no `Z` or offset) are rejected with `422`. |
| `position.x` | float | yes | Template-space X coordinate (0–1390 px). |
| `position.y` | float | yes | Template-space Y coordinate (0–1974 px). |
| `target_index` | integer | no | Index of the Target the hole landed on, when the model can determine it. `null` or absent means Miss or undetermined. |
| `x_mm` | float | no | Horizontal offset from Target centre in millimetres. Requires a calibrated print scale. `null` if unavailable. |
| `y_mm` | float | no | Vertical offset from Target centre in millimetres. Requires a calibrated print scale. `null` if unavailable. |
| `source` | string | no | `"model"` (default). |

## Responses

| Status | Meaning |
|---|---|
| `201` | Bullet hole stored. Response body is the created row. |
| `404` | Session not found. |
| `409` | Session is completed and `source` is `"model"`. |
| `422` | Payload validation failed (wrong `version`, missing field, bad type, naive timestamp). |
