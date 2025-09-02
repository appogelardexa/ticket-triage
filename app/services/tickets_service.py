from typing import Optional
from fastapi import HTTPException
from app.models.schemas import TicketCreateInputV3


def fail_400(msg: str):
    raise HTTPException(status_code=400, detail=msg)


def fetch_single_id(sb, table: str, where: dict):
    q = sb.table(table).select("id").limit(2)
    for k, v in where.items():
        q = q.eq(k, v)
    res = q.execute()
    if getattr(res, "error", None):
        raise HTTPException(status_code=502, detail=str(res.error))
    rows = res.data or []
    if len(rows) == 0:
        return None
    if len(rows) > 1:
        fail_400(f"Multiple matches in {table} for {where}")
    return rows[0]["id"]


def resolve_ticket_create_refs(sb, inp: TicketCreateInputV3,) -> dict:
    data = inp.model_dump(exclude_none=True)

    # Priority/status/channel are enums in DB (not FKs); leave as-is if present.

    # Helper to create a client on the fly
    def _create_client(name: str, email: Optional[str] = None) -> int:
        payload = {"name": name}
        if email:
            payload["email"] = email
        res_c = sb.table("clients").insert(payload).execute()
        if getattr(res_c, "error", None):
            raise HTTPException(status_code=502, detail=str(res_c.error))
        if not getattr(res_c, "data", None):
            raise HTTPException(status_code=502, detail="Failed to create client")
        # Supabase v2 insert returns a list of rows; normalize to a dict
        row = res_c.data[0] if isinstance(res_c.data, list) else res_c.data
        if not isinstance(row, dict) or "id" not in row:
            raise HTTPException(status_code=502, detail="Create client: missing id in response")
        return row["id"]

    # Client resolution order
    if "client_id" not in data:
        if data.get("client_email"):
            cid = fetch_single_id(sb, "clients", {"email": data["client_email"]})
            if cid is None:
                # Create client with provided email and optional name
                fallback_name = data.get("client_name") or data["client_email"].split("@")[0]
                cid = _create_client(name=fallback_name, email=data["client_email"])
            data["client_id"] = cid
        elif data.get("client_name"):
            # Try unique match by name; if none -> create; if multiple -> 400
            cid = fetch_single_id(sb, "clients", {"name": data["client_name"]})
            if cid is None:
                cid = _create_client(name=data["client_name"])  # email absent
            data["client_id"] = cid

    # Department: prefer id; else resolve by name (unique)
    if "department_id" not in data and data.get("department_name"):
        did = fetch_single_id(sb, "departments", {"name": data["department_name"]})
        if did is None:
            fail_400("department_name not found")
        data["department_id"] = did

    # Assignee: prefer id; else resolve by email; else by name (exact)
    if "assignee_id" not in data:
        if data.get("assignee_email"):
            aid = fetch_single_id(sb, "internal_staff", {"email": data["assignee_email"]})
            if aid is None:
                fail_400("assignee_email not found")
            data["assignee_id"] = aid
        elif data.get("assignee_name"):
            aid = fetch_single_id(sb, "internal_staff", {"name": data["assignee_name"]})
            if aid is None:
                fail_400("assignee_name not found")
            data["assignee_id"] = aid

    # Category: prefer id; else resolve by (department_id, name)
    if "category_id" not in data and data.get("category_name"):
        dept_id = data.get("department_id")
        if not dept_id:
            fail_400("category_name requires department_id or department_name")
        cid = fetch_single_id(sb, "categories", {"department_id": dept_id, "name": data["category_name"]})
        if cid is None:
            fail_400("category_name not found under the given department")
        data["category_id"] = cid

    # Drop helper fields not in tickets table
    for k in ["client_email", "client_name", "assignee_email", "assignee_name", "department_name", "category_name"]:
        data.pop(k, None)


    return data


def build_ticket_insertable(data: dict) -> dict:
    allowed = {
        "summary", "status", "priority", "channel",
        "client_id", "assignee_id", "department_id", "category_id", "subject",
        "body", "message_id", "thread_id",
    }
    insertable = {k: v for k, v in data.items() if k in allowed}
    
    return insertable


from datetime import datetime, timezone, timedelta

def _parse_ymd_utc(value: str) -> datetime:
    """
    Parse a date string in flexible YYYY-M-D format (e.g., "2025-9-1" or "2025-09-01")
    and return a timezone-aware UTC datetime at 00:00:00.
    """
    if not isinstance(value, str):
        raise ValueError("Date must be a string like '2025-9-1'.")
    parts = value.strip().split("-")
    if len(parts) != 3:
        raise ValueError("Invalid date format. Use 'YYYY-M-D', e.g. '2025-9-1'.")
    try:
        y, m, d = (int(parts[0]), int(parts[1]), int(parts[2]))
        return datetime(y, m, d, tzinfo=timezone.utc)
    except Exception as exc:
        raise ValueError(f"Invalid date components for '{value}': {exc}") from exc


def build_utc_range(
    on: Optional[str] = None,
    start_at: Optional[str] = None,
    end_at: Optional[str] = None,   
    ) -> tuple[str, str]:
    """
    Build an ISO8601 UTC range [start, end) with 'Z'.
    Parameters accept dates like '2025-9-1' (YYYY-M-D):
    - on: single specific date; returns that day's 00:00Z to next day 00:00Z
    - start_at, end_at: inclusive calendar dates; returns
      [start_at 00:00Z, (end_at + 1 day) 00:00Z)
    Exactly one of the following must be provided:
      - 'on'
      - both 'start_at' and 'end_at'
    """
    if on:
        start_dt = _parse_ymd_utc(on)
        end_dt = start_dt + timedelta(days=1)
    else:
        if not (start_at and end_at):
            raise ValueError("Provide either 'on' or both 'start_at' and 'end_at'.")
        
        start_dt = _parse_ymd_utc(start_at)
        end_dt = _parse_ymd_utc(end_at) + timedelta(days=1)

    start_iso = start_dt.isoformat().replace("+00:00", "Z")
    end_iso = end_dt.isoformat().replace("+00:00", "Z")

    return start_iso, end_iso