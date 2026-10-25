"""Checks for Registration: placing each Look's frame onto the Board (#138).
No model, no video: `board`'s fits are scripted per frame, and frames are
registered one by one, as the loop does past the baseline."""
import types

import numpy as np

from detection import new_bullet_holes as nbh

N = nbh.REANCHOR_AFTER_LOST
GROSS = nbh.GROSS_DISAGREEMENT_PX


def _registration(monkeypatch, registers, below=lambda i: 0.0,
                  reanchors=lambda i: False, correlation=lambda i: 0.9,
                  disagreement=lambda i: 0.0):
    """Registration onto a Board space whose view is frame 0's; `registers(index)`
    says which frames register when tracked, `reanchors(index)` which when
    re-anchored (#80), and `below(index)` how far that frame's view runs past
    the canvas bottom, in Board px against a 100 px Target span — None for an
    unmeasurable view, 0 the baseline's. A fit converges at
    `correlation(index)`, and an independent silhouette fit disagrees with it
    by `disagreement(index)` Board px (#110).

    `reg.calls` records `(how, index, last)` for each fit, where `how` is
    "track" or "reanchor" and `last` is the view it was handed;
    `reg.previous` records `(index, previous)` for each tracked fit, `previous`
    the index of the frame it was handed as the one `last` was registered on
    (#171), frame 0 the baseline frame;
    `reg.silhouetted` the indices whose fit was checked against the silhouette;
    `reg.space` is Board space's own view."""
    calls, checked, previous = [], [], []
    def fit(how, succeeds):
        def call(frame, *args, **kwargs):
            index, last = int(frame[0, 0, 0]), args[-1]
            calls.append((how, index, last))
            if how == "track":
                handed = kwargs.get("previous")
                previous.append((index, None if handed is None else int(handed[0, 0, 0])))
            if not succeeds(index):
                return None, None
            # A re-anchor only ever returns a fit at or above its floor.
            floor = nbh.board.REANCHOR_MIN_CORRELATION if how == "reanchor" else 0.0
            return types.SimpleNamespace(index=index), max(floor, correlation(index))
        return call
    def silhouette(frame, template_mask, view):
        checked.append(view.index)
        return disagreement(view.index)
    monkeypatch.setattr(nbh.board, "silhouette_disagreement", silhouette)
    edges = dict.fromkeys(("left", "right", "above"), 0.0)
    def uncovered(view, size):
        reach = below(view.index)
        return None if reach is None else (0.0, {**edges, "below": reach})
    monkeypatch.setattr(nbh.board, "uncovered_view", uncovered)
    monkeypatch.setattr(nbh.board, "target_span", lambda view: 100.0)
    monkeypatch.setattr(nbh.board, "track_view", fit("track", registers))
    monkeypatch.setattr(nbh.board, "reanchor_view", fit("reanchor", reanchors))
    space = types.SimpleNamespace(index=0)
    reg = nbh.Registration(space, _frame(0), np.zeros((8, 8), np.uint8),
                           lambda index: f"{index / 25:.2f}s")
    reg.calls, reg.silhouetted, reg.space, reg.previous = calls, checked, space, previous
    return reg


def _frame(index):
    """A frame whose pixels are its index, so a fake fit can tell which it was handed."""
    return np.full((8, 8, 3), index, np.int64)


def _register(reg, frames):
    """Register frames 1..`frames` in order; the view each came back with."""
    return [reg.register(_frame(i), i) for i in range(1, frames + 1)]


# --- re-anchoring after the Board is lost (#80) ------------------------------


def _reanchored(reg):
    return [index for how, index, _ in reg.calls if how == "reanchor"]


def test_one_lost_frame_short_of_the_trigger_does_not_re_anchor(monkeypatch):
    reg = _registration(monkeypatch, lambda i: i > N - 1)
    _register(reg, N + 5)
    assert _reanchored(reg) == []


def test_the_frame_after_a_full_trigger_of_lost_frames_is_re_anchored(monkeypatch):
    """Frames 1..N are lost; frame N+1 is re-anchored instead of tracked."""
    reg = _registration(monkeypatch, lambda i: False)
    _register(reg, N + 5)
    assert _reanchored(reg) == [N + 1]


def test_after_a_re_anchor_later_frames_track_from_the_re_anchored_view(monkeypatch):
    reg = _registration(monkeypatch, lambda i: i > N + 1, reanchors=lambda i: True)
    views = _register(reg, N + 4)
    recovered = views[N]
    assert recovered is not None and recovered.index == N + 1
    assert [last for how, index, last in reg.calls if index == N + 2] == [recovered]
    assert None not in views[N:] and reg.last is views[-1]


def test_a_re_anchor_starts_from_the_last_registered_view(monkeypatch):
    """Board space and the anchor come from it; nothing is rebuilt."""
    reg = _registration(monkeypatch, lambda i: False)
    _register(reg, N + 1)
    assert [last for how, _, last in reg.calls if how == "reanchor"] == [reg.space]


def test_a_failed_re_anchor_stays_lost_and_waits_a_full_interval(monkeypatch):
    reg = _registration(monkeypatch, lambda i: False)
    views = _register(reg, 3 * N + 5)
    assert _reanchored(reg) == [N + 1, 2 * N + 1, 3 * N + 1]
    assert views == [None] * (3 * N + 5)


def test_a_registered_frame_resets_the_count(monkeypatch):
    """Only consecutive lost frames trigger: N lost in two runs is not N in a row."""
    reg = _registration(monkeypatch, lambda i: i == N // 2)
    _register(reg, N + 5)
    assert _reanchored(reg) == []


def test_each_re_anchor_is_logged_and_counted_at_the_end(monkeypatch, capsys, caplog):
    caplog.set_level("INFO")
    reg = _registration(monkeypatch, lambda i: False, reanchors=lambda i: i == 2 * N + 1)
    _register(reg, 2 * N + 2)
    reg.report()
    out = capsys.readouterr().out
    records = [r for r in caplog.records if r.getMessage().startswith("Re-anchor at")]
    assert [r.levelname for r in records] == ["WARNING", "INFO"]   # failed, then registered
    lines = [r.getMessage() for r in records]
    assert len(lines) == 2
    assert f"frame {N + 1}" in lines[0] and f"after {N} lost" in lines[0]
    assert "failed" in lines[0]
    assert f"frame {2 * N + 1}" in lines[1] and f"after {2 * N} lost" in lines[1]
    assert "registered" in lines[1]
    assert "[REGISTRATION] 2 re-anchor attempt(s): 1 registered, 1 failed" in out


def test_a_run_that_never_lost_the_board_reports_no_re_anchor(monkeypatch, capsys):
    reg = _registration(monkeypatch, lambda i: True)
    _register(reg, 3)
    reg.report()
    assert "[REGISTRATION] 0 re-anchor attempt(s)" in capsys.readouterr().out
    assert _reanchored(reg) == []


def test_a_fit_that_fails_to_converge_is_lost_and_feeds_the_re_anchor(monkeypatch):
    """ECC raising is no evidence either way, as a Board not found is."""
    reg = _registration(monkeypatch, lambda i: True)
    def diverges(frame, last, previous=None):
        raise nbh.cv2.error("ECC did not converge")
    monkeypatch.setattr(nbh.board, "track_view", diverges)
    assert _register(reg, N + 1) == [None] * (N + 1)
    assert _reanchored(reg) == [N + 1]


# --- the frame a tracked fit starts from (#171) ------------------------------


def test_each_tracked_fit_is_handed_the_frame_its_starting_fit_was_registered_on(monkeypatch):
    """The Board's shift is read from that frame to this one, so it must be the
    frame `last` was registered on: the baseline frame first, then the last
    registered frame. A Lost Look has no fit to start from, so it is skipped."""
    reg = _registration(monkeypatch, lambda i: i != 2)
    _register(reg, 4)
    assert reg.previous == [(1, 0), (2, 1), (3, 1), (4, 3)]


def test_after_a_re_anchor_the_next_fit_starts_from_the_re_anchored_frame(monkeypatch):
    reg = _registration(monkeypatch, lambda i: i > N + 1, reanchors=lambda i: True)
    _register(reg, N + 2)
    assert reg.previous[-1] == (N + 2, N + 1)


# --- a converged fit that is grossly wrong (#110) ----------------------------


def test_a_fit_converging_above_the_floor_is_not_checked(monkeypatch):
    """The check costs ~0.5 s a frame; a fit the re-anchor floor would accept
    is not paid for (#110)."""
    reg = _registration(monkeypatch, lambda i: True,
                        correlation=lambda i: nbh.board.REANCHOR_MIN_CORRELATION,
                        disagreement=lambda i: 10 * GROSS)
    views = _register(reg, 4)
    assert reg.silhouetted == [] and None not in views


def test_a_grossly_wrong_fit_is_lost_and_feeds_the_re_anchor(monkeypatch, capsys):
    """Frames 1..N converge on the wrong scene: each is lost, the count runs
    on, and frame N+1 is re-anchored from the last right view (#110, #80)."""
    reg = _registration(monkeypatch, lambda i: True,
                        correlation=lambda i: 0.2, disagreement=lambda i: GROSS)
    views = _register(reg, N + 3)
    assert views == [None] * (N + 3)   # none recovers: the re-anchor fails too
    assert _reanchored(reg) == [N + 1]
    assert all(last is reg.space for how, i, last in reg.calls if i <= N + 1)
    reg.report()
    assert "[REGISTRATION] 1 re-anchor attempt(s)" in capsys.readouterr().out


def test_a_moderate_disagreement_keeps_the_frame_and_warns_once(monkeypatch, capsys):
    """Below the gross bound nothing is rejected; the run says how many of the
    frames it checked disagreed, and that only those were checked (#110)."""
    reg = _registration(monkeypatch, lambda i: True,
                        correlation=lambda i: 0.5 if i in (2, 3, 4) else 0.95,
                        disagreement=lambda i: GROSS - 1 if i in (2, 3) else 0.0)
    assert None not in _register(reg, 5)
    reg.report()
    out = capsys.readouterr().out
    lines = [l for l in out.splitlines() if "silhouette" in l and "[WARN]" in l]
    assert len(lines) == 1
    assert "2 of 3" in lines[0]


def test_a_check_with_no_verdict_keeps_the_frame(monkeypatch, capsys):
    """A silhouette fit that fails says nothing about the tracked one."""
    reg = _registration(monkeypatch, lambda i: True,
                        correlation=lambda i: 0.2, disagreement=lambda i: None)
    assert None not in _register(reg, 3)
    reg.report()
    assert "0 of 3 converged fit(s) checked" in capsys.readouterr().out


# --- how far the view runs off the canvas (#41) ------------------------------


def test_a_view_moving_further_off_the_canvas_is_reported_once(monkeypatch, capsys):
    """The baseline's view is only the first: a camera that later swings past
    the canvas uncovers Board no run searches (#41)."""
    reg = _registration(monkeypatch, lambda i: True,
                        below=lambda i: [0.0, 0.0, 40.0, 20.0, 0.0][i])
    _register(reg, 4)
    reg.report()
    out = capsys.readouterr().out
    assert out.count("further off the canvas than the baseline did") == 1
    assert "0.40 below" in out


def test_a_view_that_stays_within_the_baseline_says_nothing(monkeypatch, capsys):
    reg = _registration(monkeypatch, lambda i: True)
    _register(reg, 3)
    reg.report()
    assert "[WARN]" not in capsys.readouterr().out


def test_any_growth_past_rounding_is_reported(monkeypatch, capsys):
    """A pixel more than the baseline showed is Board no run searched, however
    it prints; only the sub-pixel rounding floor is let through."""
    reg = _registration(monkeypatch, lambda i: True,
                        below=lambda i: [30.0, 31.0, 30.0][i])
    _register(reg, 2)
    reg.report()
    assert "further off the canvas than the baseline did" in capsys.readouterr().out


def test_a_later_view_that_cannot_be_measured_is_reported(monkeypatch, capsys):
    """The baseline measured fine, so its line said nothing is unknown; a later
    frame past the Board plane's horizon still has to say so."""
    reg = _registration(monkeypatch, lambda i: True,
                        below=lambda i: [0.0, None, 0.0, 0.0][i])
    _register(reg, 3)
    reg.report()
    assert "[WARN] 1 registered frame(s)' view did not map" in capsys.readouterr().out
