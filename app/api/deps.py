from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from supabase import create_client

from app.core.config import get_settings, get_supabase


bearer = HTTPBearer(auto_error=False)


def require_user(credentials: HTTPAuthorizationCredentials = Depends(bearer)) -> dict:
    """Validate a Supabase access token, load role + domain ids, and return user context.

    Returns a dict: { user_id, email, role, staff_id, client_id }
    """
    if not credentials or not credentials.credentials:
        raise HTTPException(status_code=401, detail="Missing bearer token")

    jwt = credentials.credentials
    sb_admin = get_supabase()

    # Validate token using an ANON-key client to avoid mixing service-role
    # credentials with a user JWT on /auth/v1/user (which can yield 403
    # session_not_found). Use service client only for subsequent DB lookups.
    s = get_settings()
    sb_anon = create_client(s.SUPABASE_URL, s.SUPABASE_ANON_KEY or "")
    res = sb_anon.auth.get_user(jwt)
    if getattr(res, "error", None) or not getattr(res, "user", None):
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    user = res.user
    user_id = getattr(user, "id", None) or (user.get("id") if isinstance(user, dict) else None)
    email = getattr(user, "email", None) or (user.get("email") if isinstance(user, dict) else None)
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token: missing user id")

    # Load role from user_profiles
    role = None
    try:
        prof = (
            sb_admin.table("user_profiles")
            .select("role")
            .eq("user_id", user_id)
            .single()
            .execute()
        )
        if not getattr(prof, "error", None) and getattr(prof, "data", None):
            role = prof.data.get("role") if isinstance(prof.data, dict) else None
    except Exception:
        role = None

    # Optional: lookup linked domain ids and names
    staff_id = None
    staff_name = None
    client_id = None
    client_name = None
    try:
        sres = (
            sb_admin.table("internal_staff").select("id,name").eq("user_id", user_id).single().execute()
        )
        if not getattr(sres, "error", None) and getattr(sres, "data", None):
            if isinstance(sres.data, dict):
                staff_id = sres.data.get("id")
                staff_name = sres.data.get("name")
    except Exception:
        staff_id = None
        staff_name = None
    try:
        cres = (
            sb_admin.table("clients").select("id,name").eq("user_id", user_id).single().execute()
        )
        if not getattr(cres, "error", None) and getattr(cres, "data", None):
            if isinstance(cres.data, dict):
                client_id = cres.data.get("id")
                client_name = cres.data.get("name")
    except Exception:
        client_id = None
        client_name = None

    # Choose a display name
    display_name = staff_name or client_name
    if not display_name and email:
        try:
            display_name = email.split("@", 1)[0].replace(".", " ").replace("_", " ")
            display_name = display_name.title()
        except Exception:
            display_name = None

    return {
        "user_id": user_id,
        "email": email,
        "role": role,
        "staff_id": staff_id,
        "client_id": client_id,
        "name": display_name,
        "jwt": jwt,
    }


def get_user_supabase(jwt: str):
    """Build a Supabase client that uses the provided user access token.

    This ensures PostgREST/Storage calls run under RLS as the user (auth.uid()).
    """
    s = get_settings()
    client = create_client(s.SUPABASE_URL, s.SUPABASE_ANON_KEY or "")
    try:
        # Set auth for PostgREST and Storage
        client.postgrest.auth(jwt)
        try:
            client.storage.set_auth(jwt)
        except Exception:
            pass
    except Exception:
        pass
    return client


def require_admin(user=Depends(require_user)) -> dict:
    """Ensure the authenticated user has an admin role.

    Accepts roles 'admin' or 'superadmin'. Adjust as needed.
    Returns the same user dict on success.
    """
    role = (user or {}).get("role")
    if role not in {"admin"}:
        raise HTTPException(status_code=403, detail="Admin privileges required")
    return user
