# Ticket Triage Backend

FastAPI + Supabase backend packaged with Docker, deployed on a Hostinger VPS (Docker Swarm).

## Stack
- FastAPI (Python)
- Supabase (Postgres + Storage)
- Docker / Docker Swarm

## Local Development
1. Copy envs and configure:
   - Duplicate `.env.prod` to `.env` (or set the same vars locally).
2. Initialize database (first time):
   - Run `app/db/schema/schema.sql` in Supabase SQL editor.
3. Start the API:
   - `docker compose up --build`
   - Docs: `http://localhost:8000/docs`

## Environment Variables (key ones)
- `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`
- `SUPABASE_TICKET_ATTACHMENTS_BUCKET` (storage bucket name)
- See `.env.prod` for the full list used in production.

## Database Notes
- Schema and views are defined under `app/db/schema/schema.sql`.
- If you add columns (e.g., `tickets.title`), also update related views using `CREATE OR REPLACE VIEW` and keep existing column names intact.

## Build & Deploy (Hostinger VPS)
Prereqs:
- Docker + Swarm initialized on the VPS
- A Docker registry (Docker Hub) with access for the VPS
- Local Docker context configured for the VPS (e.g., `hostinger`)

Steps:
1) Build and push image (use versioned tags):
```bash
docker buildx build \
  -t <dockerhub-user>/ticket-triage:1.0.0 \
  -t <dockerhub-user>/ticket-triage:latest \
  --platform linux/amd64 \
  --push .
```

2) Use Hostinger context and enable SSH agent:
```bash
# Switch context
docker context use hostinger

# Linux/macOS (each new terminal)
eval "$(ssh-agent -s)" && ssh-add ~/.ssh/hostinger_key

# Windows PowerShell (if OpenSSH Agent is installed)
Start-Service ssh-agent; ssh-add $env:USERPROFILE\.ssh\hostinger_key
```

3) Deploy the stack on the VPS:
```bash
docker stack deploy -c docker-compose.prod.yaml --with-registry-auth --prune ardexaticket
```

Tips:
- Always bump the image tag (e.g., `1.0.1`) to ensure Swarm pulls the new image.
- To roll back: redeploy with a previous tag.

## Useful Commands
- View services: `docker service ls`
- Logs: `docker service logs -f ardexaticket_web`
- Inspect tasks: `docker service ps ardexaticket_web`
