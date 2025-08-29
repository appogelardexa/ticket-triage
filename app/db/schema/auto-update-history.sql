-- =========================================================
-- CLEANUP: remove last_modified columns & related trigger
-- =========================================================
-- Drop the BEFORE UPDATE trigger that wrote *_last_modified (if it exists)
DROP TRIGGER IF EXISTS trg_tickets_change_flags ON public.tickets;

-- Drop the function used by that trigger (if it exists)
DO $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM pg_proc p
    JOIN pg_namespace n ON n.oid = p.pronamespace
    WHERE n.nspname = 'public' AND p.proname = 'set_ticket_change_timestamps'
  ) THEN
    DROP FUNCTION public.set_ticket_change_timestamps();
  END IF;
END$$;

-- Drop the columns (if they exist)
ALTER TABLE public.tickets
  DROP COLUMN IF EXISTS status_last_modified,
  DROP COLUMN IF EXISTS priority_last_modified,
  DROP COLUMN IF EXISTS assignee_last_modified;

-- =========================================================
-- STATUS CHANGES: ticket_status_history
-- =========================================================

-- STEP 1: TABLE + INDEX
CREATE TABLE IF NOT EXISTS public.ticket_status_history (
  id           bigserial PRIMARY KEY,
  ticket_id    bigint NOT NULL REFERENCES public.tickets(id) ON DELETE CASCADE,
  from_status  ticket_status,
  to_status    ticket_status NOT NULL,
  changed_at   timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_tsh_ticket_time
  ON public.ticket_status_history(ticket_id, changed_at);

-- STEP 2: FUNCTIONS
CREATE OR REPLACE FUNCTION public.log_status_on_insert()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  INSERT INTO public.ticket_status_history (ticket_id, from_status, to_status, changed_at)
  VALUES (NEW.id, NULL, NEW.status, now());
  RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION public.log_status_on_update()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NEW.status IS DISTINCT FROM OLD.status THEN
    INSERT INTO public.ticket_status_history (ticket_id, from_status, to_status, changed_at)
    VALUES (NEW.id, OLD.status, NEW.status, now());
  END IF;
  RETURN NEW;
END;
$$;

-- STEP 3: TRIGGERS (recreate to ensure exact behavior)
DROP TRIGGER IF EXISTS trg_tickets_status_insert ON public.tickets;
CREATE TRIGGER trg_tickets_status_insert
  AFTER INSERT ON public.tickets
  FOR EACH ROW EXECUTE FUNCTION public.log_status_on_insert();

DROP TRIGGER IF EXISTS trg_tickets_status_update ON public.tickets;
CREATE TRIGGER trg_tickets_status_update
  AFTER UPDATE OF status ON public.tickets
  FOR EACH ROW EXECUTE FUNCTION public.log_status_on_update();

-- =========================================================
-- PRIORITY CHANGES: ticket_priority_history
-- =========================================================

-- STEP 1: TABLE + INDEX
CREATE TABLE IF NOT EXISTS public.ticket_priority_history (
  id             bigserial PRIMARY KEY,
  ticket_id      bigint NOT NULL REFERENCES public.tickets(id) ON DELETE CASCADE,
  from_priority  ticket_priority,
  to_priority    ticket_priority NOT NULL,
  changed_at     timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_tph_ticket_time
  ON public.ticket_priority_history(ticket_id, changed_at);

-- STEP 2: FUNCTIONS
CREATE OR REPLACE FUNCTION public.log_priority_on_insert()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  INSERT INTO public.ticket_priority_history (ticket_id, from_priority, to_priority, changed_at)
  VALUES (NEW.id, NULL, NEW.priority, now());
  RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION public.log_priority_on_update()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NEW.priority IS DISTINCT FROM OLD.priority THEN
    INSERT INTO public.ticket_priority_history (ticket_id, from_priority, to_priority, changed_at)
    VALUES (NEW.id, OLD.priority, NEW.priority, now());
  END IF;
  RETURN NEW;
END;
$$;

-- STEP 3: TRIGGERS (recreate to ensure exact behavior)
DROP TRIGGER IF EXISTS trg_tickets_priority_insert ON public.tickets;
CREATE TRIGGER trg_tickets_priority_insert
  AFTER INSERT ON public.tickets
  FOR EACH ROW EXECUTE FUNCTION public.log_priority_on_insert();

DROP TRIGGER IF EXISTS trg_tickets_priority_update ON public.tickets;
CREATE TRIGGER trg_tickets_priority_update
  AFTER UPDATE OF priority ON public.tickets
  FOR EACH ROW EXECUTE FUNCTION public.log_priority_on_update();

-- (optional) Keep the updated_at refresher if you use it:
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname='trg_tickets_updated_at') THEN
    CREATE TRIGGER trg_tickets_updated_at
      BEFORE UPDATE ON public.tickets
      FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();
  END IF;
END$$;
