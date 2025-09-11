# FastAPI App Guide

Concise reference for running and using the Ticket Triage FastAPI app.

## Run
- Local (reload): `uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload`
- Docker: `docker compose up --build`

Docs and health:
- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`
- OpenAPI: `http://localhost:8000/openapi.json`
- Health: `GET /health` → `{ "status": "ok" }`

## Auth
- Supabase JWT bearer tokens.
- Obtain tokens via `POST /api/auth/login` with `{ email, password }`.
- Include header on protected routes: `Authorization: Bearer <access_token>`.

Key endpoints:
- `POST /api/auth/register` → create user (and seed user profile/client)
- `POST /api/auth/login` → `{ access_token, refresh_token }`
- `POST /api/auth/refresh` → new access token from refresh token
- `POST /api/auth/forgot` → trigger password recovery email
- `GET  /api/auth/me` or `GET /api/me` → current user info (requires bearer)

## Tickets (prefix `/tickets`)
- `POST /tickets/create` (multipart): create ticket with optional attachments.
  - Fields (Form): `summary` (required), `title`, `status`, `priority`, `channel`, `client_id`, `assignee_id`, `department_id`, `category_id`, `subject`, `body`, `message_id`, `thread_id`
  - Files (File[]): `attachments`
- `GET  /tickets/paginated` → paginated tickets (with attachments)
- `GET  /tickets/{ticket_id}` → single ticket (with attachments)
- `PATCH /tickets/{ticket_id}` (multipart) → update fields and optionally replace attachments
- `DELETE /tickets/{ticket_id}` → delete ticket
- Attachments
  - `POST   /tickets/{ticket_id}/attachments` (File[]): upload
  - `PUT    /tickets/{ticket_id}/attachments/{attachment_id}`: replace file
  - `DELETE /tickets/{ticket_id}/attachments/{attachment_id}`: delete

Filtering helpers (selected):
- `GET /tickets/by-date?on=YYYY-MM-DD`
- `GET /tickets/by-attributes?status=open&priority=P3`
- `GET /tickets?assignee_id=...&department_id=...` (id filters)

## Categories & Defaults (prefix `/categories`)
- `GET  /categories` → list categories with default assignees
- `GET  /categories/{category_id}/default-assignees`
- `POST /categories/{category_id}/default-assignees`
- `PUT  /categories/{category_id}/default-assignees/{staff_id}`
- `DELETE /categories/{category_id}/default-assignees/{staff_id}`

## Analytics (prefix `/api/analytics`) [admin]
- Aggregated ticket counts and trends; protected by admin role.

## Example: Login then call a protected route
```bash
# 1) Login
ACCESS=$(curl -s -X POST http://localhost:8000/api/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"user@example.com","password":"secret"}' | jq -r .access_token)

# 2) Call a protected endpoint
curl -s http://localhost:8000/tickets/paginated \
  -H "Authorization: Bearer $ACCESS"
```

## Environment
- `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`
- Optional storage: `SUPABASE_TICKET_ATTACHMENTS_BUCKET`
- See `.env.prod` for the full production set.

