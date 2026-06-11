"""Path-safety tests for project name validation and containment."""

import pytest
from fastapi import HTTPException

from backend.services.project_utils import (
    validate_project_name, is_within, project_dir_for, PROJECTS_DIR,
)


GOOD_NAMES = ["my-stream", "ZAO Stream 01", "clip.final", "good_name", "a"]
BAD_NAMES = [
    "../../etc/passwd", "..", "a/../b", "/etc/passwd", "a/b", "a\\b",
    ".hidden", "", "x" * 101,
]


@pytest.mark.parametrize("name", GOOD_NAMES)
def test_validate_accepts_good(name):
    assert validate_project_name(name) == name


@pytest.mark.parametrize("name", BAD_NAMES)
def test_validate_rejects_bad(name):
    with pytest.raises(HTTPException) as exc:
        validate_project_name(name)
    assert exc.value.status_code == 422


def test_is_within_true_for_nested():
    assert is_within(PROJECTS_DIR / "proj" / "input", PROJECTS_DIR) is True


def test_is_within_false_for_sibling_prefix():
    # the classic str.startswith bypass: /projects-evil shares the prefix
    assert is_within(PROJECTS_DIR.parent / (PROJECTS_DIR.name + "-evil"), PROJECTS_DIR) is False


def test_is_within_false_for_parent():
    assert is_within(PROJECTS_DIR.parent, PROJECTS_DIR) is False


def test_project_dir_for_rejects_traversal():
    with pytest.raises(HTTPException):
        project_dir_for("../escape")


def test_project_dir_for_returns_path_for_valid_name():
    d = project_dir_for("valid-name")
    assert is_within(d, PROJECTS_DIR)
