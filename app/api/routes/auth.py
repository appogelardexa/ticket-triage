from typing import Optional
import httpx
from fastapi import APIRouter, Depends, HTTPException
from app.models.schemas import RegisterIn, LoginIn, RefreshIn, ForgotIn

from app.core.config import get_supabase, get_settings
from app.api.deps import require_user, get_user_supabase


router = APIRouter(prefix="/api/auth", tags=["auth"])
@router.post("/register")
def register(body: RegisterIn):
    sb = get_supabase()  # service-role client
    try:
        res = sb.auth.sign_up({"email": body.email, "password": body.password})
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Registration failed: {exc}")
    if getattr(res, "error", None):
        raise HTTPException(status_code=400, detail=str(res.error))

    user = getattr(res, "user", None) or {}
    user_id = getattr(user, "id", None) or (user.get("id") if isinstance(user, dict) else None)
    email = getattr(user, "email", None) or (user.get("email") if isinstance(user, dict) else None)

    # Seed user_profiles with default role 'user'
    if user_id:
        try:
            sb.table("user_profiles").upsert({"user_id": user_id, "role": "user"}).execute()
        except Exception:
            pass

    # Ensure a linked client row exists for this user (requester)
    client_row = None
    if user_id and email:
        # Derive a readable default name if none provided
        default_name = None
        try:
            default_name = email.split("@", 1)[0].replace(".", " ").replace("_", " ").title()
        except Exception:
            default_name = None
        client_name = body.name or default_name or "User"

        try:
            # Try to find existing client either by user_id or email
            found = (
                sb.table("clients")
                  .select("id")
                  .or_(f"user_id.eq.{user_id},email.eq.{email}")
                  .limit(1)
                  .execute()
            )
            rows = getattr(found, "data", None) or []
            if isinstance(rows, list) and rows:
                cid = rows[0].get("id")
                if cid is not None:
                    # Make sure the linkage is set
                    sb.table("clients").update({"user_id": user_id}).eq("id", cid).execute()
                    client_row = {"id": cid}
            else:
                ins = sb.table("clients").insert({
                    "name": client_name,
                    "email": email,
                    "user_id": user_id,
                }).execute()
                client_row = ins.data[0] if isinstance(ins.data, list) and ins.data else ins.data
        except Exception:
            # Don't block registration if client creation/linking fails
            client_row = None

    return {
        "user_id": user_id,
        "email": email,
        "client_id": (client_row or {}).get("id") if isinstance(client_row, dict) else None,
    }


@router.post("/register-staff")
def register_staff(body: RegisterIn):
    """
    Register a new user and grant staff role. Also ensures an internal_staff record
    is linked to this user for assignment and authoring purposes.
    """
    sb = get_supabase()  # service-role client
    # 1) Create auth user
    try:
        res = sb.auth.sign_up({"email": body.email, "password": body.password})
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Registration failed: {exc}")
    if getattr(res, "error", None):
        raise HTTPException(status_code=400, detail=str(res.error))

    user = getattr(res, "user", None) or {}
    user_id = getattr(user, "id", None) or (user.get("id") if isinstance(user, dict) else None)
    email = getattr(user, "email", None) or (user.get("email") if isinstance(user, dict) else None)
    if not user_id:
        raise HTTPException(status_code=400, detail="Registration failed: missing user id")

    # 2) Set staff role
    try:
        sb.table("user_profiles").upsert({"user_id": user_id, "role": "staff"}).execute()
    except Exception:
        pass

    # 3) Ensure internal_staff exists and is linked
    staff_row = None
    # Try find by user_id (non-throwing)
    f1 = sb.table("internal_staff").select("id").eq("user_id", user_id).limit(1).execute()
    if not getattr(f1, "error", None) and (getattr(f1, "data", None) or []) != []:
        rows = f1.data if isinstance(f1.data, list) else [f1.data]
        staff_row = rows[0]
    else:
        # Try link by email
        f2 = sb.table("internal_staff").select("id").eq("email", email).limit(1).execute()
        if getattr(f2, "error", None):
            # Fall through to insert
            pass
        else:
            rows = f2.data or []
            if rows:
                sid = rows[0].get("id")
                upd = sb.table("internal_staff").update({"user_id": user_id}).eq("id", sid).execute()
                if getattr(upd, "error", None):
                    raise HTTPException(status_code=502, detail=f"Failed to link staff user_id: {upd.error}")
                staff_row = {"id": sid}

        # If still not found/linked, insert
        if staff_row is None:
            display_name = body.name
            if not display_name and email:
                try:
                    display_name = email.split("@", 1)[0].replace(".", " ").replace("_", " ").title()
                except Exception:
                    display_name = "Staff"
            ins = sb.table("internal_staff").insert({
                "name": display_name or "Staff",
                "email": email,
                "user_id": user_id,
            }).execute()
            if getattr(ins, "error", None):
                raise HTTPException(status_code=502, detail=f"Failed to create staff: {ins.error}")
            staff_row = ins.data[0] if isinstance(ins.data, list) and ins.data else ins.data

    if not staff_row or not isinstance(staff_row, dict) or staff_row.get("id") is None:
        raise HTTPException(status_code=502, detail="Failed to ensure internal_staff record for user")

    return {
        "user_id": user_id,
        "email": email,
        "role": "staff",
        "staff_id": (staff_row or {}).get("id") if isinstance(staff_row, dict) else None,
    }

@router.post("/login")
def login(body: LoginIn):
    sb = get_supabase()
    try:
        res = sb.auth.sign_in_with_password({"email": body.email, "password": body.password})
    except Exception as exc:
        raise HTTPException(status_code=401, detail=f"Login failed: {exc}")
    if getattr(res, "error", None) or not getattr(res, "session", None):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    sess = res.session
    user = getattr(res, "user", None) or {}
    return {
        "access_token": getattr(sess, "access_token", None),
        "refresh_token": getattr(sess, "refresh_token", None),
        "token_type": "bearer",
        "expires_in": getattr(sess, "expires_in", None),
        "user": {
            "id": getattr(user, "id", None) or (user.get("id") if isinstance(user, dict) else None),
            "email": getattr(user, "email", None) or (user.get("email") if isinstance(user, dict) else None),
        },
    }

@router.post("/refresh")
def refresh(body: RefreshIn):
    sb = get_supabase()
    try:
        res = sb.auth.refresh_session(body.refresh_token)
    except Exception as exc:
        raise HTTPException(status_code=401, detail=f"Refresh failed: {exc}")
    if getattr(res, "error", None) or not getattr(res, "session", None):
        raise HTTPException(status_code=401, detail="Invalid refresh token")
    sess = res.session
    return {
        "access_token": getattr(sess, "access_token", None),
        "refresh_token": getattr(sess, "refresh_token", None),
        "token_type": "bearer",
        "expires_in": getattr(sess, "expires_in", None),
    }

@router.post("/forgot")
def forgot_password(body: ForgotIn):
    """Trigger a password recovery email via Supabase Auth public recover endpoint.

    No authentication required. The `redirect_to` URL must be allowed in Supabase Auth settings.
    """
    s = get_settings()
    if not s.SUPABASE_URL or not s.SUPABASE_ANON_KEY:
        raise HTTPException(status_code=500, detail="Server auth misconfigured")

    url = f"{s.SUPABASE_URL}/auth/v1/recover"
    payload = {"email": body.email}
    if body.redirect_to:
        payload["redirect_to"] = body.redirect_to
    headers = {
        "Content-Type": "application/json",
        "apikey": s.SUPABASE_ANON_KEY,
    }
    try:
        resp = httpx.post(url, json=payload, headers=headers, timeout=15)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Recovery request failed: {exc}")

    if resp.status_code >= 400:
        try:
            detail = resp.json()
        except Exception:
            detail = resp.text
        raise HTTPException(status_code=502, detail=f"Recovery request failed: {detail}")

    return {"ok": True}


@router.post("/logout")
def logout():
    # Stateless API: client should discard tokens. Best-effort sign out.
    try:
        get_supabase().auth.sign_out()
    except Exception:
        pass
    return {"ok": True}


@router.get("/me")
def me(user=Depends(require_user)):
    # user contains: user_id, email, role, staff_id, client_id, jwt
    return {k: v for k, v in user.items() if k != "jwt"}
