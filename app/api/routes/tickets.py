from typing import List, Optional
from uuid import uuid4
import os
import mimetypes
from datetime import date, datetime, timedelta, timezone
from app.api.deps import require_user, get_user_supabase
from fastapi import APIRouter, HTTPException, Query, Response, UploadFile, File, Form, Depends
from app.core.config import get_supabase
from app.models.schemas import (
    TicketPatch,
    TicketOut,
    TicketWithClientFlat,
    StatusHistoryRow,
    PriorityHistoryRow,
    TicketsPage,
    TicketFormattedOut,
    TicketFormattedWithAttachmentsOut,
    TicketsPageFormatted,
    TicketCreateInputV3,
    TicketsListWithCount,
    TicketStatus,
    TicketPriority,
    TicketChannel,
    TicketAttachmentOut,
    TicketCreatedWithAttachmentsOut,
    TicketsPageFormattedWithAttachments,
    TicketsListWithCountWithAttachments,
    TicketCommentOut,
    TicketCommentCreate,
    TicketCommentPatch,
)
from app.services.tickets_service import (
    resolve_ticket_create_refs,
    build_ticket_insertable,
    build_utc_range,
    upload_attachments_for_ticket,
    get_ticket_pk_and_public_id,
    enrich_tickets_with_attachments,
)



# Storage config
ATTACHMENTS_BUCKET = os.getenv("SUPABASE_TICKET_ATTACHMENTS_BUCKET")


router = APIRouter(tags=["tickets"])

@router.post(
    "/create",
    response_model=TicketCreatedWithAttachmentsOut,
    status_code=201,
    summary="Create ticket with optional attachments",
)
def create_ticket_with_attachments(
    # TicketCreateInputV3 fields via Form to support multipart
    summary: str = Form(...),
    status: Optional[TicketStatus] = Form(None),
    priority: Optional[TicketPriority] = Form(None),
    channel: Optional[TicketChannel] = Form(None),
    client_id: Optional[int] = Form(None),
    client_name: Optional[str] = Form(None),
    client_email: Optional[str] = Form(None),
    assignee_id: Optional[int] = Form(None),
    department_id: Optional[int] = Form(None),
    category_id: Optional[int] = Form(None),
    body: Optional[str] = Form(None),
    subject: Optional[str] = Form(None),
    message_id: Optional[str] = Form(None),
    thread_id: Optional[str] = Form(None),
    attachments: Optional[List[UploadFile]] = File(None),
    user=Depends(require_user),
):
    # Use user-scoped client so tickets insert/select respects RLS
    sb_user = get_user_supabase(user["jwt"])
    # Keep service-role client for Storage uploads and attachment metadata until Storage RLS is configured
    sb_admin = get_supabase()

    payload = TicketCreateInputV3(
        summary=summary,
        status=status,
        priority=priority,
        channel=channel,
        client_id=client_id,
        client_name=client_name,
        client_email=client_email,
        assignee_id=assignee_id,
        department_id=department_id,
        category_id=category_id,
        body=body,
        subject=subject,
        message_id=message_id,
        thread_id=thread_id,
    )

    data = resolve_ticket_create_refs(sb_user, payload)
    insertable = build_ticket_insertable(data)

    res = sb_user.table("tickets").insert(insertable).execute()
    if getattr(res, "error", None):
        raise HTTPException(status_code=502, detail=str(res.error))

    row = res.data[0] if isinstance(res.data, list) and res.data else res.data
    ticket_id = row.get("ticket_id") if isinstance(row, dict) else None
    if not ticket_id:
        raise HTTPException(status_code=502, detail="Failed to retrieve created ticket_id")

    res2 = (
        sb_user.table("tickets_formatted")
          .select("*")
          .eq("ticket_id", ticket_id)
          .single()
          .execute()
    )
    if getattr(res2, "error", None):
        raise HTTPException(status_code=502, detail=str(res2.error))
    if not getattr(res2, "data", None):
        raise HTTPException(status_code=502, detail="Created ticket not found in formatted view")

    ticket_row = res2.data
    uploaded = upload_attachments_for_ticket(sb_admin, ticket_row, attachments)
    return {"ticket": ticket_row, "attachments": uploaded}


# @router.get(
#     "/{ticket_id}/attachments",
#     response_model=List[TicketAttachmentOut],
#     summary="List attachments for a ticket",
# )
# def list_ticket_attachments(ticket_id: str):
#     sb = get_supabase()
#     # Support numeric or public id
#     ticket_pk, _ = get_ticket_pk_and_public_id(sb, ticket_id)
#     res = (
#         sb.table("ticket_attachments")
#           .select("*")
#           .eq("ticket_id", ticket_pk)
#           .order("created_at")
#           .execute()
#     )
#     if getattr(res, "error", None):
#         raise HTTPException(status_code=502, detail=str(res.error))
#     return res.data or []


@router.post(
    "/{ticket_id}/attachments",
    response_model=List[TicketAttachmentOut],
    status_code=201,
    summary="Upload one or more attachments to a ticket",
)
def add_ticket_attachments(ticket_id: str, files: Optional[List[UploadFile]] = File(None)):
    sb = get_supabase()
    # Resolve public id for fetching formatted row
    _, public_id = get_ticket_pk_and_public_id(sb, ticket_id)
    t = sb.table("tickets_formatted").select("*").eq("ticket_id", public_id).single().execute()
    if getattr(t, "error", None) or not getattr(t, "data", None):
        raise HTTPException(status_code=404, detail="Ticket not found")
    ticket_row = t.data
    rows = upload_attachments_for_ticket(sb, ticket_row, files)
    return rows


@router.delete(
    "/{ticket_id}/attachments/{attachment_id}",
    status_code=204,
    summary="Delete an attachment from a ticket",
)
def delete_ticket_attachment(ticket_id: str, attachment_id: int):
    sb = get_supabase()
    # Verify ticket and attachment match and fetch the object path
    ticket_pk, _ = get_ticket_pk_and_public_id(sb, ticket_id)

    a = (
        sb.table("ticket_attachments")
          .select("id,file_path,ticket_id")
          .eq("id", attachment_id)
          .eq("ticket_id", ticket_pk)
          .single()
          .execute()
    )
    if getattr(a, "error", None) or not getattr(a, "data", None):
        raise HTTPException(status_code=404, detail="Attachment not found for ticket")
    object_path = a.data.get("file_path") if isinstance(a.data, dict) else None

    # Try to remove from storage first (ignore errors)
    try:
        sb.storage.from_(ATTACHMENTS_BUCKET).remove([object_path])
    except Exception:
        pass

    # Remove DB row
    d = sb.table("ticket_attachments").delete().eq("id", attachment_id).execute()
    if getattr(d, "error", None):
        raise HTTPException(status_code=502, detail=str(d.error))
    return Response(status_code=204)


@router.put(
    "/{ticket_id}/attachments/{attachment_id}",
    response_model=TicketAttachmentOut,
    summary="Replace file content for an attachment",
)
def replace_ticket_attachment(ticket_id: str, attachment_id: int, file: UploadFile = File(...)):
    sb = get_supabase()
    # Verify ticket and fetch attachment row
    ticket_pk, _ = get_ticket_pk_and_public_id(sb, ticket_id)

    a = (
        sb.table("ticket_attachments")
          .select("*")
          .eq("id", attachment_id)
          .eq("ticket_id", ticket_pk)
          .single()
          .execute()
    )
    if getattr(a, "error", None) or not getattr(a, "data", None):
        raise HTTPException(status_code=404, detail="Attachment not found for ticket")
    att = a.data
    object_path = att.get("file_path")

    # Upload new content to the same path (upsert)
    try:
        try:
            file.file.seek(0)
        except Exception:
            pass
        content = file.file.read()
        up = sb.storage.from_(ATTACHMENTS_BUCKET).upload(
            path=object_path,
            file=content,
            file_options={
                "content-type": file.content_type or "application/octet-stream",
                "x-upsert": "true",
            },
        )
        up_err = None
        if isinstance(up, dict):
            up_err = up.get("error")
        else:
            up_err = getattr(up, "error", None)
        if up_err:
            raise HTTPException(status_code=502, detail=f"Storage upload failed: {up_err}")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Failed to upload replacement file: {exc}")

    # Update metadata
    upd = (
        sb.table("ticket_attachments")
          .update({
              "filename": file.filename or att.get("filename"),
              "mime_type": getattr(file, "content_type", None),
              "size_bytes": len(content) if content is not None else None,
          })
          .eq("id", attachment_id)
          .execute()
    )
    if getattr(upd, "error", None):
        raise HTTPException(status_code=502, detail=str(upd.error))

    # Return latest row
    res = sb.table("ticket_attachments").select("*").eq("id", attachment_id).single().execute()
    if getattr(res, "error", None) or not getattr(res, "data", None):
        raise HTTPException(status_code=502, detail="Failed to fetch updated attachment")
    return res.data

@router.get(
    "/{ticket_id}/comments",
    response_model=List[TicketCommentOut],
    summary="List comments for a ticket",
)
def list_ticket_comments(
    ticket_id: str,
    limit: int = Query(50, ge=1, le=100, description="Max rows to return"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    is_private: Optional[bool] = Query(None, description="Filter by privacy flag"),
    user=Depends(require_user),
):
    sb = get_user_supabase(user["jwt"])
    try: 
        ticket_pk, _ = get_ticket_pk_and_public_id(sb, ticket_id)
        q = (
            sb.table("ticket_comments")
            .select("*")
            .eq("ticket_id", ticket_pk)
            .order("created_at", desc=True)
            .range(offset, offset + limit - 1)
        )
        if is_private is not None:
            q = q.eq("is_private", is_private)
        res = q.execute()
        if getattr(res, "error", None):
            raise HTTPException(status_code=502, detail=str(res.error))
        return res.data or []
    except Exception as exc:
        raise HTTPException(status_code=502, detail="Upstream error while fetching comments") from exc


@router.post(
    "/{ticket_id}/comments",
    response_model=TicketCommentOut,
    status_code=201,
    summary="Add a comment to a ticket",
)
def add_ticket_comment(ticket_id: str, payload: TicketCommentCreate, user=Depends(require_user)):
    sb = get_user_supabase(user["jwt"])
    ticket_pk, _ = get_ticket_pk_and_public_id(sb, ticket_id)

    if not payload.internal_staff_id:
        raise HTTPException(status_code=400, detail="internal_staff_id is required")

    data = payload.model_dump(exclude_none=True)
    data["ticket_id"] = ticket_pk

    res = sb.table("ticket_comments").insert(data).execute()
    if getattr(res, "error", None):
        raise HTTPException(status_code=502, detail=str(res.error))

    row = res.data[0] if isinstance(res.data, list) and res.data else res.data
    if not row:
        # Fallback: fetch latest inserted for this ticket by created_at
        sel = (
            sb.table("ticket_comments")
              .select("*")
              .eq("ticket_id", ticket_pk)
              .order("created_at", desc=True)
              .limit(1)
              .execute()
        )
        if getattr(sel, "error", None) or not getattr(sel, "data", None):
            raise HTTPException(status_code=502, detail="Failed to fetch created comment")
        return sel.data[0]
    return row


@router.put(
    "/comments/{comment_id}",
    response_model=TicketCommentOut,
    summary="Update a comment",
)
def update_ticket_comment(comment_id: int, patch: TicketCommentPatch, user=Depends(require_user)):
    sb = get_user_supabase(user["jwt"])
    data = patch.model_dump(exclude_none=True)
    if not data:
        raise HTTPException(status_code=400, detail="No fields to update")

    res = sb.table("ticket_comments").update(data).eq("id", comment_id).execute()
    if getattr(res, "error", None):
        raise HTTPException(status_code=502, detail=str(res.error))

    sel = sb.table("ticket_comments").select("*").eq("id", comment_id).single().execute()
    if getattr(sel, "error", None) or not getattr(sel, "data", None):
        raise HTTPException(status_code=404, detail="Comment not found")
    return sel.data


@router.delete(
    "/comments/{comment_id}",
    status_code=204,
    summary="Delete a comment",
)
def delete_ticket_comment(comment_id: int, user=Depends(require_user)):
    sb = get_user_supabase(user["jwt"])
    # Ensure it exists for 404
    sel = sb.table("ticket_comments").select("id").eq("id", comment_id).single().execute()
    if getattr(sel, "error", None) or not getattr(sel, "data", None):
        raise HTTPException(status_code=404, detail="Comment not found")

    d = sb.table("ticket_comments").delete().eq("id", comment_id).execute()
    if getattr(d, "error", None):
        raise HTTPException(status_code=502, detail=str(d.error))
    return Response(status_code=204)

@router.get("/paginated", response_model=TicketsPageFormattedWithAttachments, summary="Fetch a paginated list of tickets (with attachments)")
def list_tickets(
    limit: int = Query(10, ge=1, le=100, description="Number of tickets to return"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    sort: bool = Query(False, description="True=descending (newest first), False=ascending"),
    user=Depends(require_user),
):
    """
    Retrieve a paginated list of tickets from the `tickets_formatted` table.

    - Results are ordered by `created_at` (ascending by default; descending if `sort=True`).
    - Pagination is controlled by:
    * `limit` — maximum number of rows per page (default 10, max 100).
    * `offset` — starting row for the current page.

    Response:
    - `count` — total number of tickets available.
    - `limit` — page size applied.
    - `offset` — current page offset.
    - `next_offset` — offset value for the next page, or `null` if no more results.
    - `data` — the ticket records returned.

    Errors:
    - 502 if the database query fails.
    """

    sb_user = get_user_supabase(user["jwt"])
    res = (
        sb_user.table("tickets_formatted")
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

    enriched = enrich_tickets_with_attachments(get_supabase(), data)

    return {
        "count": count,
        "limit": limit,
        "offset": offset,
        "next_offset": next_offset,
        "data": enriched,
    }

@router.get("/by-date", response_model=TicketsListWithCountWithAttachments, summary="Filter tickets by created_at date (with attachments)")
def filter_tickets_by_date(
    on: Optional[str] = Query(None, description="Specific date (YYYY-MM-DD)"),
    start_date: Optional[str] = Query(None, description="Start date inclusive (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="End date inclusive (YYYY-MM-DD)"),
    sort: bool = Query(True, description="True=newest first; False=oldest first"),
    limit: int = Query(50, ge=1, le=100, description="Max rows to return"),
    user=Depends(require_user),
):
    """
    Retrieve tickets filtered by their `created_at` timestamp.

    - Provide at least one of:
    * `on` — a specific calendar date (filters tickets created on that day, UTC).
    * `start_date` — the inclusive start date of the range.
    * `end_date` — the inclusive end date of the range.
    - If only `on` is given, results cover that single day.
    - If `start_date` and/or `end_date` are provided, results cover the inclusive date range.
    - Results are ordered by `created_at` (newest first by default; oldest first if `sort=False`).
    - Maximum rows are capped by `limit` (default 50, maximum 100).

    Response:
    - `count` — total matching records.
    - `limit` — applied row limit.
    - `data` — list of tickets.

    Errors:
    - 400 if no date filters are provided or if `start_date >= end_date`.
    - 502 if the database query fails.
    """

    sb = get_user_supabase(user["jwt"])

    if on is not None:
        start_at, end_at = build_utc_range(on=on)
    else:
        start_at, end_at = build_utc_range(start_at=start_date, end_at=end_date)
        if start_at >= end_at:
            raise HTTPException(status_code=400, detail="start_date must be before end_date")

        
    q = sb.table("tickets_detailed").select("*", count="exact")
    if sort is not None:
        q = q.order("created_at", desc=sort)
    if limit is not None:
        q = q.limit(limit)

    q = q.gte("created_at", start_at).lt("created_at", end_at)
    res = q.execute()
    
    if getattr(res, "error", None):
        raise HTTPException(status_code=502, detail=str(res.error))

    rows = res.data or []
    enriched = enrich_tickets_with_attachments(get_supabase(), rows)
    return {
        "count": getattr(res, "count", None),
        "limit": limit,
        "data": enriched,
    }


@router.get("/by-attributes", response_model=TicketsListWithCountWithAttachments, summary="Filter tickets by status, priority, or channel (with attachments)")
def filter_tickets_by_attributes(
    status: Optional[TicketStatus] = Query(None, description="Ticket status"),
    priority: Optional[TicketPriority] = Query(None, description="Ticket priority"),
    channel: Optional[TicketChannel] = Query(None, description="Ticket channel"),
    
    on: Optional[str] = Query(None, description="Specific date (YYYY-MM-DD)"),
    start_date: Optional[str] = Query(None, description="Start date inclusive (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="End date inclusive (YYYY-MM-DD)"),
    
    sort: bool = Query(True, description="True=newest first; False=oldest first"),
    limit: int = Query(50, ge=1, le=100, description="Max rows to return"),
    user=Depends(require_user),
):
    """
    Retrieve tickets filtered by one or more attributes: `status`, `priority`, or `channel`.
    Optional date filters (`on`, `start_date`, `end_date`) may also be applied.

    - At least one of `status`, `priority`, or `channel` must be provided; otherwise a 400 error is returned.
    - If `on` is given, results cover that single UTC calendar day.
    - If `start_date` and/or `end_date` are provided, results cover the inclusive date range.
    - Results are ordered by `created_at` (newest first by default; oldest first if `sort=False`).
    - Maximum rows are capped by `limit` (default 50, maximum 100).

    Response:
    - `count` — total number of records matching the filters.
    - `limit` — the applied row limit.
    - `data` — the list of ticket records.

    Errors:
    - 400 if no attribute filters are provided, or if `start_date >= end_date`.
    - 502 if the database query fails.
    """

    sb = get_user_supabase(user["jwt"])

    # Require at least one filter to avoid unbounded result
    if not any([status, priority, channel]):
        raise HTTPException(status_code=400, detail="Provide at least one of status, priority or channel")

    q = sb.table("tickets_detailed").select("*", count="exact")

    # Apply filters; use enum .value if provided
    if status is not None:
        q = q.eq("status", getattr(status, "value", status))
    if priority is not None:
        q = q.eq("priority", getattr(priority, "value", priority))
    if channel is not None:
        q = q.eq("channel", getattr(channel, "value", channel))

    if on is not None:
        start_at, end_at = build_utc_range(on=on)
        q = q.gte("created_at", start_at).lt("created_at", end_at)
    else:
        if start_date is not None or end_date is not None:
            start_at, end_at = build_utc_range(start_at=start_date, end_at=end_date)
            if start_at >= end_at:
                raise HTTPException(status_code=400, detail="start_date must be before end_date")
            q = q.gte("created_at", start_at).lt("created_at", end_at)

    res = q.order("created_at", desc=sort).range(0, max(0, limit - 1)).execute()
    if getattr(res, "error", None):
        raise HTTPException(status_code=502, detail=str(res.error))

    rows = res.data or []
    enriched = enrich_tickets_with_attachments(get_supabase(), rows)
    return {
        "count": getattr(res, "count", None),
        "limit": limit,
        "data": enriched,
    }


@router.get("/{ticket_id}", response_model=TicketFormattedWithAttachmentsOut, summary="Get ticket by ticket_id (with attachments)")
def get_ticket_by_ticket_id(ticket_id: str, user=Depends(require_user)):
    sb = get_user_supabase(user["jwt"])  # RLS-enforced
    try:
        res = (
            sb.table("tickets_formatted")
              .select("*")
              .eq("ticket_id", ticket_id)
              .limit(1)
              .execute()
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail="Upstream error while fetching ticket") from exc

    # Normalize result: Supabase may return a list or dict depending on driver
    row = None
    if isinstance(getattr(res, "data", None), list):
        data_list = res.data or []
        if data_list:
            row = data_list[0]
    elif isinstance(getattr(res, "data", None), dict):
        row = res.data

    if not isinstance(row, dict):
        raise HTTPException(status_code=404, detail="Ticket not found")

    enriched = enrich_tickets_with_attachments(get_supabase(), [row])
    return enriched[0] if enriched else row


@router.get("/", response_model=TicketsListWithCountWithAttachments, summary="Filter tickets by IDs (with attachments)")
def filter_tickets(
    assignee_id: Optional[int] = Query(None, description="Tickets assigned to this staff user"),
    department_id: Optional[int] = Query(None, description="Tickets under this department"),
    category_id: Optional[int] = Query(None, description="Tickets tagged with this category"),
    company_id: Optional[int] = Query(None, description="Tickets where client belongs to this company"),
    client_id: Optional[int] = Query(None, description="Tickets for this client/requester"),
    sort: bool = Query(True, description="True=newest first; False=oldest first"),
    limit: int = Query(50, ge=1, le=100, description="Max rows to return"),
    user=Depends(require_user),
):
    """
    Filters tickets using any combination of the provided parameters.
    - Combination: All provided filters are combined with AND.
    - Required: At least one filter must be provided; otherwise returns 400
    """
    sb = get_user_supabase(user["jwt"])

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
    rows = res.data or []
    enriched = enrich_tickets_with_attachments(get_supabase(), rows)
    return {
        "count": getattr(res, "count", None),
        "limit": limit,
        "data": enriched,
    }


# @router.patch("/{ticket_id}", response_model=TicketFormattedOut, summary="Update ticket by ticket_id")
# def update_ticket(ticket_id: str, patch: TicketPatch):
#     sb = get_supabase()
#     data = patch.model_dump(exclude_none=True)
#     if not data:
#         raise HTTPException(status_code=400, detail="No fields to update")

#     # Update the base ticket row
#     res = (
#         sb.table("tickets")
#           .update(data)
#           .eq("ticket_id", ticket_id)
#         #   .select("id,ticket_id")
#         #   .single()
#           .execute()
#     )
#     if getattr(res, "error", None):
#         raise HTTPException(status_code=502, detail=str(res.error))
#     if not getattr(res, "data", None):
#         raise HTTPException(status_code=404, detail="Ticket not found")

#     # Return the formatted view of the updated ticket
#     res2 = (
#         sb.table("tickets_formatted")
#           .select("*")
#           .eq("ticket_id", ticket_id)
#           .single()
#           .execute()
#     )
#     if getattr(res2, "error", None):
#         raise HTTPException(status_code=502, detail=str(res2.error))
#     if not getattr(res2, "data", None):
#         raise HTTPException(status_code=404, detail="Ticket not found after update")
#     return res2.data


@router.patch(
    "/{ticket_id}",
    response_model=TicketFormattedWithAttachmentsOut,
    summary="Update ticket by Ticket ID",
)
def update_ticket_with_attachments(
    ticket_id: str,
    # TicketPatch fields via Form to support multipart
    summary: Optional[str] = Form(None),
    status: Optional[TicketStatus] = Form(None),
    priority: Optional[TicketPriority] = Form(None),
    channel: Optional[TicketChannel] = Form(None),
    client_id: Optional[int] = Form(None),
    assignee_id: Optional[int] = Form(None),
    department_id: Optional[int] = Form(None),
    category_id: Optional[int] = Form(None),
    body: Optional[str] = Form(None),
    files: Optional[List[UploadFile]] = File(None),
):
    sb = get_supabase()

    # Build patch dict from provided form fields
    patch_data = {
        "summary": summary,
        "status": status,
        "priority": priority,
        "channel": channel,
        "client_id": client_id,
        "assignee_id": assignee_id,
        "department_id": department_id,
        "category_id": category_id,
        "body": body,
    }
    data = {k: v for k, v in patch_data.items() if v is not None}

    # If there are field updates, apply them
    if data:
        res = (
            sb.table("tickets")
              .update(data)
              .eq("ticket_id", ticket_id)
              .execute()
        )
        if getattr(res, "error", None):
            raise HTTPException(status_code=502, detail=str(res.error))
        if not getattr(res, "data", None):
            raise HTTPException(status_code=404, detail="Ticket not found")

    # If new files are provided, replace existing attachments
    if files:
        ticket_pk, _ = get_ticket_pk_and_public_id(sb, ticket_id)

        # Load existing attachments to collect storage paths
        ares = (
            sb.table("ticket_attachments")
              .select("id,file_path")
              .eq("ticket_id", ticket_pk)
              .execute()
        )
        if getattr(ares, "error", None):
            raise HTTPException(status_code=502, detail=str(ares.error))

        paths = [row.get("file_path") for row in (ares.data or []) if isinstance(row, dict) and row.get("file_path")]
        # Best-effort storage removal
        try:
            if paths:
                sb.storage.from_(ATTACHMENTS_BUCKET).remove(paths)
        except Exception:
            pass

        # Delete DB rows
        dres = sb.table("ticket_attachments").delete().eq("ticket_id", ticket_pk).execute()
        if getattr(dres, "error", None):
            raise HTTPException(status_code=502, detail=str(dres.error))

    # Fetch the formatted row (exists regardless of whether we changed fields)
    t = (
        sb.table("tickets_formatted")
          .select("*")
          .eq("ticket_id", ticket_id)
          .single()
          .execute()
    )
    if getattr(t, "error", None) or not getattr(t, "data", None):
        raise HTTPException(status_code=404, detail="Ticket not found after update")
    ticket_row = t.data

    # Upload new files if provided
    uploaded = upload_attachments_for_ticket(sb, ticket_row, files)

    # Re-enrich to include final attachments
    enriched = enrich_tickets_with_attachments(sb, [ticket_row])
    return enriched[0] if enriched else {**ticket_row, "attachments": uploaded or []}


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


@router.get(
    "/staff/{staff_id}",
    response_model=TicketsListWithCountWithAttachments,
    summary="List tickets assigned to a staff user (with attachments)",
)
def list_tickets_for_staff_user(
    staff_id: int,
    sort: bool = Query(True, description="True=newest first; False=oldest first"),
    limit: int = Query(50, ge=1, le=100, description="Max rows to return"),
    user=Depends(require_user),
):
    sb = get_user_supabase(user["jwt"])
    q = (
        sb.table("tickets_detailed")
          .select("*", count="exact")
          .eq("assignee_id", staff_id)
          .order("created_at", desc=sort)
          .limit(limit)
    )
    res = q.execute()
    if getattr(res, "error", None):
        raise HTTPException(status_code=502, detail=str(res.error))
    rows = res.data or []
    enriched = enrich_tickets_with_attachments(get_supabase(), rows)
    return {
        "count": getattr(res, "count", None),
        "limit": limit,
        "data": enriched,
    }


@router.get(
    "/user/{client_id}",
    response_model=TicketsListWithCountWithAttachments,
    summary="List tickets requested by a client (with attachments)",
)
def list_tickets_for_client(
    client_id: int,
    sort: bool = Query(True, description="True=newest first; False=oldest first"),
    limit: int = Query(50, ge=1, le=100, description="Max rows to return"),
    user=Depends(require_user),
):
    sb = get_user_supabase(user["jwt"])
    q = (
        sb.table("tickets_detailed")
          .select("*", count="exact")
          .eq("client_id", client_id)
          .order("created_at", desc=sort)
          .limit(limit)
    )
    res = q.execute()
    if getattr(res, "error", None):
        raise HTTPException(status_code=502, detail=str(res.error))
    rows = res.data or []
    enriched = enrich_tickets_with_attachments(get_supabase(), rows)
    return {
        "count": getattr(res, "count", None),
        "limit": limit,
        "data": enriched,
    }
