"""Pydantic-layer validation: project names rejected before they reach the filesystem."""

import pytest
from pydantic import ValidationError

from backend.models.schemas import ProjectCreate, AssemblyRequest
from backend.routers.ingest import IngestRequest


@pytest.mark.parametrize("bad", ["../../etc", "..", "a/b", "a\\b", ".hidden", ""])
def test_project_create_rejects_traversal(bad):
    with pytest.raises(ValidationError):
        ProjectCreate(name=bad)


@pytest.mark.parametrize("good", ["my-stream", "ZAO Stream 01", "clip.final"])
def test_project_create_accepts_good(good):
    assert ProjectCreate(name=good).name == good.strip()


def test_assembly_request_rejects_traversal():
    with pytest.raises(ValidationError):
        AssemblyRequest(project_name="../evil")


def test_ingest_request_rejects_traversal():
    with pytest.raises(ValidationError):
        IngestRequest(url="https://youtube.com/watch?v=x", project_name="../evil")


def test_ingest_request_requires_valid_url():
    with pytest.raises(ValidationError):
        IngestRequest(url="not-a-url", project_name="ok-name")


def test_ingest_request_accepts_valid():
    req = IngestRequest(url="https://youtube.com/watch?v=abc", project_name="ok-name")
    assert req.project_name == "ok-name"
