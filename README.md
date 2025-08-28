# Ticket Triage Backend

FastAPI + Supabase + Docker backend for the Ticket Triage project.

## Quick start
1. Copy `.env.example` to `.env` and set Supabase keys.
2. Paste `app/db/schema/schema.sql` into Supabase SQL editor to create tables, enums, triggers.
3. Run:
```bash
docker compose up --build
```
Then visit http://localhost:8000/docs
