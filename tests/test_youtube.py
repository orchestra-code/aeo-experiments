import pytest

from aeo_research.youtube import (
    description_features,
    extract_chapter_timestamps,
    parse_timestamp,
    parse_video_id,
    timestamp_matches_chapter,
)


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://www.youtube.com/watch?v=r76p4i55-Us", "r76p4i55-Us"),
        ("https://youtube.com/watch?v=r76p4i55-Us&t=138", "r76p4i55-Us"),
        ("https://youtu.be/r76p4i55-Us", "r76p4i55-Us"),
        ("https://youtu.be/r76p4i55-Us?t=90", "r76p4i55-Us"),
        ("https://m.youtube.com/watch?v=r76p4i55-Us", "r76p4i55-Us"),
        ("https://www.youtube.com/shorts/r76p4i55-Us", "r76p4i55-Us"),
        ("https://www.youtube.com/embed/r76p4i55-Us", "r76p4i55-Us"),
        ("https://www.youtube.com/live/r76p4i55-Us", "r76p4i55-Us"),
        ("https://www.youtube.com/@somechannel", None),
        ("https://www.youtube.com/watch?v=tooshort", None),
        ("https://example.com/watch?v=r76p4i55-Us", None),
        ("not a url", None),
        (None, None),
    ],
)
def test_parse_video_id(url, expected):
    assert parse_video_id(url) == expected


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://www.youtube.com/watch?v=x&t=138", 138),
        ("https://www.youtube.com/watch?v=x&t=138s", 138),
        ("https://www.youtube.com/watch?v=x&t=2m18s", 138),
        ("https://www.youtube.com/watch?v=x&t=1h2m3s", 3723),
        ("https://youtu.be/x?t=90", 90),
        ("https://www.youtube.com/watch?v=x#t=45", 45),
        ("https://www.youtube.com/watch?v=x", None),
        ("https://www.youtube.com/watch?v=x&t=", None),
        (None, None),
    ],
)
def test_parse_timestamp(url, expected):
    assert parse_timestamp(url) == expected


DESCRIPTION = """Great video about testing.

Chapters:
0:00 Intro
2:18 The main part
- 10:05 Details
1:02:33 Wrap up

More at https://example.com and https://example.org
"""


def test_extract_chapter_timestamps():
    assert extract_chapter_timestamps(DESCRIPTION) == [0, 138, 605, 3753]
    assert extract_chapter_timestamps(None) == []
    assert extract_chapter_timestamps("no timestamps here") == []


def test_timestamp_matches_chapter():
    chapters = [0, 138, 605]
    assert timestamp_matches_chapter(140, chapters, tol=5)
    assert not timestamp_matches_chapter(150, chapters, tol=5)


def test_description_features():
    f = description_features(DESCRIPTION)
    assert f["has_chapters"] is True  # >=3 markers incl. 0:00
    assert f["chapter_count"] == 4
    assert f["desc_link_count"] == 2
    assert f["desc_word_count"] > 10

    empty = description_features(None)
    assert empty["has_chapters"] is False
    assert empty["desc_word_count"] == 0


def test_two_markers_is_not_chapters():
    f = description_features("0:00 start\n5:00 end")
    assert f["chapter_count"] == 2
    assert f["has_chapters"] is False
