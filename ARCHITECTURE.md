# Architecture note

## Layers and module boundaries

```
onboarding/
├── flows/          Layer 1: what steps exist, for which country/account type
├── integrations/   Layer 2: mocked external checks (typed request/response)
├── decisioning/    Layer 3: integration results -> approved/manual_review/rejected
├── services/        Orchestration glue between the layers above and the DB
├── models.py         Persistence: Application, StepAnswer, IntegrationResult, AuditEvent
├── views.py / urls.py  Thin HTTP layer -> calls services only
├── admin.py           Django admin registration (audit/inspection "for free")
└── templates/          Generic, schema-driven form rendering
```

Dependency direction is one-way: `views -> services -> {flows, integrations,
decisioning, models}`. `decisioning/engine.py` doesn't import Django or the
ORM at all — it takes duck-typed objects with `.check_type` / `.outcome`,
which is what makes it trivially unit-testable in isolation.

## Data model

- **Application** — one row per onboarding attempt. UUID primary key
  (never a sequential/guessable ID), `country`, `account_type`, `status`
  (`in_progress` / `submitted` / `manual_review` / `approved` / `rejected`
  / `abandoned` / `expired`), `current_step_key`, hashed resume token +
  expiry, final `decision_outcome` / `decision_reasons`.
- **StepAnswer** — one row per completed step, `data` JSON with
  field-name -> value. Fields flagged `sensitive=True` in the flow schema
  are masked (see Redaction below) before this row is ever written.
- **IntegrationResult** — one row per mock check call: `check_type`,
  `outcome`, a `details` JSON restricted to decision-relevant, non-sensitive
  fields (score, confidence, boolean flags — never raw IDs/IBANs/names),
  `latency_ms`, `attempt_count` (for the bank check's retry simulation).
- **AuditEvent** — append-only: `event_type`, a sanitized `message`, and
  sanitized `metadata`. Every meaningful action logs one of these:
  `application_created`, `step_completed`, `integration_result`,
  `decision_made`, `resumed`.

All four are registered in Django admin with inlines, so an application's
full history — answers, integration results, and audit trail — is
browsable in one place without any custom tooling.

## How flows are configured

The core "senior signal" the brief asks for is avoiding a large nested
if/else tree as countries/account types/steps grow. The mechanism:

1. **`flows/schema.py`** defines `Field`, `Step`, `Flow` as frozen
   dataclasses. A flow is just an ordered tuple of steps; a step is a title
   + a tuple of fields + an optional `IntegrationSpec`.
2. **`flows/country_config.py`** holds the only things that differ between
   Sweden, Spain and Poland as plain data: ID label/pattern/help text,
   provider names (BankID vs Cl@ve vs eID), registry name, credit bureau
   name, address-region label.
3. **`flows/definitions.py`** has exactly two builder functions —
   `build_individual_flow(cfg)` and `build_business_flow(cfg)` — each
   consuming a `CountryConfig` to produce a `Flow`. The registry is built
   once: `FLOWS = {(country, account_type): Flow, ...}` for all 3x2
   combinations.

**To add a 4th country**: add one `CountryConfig` entry. Zero new branches
anywhere else.
**To add a step for every market**: edit one builder function once.
**To add a market-only step**: a single, contained `if cfg.code == "XX":`
inside the relevant builder — a contained, well-named exception, not a
flow-wide conditional tree.

Steps reference an `IntegrationSpec(check_type="credit", input_fields=(...))`
by string, not by importing a client class — `integrations/registry.py` is
the only place that maps `check_type` to an implementation, so the flow
layer and the integration layer can change independently.

## Mock integrations

Each of the 5 required check types (identity/KYC, KYB/registry,
PEP/sanctions, credit/affordability, bank account), plus address lookup and
signatory-authority verification, is its own module under `integrations/`,
sharing a `base.py` with:

- **`deterministic_bucket(seed, buckets)`** — hashes the seed (a
  string built from the relevant input fields) into one of a weighted
  tuple of outcomes. Same input always gives the same output — this keeps
  the demo reproducible and the test suite non-flaky, while still being
  "randomly" distributed across a realistic population (e.g. identity
  checks are weighted 90% verified / 10% manual review, so a normal demo
  path is likely to complete while explicit overrides exercise failures).
- **`magic_override(*values)`** — lets a demo user or a test force a
  specific branch by including a keyword (`FAIL`, `REVIEW`, `TIMEOUT`,
  `CONFIRMEDHIT`) in a relevant field, mapped by each client to its own
  domain-appropriate outcome via an `OVERRIDE_MAP`.
- The **bank client** additionally simulates a flaky provider: an
  `unreachable` outcome retries with backoff up to `MAX_ATTEMPTS`, and
  recovers on the final attempt unless a persistent timeout was forced —
  demonstrating graceful degradation to manual review rather than a hard
  crash when a downstream dependency is flaky.

## Decisioning

`decisioning/engine.py` is a pure function: given every `IntegrationResult`
recorded for an application, look up each `(check_type, outcome)` pair in a
static `RULES` table, take the worst severity across all of them
(`approved < manual_review < rejected`), and return all matching reasons.
Affordability (a boolean inside the credit check's `details`, not its own
outcome bucket) is handled as a cross-cutting flag so a "strong" credit
score with an unaffordable requested amount still lands in manual review.

This is the same function for all 6 flows — country/account-type
differences never leak into decisioning logic, only into which checks run
and what data they see.

## Data handling / security

- **Redaction at the boundary**: any `Field` marked `sensitive=True`
  (national IDs, business IDs, IBANs) is masked (`***2384`, last 4 chars
  visible) by `services/redaction.py` before `StepAnswer.data` is
  persisted. Later mock credit checks use a keyed, non-reversible subject
  reference rather than a raw identifier.
- **Integration `details` and audit `metadata` are hand-built allowlists**,
  not raw payload dumps — each client only returns decision-relevant
  fields (score, confidence, boolean flags), and the sanctions client
  never puts screened names in its stored details, only a count.
- **Resume tokens are capability tokens, not identifiers.** Generated with
  `secrets.token_urlsafe(32)`; only a SHA-256 hash is persisted
  (`Application.resume_token_hash`); comparison uses
  `secrets.compare_digest` to avoid timing attacks; tokens expire
  (`RESUME_TOKEN_TTL_HOURS`, default 72h) and an application whose token
  has expired flips to `expired` status on the next resume attempt.
- **Resume-link hardening**: token attempts are rate limited per source
  address and a successful magic-link resume rotates the browser session key.
  `no-referrer` prevents the token URL from leaking in outbound Referer
  headers.
- **Deployment controls**: Django debug mode is off by default; the secret
  key comes from an environment variable (with an ephemeral local fallback),
  and HTTPS redirects/cookie flags are environment-controlled so local HTTP
  development remains possible without weakening production configuration.
- **Embedded local browser support**: the desktop preview sends an opaque
  `Origin: null`. `LocalNullOriginCsrfMiddleware` removes only that origin on
  loopback hosts before Django's CSRF middleware runs; the CSRF token remains
  mandatory, and non-loopback requests retain Django's normal origin checks.
- **Request/event IDs for traceability**: every `IntegrationResult` gets a
  UUID `request_id`, and every `AuditEvent` gets a UUID `event_id` — so a
  support person could trace one specific integration call or audit
  entry, matching the "use request IDs so a support person can trace an
  application" production-mindset ask.
- **Access control** is a session-capability model (see README
  assumptions) — deliberately simple for a sample, explicitly flagged as
  the first thing to replace with real authentication in production.

## Why Django (vs Flask/FastAPI)

Discussed with the requester mid-build; Django was chosen because: the
admin panel gives free, no-extra-code inspection of the audit
trail/integration history per application (useful for the interview
walkthough); migrations + the ORM are "batteries included" for a
stateful, regulated-feeling flow; and server-rendered Jinja-equivalent
templates matched the brief's "server-rendered app is completely
acceptable" guidance more directly than FastAPI would have without
manually wiring `Jinja2Templates`, sessions, and forms.

## What I'd do next for production

1. Real authentication (magic-link login or SSO) instead of the session-
   capability model; put `/apply/*/audit/` behind staff-only auth.
2. Idempotency keys and optimistic locking on step submission. A unique
   `(application, step_key)` constraint already prevents duplicate answers,
   but concurrent requests can still race when advancing
   `Application.current_step_key`.
3. A periodic sweep for abandoned/expired applications, in addition to the
   on-access check.
4. Replace the mock integration clients with real HTTP clients behind the
   same `BaseIntegrationClient` interface — the flow layer, decisioning
   layer and views wouldn't need to change at all.
5. Structured logging / metrics around integration latency and outcome
   distribution (the pieces — `latency_ms`, `attempt_count` — are already
   captured per `IntegrationResult`).
6. Replace the local rate-limit cache with Redis, store secrets in a managed
   secrets service, and add CSP/observability at the platform edge.
