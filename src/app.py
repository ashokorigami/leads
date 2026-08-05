"""Origami Outbound — the console.

Server-rendered. No build step, no JS framework: approve/reject are plain form
POSTs, so the thing cannot break in a way that silently loses a decision.

Accounts live in the `users` table and sessions in `sessions` (see auth.py).
Every route except /login and /healthz requires a session — enforced in one
middleware rather than per-route, so a new page cannot accidentally ship
unprotected.
"""
from datetime import date, timedelta
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, PlainTextResponse
import html as H

from config import db
import auth
import review

app = FastAPI(title="Origami Outbound")

OPEN_PATHS = {"/login", "/healthz"}


@app.middleware("http")
async def require_login(request: Request, call_next):
    if request.url.path in OPEN_PATHS:
        return await call_next(request)
    user = auth.current_user(request.cookies.get(auth.COOKIE))
    if not user:
        return RedirectResponse("/login", status_code=303)
    request.state.user = user
    return await call_next(request)

CSS = """
:root{--ink:#1a1416;--paper:#fbf8f8;--panel:#fff;--rule:#e8dfe0;--muted:#6f6467;
--red:#d62839;--send:#1f6b45;--send-soft:#eaf4ee;--hold:#8a6516;--hold-soft:#faf1de;
--mono:#f6f2f2;--kill:#a3242e;--kill-soft:#fdeef0}
@media(prefers-color-scheme:dark){:root{--ink:#f2ecec;--paper:#141011;--panel:#1c1618;
--rule:#332a2c;--muted:#9d9095;--red:#ff5c69;--send:#5fc48d;--send-soft:#12261c;
--hold:#d9a94a;--hold-soft:#251d0f;--mono:#221b1d;--kill:#ff8a92;--kill-soft:#2b1418}}
*{box-sizing:border-box}
body{background:var(--paper);color:var(--ink);margin:0;padding:0 1.25rem 5rem;
font:15px/1.55 ui-sans-serif,-apple-system,"Segoe UI",Roboto,sans-serif;-webkit-font-smoothing:antialiased}
.wrap{max-width:62rem;margin:0 auto}
header{padding:2.2rem 0 1.4rem;border-bottom:2px solid var(--ink);display:flex;
flex-wrap:wrap;align-items:baseline;gap:.5rem 1.2rem}
h1{font-size:1.55rem;margin:0;letter-spacing:-.02em;font-weight:750}
nav{margin-left:auto;display:flex;gap:1.1rem}
nav a{color:var(--muted);text-decoration:none;font-size:.85rem;font-weight:600}
nav a.on,nav a:hover{color:var(--red)}
.status{display:grid;gap:1px;background:var(--rule);border:1px solid var(--rule);
grid-template-columns:repeat(auto-fit,minmax(8.5rem,1fr));margin:1.6rem 0 2.4rem}
.stat{background:var(--panel);padding:.85rem 1rem}
.stat dt{font-size:.6rem;letter-spacing:.13em;text-transform:uppercase;color:var(--muted);
margin:0 0 .25rem;font-weight:600}
.stat dd{margin:0;font-size:1.35rem;font-weight:680;font-variant-numeric:tabular-nums;letter-spacing:-.02em}
.stat dd small{display:block;font-size:.7rem;font-weight:500;color:var(--muted);letter-spacing:0}
.stat.alert dd{color:var(--red)}
.card{border:1px solid var(--rule);background:var(--panel);margin-bottom:1.4rem}
.head{display:flex;flex-wrap:wrap;align-items:baseline;gap:.5rem 1rem;padding:.85rem 1.1rem;
border-bottom:1px solid var(--rule)}
.co{font-weight:700;font-size:1.02rem}
.to{color:var(--muted);font-size:.84rem}
.sp{flex:1 1 auto}
.score{font-variant-numeric:tabular-nums;font-weight:750}
.pill{font-size:.6rem;letter-spacing:.1em;text-transform:uppercase;font-weight:700;
padding:.2rem .45rem;border:1px solid currentColor}
.pill.w{color:var(--muted);border-color:var(--rule)}
.pill.ok{color:var(--send);background:var(--send-soft)}
.pill.no{color:var(--kill);background:var(--kill-soft)}
.trig{padding:.75rem 1.1rem;border-bottom:1px solid var(--rule);font-size:.85rem;color:var(--muted)}
.trig b{color:var(--ink);font-weight:600}
.msg{padding:1.2rem 1.1rem;background:var(--mono);font-family:ui-monospace,Menlo,monospace;
font-size:.845rem;line-height:1.7;white-space:pre-wrap;max-width:64ch}
.subj{font-family:ui-monospace,Menlo,monospace;font-size:.82rem;color:var(--muted);
padding:.7rem 1.1rem;border-bottom:1px dashed var(--rule)}
.subj b{color:var(--ink)}
.why{padding:.8rem 1.1rem;font-size:.84rem;color:var(--muted);border-top:1px solid var(--rule)}
.why b{color:var(--ink)}
.acts{padding:.75rem 1.1rem;border-top:1px solid var(--rule);display:flex;gap:.6rem;align-items:center}
button{font:inherit;font-size:.84rem;font-weight:650;padding:.45rem .95rem;cursor:pointer;
border:1px solid var(--rule);background:var(--panel);color:var(--ink)}
button.go{border-color:var(--send);color:var(--send);background:var(--send-soft)}
button.stop{border-color:var(--kill);color:var(--kill);background:var(--kill-soft)}
button:hover{filter:brightness(.97)}
button:focus-visible{outline:2px solid var(--red);outline-offset:2px}
.bulk{display:flex;gap:.6rem;align-items:center;margin:0 0 1.6rem;padding:.9rem 1.1rem;
border:1px solid var(--rule);background:var(--panel)}
.bulk span{color:var(--muted);font-size:.85rem;margin-right:auto}
table{border-collapse:collapse;width:100%;font-size:.86rem;background:var(--panel)}
th{text-align:left;font-size:.6rem;letter-spacing:.13em;text-transform:uppercase;color:var(--muted);
font-weight:600;padding:.6rem .85rem;border-bottom:1px solid var(--rule);white-space:nowrap}
td{padding:.6rem .85rem;border-bottom:1px solid var(--rule);vertical-align:top}
td.n{font-variant-numeric:tabular-nums;font-weight:650;white-space:nowrap}
.tw{overflow-x:auto;border:1px solid var(--rule)}
h2{font-size:.68rem;letter-spacing:.16em;text-transform:uppercase;font-weight:700;
margin:2.6rem 0 1rem;padding-bottom:.45rem;border-bottom:1px solid var(--rule)}
.empty{padding:2.5rem 1.1rem;text-align:center;color:var(--muted);border:1px dashed var(--rule)}
tr.today td{background:var(--hold-soft)}
tr.done td{color:var(--muted)}
tr.done td.f{text-decoration:line-through}
td.day{white-space:nowrap;font-variant-numeric:tabular-nums;font-weight:650}
td.day small{display:block;font-weight:500;color:var(--muted);font-size:.7rem}
.wk{font-size:.62rem;letter-spacing:.14em;text-transform:uppercase;font-weight:700;
color:var(--muted);padding:1.1rem .85rem .4rem}
.own{font-size:.6rem;letter-spacing:.09em;text-transform:uppercase;font-weight:700;
padding:.15rem .4rem;border:1px solid var(--rule);color:var(--muted);white-space:nowrap}
.own.ashok{color:var(--red);border-color:var(--red)}
.own.devops{color:var(--hold);border-color:var(--hold)}
.tick{border:0;background:none;cursor:pointer;font-size:1rem;padding:0;color:var(--muted)}
.tick.on{color:var(--send)}
.nda{color:var(--kill);background:var(--kill-soft);border:1px solid currentColor;
font-size:.6rem;letter-spacing:.1em;text-transform:uppercase;font-weight:700;padding:.15rem .4rem}
.lede{color:var(--muted);font-size:.9rem;max-width:60ch;margin:0 0 1.5rem}
.hold{color:var(--hold);font-weight:650}
.who{margin-left:1.2rem;display:flex;align-items:baseline;gap:.6rem;font-size:.8rem;color:var(--muted)}
button.link{border:0;background:none;color:var(--red);font-size:.8rem;font-weight:650;
padding:0;cursor:pointer;text-decoration:underline}
body.signin{display:grid;place-items:center;min-height:100vh;padding:1.25rem}
form.login{width:min(24rem,100%);border:1px solid var(--rule);background:var(--panel);
padding:2rem 1.9rem 1.9rem;display:flex;flex-direction:column;gap:1rem}
form.login h1{font-size:1.3rem;margin:0}
form.login .sub{margin:-.55rem 0 .3rem;color:var(--muted);font-size:.86rem}
form.login label{display:flex;flex-direction:column;gap:.35rem;font-size:.68rem;
letter-spacing:.12em;text-transform:uppercase;color:var(--muted);font-weight:650}
form.login input{font:inherit;font-size:.95rem;letter-spacing:0;text-transform:none;
padding:.55rem .65rem;border:1px solid var(--rule);background:var(--paper);color:var(--ink)}
form.login input:focus-visible{outline:2px solid var(--red);outline-offset:1px}
form.login button{margin-top:.4rem;padding:.6rem}
.err{margin:0;padding:.6rem .7rem;font-size:.84rem;color:var(--kill);
background:var(--kill-soft);border:1px solid currentColor}
.two{display:grid;gap:1.4rem;grid-template-columns:repeat(auto-fit,minmax(20rem,1fr))}
.mini{border:1px solid var(--rule);background:var(--panel);padding:.75rem .95rem;
font-size:.86rem;border-bottom:0}
.mini:last-child{border-bottom:1px solid var(--rule)}
.mini b{font-weight:650}
.mini small{color:var(--muted)}
a.more{display:inline-block;margin-top:.8rem;font-size:.82rem;font-weight:650;color:var(--red)}
.filters{display:flex;flex-wrap:wrap;gap:.8rem;align-items:flex-end;margin:0 0 1.6rem;
padding:.9rem 1.1rem;border:1px solid var(--rule);background:var(--panel)}
.filters label{display:flex;flex-direction:column;gap:.3rem;font-size:.6rem;
letter-spacing:.12em;text-transform:uppercase;color:var(--muted);font-weight:650}
.filters select{font:inherit;font-size:.85rem;letter-spacing:0;text-transform:none;
padding:.35rem .5rem;border:1px solid var(--rule);background:var(--paper);color:var(--ink)}
"""


def page(title: str, current: str, body: str, user: dict | None = None) -> HTMLResponse:
    nav = "".join(
        f'<a href="{h}"{" class=\'on\'" if k == current else ""}>{n}</a>'
        for k, h, n in [("home", "/", "Today"), ("queue", "/queue", "Approve"),
                        ("targets", "/targets", "Companies"),
                        ("contacted", "/contacted", "Contacted"), ("plan", "/plan", "Plan"),
                        ("territory", "/territory", "Territory"),
                        ("sent", "/sent", "Approved"), ("rejected", "/rejected", "Rejected"),
                        ("health", "/health", "Health")])
    who = (f'<form class="who" method="post" action="/logout">'
           f'<a href="/account">{H.escape(user["name"])}</a>'
           f'<button class="link">Sign out</button></form>') if user else ""
    return HTMLResponse(f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow">
<title>{H.escape(title)} — Origami Outbound</title><style>{CSS}</style></head><body>
<div class="wrap"><header><h1>Origami Outbound</h1><nav>{nav}</nav>{who}</header>
{body}</div></body></html>""")


@app.get("/login", response_class=HTMLResponse)
def login_form(request: Request, bad: int = 0):
    if auth.current_user(request.cookies.get(auth.COOKIE)):
        return RedirectResponse("/", status_code=303)
    err = ('<p class="err">That email and password combination did not work.</p>'
           if bad else "")
    return HTMLResponse(f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow">
<title>Sign in — Origami Outbound</title><style>{CSS}</style></head><body class="signin">
<form class="login" method="post" action="/login">
  <h1>Origami Outbound</h1>
  <p class="sub">Sign in to review and approve today's outbound.</p>
  {err}
  <label>Email<input type="email" name="email" autocomplete="username" required autofocus></label>
  <label>Password<input type="password" name="password" autocomplete="current-password" required></label>
  <button class="go" type="submit">Sign in</button>
</form></body></html>""")


@app.post("/login")
def login_submit(email: str = Form(...), password: str = Form(...)):
    token = auth.login(email, password)
    if not token:
        return RedirectResponse("/login?bad=1", status_code=303)
    r = RedirectResponse("/", status_code=303)
    r.set_cookie(auth.COOKIE, token, httponly=True, secure=True, samesite="lax",
                 max_age=auth.SESSION_DAYS * 86400, path="/")
    return r


@app.post("/logout")
def logout(request: Request):
    auth.logout(request.cookies.get(auth.COOKIE))
    r = RedirectResponse("/login", status_code=303)
    r.delete_cookie(auth.COOKIE, path="/")
    return r


@app.get("/healthz")
def healthz():
    """Unauthenticated liveness probe. Deliberately leaks nothing."""
    return PlainTextResponse("ok")


@app.get("/account", response_class=HTMLResponse)
def account(request: Request, changed: int = 0, bad: int = 0):
    u = request.state.user
    msg = ('<p class="err" style="color:var(--send);background:var(--send-soft)">'
           'Password changed.</p>' if changed else
           '<p class="err">Current password was wrong, or the new one was under '
           '12 characters.</p>' if bad else "")
    body = f"""<h2>Your account</h2>
      <div class="mini"><b>{H.escape(u['name'])}</b><br>
      <small>{H.escape(u['email'])} · {H.escape(u['role'])}</small></div>
      <h2>Change password</h2>{msg}
      <form class="login" style="border:1px solid var(--rule);max-width:24rem;margin:0"
            method="post" action="/account">
        <label>Current password<input type="password" name="old"
               autocomplete="current-password" required></label>
        <label>New password<input type="password" name="new" minlength="12"
               autocomplete="new-password" required></label>
        <button class="go" type="submit">Change password</button>
      </form>"""
    return page("Account", "account", body, u)


@app.post("/account")
def account_change(request: Request, old: str = Form(...), new: str = Form(...)):
    u = request.state.user
    if len(new) < 12 or not auth.login(u["email"], old):
        return RedirectResponse("/account?bad=1", status_code=303)
    auth.set_password(u["email"], new)
    return RedirectResponse("/account?changed=1", status_code=303)


def stats() -> dict:
    with db() as c, c.cursor() as cur:
        s = {}
        cur.execute("SELECT count(*) FILTER (WHERE approved IS NULL), "
                    "count(*) FILTER (WHERE approved IS TRUE), "
                    "count(*) FILTER (WHERE approved IS FALSE) FROM emails")
        s["pending"], s["approved"], s["rejected"] = cur.fetchone()
        cur.execute("SELECT min(warmup_start), min(status) FROM mailboxes WHERE status='warming'")
        ws, _ = cur.fetchone()
        s["warmup_day"] = (date.today() - ws).days + 1 if ws else 0
        s["live_from"] = (ws + timedelta(days=21)) if ws else None
        cur.execute("SELECT count(*) FROM companies WHERE stage='sourced'")
        s["sourced"] = cur.fetchone()[0]
        cur.execute("""SELECT count(*) FROM replies WHERE classification IN
                       ('interested','referral') AND NOT handled""")
        s["warm_waiting"] = cur.fetchone()[0]
        return s


def strip(title: str, s: dict) -> str:
    cells = [
        ("Awaiting you", s["pending"], "to review", s["pending"] > 0),
        ("Approved", s["approved"], "ready", False),
        ("Warmup", s["warmup_day"], "of 21 days", False),
        ("First send", s["live_from"].strftime("%d %b") if s["live_from"] else "—", "2026", False),
        ("Sourced", s["sourced"], "in pipeline", False),
        ("Warm replies", s["warm_waiting"], "unanswered", s["warm_waiting"] > 0),
    ]
    return '<dl class="status">' + "".join(
        f'<div class="stat{" alert" if a else ""}"><dt>{k}</dt><dd>{v}<small>{sub}</small></dd></div>'
        for k, v, sub, a in cells) + "</dl>"


def rows(where: str, params=()) -> list[dict]:
    with db() as c, c.cursor() as cur:
        cur.execute(f"""
            SELECT DISTINCT ON (p.id) e.id, c.name, c.employees, c.country,
                   r.score, r.wedge, r.primary_trigger, r.raw->>'reasoning',
                   p.first_name, p.last_name, p.title, p.email, e.subject, e.body,
                   e.approved, e.approved_at
            FROM emails e
            JOIN prospects p ON p.id = e.prospect_id
            JOIN companies c ON c.id = p.company_id
            JOIN research  r ON r.company_id = c.id
            WHERE {where}
            ORDER BY p.id, r.created_at DESC""", params)
        cols = ["id","name","employees","country","score","wedge","trigger","reasoning",
                "first_name","last_name","title","email","subject","body","approved","approved_at"]
        out = [dict(zip(cols, r)) for r in cur.fetchall()]
    out.sort(key=lambda x: -(x["score"] or 0))
    return out


def card(x: dict, n, actions=True) -> str:
    nm = f"{x['first_name'] or ''} {x['last_name'] or ''}".strip()
    emp = f"{x['employees']:,} employees" if x["employees"] else ""
    state = ('<span class="pill ok">approved</span>' if x["approved"]
             else '<span class="pill no">rejected</span>' if x["approved"] is False else "")
    acts = f"""<form class="acts" method="post" action="/decide">
      <input type="hidden" name="ids" value="{x['id']}">
      <button class="go" name="verdict" value="yes">Approve</button>
      <button class="stop" name="verdict" value="no">Reject</button>
    </form>""" if actions else ""
    return f"""<article class="card">
  <div class="head"><span class="co">{n}. {H.escape(x['name'] or '')}</span>
    <span class="to">→ {H.escape(nm)}, {H.escape(x['title'] or '')}</span>
    <span class="sp"></span><span class="pill w">{(x['wedge'] or '').replace('_',' ')}</span>
    <span class="score">{x['score']}</span>{state}</div>
  <p class="trig"><b>Trigger —</b> {H.escape((x['trigger'] or '')[:230])}<br>
    <b>To —</b> {H.escape(x['email'] or '')}{' · ' + emp if emp else ''}</p>
  <p class="subj">subject: <b>{H.escape(x['subject'] or '')}</b></p>
  <div class="msg">{H.escape(x['body'] or '')}</div>
  <p class="why"><b>Scored {x['score']} —</b> {H.escape((x['reasoning'] or '')[:260])}</p>
  {acts}</article>"""


@app.get("/queue", response_class=HTMLResponse)
def queue(request: Request):
    s = stats()
    items = rows("e.approved IS NULL")
    u = request.state.user
    if not items:
        body = strip("Queue", s) + '<div class="empty">Nothing waiting. The pipeline will add more.</div>'
        return page("Approve", "queue", body, u)
    ids = ",".join(str(x["id"]) for x in items)
    bulk = f"""<form class="bulk" method="post" action="/decide">
      <span>{len(items)} waiting. Read four or five — the rest are built identically.</span>
      <input type="hidden" name="ids" value="{ids}">
      <button class="go" name="verdict" value="yes">Approve all {len(items)}</button></form>"""
    body = strip("Queue", s) + bulk + "".join(card(x, i) for i, x in enumerate(items, 1))
    return page("Approve", "queue", body, u)


@app.post("/decide")
def decide(request: Request, ids: str = Form(...), verdict: str = Form(...)):
    id_list = [int(i) for i in ids.split(",") if i.strip().isdigit()]
    if id_list:
        review.decide(id_list, verdict == "yes", by=request.state.user["email"])
    return RedirectResponse("/queue", status_code=303)


@app.get("/sent", response_class=HTMLResponse)
def sent(request: Request):
    items = rows("e.approved IS TRUE")
    body = strip("Approved", stats()) + (
        "".join(card(x, i, actions=False) for i, x in enumerate(items, 1))
        or '<div class="empty">Nothing approved yet.</div>')
    return page("Approved", "sent", body, request.state.user)


@app.get("/rejected", response_class=HTMLResponse)
def rejected(request: Request):
    with db() as c, c.cursor() as cur_:
        cur_.execute("""SELECT name, stage, rejected_reason,
                        (SELECT score FROM research WHERE company_id=companies.id
                         ORDER BY created_at DESC LIMIT 1)
                        FROM companies WHERE stage='rejected'
                        ORDER BY updated_at DESC LIMIT 200""")
        rs = cur_.fetchall()
    trs = "".join(
        f"<tr><td>{H.escape(n or '')}</td><td class='n'>{sc if sc is not None else '—'}</td>"
        f"<td class='reason'>{H.escape(rr or '')}</td></tr>" for n, st, rr, sc in rs)
    body = strip("Rejected", stats()) + f"""<h2>Rejected — most recent 200</h2>
      <div class="tw"><table><thead><tr><th>Company</th><th>Score</th>
      <th>Why</th></tr></thead><tbody>{trs}</tbody></table></div>"""
    return page("Rejected", "rejected", body, request.state.user)


@app.get("/health", response_class=HTMLResponse)
def health(request: Request):
    d = review.digest()
    with db() as c, c.cursor() as cur:
        cur.execute("""SELECT address, provider, status, daily_cap, warmup_start
                       FROM mailboxes ORDER BY domain, address""")
        mb = cur.fetchall()
        cur.execute("""SELECT stage, count(*) FROM companies GROUP BY stage ORDER BY 2 DESC""")
        st = cur.fetchall()
    mrows = "".join(f"<tr><td>{H.escape(a)}</td><td>{p}</td><td>{s}</td>"
                    f"<td class='n'>{c_}</td><td>{w or '—'}</td></tr>" for a, p, s, c_, w in mb)
    srows = "".join(f"<tr><td>{s}</td><td class='n'>{n}</td></tr>" for s, n in st)
    drows = "".join(f"<tr><td>{k.replace('_',' ')}</td><td class='n'>{v}</td></tr>"
                    for k, v in d.items())
    body = strip("Health", stats()) + f"""
      <h2>Mailboxes</h2><div class="tw"><table><thead><tr><th>Address</th><th>Provider</th>
      <th>Status</th><th>Cap</th><th>Warmup started</th></tr></thead><tbody>{mrows}</tbody></table></div>
      <h2>Pipeline</h2><div class="tw"><table><tbody>{srows}</tbody></table></div>
      <h2>Today</h2><div class="tw"><table><tbody>{drows}</tbody></table></div>"""
    return page("Health", "health", body, request.state.user)


LAUNCH = date(2026, 8, 19)


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    """Everything in one place: what came in today, what needs you, what goes out."""
    u = request.state.user
    today = date.today()
    with db() as c, c.cursor() as cur:
        cur.execute("""
            SELECT
              (SELECT count(*) FROM companies WHERE created_at::date = %(d)s),
              (SELECT count(*) FROM research  WHERE created_at::date = %(d)s),
              (SELECT count(*) FROM emails    WHERE created_at::date = %(d)s),
              (SELECT count(*) FROM emails    WHERE approved IS NULL),
              (SELECT count(*) FROM emails    WHERE approved IS TRUE
                 AND id NOT IN (SELECT email_id FROM sends)),
              (SELECT count(*) FROM sends     WHERE sent_at::date = %(d)s),
              (SELECT count(*) FROM replies   WHERE received_at::date = %(d)s),
              (SELECT count(*) FROM replies   WHERE classification IN
                 ('interested','referral') AND NOT handled)
        """, {"d": today})
        (new_co, researched, written, pending, ready,
         sent_today, replies_today, warm_open) = cur.fetchone()

        cur.execute("""SELECT focus, owner, target, done FROM plan_days
                       WHERE day = %s ORDER BY owner DESC""", (today,))
        plan_today = cur.fetchall()

        cur.execute("""SELECT r.from_email, r.classification, r.subject, rp.full_name
                       FROM replies r LEFT JOIN reps rp ON rp.id = r.routed_rep_id
                       WHERE NOT r.handled ORDER BY r.received_at DESC LIMIT 6""")
        open_replies = cur.fetchall()

    nums = [
        ("Needs you", pending, "to approve", pending > 0),
        ("Ready to send", ready, "approved, unsent", False),
        ("Sourced today", new_co, "new companies", False),
        ("Researched today", researched, "scored by Opus", False),
        ("Written today", written, "drafted by Fable", False),
        ("Sent today", sent_today, "emails", False),
        ("Replies today", replies_today, "received", False),
        ("Warm & open", warm_open, "unanswered", warm_open > 0),
    ]
    grid = '<dl class="status">' + "".join(
        f'<div class="stat{" alert" if a else ""}"><dt>{k}</dt>'
        f'<dd>{v}<small>{sub}</small></dd></div>' for k, v, sub, a in nums) + "</dl>"

    days_out = (LAUNCH - today).days
    if days_out > 0:
        banner = (f'<p class="lede">Not sending yet — mailboxes are still warming. '
                  f'First real send is <b>Wednesday 19 August</b>, {days_out} days away. '
                  f'Until then the job is to bank approved emails so day one starts full.</p>')
    else:
        banner = (f'<p class="lede">Live. Sending from 3 mailboxes, '
                  f'{sent_today} gone out today.</p>')

    # Next five awaiting approval, so the front page is actionable, not just a report.
    nxt = rows("e.approved IS NULL")[:5]
    if nxt:
        peek = "".join(
            f'<div class="mini"><b>{H.escape(x["name"] or "")}</b> '
            f'<small>→ {H.escape(x["title"] or "")} · score {x["score"]} · '
            f'{(x["wedge"] or "").replace("_", " ")}</small><br>'
            f'<small>{H.escape((x["subject"] or "")[:90])}</small></div>' for x in nxt)
        approve_col = (f"<h2>Waiting for you — {pending} total</h2>{peek}"
                       f'<a class="more" href="/queue">Read and approve →</a>')
    else:
        approve_col = ('<h2>Waiting for you</h2>'
                       '<div class="empty">Nothing to approve right now.</div>')

    if open_replies:
        rep = "".join(
            f'<div class="mini"><b>{H.escape(fe or "")}</b> '
            f'<small>· {H.escape(cl or "unclassified")}'
            f'{" · " + H.escape(rn) if rn else ""}</small><br>'
            f'<small>{H.escape((sj or "")[:80])}</small></div>'
            for fe, cl, sj, rn in open_replies)
        reply_col = f"<h2>Replies not yet handled</h2>{rep}"
    else:
        reply_col = ('<h2>Replies not yet handled</h2>'
                     '<div class="empty">No open replies.</div>')

    if plan_today:
        pt = "".join(
            f'<div class="mini">{"&#10003; " if dn else ""}<b>{H.escape(f)}</b><br>'
            f'<small>{H.escape(o)} · target {H.escape(t or "—")}</small></div>'
            for f, o, t, dn in plan_today)
    else:
        pt = '<div class="empty">Nothing scheduled today.</div>'

    body = (grid + banner +
            f'<h2>Today — {today.strftime("%A %d %B")}</h2>{pt}'
            f'<div class="two"><div>{approve_col}</div><div>{reply_col}</div></div>')
    return page("Today", "home", body, u)


@app.get("/plan", response_class=HTMLResponse)
def plan(request: Request):
    today = date.today()
    with db() as c, c.cursor() as cur:
        cur.execute("""SELECT id, day, week, phase, focus, owner, target, done, note
                       FROM plan_days ORDER BY day, owner DESC, id""")
        items = cur.fetchall()

    # Week header shows what that week is FOR, not just its dates.
    weeks, order = {}, []
    for it in items:
        if it[2] not in weeks:
            weeks[it[2]] = []
            order.append(it[2])
        weeks[it[2]].append(it)

    out = []
    for w in order:
        rs = weeks[w]
        d0, d1 = rs[0][1], rs[-1][1]
        phases = " · ".join(dict.fromkeys(r[3] for r in rs))
        left = sum(1 for r in rs if not r[7])
        out.append(f'<div class="wk">Week {w} — {d0.strftime("%d %b")} to '
                   f'{d1.strftime("%d %b")} — {phases} — {left} open</div>')
        trs = []
        for pid, d, _w, ph, focus, owner, target, done, note in rs:
            cls = " ".join(x for x in ("today" if d == today else "",
                                       "done" if done else "") if x)
            oc = f"own {owner}" if owner in ("ashok", "devops") else "own"
            trs.append(
                f'<tr class="{cls}">'
                f'<td class="day">{d.strftime("%d %b")}<small>{d.strftime("%a")}</small></td>'
                f'<td><span class="{oc}">{H.escape(owner)}</span></td>'
                f'<td class="f">{H.escape(focus)}'
                + (f'<br><small style="color:var(--muted)">{H.escape(note)}</small>' if note else "")
                + f'</td><td class="n">{H.escape(target or "—")}</td>'
                f'<td><form method="post" action="/plan/done">'
                f'<input type="hidden" name="pid" value="{pid}">'
                f'<button class="tick{" on" if done else ""}" '
                f'title="mark {"not done" if done else "done"}">'
                f'{"&#10003;" if done else "&#9675;"}</button></form></td></tr>')
        out.append('<div class="tw"><table><tbody>' + "".join(trs) + "</tbody></table></div>")

    days_out = (LAUNCH - today).days
    when = (f"{days_out} days from now" if days_out > 0
            else "today" if days_out == 0 else f"{-days_out} days ago")
    lede = (f'<p class="lede">First real send is <b>Wednesday 19 August</b> — {when}. '
            "Everything before it is warmup and banking approved emails, so day one "
            "starts with a full queue instead of an empty one. Weekends are deliberately "
            "blank: cold mail sent at a weekend gets deleted on Monday.</p>")
    return page("Plan", "plan", strip("Plan", stats()) + lede + "".join(out), request.state.user)


@app.post("/plan/done")
def plan_done(pid: int = Form(...)):
    with db() as c, c.cursor() as cur:
        cur.execute("UPDATE plan_days SET done = NOT done WHERE id=%s", (pid,))
    return RedirectResponse("/plan", status_code=303)


STAGE_LABEL = {"sourced": "not yet researched", "qualified": "passed research",
               "queued": "email written", "rejected": "rejected"}

CONTACTED_SQL = """
    SELECT c.name, c.domain, c.country, p.first_name, p.last_name, p.title,
           p.email,
           CASE WHEN s.sent_at IS NOT NULL THEN 'sent'
                WHEN e.approved IS TRUE     THEN 'approved, not yet sent'
                WHEN e.approved IS FALSE    THEN 'rejected by you'
                ELSE 'drafted, awaiting approval' END AS status,
           s.sent_at, e.subject, r.full_name AS rep
    FROM emails e
    JOIN prospects p  ON p.id = e.prospect_id
    JOIN companies c  ON c.id = p.company_id
    LEFT JOIN sends s ON s.email_id = e.id
    LEFT JOIN mailboxes m ON m.id = s.mailbox_id
    LEFT JOIN reps r  ON r.id = m.rep_id
    ORDER BY s.sent_at DESC NULLS LAST, c.name
"""


@app.get("/contacted", response_class=HTMLResponse)
def contacted(request: Request):
    """Every company that has an email in the system, so nobody double-mails.

    Deliberately includes drafts and approved-but-unsent, not only sent: a rep
    who mails someone we are about to mail causes the same collision.
    """
    u = request.state.user
    with db() as c_, c_.cursor() as cur:
        cur.execute(CONTACTED_SQL)
        rs = cur.fetchall()

    trs = "".join(
        f'<tr><td><b>{H.escape(nm or "")}</b><br>'
        f'<small style="color:var(--muted)">{H.escape(dom or "")}</small></td>'
        f'<td>{H.escape(co or "—")}</td>'
        f'<td>{H.escape(f"{fn or ""} {ln or ""}".strip())}<br>'
        f'<small style="color:var(--muted)">{H.escape(ti or "")}</small></td>'
        f'<td><small>{H.escape(em or "")}</small></td>'
        f'<td><small>{H.escape(st)}</small></td>'
        f'<td><small>{sent.strftime("%d %b %H:%M") if sent else "—"}</small></td>'
        f'<td><small>{H.escape(rep or "—")}</small></td></tr>'
        for nm, dom, co, fn, ln, ti, em, st, sent, subj, rep in rs)

    body = strip("Contacted", stats()) + (
        '<p class="lede">Every company with an email in the system — sent, '
        'approved, or still a draft. Give this to the team before they mail '
        'anyone: a rep writing to someone we are <i>about</i> to write to '
        'causes the same collision as a duplicate send. '
        '<a class="more" href="/contacted.csv">Download CSV</a></p>'
        f'<h2>{len(rs)} companies contacted or queued</h2>'
        '<div class="tw"><table><thead><tr><th>Company</th><th>Country</th>'
        '<th>Person</th><th>Email</th><th>Status</th><th>Sent</th><th>Rep</th>'
        f'</tr></thead><tbody>{trs}</tbody></table></div>'
        if rs else '<div class="empty">Nothing contacted yet.</div>')
    return page("Contacted", "contacted", body, u)


@app.get("/contacted.csv")
def contacted_csv(request: Request):
    import csv
    import io
    with db() as c_, c_.cursor() as cur:
        cur.execute(CONTACTED_SQL)
        rs = cur.fetchall()
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["company", "domain", "country", "first_name", "last_name",
                "title", "email", "status", "sent_at", "subject", "rep"])
    for row in rs:
        w.writerow(["" if v is None else v for v in row])
    return PlainTextResponse(
        buf.getvalue(), media_type="text/csv",
        headers={"Content-Disposition":
                 'attachment; filename="origami-contacted.csv"'})


@app.get("/targets", response_class=HTMLResponse)
def targets(request: Request, country: str = "", segment: str = "",
            stage: str = "", limit: int = 300):
    """Every company by name, with where it is and what it would be offered."""
    u = request.state.user
    where, params = ["TRUE"], {}
    if country:
        where.append("c.country = %(country)s"); params["country"] = country
    if segment:
        where.append("c.segment = %(segment)s"); params["segment"] = segment
    if stage:
        where.append("c.stage::text = %(stage)s"); params["stage"] = stage
    params["lim"] = max(1, min(limit, 2000))

    with db() as c_, c_.cursor() as cur:
        cur.execute(f"""
            SELECT c.name, c.domain, c.country, c.employees, c.segment,
                   c.stage::text, r.score, r.wedge, r.primary_trigger
            FROM companies c
            LEFT JOIN LATERAL (
              SELECT score, wedge, primary_trigger FROM research
              WHERE company_id = c.id ORDER BY created_at DESC LIMIT 1
            ) r ON TRUE
            WHERE {' AND '.join(where)}
              AND NOT EXISTS (SELECT 1 FROM suppression sp
                              WHERE (sp.kind = 'domain' AND sp.value = c.domain)
                                 OR (sp.kind = 'name'
                                     AND c.name ~* ('\\m' || sp.value || '\\M')))
            ORDER BY r.score DESC NULLS LAST, c.name
            LIMIT %(lim)s""", params)
        rowset = cur.fetchall()
        cur.execute("SELECT count(*) FROM companies c WHERE " + " AND ".join(where),
                    {k: v for k, v in params.items() if k != "lim"})
        total = cur.fetchone()[0]
        cur.execute("""SELECT coalesce(country,'not recorded'), count(*)
                       FROM companies GROUP BY 1 ORDER BY 2 DESC""")
        by_country = cur.fetchall()
        cur.execute("""SELECT coalesce(c.segment,'not recorded'),
                              coalesce(s.offer,'—'), count(*)
                       FROM companies c
                       LEFT JOIN segments s ON s.code = c.segment
                       GROUP BY 1,2 ORDER BY 3 DESC""")
        by_segment = cur.fetchall()

    def opts(name, values, cur_val):
        o = "".join(
            f'<option value="{H.escape(str(v))}"'
            f'{" selected" if str(v) == cur_val else ""}>{H.escape(str(v))}</option>'
            for v in values)
        return (f'<label>{name}<select name="{name.lower()}">'
                f'<option value="">all</option>{o}</select></label>')

    filt = (f'<form class="filters" method="get" action="/targets">'
            + opts("Country", [c for c, _ in by_country if c != "not recorded"], country)
            + opts("Segment", sorted({s for s, _, _ in by_segment if s != "not recorded"}), segment)
            + opts("Stage", ["sourced", "qualified", "queued", "rejected"], stage)
            + '<button type="submit">Filter</button>'
            + (' <a class="more" href="/targets">clear</a>' if (country or segment or stage) else "")
            + "</form>")

    trs = "".join(
        f'<tr><td><b>{H.escape(nm or "")}</b><br>'
        f'<small style="color:var(--muted)">{H.escape(dom or "")}</small></td>'
        f'<td>{H.escape(co or "—")}</td>'
        f'<td class="n">{f"{emp:,}" if emp else "—"}</td>'
        f'<td>{H.escape((seg or "—").replace("_", " "))}</td>'
        f'<td>{("<span class=\'pill w\'>" + wg.replace("_", " ") + "</span>") if wg else "—"}</td>'
        f'<td class="n">{sc if sc is not None else "—"}</td>'
        f'<td><small>{H.escape(STAGE_LABEL.get(st, st or ""))}</small></td>'
        f'<td style="color:var(--muted)"><small>{H.escape((tr or "")[:120])}</small></td></tr>'
        for nm, dom, co, emp, seg, st, sc, wg, tr in rowset)

    cs = "".join(f'<tr><td>{H.escape(c)}</td><td class="n">{n}</td></tr>'
                 for c, n in by_country)
    ss = "".join(f'<tr><td>{H.escape(s.replace("_", " "))}</td>'
                 f'<td>{H.escape(o.replace("_", " "))}</td><td class="n">{n}</td></tr>'
                 for s, o, n in by_segment)

    unknown = next((n for c, n in by_country if c == "not recorded"), 0)
    warn = (f'<p class="lede"><b class="hold">{unknown} companies have no country '
            f'recorded.</b> Apollo\'s company search returns no location field at '
            f'all, so until 1 August we filtered by country and then threw the '
            f'answer away. Sourcing now runs one country at a time and records it. '
            f'The older rows fill in as they reach enrichment.</p>') if unknown else ""

    body = strip("Companies", stats()) + warn + filt + f"""
      <p class="lede">Every company here is real, including the ones whose
      website we could not read &mdash; those say <b>site unreachable</b> rather
      than disappearing. <a class="more" href="/targets.csv?country={H.escape(country)}&amp;segment={H.escape(segment)}&amp;stage={H.escape(stage)}">Download this list as CSV</a></p>
      <h2>{len(rowset)} shown of {total} matching — highest score first</h2>
      <div class="tw"><table><thead><tr><th>Company</th><th>Country</th>
      <th>Staff</th><th>Segment</th><th>Offer</th><th>Score</th><th>Stage</th>
      <th>Trigger</th></tr></thead><tbody>{trs}</tbody></table></div>
      <div class="two">
        <div><h2>By country</h2><div class="tw"><table><tbody>{cs}</tbody></table></div></div>
        <div><h2>By segment and offer</h2><div class="tw"><table><tbody>{ss}</tbody></table></div></div>
      </div>"""
    return page("Companies", "targets", body, u)


TARGETS_SQL = """
    SELECT c.name, c.domain, c.country, c.employees, c.segment, s.offer,
           c.stage::text, r.score, r.wedge, r.primary_trigger,
           c.rejected_reason,
           (SELECT t.detail FROM triggers t
             WHERE t.company_id = c.id AND t.kind = 'profile'
             ORDER BY t.observed_at DESC LIMIT 1) AS verified_quote,
           (SELECT t.evidence_url FROM triggers t
             WHERE t.company_id = c.id AND t.kind = 'profile'
             ORDER BY t.observed_at DESC LIMIT 1) AS evidence_url
    FROM companies c
    LEFT JOIN segments s ON s.code = c.segment
    LEFT JOIN LATERAL (
      SELECT score, wedge, primary_trigger FROM research
      WHERE company_id = c.id ORDER BY created_at DESC LIMIT 1
    ) r ON TRUE
    WHERE {where}
      -- Suppressed companies are EXCLUDED, not merely marked rejected. The NDA
      -- client's subsidiary appeared in a published target list with the status
      -- 'rejected' next to it - which still printed the client's name in a
      -- targeting document. Suppression has to mean absent.
      AND NOT EXISTS (SELECT 1 FROM suppression sp
                      WHERE (sp.kind = 'domain' AND sp.value = c.domain)
                         OR (sp.kind = 'name'
                             AND c.name ~* ('\\m' || sp.value || '\\M')))
    ORDER BY r.score DESC NULLS LAST, c.name
"""

TARGET_COLS = ["company", "domain", "country", "employees", "segment", "offer",
               "stage", "score", "wedge", "opening_fact", "why_not",
               "verified_quote", "evidence_url"]


@app.get("/targets.csv")
def targets_csv(request: Request, country: str = "", segment: str = "",
                stage: str = ""):
    """The whole list, unreachable sites included.

    A company whose website we could not read is still a real company - it is
    reported with `stage = rejected` and a plain reason, never dropped. The
    team can find those by hand.
    """
    import csv
    import io
    where, params = ["TRUE"], {}
    if country:
        where.append("c.country = %(country)s"); params["country"] = country
    if segment:
        where.append("c.segment = %(segment)s"); params["segment"] = segment
    if stage:
        where.append("c.stage::text = %(stage)s"); params["stage"] = stage
    with db() as c_, c_.cursor() as cur:
        cur.execute(TARGETS_SQL.format(where=" AND ".join(where)), params)
        rows = cur.fetchall()
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(TARGET_COLS)
    for row in rows:
        w.writerow(["" if v is None else v for v in row])
    tag = "-".join(x for x in (country, segment, stage) if x) or "all"
    return PlainTextResponse(
        buf.getvalue(), media_type="text/csv",
        headers={"Content-Disposition":
                 f'attachment; filename="origami-targets-{tag}.csv"'})


@app.get("/territory", response_class=HTMLResponse)
def territory(request: Request):
    with db() as c, c.cursor() as cur:
        cur.execute("""SELECT r.code, r.name, r.countries, r.priority, r.coverage, r.notes,
                       (SELECT count(*) FROM companies co
                        WHERE co.country = ANY(r.countries)) AS sourced
                       FROM regions r ORDER BY r.priority""")
        regs = cur.fetchall()
        cur.execute("""SELECT code, name, offer, min_employees, max_employees,
                       priority, why FROM segments ORDER BY priority, code""")
        segs = cur.fetchall()
        cur.execute("SELECT label, wedge, segments, detail, nda, caution "
                    "FROM client_proof ORDER BY nda DESC, label")
        cps = cur.fetchall()

    rrows = "".join(
        f'<tr><td class="n">{p}</td><td><b>{H.escape(n)}</b><br>'
        f'<small style="color:var(--muted)">{H.escape(", ".join(cs))}</small></td>'
        f'<td>{"<span class=hold>thin</span>" if cov == "thin" else cov}</td>'
        f'<td class="n">{src:,}</td>'
        f'<td style="color:var(--muted)">{H.escape(note or "")}</td></tr>'
        for code, n, cs, p, cov, note, src in regs)

    def size(lo, hi):
        return f"{lo:,}+" if hi is None else f"{lo:,}–{hi:,}"

    srows = "".join(
        f'<tr><td><b>{H.escape(n)}</b></td>'
        f'<td><span class="pill w">{o.replace("_", " ")}</span></td>'
        f'<td class="n">{size(lo, hi)}</td>'
        f'<td style="color:var(--muted)">{H.escape(why)}</td></tr>'
        for code, n, o, lo, hi, p, why in segs)

    crows = "".join(
        f'<tr><td><b>{H.escape(lbl)}</b>{" <span class=nda>nda</span>" if nda else ""}</td>'
        f'<td><span class="pill w">{w.replace("_", " ")}</span></td>'
        f'<td style="color:var(--muted)">{H.escape(det)}'
        + (f'<br><b style="color:var(--kill)">{H.escape(caut)}</b>' if caut else "")
        + "</td></tr>"
        for lbl, w, sg, det, nda, caut in cps)

    lede = ('<p class="lede">Broad targeting, narrow message. The company\'s <b>size and '
            'document load</b> pick the offer, not its industry label: a 5,000-person '
            'insurer and a 5,000-person retailer with 3,000 suppliers get the same '
            'Document Intelligence pitch, while a 400-person consumer brand gets an app. '
            'A region is only worked once a trigger can actually be found in it.</p>')

    body = strip("Territory", stats()) + lede + f"""
      <h2>Regions — worked in priority order</h2>
      <div class="tw"><table><thead><tr><th>#</th><th>Region</th><th>Trigger data</th>
      <th>Sourced</th><th>Why</th></tr></thead><tbody>{rrows}</tbody></table></div>
      <h2>Segments — who gets which offer</h2>
      <div class="tw"><table><thead><tr><th>Segment</th><th>Offer</th><th>Headcount</th>
      <th>Why this offer</th></tr></thead><tbody>{srows}</tbody></table></div>
      <h2>Proof the emails may cite</h2>
      <div class="tw"><table><thead><tr><th>Client</th><th>Wedge</th>
      <th>What may be said</th></tr></thead><tbody>{crows}</tbody></table></div>"""
    return page("Territory", "territory", body, request.state.user)
