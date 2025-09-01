from typing import List
from fastapi import APIRouter, HTTPException, Query
from app.core.config import get_supabase
from app.models.schemas import (
    CategoryOut,
    CategoryCreate,
    CategoryPatch,
)

router = APIRouter(tags=["categories"])


@router.get("/", summary="List categories")
def list_categories(
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    department_id: int | None = Query(None, description="Filter by department_id"),
):
    sb = get_supabase()
    q = sb.table("categories").select("*")
    if department_id is not None:
        q = q.eq("department_id", department_id)
    res = q.order("id").range(offset, offset + limit - 1).execute()
    if getattr(res, "error", None):
        raise HTTPException(status_code=502, detail=str(res.error))
    return res.data or []


@router.get("/{category_id}", response_model=CategoryOut, summary="Get category by id")
def get_category_by_id(category_id: int):
    sb = get_supabase()
    res = (
        sb.table("categories")
          .select("*")
          .eq("id", category_id)
          .execute()
    )
    if getattr(res, "error", None):
        raise HTTPException(status_code=502, detail=str(res.error))
    rows = res.data or []
    if not rows:
        raise HTTPException(status_code=404, detail="Category not found")
    return rows[0]


@router.post("/", response_model=CategoryOut, status_code=201, summary="Create category")
def create_category(payload: CategoryCreate):
    sb = get_supabase()
    res = (
        sb.table("categories")
          .insert(payload.model_dump(exclude_none=True))
          .execute()
    )
    if getattr(res, "error", None):
        raise HTTPException(status_code=502, detail=str(res.error))
    if isinstance(res.data, list) and res.data:
        return res.data[0]
    if isinstance(res.data, dict):
        return res.data
    # Fallback: unique key (department_id, name)
    res2 = (
        sb.table("categories")
          .select("*")
          .eq("department_id", payload.department_id)
          .eq("name", payload.name)
          .execute()
    )
    if getattr(res2, "error", None):
        raise HTTPException(status_code=502, detail=str(res2.error))
    rows = res2.data or []
    if rows:
        return rows[0]
    raise HTTPException(status_code=502, detail="Failed to retrieve created category")


@router.patch("/{category_id}", response_model=CategoryOut, summary="Update category by id")
def update_category(category_id: int, patch: CategoryPatch):
    sb = get_supabase()
    data = patch.model_dump(exclude_none=True)
    if not data:
        raise HTTPException(status_code=400, detail="No fields to update")

    res = (
        sb.table("categories")
          .update(data)
          .eq("id", category_id)
          .execute()
    )
    if getattr(res, "error", None):
        raise HTTPException(status_code=502, detail=str(res.error))

    res2 = (
        sb.table("categories")
          .select("*")
          .eq("id", category_id)
          .execute()
    )
    if getattr(res2, "error", None):
        raise HTTPException(status_code=502, detail=str(res2.error))
    rows = res2.data or []
    if not rows:
        raise HTTPException(status_code=404, detail="Category not found")
    return rows[0]


@router.delete("/{category_id}", status_code=204, summary="Delete category by id")
def delete_category(category_id: int):
    sb = get_supabase()

    exists = (
        sb.table("categories")
          .select("id")
          .eq("id", category_id)
          .execute()
    )
    if getattr(exists, "error", None) or not getattr(exists, "data", None):
        raise HTTPException(status_code=404, detail="Category not found")

    res = sb.table("categories").delete().eq("id", category_id).execute()
    if getattr(res, "error", None):
        raise HTTPException(status_code=502, detail=str(res.error))
    return {}
