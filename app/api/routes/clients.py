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

router = APIRouter(tags=["clients"])

@router.get("/", summary="List clients")
def list_clients(limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0)):
    sb = get_supabase()
    res = (sb.table("clients").select("*").order("id").range(offset, offset+limit-1).execute())
    return res.data or []
