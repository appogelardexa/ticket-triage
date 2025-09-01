-- View: tickets_detailed (IDs + formatted names + org info)
-- Contains base foreign keys for filtering and readable fields for convenience.

CREATE OR REPLACE VIEW public.tickets_detailed AS
SELECT
  -- Ticket core
  t.id,
  t.ticket_id,
  t.status,
  t.priority,
  t.channel,
  t.summary,
  t.subject,                
  t.body,                     
  t.message_id,
  t.thread_id,

  -- Client and organization (IDs first, then readable)
  t.client_id,
  c.name              AS client_name,
  c.email             AS client_email,
  c.company_id        AS company_id,
  co.name             AS company_name,

  -- Assignee
  t.assignee_id,
  s.name              AS assignee_name,
  s.email             AS assignee_email,

  -- Department
  t.department_id,
  d.name              AS department_name,

  -- Category
  t.category_id,
  cat.name            AS category_name,

  -- Timestamps
  t.created_at,
  t.updated_at
FROM public.tickets t
LEFT JOIN public.clients        c   ON c.id = t.client_id
LEFT JOIN public.companies      co  ON co.id = c.company_id
LEFT JOIN public.internal_staff s   ON s.id = t.assignee_id
LEFT JOIN public.departments    d   ON d.id = t.department_id
LEFT JOIN public.categories     cat ON cat.id = t.category_id;