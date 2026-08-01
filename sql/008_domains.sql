-- Sending domains and their aging clock. A freshly-registered domain that
-- starts cold-sending gets filtered; 30 days of age before warmup is the
-- cheapest deliverability insurance there is.
CREATE TABLE IF NOT EXISTS sending_domains (
  domain        TEXT PRIMARY KEY,
  registered_on DATE NOT NULL,
  platform      TEXT,                -- google | m365 | none yet
  phase         TEXT NOT NULL,       -- A = sending now, B = next wave
  status        TEXT NOT NULL,       -- live | aging | redirect_only
  note          TEXT
);

INSERT INTO sending_domains (domain,registered_on,platform,phase,status,note) VALUES
 ('myorigami.co','2019-01-01','google','A','live',
  'Carries most volume: 3 mailboxes x 25/day. Google Workspace, a different landlord to the M365 tenant.'),
 ('eorigami.in','2020-01-01','m365','A','redirect_only',
  'Held back - needs M365 admin consent. Low-exposure A/B arm only, 8/day, because M365 reputation is TENANT level and origami.dev shares that tenant.'),
 ('origamiconsulting.ai','2026-07-20',NULL,'B','aging',NULL),
 ('origamiconsulting.co','2026-07-20',NULL,'B','aging',NULL),
 ('origamiconsulting.in','2026-07-20',NULL,'B','aging',NULL),
 ('origamiconsulting.io','2026-07-20',NULL,'B','aging',NULL),
 ('hireorigami.com','2026-08-01',NULL,'B','aging','Bought 1 Aug'),
 ('buildwithorigami.com','2026-08-01',NULL,'B','aging','Bought 1 Aug'),
 ('origamiteams.com','2026-08-01',NULL,'B','aging','Bought 1 Aug'),
 ('origamibuilds.com','2026-08-01',NULL,'B','aging','Bought 1 Aug'),
 ('origami.dev','2014-01-01','m365','-','redirect_only',
  'NEVER sends cold. Signature and reply-continuation only.')
ON CONFLICT (domain) DO UPDATE SET note = EXCLUDED.note;
