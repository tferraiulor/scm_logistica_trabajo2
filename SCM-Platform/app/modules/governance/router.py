from __future__ import annotations

"""Routers del Módulo 5 (Gobernanza / HITL)."""

from fastapi import APIRouter, HTTPException

from ...core import security
from . import hitl

router = APIRouter(prefix="/api/governance", tags=["governance"])


@router.get("/matrix")
def matrix():
    return hitl.decision_matrix()


@router.get("/pending")
def pending():
    return hitl.pending()


@router.get("/trace")
def trace(module: str = None):
    return hitl.decision_trace(module)


@router.post("/approve/{rec_id}")
def approve(rec_id: int, body: dict = None):
    body = body or {}
    try:
        return hitl.approve(rec_id, body.get("actor"))
    except PermissionError as exc:
        raise HTTPException(403, str(exc)) from exc


@router.post("/reject/{rec_id}")
def reject(rec_id: int, body: dict = None):
    body = body or {}
    return hitl.reject(rec_id, body.get("actor"), body.get("note", ""))


@router.get("/roles")
def roles():
    return {"roles": sorted(security.ROLES), "current_role": security.current_role(),
            "can_authorize": security.can_authorize()}
