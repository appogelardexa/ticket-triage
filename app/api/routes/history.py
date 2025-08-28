from typing import List
from fastapi import APIRouter, HTTPException, Query

from app.core.config import get_supabase
from app.models.schemas import StatusHistoryRow, PriorityHistoryRow


router = APIRouter(tags=["ticket-history"])

# response_model=List[StatusHistoryRow],
@router.get("/status/{ticket_id}", response_model=List[StatusHistoryRow], summary="Status history for a ticket")
def status_history(ticket_id: str, sort: bool = Query(True, description="True=oldest first, False=newest first")):
    sb = get_supabase()
    res = (
        sb.table("ticket_status_history_vw")
          .select("*")
          .eq("ticket_id", ticket_id)
          .order("changed_at", desc=sort)
          .execute()
    )
    if getattr(res, "error", None):
        raise HTTPException(status_code=502, detail=str(res.error))
    return res.data or []


@router.get("/priority/{ticket_id}", response_model=List[PriorityHistoryRow], summary="Priority history for a ticket")
def priority_history(ticket_id: str, sort: bool = Query(True, description="True=oldest first, False=newest first")):
    sb = get_supabase()
    res = (
        sb.table("ticket_priority_history_vw")
          .select("*")
          .eq("ticket_id", ticket_id)
          .order("changed_at", desc=sort)
          .execute()
    )
    if getattr(res, "error", None):
        raise HTTPException(status_code=502, detail=str(res.error))
    return res.data or []

