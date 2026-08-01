-- tech_stack is CONTEXT, not a buying signal. "They use Shopify" is true of
-- millions of companies and is no reason to be in someone's inbox. It stays
-- available to sharpen the angle, but can no longer qualify a company alone.
CREATE OR REPLACE VIEW v_sendable AS
SELECT p.id AS prospect_id, p.email, c.id AS company_id, c.domain,
       r.score, r.wedge, r.primary_trigger
FROM prospects p
JOIN companies c ON c.id = p.company_id
JOIN research  r ON r.company_id = c.id
WHERE p.email IS NOT NULL
  AND p.email_status = 'verified'
  AND r.score >= 70
  AND r.disqualify_reason IS NULL
  AND EXISTS (SELECT 1 FROM triggers t
              WHERE t.company_id = c.id
                AND t.kind IN ('hiring_eng','funding','exec_hire',
                               'weak_app','launch','headcount_growth'))
  AND NOT EXISTS (SELECT 1 FROM suppression s
                  WHERE (s.kind='domain' AND s.value = c.domain)
                     OR (s.kind='email'  AND s.value = p.email));
