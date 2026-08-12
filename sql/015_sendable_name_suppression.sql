-- 015_sendable_name_suppression.sql
--
-- v_sendable honoured suppression by domain and email only. Name suppression
-- (013_nda_names.sql) was applied in pipeline.suppressed(), in /targets and in
-- the CSV export -- but NOT in the send gate itself.
--
-- Company 2145 masked this: it matches a suppressed name AND its domain is
-- listed, so the domain rule excluded it and the gap was invisible. The gap
-- bites a company whose NAME matches on a domain nobody has listed yet -- the
-- exact case LESSONS.md sec.4 says will keep recurring, because listing
-- subsidiary domains one at a time will always miss the next one.
--
-- Proven in a rolled-back transaction, both directions (LESSONS.md sec.5):
--   must fire     '<name> Infra Limited' on an unlisted domain  90 -> 91 -> removed
--   must NOT fire 'Zz<name>qq Industries' (token inside a word) retained
--   live row count before and after: 90 -> 90 (no legitimate target lost)

CREATE OR REPLACE VIEW v_sendable AS
 SELECT p.id AS prospect_id, p.email, c.id AS company_id, c.domain,
        r.score, r.wedge, r.primary_trigger
   FROM prospects p
   JOIN companies c ON c.id = p.company_id
   JOIN research  r ON r.company_id = c.id
  WHERE p.email IS NOT NULL AND p.email_status = 'verified'
    AND r.score >= 70 AND r.disqualify_reason IS NULL
    AND EXISTS (SELECT 1 FROM triggers t WHERE t.company_id = c.id
                  AND t.kind = ANY (ARRAY['hiring_eng','funding','exec_hire',
                        'weak_app','launch','headcount_growth','profile']))
    AND NOT EXISTS (SELECT 1 FROM suppression s
                     WHERE (s.kind='domain' AND s.value = c.domain)
                        OR (s.kind='email'  AND s.value = p.email)
                        OR (s.kind='name'   AND c.name ~* ('\m' || s.value || '\M')));
