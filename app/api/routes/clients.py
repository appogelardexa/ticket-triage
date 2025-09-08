from typing import List, Optional
from uuid import uuid4
import os
import mimetypes
from fastapi import APIRouter, HTTPException, Query, UploadFile, File, Form
import httpx
from app.core.config import get_supabase
from app.models.schemas import ClientOut, ClientCreate, ClientPatch

# router = APIRouter(tags=["clients"])

# Allow bucket to be configured via env; default to common name 'avatars'
AVATARS_BUCKET = os.getenv("SUPABASE_AVATARS_BUCKET")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

# @router.get("/", summary="List clients")
def list_clients(limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0)):
    sb = get_supabase()
    res = (sb.table("clients").select("*").order("id").range(offset, offset+limit-1).execute())
    return res.data or []


# @router.get("/search", summary="Search clients by email or name")
def search_clients(
    email: Optional[str] = Query(None, description="Exact email match"),
    name: Optional[str] = Query(None, min_length=1, description="Client name to search"),
    exact: bool = Query(False, description="True = exact name match; False = contains"),
    limit: int = Query(10, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    if not email and not name:
        raise HTTPException(status_code=400, detail="Provide email or name")

    sb = get_supabase()
    q = sb.table("clients").select("*")

    if email:
        q = q.eq("email", email)
    elif name:
        if exact:
            q = q.eq("name", name)
        else:
            q = q.ilike("name", f"%{name}%")

    res = q.order("id").range(offset, offset + limit - 1).execute()
    if getattr(res, "error", None):
        raise HTTPException(status_code=502, detail=str(res.error))
    return res.data or []


# @router.get("/{client_id}", response_model=ClientOut, summary="Get client by id")
def get_client_by_id(client_id: int):
    sb = get_supabase()
    res = (
        sb.table("clients")
          .select("*")
          .eq("id", client_id)
          .execute()
    )
    if getattr(res, "error", None):
        raise HTTPException(status_code=502, detail=str(res.error))
    rows = res.data or []
    if not rows:
        raise HTTPException(status_code=404, detail="Client not found")
    return rows[0]


# @router.post("/", response_model=ClientOut, status_code=201, summary="Create client")
def create_client(payload: ClientCreate):
    sb = get_supabase()
    # Perform insert
    res = (
        sb.table("clients")
          .insert(payload.model_dump(exclude_none=True))
          .execute()
    )
    if getattr(res, "error", None):
        raise HTTPException(status_code=502, detail=str(res.error))

    # Supabase usually returns the inserted row in data list
    if isinstance(res.data, list) and res.data:
        return res.data[0]
    elif isinstance(res.data, dict):
        return res.data

    # Fallback: try to fetch by a unique field if provided (email) — optional
    email = payload.email
    if email:
        res2 = sb.table("clients").select("*").eq("email", email).execute()
        if getattr(res2, "error", None):
            raise HTTPException(status_code=502, detail=str(res2.error))
        rows = res2.data or []
        if rows:
            return rows[0]
    # If still nothing, return 502 since we cannot confirm insert result
    raise HTTPException(status_code=502, detail="Failed to retrieve created client")


# @router.post("/with-image", response_model=ClientOut, status_code=201, summary="Create client with profile image upload")
def create_client_with_image(
    name: str = Form(...),
    email: Optional[str] = Form(None),
    domain: Optional[str] = Form(None),
    company_id: Optional[int] = Form(None),
    profile_image: Optional[UploadFile] = File(None),
):
    """
    Creates a client and, if provided, uploads the profile image to Supabase Storage
    and stores the public URL in the `profile_imge_link` column.
    """
    sb = get_supabase()

    # 1) Create base client row first to get an id
    base_payload = {
        "name": name,
    }
    if email is not None:
        base_payload["email"] = email
    if domain is not None:
        base_payload["domain"] = domain
    if company_id is not None:
        base_payload["company_id"] = company_id

    res = sb.table("clients").insert(base_payload).execute()
    if getattr(res, "error", None):
        raise HTTPException(status_code=502, detail=str(res.error))

    # Normalize inserted row
    row = res.data[0] if isinstance(res.data, list) and res.data else res.data
    if not isinstance(row, dict) or "id" not in row:
        raise HTTPException(status_code=502, detail="Failed to retrieve created client id")
    client_id = row["id"]

    public_url: Optional[str] = None

    # 2) If an image was uploaded, push to Supabase Storage and get public URL
    if profile_image is not None:
        try:
            # Derive filename and extension
            orig_name = profile_image.filename or "upload"
            _, ext = os.path.splitext(orig_name)
            if not ext and profile_image.content_type:
                guess = mimetypes.guess_extension(profile_image.content_type)
                ext = guess or ""

            name_no_spaces = str(name).replace(" ", "")
            unique_name = f"profile-{name_no_spaces}{ext}"
            object_path = f"clients/{client_id}/{unique_name}"

            bucket = AVATARS_BUCKET
            try:
                profile_image.file.seek(0)
            except Exception:
                pass
            content = profile_image.file.read()

            # Direct HTTP PUT with service-role Authorization to bypass Storage RLS
            if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
                raise HTTPException(status_code=500, detail="Storage upload misconfigured on server")

            url = f"{SUPABASE_URL}/storage/v1/object/{bucket}/{object_path}"
            headers = {
                "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
                "apikey": SUPABASE_SERVICE_ROLE_KEY,
                "x-upsert": "true",
                "content-type": profile_image.content_type or "application/octet-stream",
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

            # Get public URL
            public_url = f"{SUPABASE_URL}/storage/v1/object/public/{bucket}/{object_path}"

        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"Failed to upload profile image: {exc}") from exc

    print("PUBLIC URL:", public_url)
    print("CLIENT ID:", client_id)
    # 3) If we got a public URL, update the client row
    if public_url:
        print("Updating client with profile image link...")
        upd = (
            sb.table("clients")
              .update({"profile_image_link": public_url})
              .eq("id", client_id)
              .execute()
        )
        if getattr(upd, "error", None):
            raise HTTPException(status_code=502, detail=str(upd.error))

    # 4) Return the fresh client row
    res2 = sb.table("clients").select("*").eq("id", client_id).execute()
    
    if getattr(res2, "error", None):
        raise HTTPException(status_code=502, detail=str(res2.error))
    rows = res2.data or []
    if not rows:
        raise HTTPException(status_code=404, detail="Client not found after creation")
    return rows[0]


# @router.patch("/{client_id}", response_model=ClientOut, summary="Update client by id")
def update_client(client_id: int, patch: ClientPatch):
    sb = get_supabase()
    data = patch.model_dump(exclude_none=True)
    if not data:
        raise HTTPException(status_code=400, detail="No fields to update")

    res = (
        sb.table("clients")
          .update(data)
          .eq("id", client_id)
          .execute()
    )
    if getattr(res, "error", None):
        raise HTTPException(status_code=502, detail=str(res.error))

    # Verify the updated row exists and return it
    res2 = (
        sb.table("clients")
          .select("*")
          .eq("id", client_id)
          .execute()
    )
    if getattr(res2, "error", None):
        raise HTTPException(status_code=502, detail=str(res2.error))
    rows = res2.data or []
    if not rows:
        raise HTTPException(status_code=404, detail="Client not found")
    return rows[0]


# @router.delete("/{client_id}", status_code=204, summary="Delete client by id")
def delete_client(client_id: int):
    sb = get_supabase()

    # Verify existence first to return 404 if missing
    exists = (
        sb.table("clients")
          .select("id")
          .eq("id", client_id)
          .execute()
    )
    if getattr(exists, "error", None) or not getattr(exists, "data", None):
        raise HTTPException(status_code=404, detail="Client not found")

    res = sb.table("clients").delete().eq("id", client_id).execute()
    if getattr(res, "error", None):
        raise HTTPException(status_code=502, detail=str(res.error))
    # FastAPI will honor the 204 status code from decorator
    return { }
