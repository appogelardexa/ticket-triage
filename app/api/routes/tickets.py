from typing import List, Optional
from fastapi import APIRouter, HTTPException, Query
from app.core.config import get_supabase
from app.models.schemas import (
    TicketCreate, 
    TicketPatch, 
    TicketOut, 
    TicketWithClientFlat,
    StatusHistoryRow, 
    PriorityHistoryRow,
    TicketsPage,
    TicketFormattedOut,
    TicketsPageFormatted
    
)

router = APIRouter(tags=["tickets"])

@router.get("/paginated", response_model=TicketsPageFormatted, summary="List tickets (formatted, paginated)")
def list_tickets(
    limit: int = Query(10, ge=1, le=100, description="Number of tickets to return"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    sort: bool = Query(False, description="True=descending (newest first), False=ascending"),
):
    sb = get_supabase()
    res = (
        sb.table("tickets_formatted")
          .select("*", count="exact")
          .order("created_at", desc=sort)
          .range(offset, offset + limit - 1)
          .execute()
    )
    if getattr(res, "error", None):
        raise HTTPException(status_code=502, detail=str(res.error))

    data = res.data or []
    count = getattr(res, "count", None)
    has_more = len(data) == limit and (count is None or (offset + limit) < count)
    next_offset = (offset + limit) if has_more else None

    return {
        "data": data,   
        "count": count,
        "limit": limit,
        "offset": offset,
        "next_offset": next_offset,
    }


@router.get("/by-email", response_model=List[TicketFormattedOut], summary="List tickets by email")
def list_tickets_by_email(
    email: str = Query(..., min_length=3, description="Email to filter by"),
    scope: str = Query("client", description="Where to match: client | assignee | any"),
    sort: bool = Query(True, description="True=descending (newest first), False=ascending"),
):
    sb = get_supabase()
    query = sb.table("tickets_formatted").select("*")

    s = (scope or "client").lower()
    if s == "client":
        query = query.eq("client_email", email)
    elif s == "assignee":
        query = query.eq("assignee_email", email)
    else:
        # Match either client or assignee email
        query = query.or_(f"client_email.eq.{email},assignee_email.eq.{email}")

    res = query.order("created_at", desc=sort).execute()

    if getattr(res, "error", None):
        raise HTTPException(status_code=502, detail=str(res.error))

    return res.data or []


@router.get("/by-client-name", response_model=List[TicketFormattedOut], summary="List tickets by client name (no pagination)")
def list_tickets_by_client_name(
    name: str = Query(..., min_length=2, description="Client name to filter by"),
    exact: bool = Query(False, description="True=exact match, False=contains match"),
    sort: bool = Query(True, description="True=descending (newest first), False=ascending"),
):
    sb = get_supabase()
    query = sb.table("tickets_formatted").select("*")

    if exact:
        query = query.eq("client_name", name)
    else:
        query = query.ilike("client_name", f"%{name}%")

    res = query.order("created_at", desc=sort).execute()

    if getattr(res, "error", None):
        raise HTTPException(status_code=502, detail=str(res.error))

    return res.data or []


# @router.get("/{id}", response_model=TicketFormattedOut, summary="Get ticket by numeric id")
# def get_ticket_by_id(id: int):
#     sb = get_supabase()
#     res = (
#         sb.table("tickets_formatted")
#           .select("*")
#           .eq("id", id)
#           .single()
#           .execute()
#     )
#     if not getattr(res, "data", None):
#         raise HTTPException(status_code=404, detail="Ticket not found")
#     return res.data


@router.get("/{ticket_id}", response_model=TicketFormattedOut, summary="Get ticket by ticket_id")
def get_ticket_by_ticket_id(ticket_id: str):
    sb = get_supabase()
    res = (
        sb.table("tickets_formatted")
          .select("*")
          .eq("ticket_id", ticket_id)
          .single()
          .execute()
    )
    if not getattr(res, "data", None):
        raise HTTPException(status_code=404, detail="Ticket not found")
    return res.data

























# @router.get("/", response_model=List[TicketWithClientFlat])
# def list_tickets(limit: int = 50, offset: int = 0):
#     supabase = get_supabase()
#     res = (supabase.table("tickets_with_client")
#            .select("*")
#            .range(offset, offset + limit - 1)
#            .execute())
#     return res.data or []

# @router.get("/{ticket_id}", response_model=TicketOut)
# def get_ticket(ticket_id: int):
#     supabase = get_supabase()
#     res = (supabase.table("tickets")
#            .select("id,ticket_id,status,priority,channel,summary,client_id")
#            .eq("id", ticket_id).single()
#            .execute())
#     if not res.data:
#         raise HTTPException(status_code=404, detail="Ticket not found")
#     return res.data

# @router.post("/", response_model=TicketOut, status_code=201)
# def create_ticket(payload: TicketCreate):
#     supabase = get_supabase()
#     res = (supabase.table("tickets")
#            .insert(payload.model_dump(exclude_none=True))
#            .select("id,ticket_id,status,priority,channel,summary,client_id")
#            .single()
#            .execute())
#     return res.data

# @router.patch("/{ticket_id}", response_model=TicketOut)
# def update_ticket(ticket_id: int, patch: TicketPatch):
#     supabase = get_supabase()
#     data = patch.model_dump(exclude_none=True)
#     if not data:
#         raise HTTPException(status_code=400, detail="No fields to update")
#     res = (supabase.table("tickets")
#            .update(data)
#            .eq("id", ticket_id)
#            .select("id,ticket_id,status,priority,channel,summary,client_id")
#            .single()
#            .execute())
#     if not res.data:
#         raise HTTPException(status_code=404, detail="Ticket not found")
#     return res.data

# @router.get("/{ticket_id}/status-history", response_model=List[StatusHistoryRow])
# def status_history(ticket_id: int):
#     supabase = get_supabase()
#     res = (supabase.table("ticket_status_history")
#            .select("*").eq("ticket_id", ticket_id)
#            .order("changed_at", desc=False).execute())
#     return res.data or []

# @router.get("/{ticket_id}/priority-history", response_model=List[PriorityHistoryRow])
# def priority_history(ticket_id: int):
#     supabase = get_supabase()
#     res = (supabase.table("ticket_priority_history")
#            .select("*").eq("ticket_id", ticket_id)
#            .order("changed_at", desc=False).execute())
#     return res.data or []
