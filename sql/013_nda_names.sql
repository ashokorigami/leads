-- sterlitecopper.com was NOT on the domain suppression list, so "Vedanta Copper
-- & Nickel" was researched, scored 74, and reached a published target list.
-- Listing subsidiary domains one by one will always miss the next one, so
-- suppress by NAME as well.
--
-- \m and \M are word boundaries: 'Bhaktivedanta Hospital' - an unrelated Mumbai
-- hospital - must NOT match. Substring matching on names is a recurring bug in
-- this codebase and it caught me again while checking for this very leak.
INSERT INTO suppression (kind, value, reason) VALUES
  ('domain','sterlitecopper.com','client-nda'),
  ('domain','vedantaaluminium.com','client-nda'),
  ('domain','sesagoa.com','client-nda'),
  ('name','vedanta','client-nda - matches whole word only'),
  ('name','sterlite','client-nda - matches whole word only')
ON CONFLICT DO NOTHING;

-- Retire anything already in the pipeline that matches.
UPDATE companies c SET stage='rejected',
       rejected_reason='NDA client group - never target', updated_at=now()
WHERE (c.name ~* '\m(vedanta|sterlite)\M' OR EXISTS (
        SELECT 1 FROM suppression s WHERE s.kind='domain' AND s.value = c.domain))
  AND c.stage <> 'rejected';

SELECT 'suppressed by name' AS what, count(*)::text AS n
FROM companies WHERE name ~* '\m(vedanta|sterlite)\M'
UNION ALL
SELECT 'false positives correctly spared (Bhaktivedanta etc.)',
       count(*)::text FROM companies
 WHERE name ~* 'vedanta' AND name !~* '\mvedanta\M';
