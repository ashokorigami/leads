-- Which segment a company was sourced FOR. Previously computed at source time
-- and then discarded, so "who gets EDI vs apps" could not be answered from the
-- data - only from the plan document, which is exactly the drift we are trying
-- to avoid.
ALTER TABLE companies ADD COLUMN IF NOT EXISTS segment TEXT;
CREATE INDEX IF NOT EXISTS companies_segment ON companies(segment);
CREATE INDEX IF NOT EXISTS companies_country ON companies(country);
