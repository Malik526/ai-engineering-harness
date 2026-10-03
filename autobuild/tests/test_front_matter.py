"""Front matter parsing edge cases."""

import pytest

from autobuild.front_matter import FrontMatterError, split_front_matter


def test_dates_stay_strings():
    meta, body = split_front_matter("---\napproved_at: 2026-10-03\n---\n# Body\n")
    assert meta == {"approved_at": "2026-10-03"}
    assert body == "# Body\n"


@pytest.mark.parametrize("text", ["# no front matter\n", "---\nid: x\n", "---\n- a list\n---\n"])
def test_invalid_front_matter(text):
    with pytest.raises(FrontMatterError):
        split_front_matter(text)
