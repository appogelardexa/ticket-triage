from typing import Any, Dict
from fastapi import APIRouter, Depends, HTTPException, Body

from app.api.deps import require_user
from app.core.config import get_supabase
from app.models.schemas import TicketPriority


router = APIRouter(prefix="/api/settings", tags=["settings"]) 


@router.get("/priorities", summary="Get priority levels")
def get_priorities(user=Depends(require_user)):
    return [p.value for p in TicketPriority]


@router.get("/notifications/{user_id}", summary="Get user notification preferences")
def get_notifications(user_id: str, user=Depends(require_user)):
    """
    Fetch preferences by auth user id. Convenience values supported:
    - "me": current caller
    - numeric client id: will resolve to that client's linked auth user id
    """
    sb = get_supabase()

    # Resolve effective auth user id
    effective_uid = None
    if user_id.lower() == "me":
        effective_uid = (user or {}).get("user_id")
    else:
        # If looks like integer, treat as client id and resolve to user_id
        try:
            int(user_id)
            # numeric -> client id
            c = sb.table("clients").select("user_id").eq("id", int(user_id)).single().execute()
            if not getattr(c, "error", None) and getattr(c, "data", None):
                effective_uid = c.data.get("user_id") if isinstance(c.data, dict) else None
        except Exception:
            effective_uid = user_id  # assume it's an auth user id
    effective_uid = effective_uid or user_id

    # ACL: user can read their own; admins can read any
    if (user or {}).get("role") != "admin" and (user or {}).get("user_id") != effective_uid:
        raise HTTPException(status_code=403, detail="Not allowed")

    try:
        res = (
            sb.table("clients")
              .select("notification_preference")
              .eq("user_id", effective_uid)
              .single()
              .execute()
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Failed to load preferences: {exc}")

    if getattr(res, "error", None):
        # If no row, return empty preferences rather than 404 to simplify clients
        return {"user_id": effective_uid, "preferences": {}}

    row = getattr(res, "data", None) or {}
    prefs = row.get("notification_preference") if isinstance(row, dict) else None
    return {"preference": prefs or {}}


@router.put("/notifications/{user_id}", summary="Update user notification preference (string)")
def put_notifications(user_id: str, preference: str = Body(..., embed=True), user=Depends(require_user)):
    sb = get_supabase()

    # Resolve effective auth user id (supports "me" and numeric client id)
    effective_uid = None
    if user_id.lower() == "me":
        effective_uid = (user or {}).get("user_id")
    else:
        try:
            int(user_id)
            c = sb.table("clients").select("user_id").eq("id", int(user_id)).single().execute()
            if not getattr(c, "error", None) and getattr(c, "data", None):
                effective_uid = c.data.get("user_id") if isinstance(c.data, dict) else None
        except Exception:
            effective_uid = user_id
    effective_uid = effective_uid or user_id

    # ACL: user can update their own; admins can update any
    if (user or {}).get("role") != "admin" and (user or {}).get("user_id") != effective_uid:
        raise HTTPException(status_code=403, detail="Not allowed")

    try:
        upd = (
            sb.table("clients")
              .update({"notification_preference": preference})
              .eq("user_id", effective_uid)
              .execute()
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Failed to save preferences: {exc}")

    if getattr(upd, "error", None):
        msg = str(upd.error)
        if "notification_preference" in msg.lower():
            raise HTTPException(status_code=501, detail="Clients table missing notification_preference column")
        raise HTTPException(status_code=502, detail=msg)

    sel = (
        sb.table("clients")
          .select("notification_preference")
          .eq("user_id", effective_uid)
          .single()
          .execute()
    )
    if getattr(sel, "error", None) or not getattr(sel, "data", None):
        raise HTTPException(status_code=404, detail="Preferences not found after update")
    return {"preference": (sel.data or {}).get("notification_preference")}
