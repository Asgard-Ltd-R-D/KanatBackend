import asyncio

import pytest

from app.core.ranges import Unsatisfiable, file_response, parse_range


@pytest.mark.parametrize("header, expected", [
    (None, None),
    ("bytes=0-99", (0, 99)),
    ("bytes=100-", (100, 999)),
    ("bytes=-200", (800, 999)),
    ("bytes=900-5000", (900, 999)),      # an end past the file stops at its end
    ("bytes=0-9, 20-29", (0, 9)),        # only the first range is served
    ("items=0-9", None),                 # not bytes: the whole file
    ("bytes=x-y", None),
    # malformed: ignored, so the whole file
    ("bytes=-1-5", None),                # a negative start
    ("bytes=5--3", None),
    ("bytes=+1-5", None),                # int() would read these
    ("bytes=1-+5", None),
    ("bytes=-+5", None),
    ("bytes=1_0-20", None),
    ("bytes=\u0663-5", None),            # an Arabic-Indic 3
    ("bytes=-", None),
])
def test_ranges_are_read_as_the_standard_says(header, expected):
    assert parse_range(header, 1000) == expected


@pytest.mark.parametrize("header", ["bytes=1000-", "bytes=500-100", "bytes=-0"])
def test_a_range_outside_the_file_is_refused(header):
    with pytest.raises(Unsatisfiable):
        parse_range(header, 1000)


def test_a_range_gets_its_bytes_and_a_206(tmp_path):
    path = tmp_path / "v.mp4"
    path.write_bytes(bytes(range(256)) * 4)

    res = file_response(path, "bytes=10-19", "video/mp4")

    assert res.status_code == 206
    assert res.headers["Content-Range"] == "bytes 10-19/1024"
    assert res.headers["Content-Length"] == "10"
    async def body():
        return b"".join([chunk async for chunk in res.body_iterator])

    assert asyncio.run(body()) == bytes(range(10, 20))


def test_no_range_sends_the_whole_file_and_offers_ranges(tmp_path):
    path = tmp_path / "v.mp4"
    path.write_bytes(b"x" * 10)

    res = file_response(path, None, "video/mp4")

    assert res.status_code == 200
    assert res.headers["Accept-Ranges"] == "bytes"
