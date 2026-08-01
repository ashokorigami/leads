-- reps (round-robin). Vishwanath deliberately omitted; add later if reply volume needs it.
INSERT INTO reps (full_name, email) VALUES
  ('Abhaya Saxena',    'abhaya@origami.dev'),
  ('Manjunath Patil',  'manjunath@origami.dev'),
  ('Manjula BusiReddy','manjula@origami.dev');

-- Phase A mailboxes. eorigami.in confirmed created; myorigami.co pending.
INSERT INTO mailboxes (address, domain, provider, rep_id, daily_cap, status) VALUES
  ('abhaya@eorigami.in',    'eorigami.in','microsoft',1,25,'warming'),
  ('manjunath@eorigami.in', 'eorigami.in','microsoft',2,25,'warming'),
  ('manjula@eorigami.in',   'eorigami.in','microsoft',3,25,'warming'),
  ('abhaya@myorigami.co',   'myorigami.co','google',   1,25,'paused'),
  ('manjunath@myorigami.co','myorigami.co','google',   2,25,'paused'),
  ('manjula@myorigami.co',  'myorigami.co','google',   3,25,'paused');

-- never contact: own domains + existing clients/products
INSERT INTO suppression (kind, value, reason) VALUES
  ('domain','origami.dev','own'),           ('domain','myorigami.co','own'),
  ('domain','eorigami.in','own'),           ('domain','origamiconsulting.ai','own'),
  ('domain','origamiconsulting.co','own'),  ('domain','origamiconsulting.in','own'),
  ('domain','origamiconsulting.io','own'),  ('domain','theredclub.com','own'),
  ('domain','hiphopgrails.com','client'),   ('domain','playsqor.com','client'),
  ('domain','acquire.bet','client'),        ('domain','videoshops.com','client'),
  ('domain','realprofits.com','client'),    ('domain','getcashback.com','client'),
  ('domain','theschedule.com','client'),    ('domain','askpricing.com','client'),
  ('domain','onlybeaches.co','client'),     ('domain','redclub.ai','client');
