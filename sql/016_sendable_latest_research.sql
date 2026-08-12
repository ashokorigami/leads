-- 016_sendable_latest_research.sql
--
-- v_sendable joined `research` on company_id with no ordering, so a company
-- carrying more than one research row multiplied its prospects. Seven companies
-- (all researched twice-to-four-times on 29-30 July) produced 90 gate rows for
-- 64 real people -- one prospect appeared four times.
--
-- Two consequences, both live:
--   1. Duplicate sends. The gate offered the same person up to 4 times.
--   2. Non-deterministic OFFER. 13 prospects had conflicting research; 3 of them
--      disagreed on `wedge`, so which product the email pitched depended on row
--      order. `score` disagreed for all 13.
--
-- app.py already does this correctly for /targets and the CSV export:
--   LEFT JOIN LATERAL (... ORDER BY created_at DESC LIMIT 1)
-- The send gate did not, so the console displayed the newest score while the
-- gate could pick a stale one -- and the operator approves against the console
-- (LESSONS.md sec.9: operator approval is not verification).
--
-- Proven in a rolled-back transaction:
--   rows 90 -> 64, distinct prospects 64 -> 64
--   remaining duplicates ....................... 0
--   previously-sendable prospects dropped ...... 0   (must not fire)
--   rows not carrying the newest research ...... 0
--
-- id DESC is the tie-break so two rows sharing a created_at stay deterministic.

CREATE OR REPLACE VIEW v_sendable AS
 SELECT p.id AS prospect_id, p.email, c.id AS company_id, c.domain,
        r.score, r.wedge, r.primary_trigger
   FROM prospects p
   JOIN companies c ON c.id = p.company_id
   JOIN LATERAL (
        SELECT rr.score, rr.wedge, rr.primary_trigger, rr.disqualify_reason
          FROM research rr
         WHERE rr.company_id = c.id
         ORDER BY rr.created_at DESC, rr.id DESC
         LIMIT 1) r ON TRUE
  WHERE p.email IS NOT NULL AND p.email_status = 'verified'
    AND r.score >= 70 AND r.disqualify_reason IS NULL
    AND EXISTS (SELECT 1 FROM triggers t WHERE t.company_id = c.id
                  AND t.kind = ANY (ARRAY['hiring_eng','funding','exec_hire',
                        'weak_app','launch','headcount_growth','profile']))
    AND NOT EXISTS (SELECT 1 FROM suppression s
                     WHERE (s.kind='domain' AND s.value = c.domain)
                        OR (s.kind='email'  AND s.value = p.email)
                        OR (s.kind='name'   AND c.name ~* ('\m' || s.value || '\M')));
