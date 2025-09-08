import os
from functools import lru_cache
from supabase import create_client, Client
try:
    # Load variables from a local .env file early so class-level
    # os.getenv(...) reads get the values in dev. Does not override real env.
    from dotenv import load_dotenv
    load_dotenv(override=False)
except Exception:
    # If python-dotenv isn't available or any issue occurs, skip silently.
    pass

class Settings:
    SUPABASE_URL: str = os.getenv("SUPABASE_URL")
    SUPABASE_ANON_KEY: str = os.getenv("SUPABASE_ANON_KEY")
    SUPABASE_SERVICE_ROLE_KEY: str = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    ENV: str = os.getenv("ENV", "dev")

@lru_cache
def get_settings() -> Settings:
    return Settings()

@lru_cache
def get_supabase() -> Client:
    s = get_settings()
    # Prefer service role for server-side operations; fallback to anon.
    key = s.SUPABASE_SERVICE_ROLE_KEY or s.SUPABASE_ANON_KEY
    if not s.SUPABASE_URL or not key:
        raise RuntimeError("Missing SUPABASE_URL or SUPABASE_*_KEY")

    client = create_client(s.SUPABASE_URL, key)
    # Ensure PostgREST uses Authorization header for RLS-aware queries.
    try:
        client.postgrest.auth(key)
    except Exception:
        pass
    # Storage uploads now use direct HTTP with service role in tickets_service.py.
    return client
