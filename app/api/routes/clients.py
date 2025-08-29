from typing import List, Optional
from fastapi import APIRouter, HTTPException, Query
from app.core.config import get_supabase

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
