from datetime import datetime, timedelta, timezone
from collections import Counter
from typing import Dict, List

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import require_admin
from app.core.config import get_supabase


router = APIRouter(prefix="/api/analytics", tags=["analytics"], dependencies=[Depends(require_admin)])


def _count_exact(sb, table: str, filters: Dict[str, object] | None = None) -> int:
    q = sb.table(table).select("id", count="exact").limit(1)
    if filters:
        for k, v in filters.items():
            if isinstance(v, list):
                q = q.in_(k, v)
            else:
                q = q.eq(k, v)
    res = q.execute()
    if getattr(res, "error", None):
        raise HTTPException(status_code=502, detail=str(res.error))
    return int(getattr(res, "count", 0) or 0)


def _count_since(sb, table: str, ts_col: str, since: datetime, filters: Dict[str, object] | None = None) -> int:
    q = sb.table(table).select("id", count="exact").limit(1).gte(ts_col, since.isoformat())
    if filters:
        for k, v in filters.items():
            if isinstance(v, list):
                q = q.in_(k, v)
            else:
                q = q.eq(k, v)
    res = q.execute()
    if getattr(res, "error", None):
        raise HTTPException(status_code=502, detail=str(res.error))
    return int(getattr(res, "count", 0) or 0)


@router.get("/dashboard", summary="Get dashboard KPIs and stats")
def get_dashboard():
    sb = get_supabase()

    now = datetime.now(timezone.utc)
    since_7d = now - timedelta(days=7)

    open_statuses = ["new", "open", "in_progress", "on_hold"]

    total_tickets = _count_exact(sb, "tickets")
    open_tickets = _count_exact(sb, "tickets", {"status": open_statuses})
    tickets_last_7d = _count_since(sb, "tickets", "created_at", since_7d)
    comments_last_7d = _count_since(sb, "ticket_comments", "created_at", since_7d)

    # Distributions for charts (status, priority, category)
    dist_status: Dict[str, int] = {}
    dist_priority: Dict[str, int] = {}
    dist_category: Dict[str, int] = {}

    # Pull limited fields and tally in app (portable, avoids server-side group dependency)
    t_res = (
        sb.table("tickets_detailed")
        .select("status,priority,category_name")
        .limit(5000)  # safeguard; adjust as needed
        .execute()
    )
    if getattr(t_res, "error", None):
        raise HTTPException(status_code=502, detail=str(t_res.error))
    rows = t_res.data or []
    dist_status = dict(Counter([r.get("status") for r in rows if r.get("status") is not None]))
    dist_priority = dict(Counter([r.get("priority") for r in rows if r.get("priority") is not None]))
    dist_category = dict(Counter([r.get("category_name") or "Uncategorized" for r in rows]))

    return {
        "kpis": {
            "total_tickets": total_tickets,
            "open_tickets": open_tickets,
            "tickets_last_7d": tickets_last_7d,
            "comments_last_7d": comments_last_7d,
        },
        "distributions": {
            "by_status": dist_status,
            "by_priority": dist_priority,
            "by_category": dist_category,
        },
    }


@router.get("/charts", summary="Get aggregated chart data")
def get_charts():
    sb = get_supabase()
    res = (
        sb.table("tickets_detailed")
        .select("status,priority,category_name")
        .limit(10000)
        .execute()
    )
    if getattr(res, "error", None):
        raise HTTPException(status_code=502, detail=str(res.error))
    rows = res.data or []

    def as_series(counter: Dict[str, int]) -> List[Dict[str, object]]:
        return [{"label": k, "value": int(v)} for k, v in counter.items()]

    by_status = dict(Counter([r.get("status") for r in rows if r.get("status") is not None]))
    by_priority = dict(Counter([r.get("priority") for r in rows if r.get("priority") is not None]))
    by_category = dict(Counter([r.get("category_name") or "Uncategorized" for r in rows]))

    return {
        "status": as_series(by_status),
        "priority": as_series(by_priority),
        "category": as_series(by_category),
    }


@router.get("/user-stats/{staff_id}", summary="Get user-specific statistics")
def get_user_stats(staff_id: int):
    sb = get_supabase()
    now = datetime.now(timezone.utc)
    since_30d = now - timedelta(days=30)

    open_statuses = ["new", "open", "in_progress", "on_hold"]

    assigned_total = _count_exact(sb, "tickets", {"assignee_id": staff_id})
    assigned_open = _count_exact(sb, "tickets", {"assignee_id": staff_id, "status": open_statuses})
    assigned_closed = _count_exact(sb, "tickets", {"assignee_id": staff_id, "status": ["resolved", "closed"]})
    comments_last_30d = _count_since(sb, "ticket_comments", "created_at", since_30d, {"internal_staff_id": staff_id})

    return {
        "assigned_total": assigned_total,
        "assigned_open": assigned_open,
        "assigned_closed": assigned_closed,
        "comments_last_30d": comments_last_30d,
    }


@router.get("/admin-stats", summary="Get admin-wide statistics")
def get_admin_stats():
    sb = get_supabase()

    totals = {
        "tickets": _count_exact(sb, "tickets"),
        "clients": _count_exact(sb, "clients"),
        "staff": _count_exact(sb, "internal_staff"),
        "categories": _count_exact(sb, "categories"),
        "comments": _count_exact(sb, "ticket_comments"),
    }

    # Backlog by department (simple tally in app)
    res = sb.table("tickets_detailed").select("department_name,status").limit(10000).execute()
    if getattr(res, "error", None):
        raise HTTPException(status_code=502, detail=str(res.error))
    rows = res.data or []
    open_statuses = {"new", "open", "in_progress", "on_hold"}
    backlog_by_dept: Dict[str, int] = {}
    for r in rows:
        if r.get("status") in open_statuses:
            dept = r.get("department_name") or "Unassigned"
            backlog_by_dept[dept] = backlog_by_dept.get(dept, 0) + 1

    return {
        "totals": totals,
        "backlog_by_department": backlog_by_dept,
    }

