-- Territory + offer plan, and the launch schedule. Stored as data so the
-- pipeline can read it, not as a document that drifts from what runs.

CREATE TABLE IF NOT EXISTS regions (
  code        TEXT PRIMARY KEY,
  name        TEXT NOT NULL,
  countries   TEXT[] NOT NULL,
  priority    INT NOT NULL,              -- 1 = go first
  coverage    TEXT NOT NULL,             -- apollo trigger coverage: good|thin|none
  timezone    TEXT,
  notes       TEXT
);

CREATE TABLE IF NOT EXISTS segments (
  code          TEXT PRIMARY KEY,
  name          TEXT NOT NULL,
  naics         TEXT[] NOT NULL,
  offer         TEXT NOT NULL,           -- the wedge
  min_employees INT NOT NULL,
  max_employees INT,
  priority      INT NOT NULL,
  why           TEXT NOT NULL            -- why this offer for this segment
);

CREATE TABLE IF NOT EXISTS plan_days (
  day        DATE PRIMARY KEY,
  week       INT NOT NULL,
  phase      TEXT NOT NULL,
  focus      TEXT NOT NULL,
  owner      TEXT NOT NULL,              -- claude | ashok | devops | reps
  target     TEXT,
  done       BOOLEAN NOT NULL DEFAULT FALSE,
  note       TEXT
);

-- ---------- regions, ordered by where a trigger can actually be found ----------
INSERT INTO regions (code,name,countries,priority,coverage,timezone,notes) VALUES
 ('NA','North America','{"United States","Canada"}',1,'good','America/New_York',
  'Deepest Apollo hiring data. Largest budgets. Start here.'),
 ('UKI','UK & Ireland','{"United Kingdom","Ireland"}',2,'good','Europe/London',
  'Strong coverage, English-native, overlaps the NY morning.'),
 ('DACH','DACH','{"Germany","Austria","Switzerland"}',3,'good','Europe/Berlin',
  'Heavy industry and logistics. English is fine at CIO level.'),
 ('BENELUX','Benelux','{"Netherlands","Belgium"}',4,'good','Europe/Amsterdam',
  'Ports, freight, dredging, engineering. Punches above its size.'),
 ('NORDIC','Nordics','{"Sweden","Denmark","Norway","Finland"}',5,'good','Europe/Stockholm',
  'Shipping, energy, manufacturing. High English fluency.'),
 ('SEUR','Southern Europe','{"Spain","Italy","France","Portugal"}',6,'good','Europe/Madrid',
  'Good coverage. English at senior IT level, less so below.'),
 ('ANZ','Australia & NZ','{"Australia","New Zealand"}',7,'good','Australia/Sydney',
  'Mining, construction, utilities. Awkward timezone for the reps.'),
 ('SG','Singapore','{"Singapore"}',8,'good','Asia/Singapore',
  'Regional HQs for shipping and commodities. Small but dense.'),
 ('LATAM','Latin America','{"Brazil","Mexico","Chile","Colombia","Peru","Argentina"}',
  9,'thin','America/Sao_Paulo',
  'HOLD. Apollo has almost no hiring data here - 24 of 30 companies produced no '
  'trigger. Needs an app-store or local-jobs source before it is worth credits.'),
 ('MEA','Middle East & Africa','{"United Arab Emirates","Saudi Arabia","South Africa","Egypt"}',
  10,'thin','Asia/Dubai',
  'HOLD. Same problem as LATAM. Large industrials, no findable trigger.'),
 ('APAC','Rest of Asia','{"India","Malaysia","Indonesia","Japan"}',11,'thin','Asia/Kolkata',
  'HOLD. Thin trigger data. India also risks colliding with the Bangalore office.')
ON CONFLICT (code) DO NOTHING;

-- ---------- segments: who gets which offer, and why ----------
INSERT INTO segments (code,name,naics,offer,min_employees,max_employees,priority,why) VALUES
 ('insurance','Insurance & claims','{"524126","524210","524292","524130"}',
  'doc_intelligence',3000,NULL,1,
  'Claims files, policy documents, correspondence. Regulated, retention rules, '
  'and every claim is a document trail. The strongest fit we have.'),
 ('energy','Energy & utilities','{"221112","221310","221122","486210"}',
  'doc_intelligence',3000,NULL,1,
  'Permits, inspection reports, regulatory filings, asset records spanning decades.'),
 ('manufacturing','Manufacturing & industrial','{"333120","325180","332710","336390","327320"}',
  'doc_intelligence',3000,NULL,1,
  'Specifications, quality records, supplier certificates, compliance documentation.'),
 ('retail_vendor','Large retail & wholesale','{"452210","455110","444110","445110","424410","423450"}',
  'doc_intelligence',5000,NULL,1,
  'A big retailer managing thousands of vendors drowns in supplier contracts, '
  'onboarding packets, insurance and compliance certificates, POs and invoices. '
  'Not obviously document-heavy until you count the vendors.'),
 ('engineering','Engineering & construction','{"541330","541310","236220","237310","238210"}',
  'doc_intelligence',1000,NULL,1,
  'Drawings, specs, permits, submittals, RFIs, closeout docs. Every bid re-reads '
  'the last one. MEASURED best-converting segment at ~40%.'),
 ('logistics','Freight & logistics','{"488510","484121","483111","488320","493110"}',
  'doc_intelligence',2000,NULL,2,
  'Bills of lading, customs declarations, certificates of origin - multi-language '
  'and largely scanned.'),
 ('pharma','Pharma & medical devices','{"325412","339112","424210"}',
  'doc_intelligence',2000,NULL,2,
  'Regulatory submissions, trial documentation, quality records. Heavily audited.'),
 ('healthcare','Healthcare administration','{"622110","621999","541714"}',
  'doc_intelligence',3000,NULL,2,
  'Clinical records, billing, payer correspondence, accreditation evidence.'),
 ('legal','Legal services','{"541110","541199"}',
  'doc_intelligence',500,NULL,3,
  'The archive IS the business. Smaller headcount threshold because document '
  'volume per head is enormous.'),
 ('consumer_app','Consumer & DTC brands','{"448140","445110","722511","713940"}',
  'mobile',200,2000,3,
  'Too small for a 150,000-document platform. They need an app that works, and '
  'the backend, admin and analytics behind it.'),
 ('ecommerce','Ecommerce & marketplaces','{"454110","459999"}',
  'commerce',200,3000,3,
  'Catalogue, checkout, loyalty, seller onboarding, payouts. VideoShops and '
  'GetCashback are the proof.'),
 ('scaleup','Funded scale-ups','{"541511","541512","518210"}',
  'dedicated_team',300,2000,4,
  'They have engineers but not enough. Embedded senior capacity on a defined '
  'workstream, never "we will build your product".')
ON CONFLICT (code) DO NOTHING;
