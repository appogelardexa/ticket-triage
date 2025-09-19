from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.deps import require_admin
from app.core.config import get_supabase
from app.models.schemas import ClientOut

# Reuse selected client handlers
from app.api.routes.clients import (
    list_clients as _list_clients,
    get_client_by_id as _get_client_by_id,
    delete_client as _delete_client,
)


router = APIRouter(prefix="/api/users", tags=["users"], dependencies=[Depends(require_admin)])


@router.get("/", summary="List users (clients)")
def list_users(limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0)):
    return _list_clients(limit=limit, offset=offset)


# Define staff routes BEFORE parameterized user routes to avoid collisions
@router.get("/staff", summary="List staff users")
def list_staff(limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0)):
    sb = get_supabase()
    res = (
        sb.table("internal_staff")
          .select("*")
          .order("id")
          .range(offset, offset + limit - 1)
          .execute()
    )
    if getattr(res, "error", None):
        raise HTTPException(status_code=502, detail=str(res.error))
    return res.data or []


@router.get("/staff/{staff_id}", summary="Get staff by id")
def get_staff(staff_id: int):
    sb = get_supabase()
    res = sb.table("internal_staff").select("*").eq("id", staff_id).single().execute()
    if getattr(res, "error", None) or not getattr(res, "data", None):
        raise HTTPException(status_code=404, detail="Staff not found")
    return res.data


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


@router.get("/{user_id}", response_model=ClientOut, summary="Get user (client) by id")
def get_user(user_id: int):
    return _get_client_by_id(user_id)


@router.delete("/{user_id}", status_code=204, summary="Delete user (client) by id")
def delete_user(user_id: int):
    return _delete_client(user_id)