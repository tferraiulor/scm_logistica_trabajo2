from __future__ import annotations

"""Routers del Módulo 4 (Supplier Risk Scoring)."""

from fastapi import APIRouter, HTTPException

from . import risk_scoring

router = APIRouter(prefix="/api/suppliers", tags=["suppliers"])


@router.get("/scores")
def scores():
    return risk_scoring.evaluate_all()


@router.get("/score/{supplier_id}")
def score(supplier_id: str):
    try:
        return risk_scoring.evaluate_supplier(supplier_id, persist=True)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.get("/alternatives/{supplier_id}")
def alternatives(supplier_id: str, n: int = 3):
    try:
        return risk_scoring.suggest_alternatives(supplier_id, n)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.get("/history/{supplier_id}")
def history(supplier_id: str):
    return risk_scoring.history(supplier_id)


@router.get("/list")
def supplier_list():
    return risk_scoring.evaluate_all()
