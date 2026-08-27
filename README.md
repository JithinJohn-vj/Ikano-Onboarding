# Ikano-style Onboarding Sample

A small Django app demonstrating an adaptive customer onboarding flow across
3 countries (Sweden, Spain, Poland) x 2 account types (private individual,
business) = 6 flows, with mocked KYC, KYB, sanctions/PEP, credit bureau and
bank-account checks, and a deterministic decisioning layer.

This is a sample/demo. **No real external services are called** — every
check (identity, address, registry, authority, sanctions, credit, bank) is a
deterministic mock described in `onboarding/integrations/`.

---

## 1. Requirements

- Python 3.11+ (developed against 3.12)
- PostgreSQL 14+ (developed against PostgreSQL 14.18)
- No external service calls or API keys are needed at runtime

## 2. Installation

```bash
# 1. Get the code
cd ikano-onboarding

# 2. Create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Create the local PostgreSQL database (skip if it already exists)
createdb -h 127.0.0.1 -U "$USER" ikano_onboarding

# 5. Apply database migrations (creates the PostgreSQL schema)
python manage.py migrate

# 6. (optional) create an admin user, to browse applications/audit trail at /admin/
python manage.py createsuperuser

# 7. Run the dev server
python manage.py runserver
```

Then open **http://127.0.0.1:8000/** in a browser.

### PostgreSQL configuration

By default the app connects to a local PostgreSQL database named
`ikano_onboarding` on `127.0.0.1:5432`, using your current system username.
Override any connection setting when needed:

```bash
export POSTGRES_DB=ikano_onboarding
export POSTGRES_USER=your_database_user
export POSTGRES_PASSWORD=your_database_password
export POSTGRES_HOST=127.0.0.1
export POSTGRES_PORT=5432
```

### Security configuration

Set a persistent secret before running a long-lived environment. Without it,
the app generates an in-memory development secret and existing sessions are
invalidated when the server restarts.

```bash
export DJANGO_SECRET_KEY="replace-with-a-long-random-value"
```

For an HTTPS deployment, enable secure cookies and HTTPS redirection:

```bash
export DJANGO_SECURE_COOKIES=1
export DJANGO_FORCE_HTTPS=1
```

`DJANGO_DEBUG` is disabled by default. Set `DJANGO_DEBUG=1` only for local
debugging. Resume-token attempts are rate limited; production should use a
shared cache such as Redis for that limit. `DJANGO_SERVE_STATIC_FILES=1` is
enabled locally; set it to `0` when a production web server/CDN serves static
assets.

The Codex embedded browser sends an opaque `Origin: null` when accessing the
loopback development server. A narrowly scoped middleware accepts that origin
only for `127.0.0.1` and `localhost`, and only after Django validates the CSRF
token. It has no effect on non-loopback hosts.

## 3. Running the tests

```bash
pytest
```

`pytest` is the standard test command and includes an on-screen coverage
report (the current suite has 86 tests and 94% coverage). The Django test
runner remains available when needed:

```bash
python manage.py test onboarding
```

The test suite covers flow configuration, every mock integration (determinism +
forced outcomes), the decisioning engine, field validation, sensitive-data
redaction, the full application lifecycle (start → steps → decision), resume
tokens, and view-level access control.

## 4. Demo walkthrough

1. Go to `/`, pick a country and account type (e.g. Sweden + Private
   individual).
2. Fill in each step. All fields are validated server-side (try leaving one
   blank, or typing an invalid personnummer/DNI/PESEL/etc. — the pattern is
   country-specific).
3. After steps that run a check (identity, registry, sanctions, credit,
   bank), the outcome is recorded and visible on the final **Review** page
   before you submit.
4. Submit on the Review page to get a final decision: **approved**,
   **manual review**, or **rejected**, with reasons.
5. From the result page, click **View audit trail** to see every event
   logged for that application (step completions, integration calls and
   results, the final decision) — this is also fully browsable per
   application in **Django admin** (`/admin/`) if you created a superuser.

### Forcing specific outcomes for the demo

Every mock integration is deterministic (same input -> same output), but you
can force a specific branch by including a keyword in the relevant field:

| Type into... | Forces |
|---|---|
| a full legal name or company legal name containing `FAIL` | a hard-fail outcome for the related identity/registry check; a name is also sanctions-screened, so this can reject the application |
| a full legal name, company legal name, or city containing `REVIEW` | a manual-review outcome for the related check |
| a UBO or representative name containing `CONFIRMEDHIT` | a confirmed sanctions/PEP hit (always rejects) |
| a valid IBAN containing `TIMEOUT` | the bank check stays `unreachable` even after retries |

Example: enter `Fail Example` as an individual's full legal name. The identity
check returns `document_mismatch` and the sanctions check returns a confirmed
hit, so the application is rejected at review. Ordinary valid input is
deterministic-but-effectively-random based on a hash of the input, weighted to
mostly pass (matching a realistic population).

### Credit and affordability criteria

The credit-bureau outcome is a deterministic mock based on a keyed customer
reference. Normal inputs are weighted strongly toward a **strong** result;
**moderate** or **weak** requires manual review, and **insufficient** rejects.
This simulates the independent result of an external bureau, so a customer
can pass affordability but still need manual review because their mocked
bureau outcome is moderate or weak. The user-facing flow passes a keyed,
non-reversible customer reference to the credit mock rather than retaining a
raw identifier; exceptional credit outcomes are therefore exercised in the
automated integration tests rather than by placing magic text in an ID field.

For individual applications, monthly disposable income is calculated as:

```
net income - housing costs - other living costs - debt payments
           - (dependants × 350)
```

The requested amount must be positive and no more than 36 times this monthly
amount. A debt-to-income ratio above 40%, or fewer than six months in stable
employment, also requires manual review. These thresholds
are deliberately simple demo assumptions, not a real lending policy.

### Resuming an application

When you start an application, a resume link is shown in a flash message at
the top of the page (format: `/resume/<token>/`). Copy the token (the part
after `/resume/`) and paste it into **"Resume an application"** (top nav) to
pick the application back up — this works even from a different browser
session, since the token (not the browser session) is what grants access.

---

## 5. Assumptions & things deliberately left out

- **Authentication is a session-capability model, not real auth.** An
  applicant is granted access to their own application in their browser
  session when they create or resume it (resume tokens are the recovery
  mechanism if the session is lost). There's no login system, no separate
  "applicant" vs "staff" account model. A real deployment would add proper
  authentication and put the audit-trail view behind staff-only auth
  (noted directly in `audit.html` and in `views.py`).
- **Resume link is shown in-app, not emailed.** There's no mail
  infrastructure in scope, so the magic link is displayed directly rather
  than sent to an email address. The token mechanism (hashed at rest,
  expiring, unguessable) is the same either way.
- **No going back to edit a previous step once submitted.** This keeps the
  state machine simple and avoids re-running checks on stale data. A
  production version would likely add an explicit "edit a previous answer"
  path with rules about which checks need to re-run if the input changed.
- **Abandoned-application detection is on-access, not a background job.**
  `Application.mark_touched()` flips a long-idle `in_progress` application
  to `abandoned` the next time anyone loads it. A real deployment would
  probably also run a periodic sweep so idle applications don't sit
  "in progress" forever if nobody ever returns.
- **No real national ID / registry / credit bureau / bank integrations**,
  per the brief — all 7 mocks are deterministic and clearly labelled as
  mocks throughout the UI and code.
- **Country-specific ID validation is pattern-level, not checksum-level**
  (e.g. Spanish DNI's control-letter checksum isn't verified) — the brief
  is explicit that "the exact country rules are not the point of the
  exercise."
- **PostgreSQL, single dev server, no deployment config** — appropriate for
  a timeboxed sample; see `ARCHITECTURE.md` for what would change for
  production.

See `ARCHITECTURE.md` for the system design, module boundaries, and the
reasoning behind the bigger structural decisions (why Django, why the flow
is data-driven, how sensitive data is handled, etc).
