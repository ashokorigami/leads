-- What a company says about itself, stored verbatim so the researcher can only
-- quote what was actually fetched.
CREATE TABLE IF NOT EXISTS company_sources (
  id         SERIAL PRIMARY KEY,
  company_id INT NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
  url        TEXT NOT NULL,
  text       TEXT NOT NULL,
  fetched_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (company_id, url)
);
CREATE INDEX IF NOT EXISTS company_sources_co ON company_sources(company_id);

-- The gate stops being "did Apollo see a job advert" and becomes "is there a
-- specific, SOURCED fact". 'profile' is a fact quoted from the company's own
-- site and verified to appear in the stored text.
DROP VIEW IF EXISTS v_sendable;
CREATE VIEW v_sendable AS
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
                               'weak_app','launch','headcount_growth',
                               'profile'))
  AND NOT EXISTS (SELECT 1 FROM suppression s
                  WHERE (s.kind='domain' AND s.value = c.domain)
                     OR (s.kind='email'  AND s.value = p.email));

-- The held regions are held no longer: the reason was Apollo's job coverage,
-- not the quality of the market.
UPDATE regions SET coverage='research', notes=
  'Job-posting data is thin here, so this region is worked from RESEARCHED '
  'facts - what the company states about its own scale - rather than hiring '
  'signals. Same score bar, different evidence.'
WHERE code IN ('LATAM','MEA','APAC');
