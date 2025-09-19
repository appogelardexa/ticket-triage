from typing import Optional
import os
import mimetypes
import httpx
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File

from app.api.deps import require_user
from app.core.config import get_supabase, get_settings
from app.models.schemas import ClientOut, ClientPatch


router = APIRouter(prefix="/api/me", tags=["me"])


def _resolve_self_client(sb, user: dict) -> dict:
    """Find the client row for the current user.

    Prefers the client_id present in user context; otherwise looks up by
    clients.user_id or clients.email.
    Returns the client row dict or raises 404.
    """
    client_id = (user or {}).get("client_id")
    if client_id:
        res = sb.table("clients").select("*").eq("id", client_id).single().execute()
        if not getattr(res, "error", None) and getattr(res, "data", None):
            return res.data

    # Fallback: lookup by user_id/email
    user_id = (user or {}).get("user_id")
    email = (user or {}).get("email")
    q = sb.table("clients").select("*").limit(1)
    # If email can be null, still safe due to OR syntax
    if user_id and email:
        q = q.or_(f"user_id.eq.{user_id},email.eq.{email}")
    elif user_id:
        q = q.eq("user_id", user_id)
    elif email:
        q = q.eq("email", email)
    res = q.execute()
    rows = res.data or []
    if isinstance(rows, list) and rows:
        return rows[0]
    raise HTTPException(status_code=404, detail="Client not found for current user")


@router.get("/client", response_model=ClientOut, summary="Get my client profile")
def get_my_client(user=Depends(require_user)):
    sb = get_supabase()
    row = _resolve_self_client(sb, user)
    return row


@router.put("", response_model=ClientOut, summary="Update my client profile")
def update_my_client(patch: ClientPatch, user=Depends(require_user)):
    sb = get_supabase()
    current = _resolve_self_client(sb, user)

    data = patch.model_dump(exclude_none=True)
    if not data:
        raise HTTPException(status_code=400, detail="No fields to update")

    res = sb.table("clients").update(data).eq("id", current.get("id")).execute()
    if getattr(res, "error", None):
        raise HTTPException(status_code=502, detail=str(res.error))

    # Return fresh row
    got = sb.table("clients").select("*").eq("id", current.get("id")).single().execute()
    if getattr(got, "error", None) or not getattr(got, "data", None):
        raise HTTPException(status_code=404, detail="Client not found after update")
    return got.data


@router.put("/password", status_code=204, summary="Change my password")
def change_my_password(password: str, user=Depends(require_user)):
    new_password =  password # (body or {}).get("password") 
    if not new_password or not isinstance(new_password, str) or len(new_password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters")

    s = get_settings()
    if not s.SUPABASE_URL or not s.SUPABASE_SERVICE_ROLE_KEY:
        raise HTTPException(status_code=500, detail="Server auth misconfigured")

    uid = (user or {}).get("user_id")
    if not uid:
        raise HTTPException(status_code=400, detail="Missing authenticated user id")

    url = f"{s.SUPABASE_URL}/auth/v1/admin/users/{uid}"
    headers = {
        "Authorization": f"Bearer {s.SUPABASE_SERVICE_ROLE_KEY}",
        "apikey": s.SUPABASE_SERVICE_ROLE_KEY,
        "Content-Type": "application/json",
    }
    try:
        resp = httpx.put(url, json={"password": new_password}, headers=headers, timeout=15)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Password update failed: {exc}")

    if resp.status_code >= 400:
        try:
            detail = resp.json()
        except Exception:
            detail = resp.text
        raise HTTPException(status_code=502, detail=f"Password update failed: {detail}")
    return {}


@router.put("/client/image", response_model=ClientOut, summary="Update my profile image")
def update_my_client_image(profile_image: UploadFile = File(...), user=Depends(require_user)):
    sb = get_supabase()
    s = get_settings()

    current = _resolve_self_client(sb, user)
    client_id = current.get("id")
    if not client_id:
        raise HTTPException(status_code=404, detail="Client not found for current user")

    # Validate server config for direct Storage upload
    if not s.SUPABASE_URL or not s.SUPABASE_SERVICE_ROLE_KEY:
        raise HTTPException(status_code=500, detail="Storage upload misconfigured on server")

    # Bucket can be configured; default to 'avatars'
    bucket = os.getenv("SUPABASE_AVATARS_BUCKET") or "avatars"

    # Build object path
    try:
        orig_name = profile_image.filename or "upload"
        _, ext = os.path.splitext(orig_name)
        if not ext and getattr(profile_image, "content_type", None):
            guess = mimetypes.guess_extension(profile_image.content_type)
            ext = guess or ""
        name_no_spaces = str(current.get("name") or "client").replace(" ", "")
        unique_name = f"profile-{name_no_spaces}{ext}"
        object_path = f"clients/{client_id}/{unique_name}"

        try:
            profile_image.file.seek(0)
        except Exception:
            pass
        content = profile_image.file.read()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid image upload: {exc}")

    # Upload via service-role
    url = f"{s.SUPABASE_URL}/storage/v1/object/{bucket}/{object_path}"
    headers = {
        "Authorization": f"Bearer {s.SUPABASE_SERVICE_ROLE_KEY}",
        "apikey": s.SUPABASE_SERVICE_ROLE_KEY,
        "x-upsert": "true",
        "content-type": getattr(profile_image, "content_type", None) or "application/octet-stream",
    }
    try:
        resp = httpx.put(url, content=content, headers=headers, timeout=30)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Failed to upload profile image: {e}")
    if resp.status_code >= 400:
        try:
            err = resp.json()
        except Exception:
            err = resp.text
        raise HTTPException(status_code=502, detail=f"Failed to upload profile image: {err}")

    public_url = f"{s.SUPABASE_URL}/storage/v1/object/public/{bucket}/{object_path}"

    upd = (
        sb.table("clients")
          .update({"profile_image_link": public_url})
          .eq("id", client_id)
          .execute()
    )
    if getattr(upd, "error", None):
        raise HTTPException(status_code=502, detail=str(upd.error))

    got = sb.table("clients").select("*").eq("id", client_id).single().execute()
    if getattr(got, "error", None) or not getattr(got, "data", None):
        raise HTTPException(status_code=404, detail="Client not found after image update")
    return got.data
