from datetime import datetime, timedelta, timezone
from collections import Counter
from typing import Dict, List, Optional

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


# Normalization helpers used by multiple endpoints
def _norm_status(s: object) -> str | None:
    if s is None:
        return None
    mapping = {
        "new": "New",
        "in progress": "In Progress",
        "on hold": "On Hold",
        "closed": "Closed",
    }
    key = str(s)
    return mapping.get(key, mapping.get(key.lower(), key))


def _norm_priority(p: object) -> str | None:
    if p is None:
        return None
    mapping = {"low": "Low", "medium": "Medium", "high": "High", "urgent": "Urgent"}
    key = str(p)
    return mapping.get(key, mapping.get(key.lower(), key))


def _parse_dt(value: object) -> Optional[datetime]:
    try:
        if value is None:
            return None
        s = str(value)
        # Handle trailing 'Z' if present
        if s.endswith("Z"):
            s = s.replace("Z", "+00:00")
        return datetime.fromisoformat(s)
    except Exception:
        return None


def _fmt_duration(seconds: float) -> str:
    try:
        if seconds is None or seconds < 0:
            return "-"
        secs = int(seconds)
        days, rem = divmod(secs, 86400)
        hours, rem = divmod(rem, 3600)
        minutes, sec = divmod(rem, 60)
        parts: List[str] = []
        if days:
            parts.append(f"{days}d")
        if hours:
            parts.append(f"{hours}h")
        if minutes:
            parts.append(f"{minutes}m")
        if sec or not parts:
            parts.append(f"{sec}s")
        return " ".join(parts)
    except Exception:
        return "-"


@router.get("/dashboard", summary="Get dashboard KPIs and stats")
def get_dashboard():
    sb = get_supabase()

    now = datetime.now(timezone.utc)
    since_7d = now - timedelta(days=7)

    # Updated to match current TicketStatus values
    open_statuses = ["New", "In Progress", "On Hold"]

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

    # Normalize values to expected casing and seed missing buckets
    dist_status_raw = Counter([_norm_status(r.get("status")) for r in rows if r.get("status") is not None])
    dist_priority_raw = Counter([_norm_priority(r.get("priority")) for r in rows if r.get("priority") is not None])

    # Seed all known buckets so missing ones appear with 0
    status_buckets = ["New", "In Progress", "On Hold", "Closed"]
    priority_buckets = ["Low", "Medium", "High", "Urgent"]

    dist_status = {b: int(dist_status_raw.get(b, 0)) for b in status_buckets}
    dist_priority = {b: int(dist_priority_raw.get(b, 0)) for b in priority_buckets}
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

    by_status_raw = Counter([_norm_status(r.get("status")) for r in rows if r.get("status") is not None])
    by_priority_raw = Counter([_norm_priority(r.get("priority")) for r in rows if r.get("priority") is not None])

    status_buckets = ["New", "In Progress", "On Hold", "Closed"]
    priority_buckets = ["Low", "Medium", "High", "Urgent"]

    by_status = {b: int(by_status_raw.get(b, 0)) for b in status_buckets}
    by_priority = {b: int(by_priority_raw.get(b, 0)) for b in priority_buckets}
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

    # Updated to match current TicketStatus values
    open_statuses = ["New", "In Progress", "On Hold"]

    assigned_total = _count_exact(sb, "tickets", {"assignee_id": staff_id})
    # Per-status open breakdown
    assigned_open_by_status = {
        "New": _count_exact(sb, "tickets", {"assignee_id": staff_id, "status": "New"}),
        "In Progress": _count_exact(sb, "tickets", {"assignee_id": staff_id, "status": "In Progress"}),
        "On Hold": _count_exact(sb, "tickets", {"assignee_id": staff_id, "status": "On Hold"}),
    }
    assigned_open = sum(assigned_open_by_status.values())
    assigned_closed = _count_exact(sb, "tickets", {"assignee_id": staff_id, "status": ["Closed"]})
    comments_last_30d = _count_since(sb, "ticket_comments", "created_at", since_30d, {"internal_staff_id": staff_id})

    return {
        "assigned_total": assigned_total,
        "assigned_open": assigned_open,
        "assigned_open_by_status": assigned_open_by_status,
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
    open_statuses = {"New", "In Progress", "On Hold"}
    backlog_by_dept: Dict[str, int] = {}
    for r in rows:
        if r.get("status") in open_statuses:
            dept = r.get("department_name") or "Unassigned"
            backlog_by_dept[dept] = backlog_by_dept.get(dept, 0) + 1

    return {
        "totals": totals,
        "backlog_by_department": backlog_by_dept,
    }


@router.get("/response-times", summary="Average response/close/handling times (overall and by staff)")
def get_response_times(
    since_days: Optional[int] = None,
    staff_id: Optional[int] = None,
):
    """
    Computes average durations using ticket_status_history_vw:
    - to_in_progress: New -> In Progress
    - to_close: New -> Closed
    - handling: In Progress -> Closed

    Optional filter: since_days (lookback window based on changed_at).
    """
    sb = get_supabase()

    q = sb.table("ticket_status_history_vw").select("ticket_id,to_status,changed_at")
    if since_days is not None:
        since = datetime.now(timezone.utc) - timedelta(days=int(since_days))
        q = q.gte("changed_at", since.isoformat())
    res = q.order("ticket_id").order("changed_at").limit(100000).execute()
    if getattr(res, "error", None):
        raise HTTPException(status_code=502, detail=str(res.error))

    # Aggregate first occurrences
    first_new: Dict[str, datetime] = {}
    first_in_prog: Dict[str, datetime] = {}
    first_closed: Dict[str, datetime] = {}

    for r in res.data or []:
        tid = r.get("ticket_id")
        to_status = _norm_status(r.get("to_status"))
        at = _parse_dt(r.get("changed_at"))
        if not tid or not to_status or not at:
            continue
        if to_status == "New" and tid not in first_new:
            first_new[tid] = at
        elif to_status == "In Progress" and tid not in first_in_prog:
            first_in_prog[tid] = at
        elif to_status == "Closed" and tid not in first_closed:
            first_closed[tid] = at

    # Compute durations (overall)
    ttip_values: List[float] = []  # New -> In Progress
    ttr_values: List[float] = []   # New -> Closed
    handling_values: List[float] = []  # In Progress -> Closed

    for tid, created_at in first_new.items():
        ip_at = first_in_prog.get(tid)
        cl_at = first_closed.get(tid)
        if ip_at and ip_at >= created_at:
            ttip_values.append((ip_at - created_at).total_seconds())
        if cl_at and cl_at >= created_at:
            ttr_values.append((cl_at - created_at).total_seconds())
        if ip_at and cl_at and cl_at >= ip_at:
            handling_values.append((cl_at - ip_at).total_seconds())

    def _avg(vals: List[float]) -> Optional[float]:
        return (sum(vals) / len(vals)) if vals else None

    avg_ttip = _avg(ttip_values)
    avg_ttr = _avg(ttr_values)
    avg_handling = _avg(handling_values)

    overall = {
        "counts": {
            "tickets_with_new": len(first_new),
            "tickets_with_in_progress": len(first_in_prog),
            "tickets_with_closed": len(first_closed),
        },
        "averages_seconds": {
            "to_in_progress": avg_ttip,
            "to_close": avg_ttr,
            "handling": avg_handling,
        },
        "averages_human": {
            "to_in_progress": _fmt_duration(avg_ttip or -1),
            "to_close": _fmt_duration(avg_ttr or -1),
            "handling": _fmt_duration(avg_handling or -1),
        },
    }

    # Build per-staff breakdown (optionally filtered by staff_id)
    by_staff: List[Dict[str, object]] = []
    tickets_set: set[str] = set(first_new.keys()) | set(first_in_prog.keys()) | set(first_closed.keys())
    if tickets_set:
        ticket_ids = list(tickets_set)
        assignee_map: Dict[str, Dict[str, Optional[object]]] = {}
        chunk_size = 500
        for i in range(0, len(ticket_ids), chunk_size):
            chunk = ticket_ids[i : i + chunk_size]
            tres = (
                sb.table("tickets_detailed")
                  .select("ticket_id,assignee_id,assignee_name")
                  .in_("ticket_id", chunk)
                  .execute()
            )
            if getattr(tres, "error", None):
                raise HTTPException(status_code=502, detail=str(tres.error))
            for row in tres.data or []:
                tid = row.get("ticket_id")
                if tid is None:
                    continue
                assignee_map[str(tid)] = {
                    "assignee_id": row.get("assignee_id"),
                    "assignee_name": row.get("assignee_name"),
                }

        groups: Dict[Optional[int], Dict[str, object]] = {}
        for tid in ticket_ids:
            meta = assignee_map.get(tid, {})
            sid = meta.get("assignee_id")  # Optional[int]
            sname = meta.get("assignee_name")

            # If filtering by staff_id, skip others
            if staff_id is not None and sid != staff_id:
                continue

            if sid not in groups:
                groups[sid] = {
                    "staff_id": sid,
                    "staff_name": sname or ("Unassigned" if sid is None else None),
                    "tickets": 0,
                    "to_in_progress_values": [],
                    "to_close_values": [],
                    "handling_values": [],
                }

            created_at = first_new.get(tid)
            ip_at = first_in_prog.get(tid)
            cl_at = first_closed.get(tid)

            if created_at:
                groups[sid]["tickets"] = int(groups[sid]["tickets"]) + 1
            if created_at and ip_at and ip_at >= created_at:
                groups[sid]["to_in_progress_values"].append((ip_at - created_at).total_seconds())
            if created_at and cl_at and cl_at >= created_at:
                groups[sid]["to_close_values"].append((cl_at - created_at).total_seconds())
            if ip_at and cl_at and cl_at >= ip_at:
                groups[sid]["handling_values"].append((cl_at - ip_at).total_seconds())

        def _avg(vals: List[float]) -> Optional[float]:
            return (sum(vals) / len(vals)) if vals else None

        for sid, g in groups.items():
            avg_ttip_s = _avg(g["to_in_progress_values"])  # type: ignore[index]
            avg_ttr_s = _avg(g["to_close_values"])  # type: ignore[index]
            avg_handling_s = _avg(g["handling_values"])  # type: ignore[index]

            by_staff.append({
                "staff_id": g["staff_id"],
                "staff_name": g["staff_name"],
                "tickets_considered": g["tickets"],
                "averages_seconds": {
                    "to_in_progress": avg_ttip_s,
                    "to_close": avg_ttr_s,
                    "handling": avg_handling_s,
                },
                "averages_human": {
                    "to_in_progress": _fmt_duration(avg_ttip_s or -1),
                    "to_close": _fmt_duration(avg_ttr_s or -1),
                    "handling": _fmt_duration(avg_handling_s or -1),
                },
                "samples": {
                    "to_in_progress": len(g["to_in_progress_values"]),
                    "to_close": len(g["to_close_values"]),
                    "handling": len(g["handling_values"]),
                },
            })

        by_staff.sort(key=lambda r: (str(r.get("staff_name") or ""), str(r.get("staff_id") or "")))

    return {
        "since_days": since_days,
        "overall": overall,
        "by_staff": by_staff,
    }

