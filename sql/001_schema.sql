-- Origami outbound — core schema
-- Design rule: a company may only be emailed if it has at least one row in
-- triggers. No observable trigger, no email. Enforced in code AND by v_sendable.

CREATE TYPE company_stage AS ENUM
  ('sourced','enriched','researched','qualified','rejected','queued','sent');

-- ---------- reps & sending identities ----------
CREATE TABLE reps (
  id          SERIAL PRIMARY KEY,
  full_name   TEXT NOT NULL,
  email       TEXT NOT NULL UNIQUE,
  active      BOOLEAN NOT NULL DEFAULT TRUE,
  weight      INT NOT NULL DEFAULT 1 CHECK (weight >= 0),
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE mailboxes (
  id           SERIAL PRIMARY KEY,
  address      TEXT NOT NULL UNIQUE,
  domain       TEXT NOT NULL,
  provider     TEXT NOT NULL CHECK (provider IN ('google','microsoft')),
  rep_id       INT REFERENCES reps(id),
  daily_cap    INT NOT NULL DEFAULT 25 CHECK (daily_cap BETWEEN 0 AND 50),
  status       TEXT NOT NULL DEFAULT 'warming'
               CHECK (status IN ('warming','live','paused','burned')),
  warmup_start DATE,
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---------- suppression: consulted before anything else ----------
CREATE TABLE suppression (
  id         BIGSERIAL PRIMARY KEY,
  kind       TEXT NOT NULL CHECK (kind IN ('domain','email')),
  value      TEXT NOT NULL,
  reason     TEXT NOT NULL,   -- client | unsubscribed | complaint | competitor | bounce | manual
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (kind, value)
);
CREATE INDEX ON suppression (value);

-- ---------- companies ----------
CREATE TABLE companies (
  id              BIGSERIAL PRIMARY KEY,
  apollo_org_id   TEXT UNIQUE,
  domain          TEXT NOT NULL UNIQUE,
  name            TEXT,
  industry        TEXT,
  employees       INT,
  country         TEXT,
  founded_year    INT,
  linkedin_url    TEXT,
  stage           company_stage NOT NULL DEFAULT 'sourced',
  rejected_reason TEXT,
  enriched_at     TIMESTAMPTZ,
  apollo_raw      JSONB,
  scrape_raw      JSONB,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ON companies (stage);
CREATE INDEX ON companies (enriched_at);

-- ---------- triggers: THE GATE ----------
CREATE TABLE triggers (
  id           BIGSERIAL PRIMARY KEY,
  company_id   BIGINT NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
  kind         TEXT NOT NULL CHECK (kind IN
                 ('hiring_eng','funding','exec_hire','tech_stack','weak_app','launch','headcount_growth')),
  detail       TEXT NOT NULL,          -- the nameable fact quoted in the email
  evidence_url TEXT,
  observed_at  DATE,
  source       TEXT NOT NULL CHECK (source IN ('apollo','scrape','appstore','news')),
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ON triggers (company_id);

-- ---------- people ----------
CREATE TABLE prospects (
  id               BIGSERIAL PRIMARY KEY,
  company_id       BIGINT NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
  apollo_person_id TEXT UNIQUE,
  first_name       TEXT,
  last_name        TEXT,
  title            TEXT,
  seniority        TEXT,
  email            TEXT,
  email_status     TEXT CHECK (email_status IN ('verified','guessed','unavailable')),
  linkedin_url     TEXT,
  created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (company_id, email)
);
CREATE INDEX ON prospects (company_id);

-- ---------- Opus research output ----------
CREATE TABLE research (
  id                BIGSERIAL PRIMARY KEY,
  company_id        BIGINT NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
  model             TEXT NOT NULL,
  score             INT NOT NULL CHECK (score BETWEEN 0 AND 100),
  wedge             TEXT CHECK (wedge IN
                      ('doc_intelligence','auctions','gaming','mobile','commerce','ai_product','dedicated_team')),
  primary_trigger   TEXT,
  angle             TEXT,
  proof_ref         TEXT,              -- anonymised case study to cite
  disqualify_reason TEXT,
  raw               JSONB NOT NULL,
  input_tokens      INT,
  output_tokens     INT,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ON research (company_id);
CREATE INDEX ON research (score DESC);

-- ---------- generated email + human gate ----------
CREATE TABLE emails (
  id          BIGSERIAL PRIMARY KEY,
  prospect_id BIGINT NOT NULL REFERENCES prospects(id) ON DELETE CASCADE,
  step        INT NOT NULL CHECK (step BETWEEN 1 AND 3),
  subject     TEXT NOT NULL,
  body        TEXT NOT NULL,
  model       TEXT NOT NULL,
  approved    BOOLEAN,                 -- NULL = awaiting human review
  approved_by TEXT,
  approved_at TIMESTAMPTZ,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (prospect_id, step)
);
CREATE INDEX ON emails (approved);

CREATE TABLE sends (
  id              BIGSERIAL PRIMARY KEY,
  email_id        BIGINT NOT NULL REFERENCES emails(id) ON DELETE CASCADE,
  mailbox_id      INT NOT NULL REFERENCES mailboxes(id),
  provider        TEXT NOT NULL,
  provider_msg_id TEXT,
  sent_at         TIMESTAMPTZ,
  status          TEXT NOT NULL DEFAULT 'queued'
                  CHECK (status IN ('queued','sent','bounced','failed')),
  error           TEXT
);
CREATE INDEX ON sends (mailbox_id, sent_at);
CREATE INDEX ON sends (status);

-- ---------- replies ----------
CREATE TABLE replies (
  id             BIGSERIAL PRIMARY KEY,
  prospect_id    BIGINT REFERENCES prospects(id) ON DELETE SET NULL,
  send_id        BIGINT REFERENCES sends(id) ON DELETE SET NULL,
  from_email     TEXT NOT NULL,
  subject        TEXT,
  body           TEXT,
  received_at    TIMESTAMPTZ NOT NULL,
  classification TEXT CHECK (classification IN
                   ('interested','not_now','referral','not_interested',
                    'unsubscribe','ooo','auto','bounce')),
  confidence     NUMERIC(4,3),
  routed_rep_id  INT REFERENCES reps(id),
  routed_at      TIMESTAMPTZ,
  handled        BOOLEAN NOT NULL DEFAULT FALSE,
  raw            JSONB
);
CREATE INDEX ON replies (classification, handled);
CREATE INDEX ON replies (routed_rep_id);

-- ---------- the gate, expressed as a view ----------
-- Only prospects surfacing here may ever be emailed.
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
  AND EXISTS (SELECT 1 FROM triggers t WHERE t.company_id = c.id)
  AND NOT EXISTS (SELECT 1 FROM suppression s
                  WHERE (s.kind='domain' AND s.value = c.domain)
                     OR (s.kind='email'  AND s.value = p.email));
