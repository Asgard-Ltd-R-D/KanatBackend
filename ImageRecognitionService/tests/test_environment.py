"""The OpenCV pin is a correctness guard, not a reproducibility preference.

Every release from 4.11 onward — 5.x included — ships KleidiCV as a custom HAL,
and its NEON `resize` kernel writes out of bounds. It is reached through
ultralytics' letterbox on every detection, and it corrupted the heap on
`CamA_20260914_141846.mkv` at a *different frame each run* — 61 and 222 on
5.0.0, 28 and 111 on 4.14.0. It fails as exit 139 with no traceback and no
partial-result warning, so a crashed run and a clean one look identical.

4.10.0.84 is the last release without it (`Custom HAL: carotene`). A range pin
does not help: `>=4.10,<5` resolves straight back to 4.14.

So this fails closed. A measurement taken on another build is untrusted, not
merely irreproducible, and every threshold in this project is a measurement.
"""
import importlib.metadata

import cv2

# cv2.__version__ drops the packaging component: opencv-python 4.10.0.84
# reports "4.10.0". Both are checked — the module version is what the code runs
# against, the package version is what pip resolved.
REQUIRED_CV2 = "4.10.0"
REQUIRED_PACKAGE = "opencv-python==4.10.0.84"


def test_opencv_module_is_the_pinned_version():
    assert cv2.__version__ == REQUIRED_CV2, (
        f"cv2 reports {cv2.__version__}, not {REQUIRED_CV2}. Builds from 4.11 on "
        "ship KleidiCV, whose resize kernel corrupts the heap mid-run. Reinstall "
        f"with `pip install {REQUIRED_PACKAGE}` before trusting any measurement."
    )


def test_opencv_package_is_the_pinned_version():
    name, _, want = REQUIRED_PACKAGE.partition("==")
    assert importlib.metadata.version(name) == want, (
        f"{name} resolved to {importlib.metadata.version(name)}, not {want}. "
        "requirements.txt pins it exactly on purpose; see the docstring above."
    )
