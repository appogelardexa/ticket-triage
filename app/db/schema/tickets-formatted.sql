-- View: tickets_formatted (includes company_id for org filtering)
-- This view flattens ticket details with related names and org info.

CREATE OR REPLACE VIEW public.tickets_formatted AS
SELECT
  t.id,
  t.ticket_id,
  t.status,
  t.priority,
  t.channel,
  t.summary,
  NULL::text               AS subject,         -- placeholder; no column on tickets
  t.email_body             AS body,            -- map email_body -> body for API shape
  t.message_id,
  t.thread_id,
  c.name                   AS client_name,
  c.email                  AS client_email,
  s.name                   AS assignee_name,
  s.email                  AS assignee_email,
  d.name                   AS department_name,
  cat.name                 AS category_name,
  co.id                    AS company_id,      -- added for org filtering
  co.name                  AS company_name,
  t.created_at,
  t.updated_at
FROM public.tickets t
LEFT JOIN public.clients        c   ON c.id = t.client_id
LEFT JOIN public.companies      co  ON co.id = c.company_id
LEFT JOIN public.internal_staff s   ON s.id = t.assignee_id
LEFT JOIN public.departments    d   ON d.id = t.department_id
LEFT JOIN public.categories     cat ON cat.id = t.category_id;

