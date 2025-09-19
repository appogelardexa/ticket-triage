from typing import List, Optional
from fastapi import APIRouter, HTTPException, Query, Depends
from app.core.config import get_supabase
from app.models.schemas import (
    DepartmentOut,
    DepartmentCreate,
    DepartmentPatch,
)

from app.api.deps import require_admin

router = APIRouter(tags=["departments"])


@router.get("/", summary="List departments")
def list_departments(limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0)):
    sb = get_supabase()
    res = (
        sb.table("departments")
          .select("*")
          .order("id")
          .range(offset, offset + limit - 1)
          .execute()
    )
    if getattr(res, "error", None):
        raise HTTPException(status_code=502, detail=str(res.error))
    return res.data or []


@router.get("/{department_id}", response_model=DepartmentOut, summary="Get department by id")
def get_department_by_id(department_id: int):
    sb = get_supabase()
    res = (
        sb.table("departments")
          .select("*")
          .eq("id", department_id)
          .execute()
    )
    if getattr(res, "error", None):
        raise HTTPException(status_code=502, detail=str(res.error))
    rows = res.data or []
    if not rows:
        raise HTTPException(status_code=404, detail="Department not found")
    return rows[0]


@router.post("/", response_model=DepartmentOut, status_code=201, summary="Create department")
def create_department(payload: DepartmentCreate, user=Depends(require_admin)):
    sb = get_supabase()
    res = (
        sb.table("departments")
          .insert(payload.model_dump(exclude_none=True))
          .execute()
    )
    if getattr(res, "error", None):
        raise HTTPException(status_code=502, detail=str(res.error))
    if isinstance(res.data, list) and res.data:
        return res.data[0]
    if isinstance(res.data, dict):
        return res.data
    # Fallback: fetch by unique name if provided
    res2 = (
        sb.table("departments")
          .select("*")
          .eq("name", payload.name)
          .execute()
    )
    if getattr(res2, "error", None):
        raise HTTPException(status_code=502, detail=str(res2.error))
    rows = res2.data or []
    if rows:
        return rows[0]
    raise HTTPException(status_code=502, detail="Failed to retrieve created department")


@router.patch("/{department_id}", response_model=DepartmentOut, summary="Update department by id")
def update_department(department_id: int, patch: DepartmentPatch, user=Depends(require_admin)):
    sb = get_supabase()
    data = patch.model_dump(exclude_none=True)
    if not data:
        raise HTTPException(status_code=400, detail="No fields to update")

    res = (
        sb.table("departments")
          .update(data)
          .eq("id", department_id)
          .execute()
    )
    if getattr(res, "error", None):
        raise HTTPException(status_code=502, detail=str(res.error))

    res2 = (
        sb.table("departments")
          .select("*")
          .eq("id", department_id)
          .execute()
    )
    if getattr(res2, "error", None):
        raise HTTPException(status_code=502, detail=str(res2.error))
    rows = res2.data or []
    if not rows:
        raise HTTPException(status_code=404, detail="Department not found")
    return rows[0]


@router.delete("/{department_id}", status_code=204, summary="Delete department by id")
def delete_department(department_id: int, user=Depends(require_admin)):
    sb = get_supabase()

    exists = (
        sb.table("departments")
          .select("id")
          .eq("id", department_id)
          .execute()
    )
    if getattr(exists, "error", None) or not getattr(exists, "data", None):
        raise HTTPException(status_code=404, detail="Department not found")

    res = sb.table("departments").delete().eq("id", department_id).execute()
    if getattr(res, "error", None):
        raise HTTPException(status_code=502, detail=str(res.error))
    return {}
