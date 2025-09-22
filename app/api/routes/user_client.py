from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.deps import require_admin
from app.core.config import get_supabase
from app.models.schemas import ClientOut, UserPolishedOut, DepartmentBrief, UserProfileOut

# Reuse selected client handlers
from app.api.routes.clients import (
    list_clients as _list_clients,
    get_client_by_id as _get_client_by_id,
    delete_client as _delete_client,
)


router = APIRouter(prefix="/api/users", tags=["users"], dependencies=[Depends(require_admin)])


@router.get("/", response_model=list[UserPolishedOut], summary="List users")
def list_users(limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0)):
    rows = _list_clients(limit=limit, offset=offset) or []
    out: list[dict] = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        out.append({
            "id": r.get("id"),
            "email": r.get("email"),
            "name": r.get("name"),
            "role": "user",
            "staff_id": None,
            "is_active": None,
            "created_at": r.get("created_at"),
            "updated_at": r.get("updated_at"),
            "profile": {
                "avatar": r.get("profile_image_link"),
                "department": None,
            },
        })
    return out


# Define staff routes BEFORE parameterized user routes to avoid collisions
@router.get("/staff", response_model=list[UserPolishedOut], summary="List staff")
def list_staff(limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0)):
    sb = get_supabase()
    res = (sb.table("internal_staff").select("*").order("id").range(offset, offset + limit - 1).execute())
    if getattr(res, "error", None):
        raise HTTPException(status_code=502, detail=str(res.error))
    rows = res.data or []

    # Load department names
    dept_ids = sorted({r.get("department_id") for r in rows if isinstance(r, dict) and r.get("department_id") is not None})
    dept_map: dict[int, dict] = {}
    if dept_ids:
        dres = sb.table("departments").select("id,name").in_("id", dept_ids).execute()
        if getattr(dres, "error", None):
            raise HTTPException(status_code=502, detail=str(dres.error))
        for d in dres.data or []:
            if isinstance(d, dict) and d.get("id") is not None:
                dept_map[d.get("id")] = d

    out: list[dict] = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        did = r.get("department_id")
        dept = dept_map.get(did)
        out.append({
            "id": r.get("id"),
            "email": r.get("email"),
            "name": r.get("name"),
            "role": "staff",
            "staff_id": r.get("id"),
            "is_active": (r.get("status") == "active"),
            "created_at": r.get("created_at"),
            "updated_at": r.get("updated_at"),
            "profile": {
                "avatar": None,
                "department": ({"id": dept.get("id"), "name": dept.get("name")} if isinstance(dept, dict) else None),
            },
        })
    return out


@router.get("/staff/{staff_id}", response_model=UserPolishedOut, summary="Get staff by id")
def get_staff(staff_id: int):
    sb = get_supabase()
    res = sb.table("internal_staff").select("*").eq("id", staff_id).single().execute()
    if getattr(res, "error", None) or not getattr(res, "data", None):
        raise HTTPException(status_code=404, detail="Staff not found")
    r = res.data
    dept = None
    if isinstance(r, dict) and r.get("department_id") is not None:
        d = sb.table("departments").select("id,name").eq("id", r.get("department_id")).single().execute()
        if not getattr(d, "error", None) and getattr(d, "data", None):
            dept = d.data
    return {
        "id": r.get("id"),
        "email": r.get("email"),
        "name": r.get("name"),
        "role": "staff",
        "staff_id": r.get("id"),
        "is_active": (r.get("status") == "active"),
        "created_at": r.get("created_at"),
        "updated_at": r.get("updated_at"),
        "profile": {
            "avatar": None,
            "department": ({"id": dept.get("id"), "name": dept.get("name")} if isinstance(dept, dict) else None),
        },
    }


@router.put("/staff/{staff_id}/deactivate", summary="Deactivate staff by id")
def deactivate_staff(staff_id: int):
    sb = get_supabase()
    upd = sb.table("internal_staff").update({"status": "inactive"}).eq("id", staff_id).execute()
    if getattr(upd, "error", None):
        raise HTTPException(status_code=502, detail=str(upd.error))
    res = sb.table("internal_staff").select("*").eq("id", staff_id).single().execute()
    if getattr(res, "error", None) or not getattr(res, "data", None):
        raise HTTPException(status_code=404, detail="Staff not found after deactivate")
    return res.data


@router.put("/staff/{staff_id}/activate", summary="Activate staff by id")
def activate_staff(staff_id: int):
    sb = get_supabase()
    upd = sb.table("internal_staff").update({"status": "active"}).eq("id", staff_id).execute()
    if getattr(upd, "error", None):
        raise HTTPException(status_code=502, detail=str(upd.error))
    res = sb.table("internal_staff").select("*").eq("id", staff_id).single().execute()
    if getattr(res, "error", None) or not getattr(res, "data", None):
        raise HTTPException(status_code=404, detail="Staff not found after activate")
    return res.data


@router.delete("/staff/{staff_id}", status_code=204, summary="Delete staff by id")
def delete_staff(staff_id: int):
    sb = get_supabase()
    # Ensure exists
    ex = sb.table("internal_staff").select("id").eq("id", staff_id).single().execute()
    if getattr(ex, "error", None) or not getattr(ex, "data", None):
        raise HTTPException(status_code=404, detail="Staff not found")
    d = sb.table("internal_staff").delete().eq("id", staff_id).execute()
    if getattr(d, "error", None):
        raise HTTPException(status_code=502, detail=str(d.error))
    return {}


@router.get("/{user_id}", response_model=UserPolishedOut, summary="Get user by id")
def get_user(user_id: int):
    r = _get_client_by_id(user_id)
    return {
        "id": r.get("id"),
        "email": r.get("email"),
        "name": r.get("name"),
        "role": "user",
        "staff_id": None,
        "is_active": None,
        "created_at": r.get("created_at"),
        "updated_at": r.get("updated_at"),
        "profile": {
            "avatar": r.get("profile_image_link"),
            "department": None,
        },
    }


@router.delete("/{user_id}", status_code=204, summary="Delete user by id")
def delete_user(user_id: int):
    return _delete_client(user_id)
