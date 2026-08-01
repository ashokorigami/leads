DELETE FROM plan_days;
INSERT INTO plan_days (day,week,phase,focus,owner,target,note) VALUES
-- Week 0 - warmup running, backlog cleared
('2026-08-01',0,'warmup','Clear the backlog: run the 175 staged retail / wholesale / food / pharma companies through the pipeline','claude','175 processed','First real test of the vendor-heavy doc_intelligence angle'),
('2026-08-02',0,'warmup','Schedule the 08:00 daily digest; confirm warmup day 5 scores','claude','digest live',NULL),

-- Week 1 - bank the best-converting segments first
('2026-08-03',1,'warmup','Source North America: engineering & construction','claude','200 companies','MEASURED best segment at ~40% end-to-end. Bank it first.'),
('2026-08-03',1,'warmup','Regenerate the GoDaddy API token (both are 401) and add the DNS record','ashok','A record live','30 seconds in the GoDaddy DNS panel - record given below'),
('2026-08-04',1,'warmup','Source North America: insurance & claims, energy & utilities','claude','200 companies','The two strongest doc_intelligence fits'),
('2026-08-05',1,'warmup','Source UK & Ireland: engineering, logistics','claude','200 companies',NULL),
('2026-08-06',1,'warmup','Source DACH: manufacturing, logistics','claude','200 companies','English is fine at CIO level here'),
('2026-08-07',1,'warmup','Source North America: large retail & wholesale (the vendor angle)','claude','200 companies','5,000+ staff and thousands of suppliers = document load that is invisible until you count vendors'),
('2026-08-08',1,'warmup','Reply-routing rehearsal: send a real reply through classification and round-robin','claude','end-to-end pass','Must be proven BEFORE launch, not on launch day'),
('2026-08-09',1,'warmup','Read the banked emails. Reject anything that reads wrong','ashok','bank reviewed','Your judgement is the last gate before a real prospect sees it'),

-- Week 2 - widen coverage, then the non-EDI half
('2026-08-10',2,'warmup','Source Benelux & Nordics: ports, freight, engineering, energy','claude','200 companies',NULL),
('2026-08-11',2,'warmup','Source North America: pharma, healthcare admin, legal','claude','200 companies',NULL),
('2026-08-12',2,'warmup','Source Southern Europe: manufacturing, logistics, utilities','claude','200 companies',NULL),
('2026-08-13',2,'warmup','Source ANZ & Singapore: mining, construction, shipping','claude','150 companies','Timezone is awkward for the reps - keep the volume modest'),
('2026-08-14',2,'warmup','Source the NON-EDI half: consumer brands, ecommerce, funded scale-ups','claude','200 companies','200-2,000 staff. These get apps and commerce, NEVER doc_intelligence'),
('2026-08-15',2,'warmup','LATAM probe using app-store triggers only - measure, do not bulk source','claude','60 companies','A 30-company batch produced 24 with no trigger. This tests whether app-store signals fix that'),
('2026-08-16',2,'warmup','Approve the bank so week 3 starts with a full queue','ashok','400+ approved',NULL),

-- Week 3 - final prep, then launch
('2026-08-17',3,'warmup','Decision deadline: Outlook mailboxes on eorigami.in, or launch on Google only','ashok','decided','Launching on 3 Google mailboxes alone is perfectly fine - this is optional upside'),
('2026-08-18',3,'warmup','Pre-flight: SPF/DKIM/DMARC re-check, suppression list, one-click unsubscribe, digest, rep routing','claude','all green','Warmup day 21. Last day before real prospects.'),
('2026-08-19',3,'launch','FIRST REAL SEND','claude','15 emails','Deliberately small. Watch bounces and complaints before ramping.'),
('2026-08-20',3,'ramp','Send + watch bounce and complaint rate','claude','25 emails','Stop immediately if bounces exceed 2% or complaints 0.3%'),
('2026-08-21',3,'ramp','Send + first reply handling by the reps','claude','35 emails',NULL),
('2026-08-22',3,'ramp','No cold send at weekends','claude','0 emails',NULL),
('2026-08-23',3,'ramp','No cold send at weekends','claude','0 emails',NULL),

-- Week 4 - ramp to full rate
('2026-08-24',4,'ramp','Ramp','claude','45 emails',NULL),
('2026-08-25',4,'ramp','Ramp','claude','55 emails',NULL),
('2026-08-26',4,'ramp','Ramp','claude','65 emails',NULL),
('2026-08-27',4,'ramp','Full rate reached','claude','75 emails','3 mailboxes x 25/day. Do not exceed this until reps are measurably underutilised'),
('2026-08-28',4,'ramp','Full rate + first week review: reply rate by region and by segment','claude','75 emails','This is the first real data on which segments actually answer'),
('2026-08-29',4,'ramp','No cold send at weekends','claude','0 emails',NULL),
('2026-08-30',4,'ramp','No cold send at weekends','claude','0 emails',NULL);
