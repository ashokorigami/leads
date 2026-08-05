-- Third CHECK constraint to bite in one day. When adding a new value to an
-- enum-ish column, grep the schema for constraints on that column FIRST.
ALTER TABLE suppression DROP CONSTRAINT IF EXISTS suppression_kind_check;
ALTER TABLE suppression ADD CONSTRAINT suppression_kind_check
  CHECK (kind = ANY (ARRAY['domain','email','name']));

INSERT INTO suppression (kind, value, reason) VALUES
  ('domain','sterlitecopper.com','client-nda'),
  ('domain','vedantaaluminium.com','client-nda'),
  ('domain','sesagoa.com','client-nda'),
  ('name','vedanta','client-nda - whole word only'),
  ('name','sterlite','client-nda - whole word only')
ON CONFLICT DO NOTHING;
