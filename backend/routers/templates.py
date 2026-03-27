"""CRUD endpoints for processing presets/templates."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

from ..services.templates import (
    save_template, load_template, list_templates, delete_template,
)

router = APIRouter(prefix="/api/templates", tags=["templates"])


class TemplateSaveRequest(BaseModel):
    name: str
    settings: dict


@router.get("")
async def get_templates():
    """List all saved presets."""
    return list_templates()


@router.post("")
async def create_template(req: TemplateSaveRequest):
    """Save or update a named preset."""
    if not req.name.strip():
        raise HTTPException(400, "Template name is required")
    saved = save_template(req.name.strip(), req.settings)
    return {"status": "saved", "name": req.name.strip(), "settings": saved}


@router.get("/{name}")
async def get_template(name: str):
    """Get a single preset by name."""
    tpl = load_template(name)
    if tpl is None:
        raise HTTPException(404, "Template not found")
    return tpl


@router.delete("/{name}")
async def remove_template(name: str):
    """Delete a preset."""
    if not delete_template(name):
        raise HTTPException(404, "Template not found")
    return {"status": "deleted", "name": name}
