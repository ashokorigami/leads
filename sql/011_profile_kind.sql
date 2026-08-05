-- 'profile' was added to v_sendable and to the pipeline, but NOT to this CHECK
-- constraint, so every attempt to store a verified website quote raised
-- CheckViolation. Caught by a 20-company pilot: 10 of 20 failed. The earlier
-- end-to-end test called research.research() directly and never exercised the
-- write path, so it passed while this was broken.
ALTER TABLE triggers DROP CONSTRAINT IF EXISTS triggers_kind_check;
ALTER TABLE triggers ADD CONSTRAINT triggers_kind_check CHECK (kind = ANY (ARRAY[
  'hiring_eng','funding','exec_hire','tech_stack','weak_app','launch',
  'headcount_growth','profile'
]));
