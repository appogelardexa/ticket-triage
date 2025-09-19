from typing import List
from fastapi import APIRouter, HTTPException, Query, Depends
from app.core.config import get_supabase
from app.models.schemas import (
    CategoryOut,
    CategoryCreate,
    CategoryPatch,
    CategoryDefaultAssigneeOut,
    CategoryDefaultAssigneeCreate,
    CategoryDefaultAssigneePatch,
    CategoryWithDefaultAssigneesOut,
)
from app.api.deps import require_admin

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

@router.get(
    "/with-assignees",
    response_model=List[CategoryWithDefaultAssigneesOut],
    summary="List categories with their default assignees",
)
def list_categories_with_assignees(
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    department_id: int | None = Query(None, description="Filter by department_id"),
    assignee_active: bool | None = Query(None, description="Filter default assignees by active flag"),
):
    sb = get_supabase()

    # Fetch categories (paged)
    q = sb.table("categories").select("*")
    if department_id is not None:
        q = q.eq("department_id", department_id)
    cat_res = q.order("id").range(offset, offset + limit - 1).execute()
    if getattr(cat_res, "error", None):
        raise HTTPException(status_code=502, detail=str(cat_res.error))
    categories = cat_res.data or []
    if not categories:
        return []

    cat_ids = [c["id"] for c in categories if isinstance(c, dict) and "id" in c]
    if not cat_ids:
        return []

    # Fetch default assignees for the page of categories
    aq = sb.table("category_default_assignees").select("*").in_("category_id", cat_ids)
    if assignee_active is not None:
        aq = aq.eq("active", assignee_active)
    a_res = aq.order("priority").order("weight", desc=True).order("id").execute()
    if getattr(a_res, "error", None):
        raise HTTPException(status_code=502, detail=str(a_res.error))
    assignees = a_res.data or []

    # Group by category_id
    by_cat: dict[int, list] = {}
    for row in assignees:
        cid = row.get("category_id")
        if cid is not None:
            by_cat.setdefault(cid, []).append(row)

    # Compose response
    out: list[dict] = []
    for c in categories:
        cid = c.get("id")
        out.append({
            **c,
            "default_assignees": by_cat.get(cid, []),
        })

    return out


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
def create_category(payload: CategoryCreate, user=Depends(require_admin)):
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
def update_category(category_id: int, patch: CategoryPatch, user=Depends(require_admin)):
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
def delete_category(category_id: int, user=Depends(require_admin)):
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

@router.get(
    "/{category_id}/default-assignees",
    response_model=List[CategoryDefaultAssigneeOut],
    summary="List default assignees for a category",
)
def list_category_default_assignees(
    category_id: int,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    active: bool | None = Query(None, description="Filter by active flag"),
):
    sb = get_supabase()
    q = sb.table("category_default_assignees").select("*").eq("category_id", category_id)
    if active is not None:
        q = q.eq("active", active)
    res = (
        q.order("priority").order("weight", desc=True).order("id").range(offset, offset + limit - 1).execute()
    )
    if getattr(res, "error", None):
        raise HTTPException(status_code=502, detail=str(res.error))
    return res.data or []


@router.post(
    "/{category_id}/default-assignees",
    response_model=CategoryDefaultAssigneeOut,
    status_code=201,
    summary="Create a default assignee for a category",
)
def create_category_default_assignee(category_id: int, payload: CategoryDefaultAssigneeCreate, user=Depends(require_admin)):
    sb = get_supabase()
    data = payload.model_dump(exclude_none=True)
    data["category_id"] = category_id

    res = sb.table("category_default_assignees").insert(data).execute()
    if getattr(res, "error", None):
        # If unique violation on (category_id, staff_id), try to fetch existing
        # Otherwise bubble as 502 to keep consistent handling
        try:
            # Best-effort match when conflict occurs
            sel = (
                sb.table("category_default_assignees")
                .select("*")
                .eq("category_id", category_id)
                .eq("staff_id", data.get("staff_id"))
                .execute()
            )
            if getattr(sel, "error", None):
                raise HTTPException(status_code=502, detail=str(res.error))
            rows = sel.data or []
            if rows:
                return rows[0]
        except Exception:
            pass
        raise HTTPException(status_code=502, detail=str(res.error))

    if isinstance(res.data, list) and res.data:
        return res.data[0]
    if isinstance(res.data, dict):
        return res.data

    # Fallback fetch
    sel2 = (
        sb.table("category_default_assignees")
        .select("*")
        .eq("category_id", category_id)
        .eq("staff_id", data.get("staff_id"))
        .execute()
    )
    if getattr(sel2, "error", None):
        raise HTTPException(status_code=502, detail=str(sel2.error))
    rows = sel2.data or []
    if rows:
        return rows[0]
    raise HTTPException(status_code=502, detail="Failed to retrieve created mapping")


@router.patch(
    "/{category_id}/default-assignees/{staff_id}",
    response_model=CategoryDefaultAssigneeOut,
    summary="Update a default assignee mapping",
)
def update_category_default_assignee(category_id: int, staff_id: int, patch: CategoryDefaultAssigneePatch, user=Depends(require_admin)):
    sb = get_supabase()
    data = patch.model_dump(exclude_none=True)
    if not data:
        raise HTTPException(status_code=400, detail="No fields to update")

    res = (
        sb.table("category_default_assignees")
        .update(data)
        .eq("category_id", category_id)
        .eq("staff_id", staff_id)
        .execute()
    )
    if getattr(res, "error", None):
        raise HTTPException(status_code=502, detail=str(res.error))

    sel = (
        sb.table("category_default_assignees")
        .select("*")
        .eq("category_id", category_id)
        .eq("staff_id", staff_id)
        .execute()
    )
    if getattr(sel, "error", None):
        raise HTTPException(status_code=502, detail=str(sel.error))
    rows = sel.data or []
    if not rows:
        raise HTTPException(status_code=404, detail="Mapping not found")
    return rows[0]


@router.delete(
    "/{category_id}/default-assignees/{staff_id}",
    status_code=204,
    summary="Delete a default assignee mapping",
)
def delete_category_default_assignee(category_id: int, staff_id: int, user=Depends(require_admin)):
    sb = get_supabase()

    exists = (
        sb.table("category_default_assignees")
        .select("id")
        .eq("category_id", category_id)
        .eq("staff_id", staff_id)
        .execute()
    )
    if getattr(exists, "error", None) or not getattr(exists, "data", None):
        raise HTTPException(status_code=404, detail="Mapping not found")

    res = (
        sb.table("category_default_assignees")
        .delete()
        .eq("category_id", category_id)
        .eq("staff_id", staff_id)
        .execute()
    )
    if getattr(res, "error", None):
        raise HTTPException(status_code=502, detail=str(res.error))
    return {}
