# Ticket Creation Webhook

Concise guide for creating tickets via the external webhook used by the web app.

## Endpoints
- POST https://ardexa1.app.n8n.cloud/webhook/ticket-triage-web
- GET  https://ardexa1.app.n8n.cloud/webhook/ticket-triage-status?job_id=<uuid>

## Create Ticket (POST)
- Content-Type: multipart/form-data
- Fields (form):
  - `email` (required): requester email
  - `name` (optional): requester name
  - `subject` (optional): original subject/title
  - `body` (required): message body
  - `messageId` (optional): source message id
  - `providerMessageId` (optional): external/provider id
  - `threadId` (optional): conversation/thread id
  - `attachment_` (optional, repeatable): file(s) to upload

Example:
```bash
curl --location 'https://ardexa1.app.n8n.cloud/webhook/ticket-triage-web' \
  --form 'messageId=""' \
  --form 'providerMessageId=""' \
  --form 'threadId=""' \
  --form 'email="appogel.cagocons@gmail.com"' \
  --form 'name="appogel"' \
  --form 'subject="logistics issue"' \
  --form 'body="Hello Support Team,\n\nI’d like to raise a support ticket regarding a logistics issue...\n\nThank you,\nAppogel"' \
  --form 'attachment_=@"/path/to/file1.png"' \
  --form 'attachment_=@"/path/to/file2.pdf"'
```

Response (accepted):
```json
{
  "status": "pending",
  "job_id": "57e2d5ec-14fa-4dab-99da-6e62cc053611",
  "message": "Ticket triage started"
}
```

## Check Status (GET)
Poll with the `job_id` from the POST response:
```bash
curl --location \
  'https://ardexa1.app.n8n.cloud/webhook/ticket-triage-status?job_id=57e2d5ec-14fa-4dab-99da-6e62cc053611'
```

Sample completed result:
```json
{
  "job_id": "57e2d5ec-14fa-4dab-99da-6e62cc053611",
  "status": "completed",
  "created_at": "2025-09-11T16:12:36.842301+00:00",
  "result": {
    "ticket": {
      "id": 1088,
      "body": "Hello Support Team,\n...",
      "title": "Delivery delayed or incorrect, assistance needed to resolve",
      "status": "new",
      "channel": "web",
      "subject": "logistics issue",
      "summary": "Customer reports a logistics problem...",
      "priority": "P3",
      "thread_id": "1757607156380",
      "ticket_id": "TCK-001088",
      "company_id": 2,
      "created_at": "2025-09-11T16:13:51.947482Z",
      "message_id": "mid_wckhHbB2TM",
      "updated_at": "2025-09-11T16:13:51.947482Z",
      "client_name": "Appogel Cagoco",
      "client_email": "appogel.cagocons@gmail.com",
      "company_name": "Test",
      "assignee_name": "Ardexa bot",
      "category_name": "Freight Shipment Issue",
      "assignee_email": "appogel@ardexa.ai",
      "department_name": "Admin"
    },
    "attachments": []
  },
  "error": null
}
```

## Typical Status Values
- `pending` → received and queued and processing
- `completed` → success; `result` contains `ticket` and `attachments`
- `error` → error; `error` contains details

## Tips
- Multiple files: repeat `--form 'attachment_=@/path'` for each file.
- Shell capture of job id:
  ```bash
  JOB=$(curl -s -F email='user@example.com' -F body='hi' \
    https://ardexa1.app.n8n.cloud/webhook/ticket-triage-web | jq -r .job_id)
  curl -s "https://ardexa1.app.n8n.cloud/webhook/ticket-triage-status?job_id=$JOB"
  ```
- Timeouts: the POST returns quickly; poll the status endpoint until `completed`.

