-- Second constraint, found only after fixing the first: source had no 'website'
-- value, so storing a quote scraped from a company's own site still failed.
-- Two constraints, two separate failures - fixing one revealed the next.
ALTER TABLE triggers DROP CONSTRAINT IF EXISTS triggers_source_check;
ALTER TABLE triggers ADD CONSTRAINT triggers_source_check CHECK (source = ANY (ARRAY[
  'apollo','scrape','appstore','news','website'
]));
