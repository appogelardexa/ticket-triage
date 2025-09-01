from typing import List, Optional
from datetime import date, datetime, timedelta, timezone
from fastapi import APIRouter, HTTPException, Query, Response
from app.core.config import get_supabase
from app.models.schemas import (
    TicketPatch,
    TicketOut,
    TicketWithClientFlat,
    StatusHistoryRow,
    PriorityHistoryRow,
    TicketsPage,
    TicketFormattedOut,
    TicketsPageFormatted,
    TicketCreateInputV3,
    TicketsListWithCount,
)
from app.services.tickets_service import (
    resolve_ticket_create_refs,
    build_ticket_insertable,
)

router = APIRouter(tags=["tickets"])

@router.post("/create", response_model=TicketFormattedOut, status_code=201, summary="Create ticket (resolve names to IDs)")
def create_ticket(payload: TicketCreateInputV3):
    sb = get_supabase()

    data = resolve_ticket_create_refs(sb, payload)
    insertable = build_ticket_insertable(data)

    res = (
        sb.table("tickets")
          .insert(insertable)
          .execute()
    )

    if getattr(res, "error", None):
        raise HTTPException(status_code=502, detail=str(res.error))

    # Normalize insert response (Supabase may return list of rows)
    row = None
    if isinstance(res.data, list):
        row = res.data[0] if res.data else None
    else:
        row = res.data
    ticket_id = row.get("ticket_id") if isinstance(row, dict) else None
    if not ticket_id:
        raise HTTPException(status_code=502, detail="Failed to retrieve created ticket_id")

    res2 = (
        sb.table("tickets_formatted")
          .select("*")
          .eq("ticket_id", ticket_id)
          .single()
          .execute()
    )
    if getattr(res2, "error", None):
        raise HTTPException(status_code=502, detail=str(res2.error))
    if not getattr(res2, "data", None):
        raise HTTPException(status_code=502, detail="Created ticket not found in formatted view")
    return res2.data

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

# @router.get("/by-date", response_model=TicketsListWithCount, summary="Filter tickets by created_at date")
# def filter_tickets_by_date(
#     on: Optional[date] = Query(None, description="Specific date (YYYY-MM-DD)"),
#     start_date: Optional[date] = Query(None, description="Start date inclusive (YYYY-MM-DD)"),
#     end_date: Optional[date] = Query(None, description="End date inclusive (YYYY-MM-DD)"),
#     sort: bool = Query(True, description="True=newest first; False=oldest first"),
#     limit: int = Query(50, ge=1, le=100, description="Max rows to return"),
# ):
#     """
#     Basic date filtering using UTC [start, end) range.
#     - If `on` is provided, filters that single calendar day in UTC.
#     - Otherwise uses `start_date` and/or `end_date` (inclusive end date).
#     """
#     sb = get_supabase()

#     start_dt_utc: Optional[datetime] = None
#     end_dt_utc: Optional[datetime] = None

#     if on is not None:
#         start_dt_utc = datetime(on.year, on.month, on.day, tzinfo=timezone.utc)
#         end_dt_utc = start_dt_utc + timedelta(days=1)
#     else:
#         if start_date is not None:
#             start_dt_utc = datetime(start_date.year, start_date.month, start_date.day, tzinfo=timezone.utc)
#         if end_date is not None:
#             end_dt_utc = datetime(end_date.year, end_date.month, end_date.day, tzinfo=timezone.utc) + timedelta(days=1)

#     if start_dt_utc and end_dt_utc and start_dt_utc >= end_dt_utc:
#         raise HTTPException(status_code=400, detail="start_date must be before end_date")
#     if start_dt_utc is None and end_dt_utc is None:
#         raise HTTPException(status_code=400, detail="Provide on, or start_date/end_date")

#     def as_rfc3339(dt: datetime) -> str:
#         return dt.isoformat().replace("+00:00", "Z")

#     q = sb.table("tickets_detailed").select("*", count="exact")
#     if start_dt_utc is not None:
#         q = q.gte("created_at", as_rfc3339(start_dt_utc))
#     if end_dt_utc is not None:
#         q = q.lt("created_at", as_rfc3339(end_dt_utc))

#     res = q.order("created_at", desc=sort).range(0, max(0, limit - 1)).execute()
#     if getattr(res, "error", None):
#         raise HTTPException(status_code=502, detail=str(res.error))

#     return {
#         "data": res.data or [],
#         "count": getattr(res, "count", None),
#         "limit": limit,
#     }

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


@router.get("/{ticket_id}", response_model=TicketFormattedOut, summary="Get ticket by ticket_id")
def get_ticket_by_ticket_id(ticket_id: str):
    sb = get_supabase()

    res = (
        sb.table("tickets_formatted")
          .select("*")
          .eq("ticket_id", ticket_id)
          .execute()
    )
    rows = res.data or []
    if not rows:
        raise HTTPException(status_code=404, detail="Ticket not found")

    return rows[0]


@router.get("/", response_model=TicketsListWithCount, summary="Filter tickets by IDs")
def filter_tickets(
    assignee_id: Optional[int] = Query(None, description="Tickets assigned to this staff user"),
    department_id: Optional[int] = Query(None, description="Tickets under this department"),
    category_id: Optional[int] = Query(None, description="Tickets tagged with this category"),
    company_id: Optional[int] = Query(None, description="Tickets where client belongs to this company"),
    client_id: Optional[int] = Query(None, description="Tickets for this client/requester"),
    sort: bool = Query(True, description="True=newest first; False=oldest first"),
    limit: int = Query(50, ge=1, le=100, description="Max rows to return"),
):
    """
    Filters tickets using any combination of the provided parameters.
    - Combination: All provided filters are combined with AND.
    - Required: At least one filter must be provided; otherwise returns 400
    """
    sb = get_supabase()

    # Require at least one filter to avoid unbounded result
    if not any([assignee_id, department_id, category_id, company_id, client_id]):
        raise HTTPException(status_code=400, detail="Provide at least one filter parameter")

    base_filters = {
        "assignee_id": assignee_id,
        "department_id": department_id,
        "category_id": category_id,
        "client_id": client_id,
    }

    # Collect ticket PKs based on base table filters (if any of those are provided)
    ticket_ids: Optional[list] = None
    if any(v is not None for v in base_filters.values()):
        q = sb.table("tickets").select("id")
        for col, val in base_filters.items():
            if val is not None:
                q = q.eq(col, val)
        res_ids = q.execute()
        if getattr(res_ids, "error", None):
            raise HTTPException(status_code=502, detail=str(res_ids.error))
        rows = res_ids.data or []
        if not rows:
            return []
        ticket_ids = [r["id"] for r in rows if isinstance(r, dict) and "id" in r]
        if not ticket_ids:
            return []

    # Now query the formatted view and apply remaining filters
    qf = sb.table("tickets_detailed").select("*", count="exact")

    if company_id is not None:
        qf = qf.eq("company_id", company_id)

    if ticket_ids is not None:
        qf = qf.in_("id", ticket_ids)

    res = qf.order("created_at", desc=sort).range(0, max(0, limit - 1)).execute()
    if getattr(res, "error", None):
        raise HTTPException(status_code=502, detail=str(res.error))
    return {
        "data": res.data or [],
        "count": getattr(res, "count", None),
        "limit": limit,
    }


@router.patch("/{ticket_id}", response_model=TicketFormattedOut, summary="Update ticket by ticket_id")
def update_ticket(ticket_id: str, patch: TicketPatch):
    sb = get_supabase()
    data = patch.model_dump(exclude_none=True)
    if not data:
        raise HTTPException(status_code=400, detail="No fields to update")

    # Update the base ticket row
    res = (
        sb.table("tickets")
          .update(data)
          .eq("ticket_id", ticket_id)
        #   .select("id,ticket_id")
        #   .single()
          .execute()
    )
    if getattr(res, "error", None):
        raise HTTPException(status_code=502, detail=str(res.error))
    if not getattr(res, "data", None):
        raise HTTPException(status_code=404, detail="Ticket not found")

    # Return the formatted view of the updated ticket
    res2 = (
        sb.table("tickets_formatted")
          .select("*")
          .eq("ticket_id", ticket_id)
        #   .single()
          .execute()
    )
    if getattr(res2, "error", None):
        raise HTTPException(status_code=502, detail=str(res2.error))
    if not getattr(res2, "data", None):
        raise HTTPException(status_code=404, detail="Ticket not found after update")
    return res2.data


@router.delete("/{ticket_id}", status_code=204, summary="Delete ticket by ticket_id")
def delete_ticket(ticket_id: str):
    sb = get_supabase()

    # Verify existence first to return a proper 404
    exists = (
        sb.table("tickets")
          .select("id")
          .eq("ticket_id", ticket_id)
        #   .single()
          .execute()
    )
    if getattr(exists, "error", None) or not getattr(exists, "data", None):
        raise HTTPException(status_code=404, detail="Ticket not found")

    ticket_pk = exists.data["id"] if isinstance(exists.data, dict) else None
    res = sb.table("tickets").delete().eq("id", ticket_pk).execute()
    if getattr(res, "error", None):
        raise HTTPException(status_code=502, detail=str(res.error))
    return Response(status_code=204)



