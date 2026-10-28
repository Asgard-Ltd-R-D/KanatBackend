# Enable MPI in Live WebApp Reports

## Problem

MPI is already implemented and tested, but live Detection Service runs do not
currently provide a print scale to the detection pipeline. As a result,
confirmed Bullet Holes may have image coordinates (`position_x`, `position_y`)
but no physical coordinates (`x_mm`, `y_mm`).

The WebApp calculates a Group and its MPI only when a Bullet Hole has all of:

- `target_index`
- `x_mm`
- `y_mm`

Without those values, the PDF places the Bullet Hole under either `Misses` or
`Without a Position` and does not render an MPI row.

## 1. Verify the print scale

The existing development recordings use:

```text
0.1763 mm per template pixel
```

This value is recorded in
[`../config/print_scale.json`](../config/print_scale.json). Use it only when the
physical target was printed with the same artwork, paper size, and print
scaling. If the current target was printed differently, measure its scale using
[`ring_measurement.md`](ring_measurement.md) before continuing.

Do not calculate physical MPI directly from `position_x` and `position_y`.
Those fields are template-image coordinates, not millimetres relative to the
centre of a target.

## 2. Add the scale to `DetectionService`

Update `detection/service.py` so `DetectionService` accepts and stores a print
scale:

```python
class DetectionService:
    def __init__(self, model, backend_url, opener=None, mm_per_tpl_px=None):
        self._model = model
        self._backend_url = backend_url
        self._opener = opener
        self._mm_per_tpl_px = mm_per_tpl_px
        self._lock = threading.Lock()
        self._run = None
```

Validate the value with `board.checked_scale` rather than accepting an
unchecked or non-positive scale.

## 3. Pass the scale into the live pipeline

In `DetectionService._work`, pass the stored scale to `nbh.process`:

```python
nbh.process(
    loop,
    None,
    mm_per_tpl_px=self._mm_per_tpl_px,
    publish=publisher.publish,
    watching=lambda view, marks: self._watching(run, view, marks),
)
```

This causes confirmed Bullet Holes on a detected target to include `x_mm` and
`y_mm` in the payload sent to the WebApp.

## 4. Add the command-line option

In the `if __name__ == "__main__"` block of `detection/service.py`, add:

```python
p.add_argument(
    "--mm-per-px",
    type=nbh.board.checked_scale,
    default=None,
    help="verified print scale in millimetres per template pixel",
)
```

Pass the parsed value when creating the service:

```python
service = DetectionService(
    nbh.load_model(a.model),
    a.backend_url,
    mm_per_tpl_px=a.mm_per_px,
)
```

## 5. Add regression tests

Extend `tests/test_service.py` to verify both cases:

1. Without a scale, a confirmed Bullet Hole still has `x_mm` and `y_mm` set to
   `null`.
2. With a verified scale, a confirmed Bullet Hole on a target is posted with
   non-null millimetre coordinates.

Keep the existing grouping tests. They verify that the WebApp calculates MPI,
CEP, Mean Radius, RMS Radius, and Extreme Spread from stored millimetre
positions.

Run the relevant tests:

```bash
cd ImageRecognitionService
.venv/bin/pytest -q tests/test_service.py tests/test_groups.py tests/test_webapp.py
```

## 6. Start the live service with the verified scale

For a target whose verified scale is `0.1763`:

```bash
cd ImageRecognitionService
.venv/bin/python -m detection.service --mm-per-px 0.1763
```

Then start and complete a new WebApp session and export its PDF.

## 7. Verify the result

For each hit expected to participate in MPI, verify that the session API
contains:

```json
{
  "target_index": 0,
  "x_mm": 12.3,
  "y_mm": -4.1
}
```

The exact values will depend on the impact position. The completed session and
its PDF should show a Group row containing MPI.

- One positioned hit produces an MPI, but spread values are `—`.
- Two or more positioned hits on the same target produce MPI and spread
  statistics.
- A Miss has no `target_index` and is intentionally excluded from MPI.

## Existing sessions

Regenerating an old report does not create missing millimetre coordinates.
Sessions such as `test3.1` were stored without the required `x_mm` and `y_mm`
values and must be reprocessed from their recording with the verified scale, or
repeated as a new live session.

Do not backfill physical coordinates by averaging the displayed pixel
positions. That would produce an uncalibrated and incorrectly referenced MPI.

## Recommended follow-up

The command-line flag is the smallest safe fix for the current single-camera
setup. For multiple cameras or differently printed targets, store a verified
print scale per camera or Capture Setup in the WebApp and include it when the
backend starts a Detection Service Run.
