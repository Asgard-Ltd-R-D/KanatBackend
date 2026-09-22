"""Derive the new Bullet Holes from a before/after photograph pair.

Ground truth is two labelled photographs of the Board — one before firing, one
after — and the new Bullet Holes are the set difference. The derivation itself
lives in `evaluate.py`, beside the matching and the scoring it shares; this is
its command line.

    python derive_truth.py \\
        --before-image  photos/CamB.before.jpeg --before-labels export/before.txt \\
        --after-image   photos/CamB.after.jpeg  --after-labels  export/after.txt \\
        --out-dir truth/camb-20260915-102250

writes `board.new.txt` — the new Bullet Holes, as the after export's own lines —
beside byte-for-byte copies of both raw exports. `evaluate.py --truth-labels`
then points at that derived file, never at the after export.
"""
import argparse
import os

import board
import evaluate

if __name__ == "__main__":
    p = argparse.ArgumentParser(
        "Derive the new Bullet Holes from a before/after photograph pair")
    p.add_argument("--before-image", required=True,
                   help="photo of the Board before firing, or the hand-labelled "
                        "first frame where no before photo exists")
    p.add_argument("--before-labels", required=True, help="YOLO .txt for it")
    p.add_argument("--after-image", required=True,
                   help="photo of the Board after firing")
    p.add_argument("--after-labels", required=True, help="YOLO .txt for it")
    p.add_argument("--out-dir", required=True,
                   help=f"written: {evaluate.DERIVED_NAME} and the raw exports")
    p.add_argument("--template", default=board.DEFAULT_TEMPLATE)
    p.add_argument("--tolerance", type=float,
                   default=evaluate.MATCH_TOLERANCE_TPL,
                   help="how close two marks must be to be one mark, template px")
    a = p.parse_args()

    result = evaluate.derive_new_holes(a.before_image, a.before_labels,
                                       a.after_image, a.after_labels,
                                       a.template, a.tolerance)
    print(f"[TRUTH] before "
          f"{len(result['pre_existing']) + len(result['only_before'])} labelled, "
          f"after {len(result['lines'])} labelled  (registration correlation "
          f"{result['before_correlation']:.4f} / {result['after_correlation']:.4f})")
    if result["only_before"]:
        print(f"[WARN] {len(result['only_before'])} mark(s) in the before "
              "photograph have no counterpart in the after photograph. They "
              "subtract nothing, but check the registration before trusting "
              "this — a slipped homography looks exactly like this.")

    written = evaluate.write_derived(a.out_dir, result["lines"], result["new"],
                                     a.before_labels, a.after_labels)
    print(f"[NEW] {len(result['new'])} new Bullet Hole(s), "
          f"{len(result['pre_existing'])} already on the Board")
    print(f"   {written['derived']}")
    print(f"   raw exports kept: {os.path.basename(written['before_raw'])}, "
          f"{os.path.basename(written['after_raw'])}")
