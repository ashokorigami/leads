-- Delivered work, stored as rows so the writer can pick proof by segment
-- instead of me hand-editing prose. nda=true means the NAME MUST NEVER APPEAR:
-- for those rows the `label` is already anonymised and there is no name field
-- to leak.
CREATE TABLE IF NOT EXISTS client_proof (
  code        TEXT PRIMARY KEY,
  label       TEXT NOT NULL,     -- what the email is allowed to say
  wedge       TEXT NOT NULL,
  segments    TEXT[] NOT NULL,   -- which segments this proof is credible for
  detail      TEXT NOT NULL,
  nda         BOOLEAN NOT NULL DEFAULT FALSE,
  caution     TEXT
);

INSERT INTO client_proof (code,label,wedge,segments,detail,nda,caution) VALUES
 ('doc_industrial',
  'a large industrial group',
  'doc_intelligence',
  '{insurance,energy,manufacturing,retail_vendor,engineering,logistics,pharma,healthcare,legal}',
  '150,000 documents across two departments, multi-language and largely scanned, '
  'deployed inside the client''s own cloud tenancy. Three-week setup. Started as one '
  'department and grew.',
  TRUE,
  'UNDER NDA. Never name the client, its parent, or any subsidiary. Permission is '
  'pending but NOT granted. The label above is the ONLY permitted description.'),

 ('videoshops','VideoShops','commerce','{ecommerce,consumer_app}',
  'Shoppable video commerce platform - catalogue, checkout and creator tooling.',
  FALSE,NULL),

 ('fanrush','FanRush','commerce','{ecommerce,consumer_app}',
  'Fan commerce and rewards platform.',FALSE,
  'ATTRIBUTION WARNING: FanRush lists SHEIN, Adidas, Zappos, Sephora, Marks & Spencer '
  'and PrettyLittleThing as ITS OWN brand partners. Those are FanRush''s clients, NOT '
  'Origami''s. NEVER imply Origami worked for, with, or on behalf of any of them.'),

 ('affiliate_reporting','a global affiliate network','ai_product','{ecommerce,scaleup}',
  'Reporting and tracking across 30,000+ brands, ingesting Impact and CJ feeds. '
  'Reconciliation and attribution at feed scale.',FALSE,NULL),

 ('redclub','RedClub','mobile','{consumer_app,ecommerce}',
  'Cashback and rewards apps - iOS, Android and the offer engine behind them.',
  FALSE,NULL),

 ('berides','BeRides','mobile','{consumer_app,scaleup}',
  'Marketplace app going live - booking, payments and operator tooling.',FALSE,NULL),

 ('acquire','Acquire.bet','gaming','{consumer_app}',
  'Online casino and real-money gaming platform.',FALSE,
  'Only cite where gambling is a credible reference. Never to regulated '
  'institutional buyers - insurance, healthcare, pharma, utilities.'),

 ('fantasy','fantasy sports platforms','gaming','{consumer_app}',
  'Real-money fantasy sports - contests, wallets, settlement.',FALSE,
  'Same restriction as Acquire.bet.'),

 ('auctions','live auction platforms','auctions','{ecommerce,consumer_app}',
  'Real-time bidding, lot management and settlement.',FALSE,NULL)
ON CONFLICT (code) DO NOTHING;
