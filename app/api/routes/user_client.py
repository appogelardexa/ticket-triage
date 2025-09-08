from typing import Optional
import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, Form

from app.api.deps import require_admin
from app.core.config import get_settings, get_supabase
from app.models.schemas import ClientOut, ClientCreate, ClientPatch

# Reuse business logic from clients.py by calling its handlers
from app.api.routes.clients import (
    list_clients as _list_clients,
    get_client_by_id as _get_client_by_id,
    create_client_with_image as _create_client,
    update_client as _update_client,
    delete_client as _delete_client,
)


router = APIRouter(prefix="/api/users", tags=["users"], dependencies=[Depends(require_admin)])


@router.get("/", summary="List users (clients)")
def list_users(limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0)):
    return _list_clients(limit=limit, offset=offset)


@router.get("/{user_id}", response_model=ClientOut, summary="Get user (client) by id")
def get_user(user_id: int):
    return _get_client_by_id(user_id)


@router.post("/", response_model=ClientOut, status_code=201, summary="Create user (client)")
def create_user(
    name: str = Form(...),
    email: Optional[str] = Form(None),
    domain: Optional[str] = Form(None),
    company_id: Optional[int] = Form(None),
    profile_image: Optional[UploadFile] = File(None),
):
    return _create_client(
        name=name,
        email=email,
        domain=domain,
        company_id=company_id,
        profile_image=profile_image,
    )


@router.put("/{user_id}", response_model=ClientOut, summary="Update user (client)")
def update_user(user_id: int, patch: ClientPatch):
    return _update_client(user_id, patch)


@router.delete("/{user_id}", status_code=204, summary="Deactivate user (client)")
def deactivate_user(user_id: int):
    return _delete_client(user_id)


@router.put("/{user_id}/password", status_code=204, summary="Change user password (auth user)")
def change_user_password(user_id: int, body: dict):
    """Change the Supabase auth password for the auth user linked to this client.

    Requires `clients.user_id` to be present; returns 400 if not linked.
    """
    new_password = (body or {}).get("password")
    if not new_password or not isinstance(new_password, str) or len(new_password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters")

    sb = get_supabase()
    res = sb.table("clients").select("user_id").eq("id", user_id).single().execute()
    if getattr(res, "error", None) or not getattr(res, "data", None):
        raise HTTPException(status_code=404, detail="User not found")
    linked_uid = (res.data or {}).get("user_id") if isinstance(res.data, dict) else None
    if not linked_uid:
        raise HTTPException(status_code=400, detail="Client is not linked to an auth user")

    s = get_settings()
    if not s.SUPABASE_URL or not s.SUPABASE_SERVICE_ROLE_KEY:
        raise HTTPException(status_code=500, detail="Server auth misconfigured")

    url = f"{s.SUPABASE_URL}/auth/v1/admin/users/{linked_uid}"
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


@router.post("/provision", response_model=ClientOut, status_code=201, summary="Provision auth user + client (invite or password)")
def provision_user(
    # Client fields (same as create_user)
    name: str = Form(...),
    email: Optional[str] = Form(None),
    domain: Optional[str] = Form(None),
    company_id: Optional[int] = Form(None),
    profile_image: Optional[UploadFile] = File(None),
    # Auth provisioning options
    send_invite: bool = Form(True),
    password: Optional[str] = Form(None),
    email_confirm: bool = Form(True),
    redirect_to: Optional[str] = Form(None),
):
    """Creates an auth user (invite or password), then creates the client and links it via user_id.

    - If send_invite=True, sends an invite email; password is ignored.
    - If send_invite=False, requires password and optionally sets email_confirm.
    """
    s = get_settings()
    if not s.SUPABASE_URL or not s.SUPABASE_SERVICE_ROLE_KEY:
        raise HTTPException(status_code=500, detail="Server auth misconfigured")
    if not email:
        raise HTTPException(status_code=400, detail="email is required to provision a user")

    base_headers = {
        "Authorization": f"Bearer {s.SUPABASE_SERVICE_ROLE_KEY}",
        "apikey": s.SUPABASE_SERVICE_ROLE_KEY,
        "Content-Type": "application/json",
    }

    auth_user_id: Optional[str] = None

    # 1) Create or invite auth user
    try:
        if send_invite:
            # Prefer generate_link with type=invite (more widely supported than admin/invite)
            url = f"{s.SUPABASE_URL}/auth/v1/admin/generate_link"
            payload = {"type": "invite", "email": email}
            if redirect_to:
                payload["redirect_to"] = redirect_to
            resp = httpx.post(url, json=payload, headers=base_headers, timeout=20)
            if resp.status_code >= 400:
                # Try to resolve by email even if link generation failed
                try:
                    detail = resp.json()
                except Exception:
                    detail = resp.text
                lookup = httpx.get(
                    f"{s.SUPABASE_URL}/auth/v1/admin/users",
                    params={"email": email},
                    headers=base_headers,
                    timeout=15,
                )
                if lookup.status_code < 400:
                    data = lookup.json()
                    users = data.get("users") if isinstance(data, dict) else (data if isinstance(data, list) else [])
                    if users:
                        auth_user_id = users[0].get("id")
                    else:
                        raise HTTPException(status_code=502, detail=f"Invite failed and user not found: {detail}")
                else:
                    raise HTTPException(status_code=502, detail=f"Invite failed and lookup failed: {lookup.text}")
            else:
                # Success; extract user id or fall back to lookup
                try:
                    inv = resp.json()
                    auth_user_id = (inv.get("user") or {}).get("id") or inv.get("id")
                except Exception:
                    auth_user_id = None
                if not auth_user_id:
                    lookup = httpx.get(
                        f"{s.SUPABASE_URL}/auth/v1/admin/users",
                        params={"email": email},
                        headers=base_headers,
                        timeout=15,
                    )
                    if lookup.status_code < 400:
                        data = lookup.json()
                        users = data.get("users") if isinstance(data, dict) else (data if isinstance(data, list) else [])
                        if users:
                            auth_user_id = users[0].get("id")
        else:
            if not password or len(password) < 6:
                raise HTTPException(status_code=400, detail="password (>=6 chars) required when send_invite is false")
            url = f"{s.SUPABASE_URL}/auth/v1/admin/users"
            payload = {"email": email, "password": password, "email_confirm": bool(email_confirm)}
            resp = httpx.post(url, json=payload, headers=base_headers, timeout=20)
            if resp.status_code >= 400:
                try:
                    detail = resp.json()
                except Exception:
                    detail = resp.text
                # If user exists, fetch it
                if resp.status_code == 422:
                    lookup = httpx.get(
                        f"{s.SUPABASE_URL}/auth/v1/admin/users",
                        params={"email": email},
                        headers=base_headers,
                        timeout=15,
                    )
                    if lookup.status_code < 400:
                        data = lookup.json()
                        users = data.get("users") if isinstance(data, dict) else (data if isinstance(data, list) else [])
                        if users:
                            auth_user_id = users[0].get("id")
                        else:
                            raise HTTPException(status_code=502, detail=f"User create failed and user not found: {detail}")
                    else:
                        raise HTTPException(status_code=502, detail=f"User create failed and lookup failed: {lookup.text}")
                else:
                    raise HTTPException(status_code=502, detail=f"User create failed: {detail}")
            else:
                try:
                    user = resp.json()
                    auth_user_id = user.get("id") or (user.get("user") or {}).get("id")
                except Exception:
                    auth_user_id = None
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Auth provisioning failed: {exc}")

    # 2) Create client with image (reusing existing handler)
    client_row = _create_client(
        name=name,
        email=email,
        domain=domain,
        company_id=company_id,
        profile_image=profile_image,
    )

    # 3) Link client to auth user if we have one
    try:
        if auth_user_id and isinstance(client_row, dict) and client_row.get("id") is not None:
            sb = get_supabase()
            upd = sb.table("clients").update({"user_id": auth_user_id}).eq("id", client_row["id"]).execute()
            if not getattr(upd, "error", None):
                got = sb.table("clients").select("*").eq("id", client_row["id"]).single().execute()
                if not getattr(got, "error", None) and getattr(got, "data", None):
                    client_row = got.data
    except Exception:
        pass

    return client_row
