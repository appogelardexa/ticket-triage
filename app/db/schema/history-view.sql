
--=Status History View

create or replace view public.ticket_status_history_vw as
select
  tsh.id,
  tsh.ticket_id as ticket_pk,
  t.ticket_id as ticket_id,
  tsh.from_status,
  tsh.to_status,
  tsh.changed_at
from public.ticket_status_history tsh
join public.tickets t
  on t.id = tsh.ticket_id;


-- Priority History view
create or replace view public.ticket_priority_history_vw as
select
  tph.id,
  tph.ticket_id as ticket_pk,
  t.ticket_id as ticket_id,
  tph.from_priority,
  tph.to_priority,
  tph.changed_at
from public.ticket_priority_history tph
join public.tickets t
  on t.id = tph.ticket_id;

