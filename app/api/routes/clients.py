from typing import List, Optional
from fastapi import APIRouter, HTTPException, Query
from app.core.config import get_supabase
from app.models.schemas import ClientOut, ClientCreate, ClientPatch

router = APIRouter(tags=["clients"])

@router.get("/", summary="List clients")
def list_clients(limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0)):
    sb = get_supabase()
    res = (sb.table("clients").select("*").order("id").range(offset, offset+limit-1).execute())
    return res.data or []


@router.get("/search", summary="Search clients by email or name")
def search_clients(
    email: Optional[str] = Query(None, description="Exact email match"),
    name: Optional[str] = Query(None, min_length=1, description="Client name to search"),
    exact: bool = Query(False, description="True = exact name match; False = contains"),
    limit: int = Query(10, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    if not email and not name:
        raise HTTPException(status_code=400, detail="Provide email or name")

    sb = get_supabase()
    q = sb.table("clients").select("*")

    if email:
        q = q.eq("email", email)
    elif name:
        if exact:
            q = q.eq("name", name)
        else:
            q = q.ilike("name", f"%{name}%")

    res = q.order("id").range(offset, offset + limit - 1).execute()
    if getattr(res, "error", None):
        raise HTTPException(status_code=502, detail=str(res.error))
    return res.data or []


@router.get("/{client_id}", response_model=ClientOut, summary="Get client by id")
def get_client_by_id(client_id: int):
    sb = get_supabase()
    res = (
        sb.table("clients")
          .select("*")
          .eq("id", client_id)
          .execute()
    )
    if getattr(res, "error", None):
        raise HTTPException(status_code=502, detail=str(res.error))
    rows = res.data or []
    if not rows:
        raise HTTPException(status_code=404, detail="Client not found")
    return rows[0]


@router.post("/", response_model=ClientOut, status_code=201, summary="Create client")
def create_client(payload: ClientCreate):
    sb = get_supabase()
    # Perform insert
    res = (
        sb.table("clients")
          .insert(payload.model_dump(exclude_none=True))
          .execute()
    )
    if getattr(res, "error", None):
        raise HTTPException(status_code=502, detail=str(res.error))

    # Supabase usually returns the inserted row in data list
    if isinstance(res.data, list) and res.data:
        return res.data[0]
    elif isinstance(res.data, dict):
        return res.data

    # Fallback: try to fetch by a unique field if provided (email) — optional
    email = payload.email
    if email:
        res2 = sb.table("clients").select("*").eq("email", email).execute()
        if getattr(res2, "error", None):
            raise HTTPException(status_code=502, detail=str(res2.error))
        rows = res2.data or []
        if rows:
            return rows[0]
    # If still nothing, return 502 since we cannot confirm insert result
    raise HTTPException(status_code=502, detail="Failed to retrieve created client")


@router.patch("/{client_id}", response_model=ClientOut, summary="Update client by id")
def update_client(client_id: int, patch: ClientPatch):
    sb = get_supabase()
    data = patch.model_dump(exclude_none=True)
    if not data:
        raise HTTPException(status_code=400, detail="No fields to update")

    res = (
        sb.table("clients")
          .update(data)
          .eq("id", client_id)
          .execute()
    )
    if getattr(res, "error", None):
        raise HTTPException(status_code=502, detail=str(res.error))

    # Verify the updated row exists and return it
    res2 = (
        sb.table("clients")
          .select("*")
          .eq("id", client_id)
          .execute()
    )
    if getattr(res2, "error", None):
        raise HTTPException(status_code=502, detail=str(res2.error))
    rows = res2.data or []
    if not rows:
        raise HTTPException(status_code=404, detail="Client not found")
    return rows[0]


@router.delete("/{client_id}", status_code=204, summary="Delete client by id")
def delete_client(client_id: int):
    sb = get_supabase()

    # Verify existence first to return 404 if missing
    exists = (
        sb.table("clients")
          .select("id")
          .eq("id", client_id)
          .execute()
    )
    if getattr(exists, "error", None) or not getattr(exists, "data", None):
        raise HTTPException(status_code=404, detail="Client not found")

    res = sb.table("clients").delete().eq("id", client_id).execute()
    if getattr(res, "error", None):
        raise HTTPException(status_code=502, detail=str(res.error))
    # FastAPI will honor the 204 status code from decorator
    return { }
