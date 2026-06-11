"""Studio one-command app: slug + path-safety helpers."""

import pytest
from fastapi import HTTPException

from backend.routers.studio import _slug, _project_dir, PROJECTS_DIR
from backend.services.project_utils import is_within


def test_slug_from_title():
    assert _slug("WaveWarZ Talk!") == "wavewarz-talk"
    assert _slug("") == "recording"
    assert _slug("2026-06-10 Show") == "2026-06-10-show"


def test_project_dir_safe_name_contained():
    d = _project_dir("wavewarz-talk")
    assert is_within(d, PROJECTS_DIR)


@pytest.mark.parametrize("bad", ["../escape", "a/b", "a\\b"])
def test_project_dir_rejects_traversal(bad):
    with pytest.raises(HTTPException):
        _project_dir(bad)
