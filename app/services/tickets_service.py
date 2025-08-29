from typing import Optional
from fastapi import HTTPException
from app.models.schemas import TicketCreateInput


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


def resolve_ticket_create_refs(sb, inp: TicketCreateInput) -> dict:
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
        return res_c.data["id"]

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

    # Required fields
    # if not data.get("summary"):
    #     fail_400("summary is required")

    return data


def build_ticket_insertable(data: dict) -> dict:
    allowed = {
        "summary", "status", "priority", "channel",
        "client_id", "assignee_id", "department_id", "category_id", "subject",
        "body", "message_id", "thread_id",
    }
    insertable = {k: v for k, v in data.items() if k in allowed}
    # Map body -> email_body if provided
    # if "body" in data and "email_body" not in insertable:
    #     insertable["email_body"] = data["body"]
    
    return insertable
