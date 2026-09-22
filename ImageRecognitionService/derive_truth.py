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
          f"after {len(result['lines'])} labelled  (photograph-to-photograph "
          f"registration {result['correlation']:.4f}, marks are one mark within "
          f"{result['tolerance_px']:.1f} photo px)")
    if result["distances"]:
        print(f"   pre-existing marks matched at "
              f"{result['distances'][0]:.1f}-{result['distances'][-1]:.1f} px"
              f"{', after refitting on them' if result['refitted'] else ''}")

    for which, lines in (("before", result["before_lines"]),
                         ("after", result["lines"])):
        boxes = evaluate.box_lines(lines)
        if boxes and len(boxes) != len(lines):
            print(f"[MIXED] {which} export: "
                  f"{', '.join(f'line {n}' for n in boxes)} "
                  f"{'is a box' if len(boxes) == 1 else 'are boxes'} among "
                  "polygons, read as such rather than dropped")

    if result["only_before"]:
        print(f"[WARN] {len(result['only_before'])} mark(s) in the before "
              "photograph have no counterpart in the after photograph. They "
              "subtract nothing — but each one is a mark that was on the Board "
              "and is about to be counted as a new Bullet Hole, so check it "
              "before trusting this. A slipped registration looks exactly like "
              "this.")

    written = evaluate.write_derived(a.out_dir, result, a.before_image,
                                     a.before_labels, a.after_image,
                                     a.after_labels)
    print(f"[NEW] {len(result['new'])} new Bullet Hole(s), "
          f"{len(result['pre_existing'])} already on the Board")
    print(f"   {written['derived']}")
    print(f"   raw exports kept: {os.path.basename(written['before_raw'])}, "
          f"{os.path.basename(written['after_raw'])}; sources in "
          f"{os.path.basename(written['source'])}")
