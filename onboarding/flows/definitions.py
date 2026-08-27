"""
Two builder functions -- one per account type -- each parametrised by a
`CountryConfig`. This is the mechanism that satisfies the brief's "avoid a
large nested if/else tree" signal: the *shape* of the Swedish, Spanish and
Polish journeys is defined once; only labels, patterns and provider names
vary per market, and that variance lives in `country_config.py` as data.

To add a new country: add a `CountryConfig` entry. To add a new step for
every market: edit one builder function. To add a market-only step: branch
inside the builder on `cfg.code` -- a single, contained, well-named
exception rather than a flow-wide if/else tree.
"""
from .country_config import COUNTRIES, CountryConfig
from .schema import Field, FieldType, Flow, IntegrationSpec, Step

CONSENT_CHOICES = (("yes", "I agree"),)

YES_NO = (("yes", "Yes"), ("no", "No"))

# Reusable validation patterns. Centralised here so every "name"-shaped
# field across all 6 flows gets the same real validation instead of each
# Field() silently defaulting to "any text at all".
NAME_PATTERN = r"^[A-Za-zÀ-ÖØ-öø-ÿ][A-Za-zÀ-ÖØ-öø-ÿ' \-\.]{1,79}$"
NAME_MESSAGE = "Enter letters only (no numbers or symbols)."

PHONE_PATTERN = r"^\+?[0-9][0-9\s\-\(\)]{6,19}$"
PHONE_MESSAGE = "Enter a valid phone number, digits only (e.g. +46 70 123 45 67)."

ADDRESS_PATTERN = r"^[A-Za-zÀ-ÖØ-öø-ÿ][A-Za-zÀ-ÖØ-öø-ÿ'.,\-/# ]{2,119}$"
ADDRESS_MESSAGE = "Enter a street address using letters and basic punctuation only."

IBAN_PATTERN = r"^[A-Za-z]{2}[0-9]{2}[A-Za-z0-9]{10,30}$"
IBAN_MESSAGE = "Enter a valid IBAN (2 letters, 2 digits, then account identifier)."

FREE_LABEL_PATTERN = r"^[\w\sÀ-ÖØ-öø-ÿ,.\-&/]{2,120}$"
FREE_LABEL_MESSAGE = "Enter a short description (letters, numbers and basic punctuation only)."


def _consent_step(integration: IntegrationSpec | None = None) -> Step:
    return Step(
        key="consent",
        title="Consent & declarations",
        description="We need a few legal declarations before we can check your details.",
        fields=(
            Field(
                name="privacy_consent",
                label="I consent to Ikano processing my data for this application",
                type=FieldType.CHECKBOX,
                required=True,
            ),
            Field(
                name="pep_declaration",
                label="Are you, or a close family member/associate, a Politically Exposed Person (PEP)?",
                type=FieldType.SELECT,
                choices=YES_NO,
                required=True,
            ),
        ),
        integration=integration,
    )


def build_individual_flow(cfg: CountryConfig) -> Flow:
    steps = (
        Step(
            key="identity",
            title="Identity verification",
            description=(
                f"We'll verify your identity via a {cfg.identity_provider_name}-style check."
            ),
            fields=(
                Field(
                    name="full_name",
                    label="Full legal name",
                    required=True,
                    pattern=NAME_PATTERN,
                    pattern_message=NAME_MESSAGE,
                ),
                Field(
                    name="national_id",
                    label=cfg.person_id_label,
                    help_text=cfg.person_id_help,
                    pattern=cfg.person_id_pattern,
                    pattern_message=f"Enter a valid {cfg.person_id_label}.",
                    required=True,
                    sensitive=True,
                ),
                Field(
                    name="date_of_birth",
                    label="Date of birth",
                    type=FieldType.DATE,
                    required=True,
                ),
            ),
            integration=IntegrationSpec(
                check_type="identity",
                input_fields=("full_name", "national_id", "date_of_birth"),
            ),
        ),
        Step(
            key="contact",
            title="Contact details & address",
            fields=(
                Field(
                    name="email",
                    label="Email address",
                    type=FieldType.EMAIL,
                    required=True,
                    max_length=254,
                ),
                Field(
                    name="phone",
                    label="Phone number",
                    required=True,
                    pattern=PHONE_PATTERN,
                    pattern_message=PHONE_MESSAGE,
                ),
                Field(
                    name="street_address",
                    label="Street address",
                    required=True,
                    pattern=ADDRESS_PATTERN,
                    pattern_message=ADDRESS_MESSAGE,
                ),
                Field(
                    name="postal_code",
                    label="Postal code",
                    help_text=cfg.postal_code_help,
                    required=True,
                    pattern=cfg.postal_code_pattern,
                    pattern_message=f"Enter a valid {cfg.name} postal code.",
                ),
                Field(
                    name="city",
                    label="City",
                    required=True,
                    pattern=NAME_PATTERN,
                    pattern_message=NAME_MESSAGE,
                ),
                Field(
                    name="region",
                    label=cfg.address_region_label,
                    required=True,
                    pattern=NAME_PATTERN,
                    pattern_message=NAME_MESSAGE,
                ),
            ),
            integration=IntegrationSpec(
                check_type="address",
                input_fields=("street_address", "postal_code", "city"),
            ),
        ),
        _consent_step(
            IntegrationSpec(check_type="sanctions", input_fields=("full_name",))
        ),
        Step(
            key="financials",
            title="Employment, income & household",
            fields=(
                Field(
                    name="employment_status",
                    label="Employment status",
                    type=FieldType.SELECT,
                    choices=(
                        ("employed", "Employed"),
                        ("self_employed", "Self-employed"),
                        ("unemployed", "Unemployed"),
                        ("retired", "Retired"),
                        ("student", "Student"),
                    ),
                    required=True,
                ),
                Field(
                    name="monthly_income",
                    label=f"Monthly net income ({cfg.currency})",
                    type=FieldType.NUMBER,
                    required=True,
                    min_value=0,
                ),
                Field(
                    name="monthly_housing_cost",
                    label=f"Monthly housing cost ({cfg.currency})",
                    type=FieldType.NUMBER,
                    required=True,
                    min_value=0,
                ),
                Field(
                    name="dependants",
                    label="Number of financially dependent people",
                    type=FieldType.NUMBER,
                    required=True,
                    min_value=0,
                    integer_only=True,
                ),
                Field(
                    name="monthly_other_living_costs",
                    label=f"Other monthly living costs ({cfg.currency})",
                    help_text="For example, food, utilities, transport and insurance.",
                    type=FieldType.NUMBER,
                    required=True,
                    min_value=0,
                ),
                Field(
                    name="monthly_debt_payments",
                    label=f"Existing monthly loan or debt payments ({cfg.currency})",
                    type=FieldType.NUMBER,
                    required=True,
                    min_value=0,
                ),
                Field(
                    name="employment_months",
                    label="Months in current employment",
                    type=FieldType.NUMBER,
                    required=True,
                    min_value=0,
                    integer_only=True,
                ),
            ),
        ),
        Step(
            key="credit_check",
            title="Credit bureau & affordability",
            description=f"We'll run a {cfg.credit_bureau_name} check and an affordability assessment.",
            fields=(
                Field(
                    name="requested_amount",
                    label=f"Requested credit amount ({cfg.currency})",
                    type=FieldType.NUMBER,
                    required=True,
                    min_value=1,
                ),
            ),
            integration=IntegrationSpec(
                check_type="credit",
                input_fields=(
                    "credit_subject_reference",
                    "monthly_income",
                    "monthly_housing_cost",
                    "requested_amount",
                    "dependants",
                    "monthly_other_living_costs",
                    "monthly_debt_payments",
                    "employment_status",
                    "employment_months",
                ),
            ),
        ),
        Step(key="review", title="Review & submit", kind="review"),
    )
    return Flow(country=cfg.code, account_type="individual", steps=steps)


def build_business_flow(cfg: CountryConfig) -> Flow:
    steps = (
        Step(
            key="company",
            title="Company details",
            fields=(
                Field(
                    name="legal_name",
                    label="Legal company name",
                    required=True,
                    pattern=FREE_LABEL_PATTERN,
                    pattern_message=FREE_LABEL_MESSAGE,
                ),
                Field(
                    name="business_id",
                    label=cfg.org_id_label,
                    help_text=cfg.org_id_help,
                    pattern=cfg.org_id_pattern,
                    pattern_message=f"Enter a valid {cfg.org_id_label}.",
                    required=True,
                    sensitive=True,
                ),
                Field(
                    name="legal_form",
                    label="Legal form",
                    type=FieldType.SELECT,
                    choices=(
                        ("llc", "Limited liability company"),
                        ("sole_trader", "Sole trader"),
                        ("partnership", "Partnership"),
                        ("other", "Other"),
                    ),
                    required=True,
                ),
            ),
            integration=IntegrationSpec(
                check_type="registry",
                input_fields=("business_id", "legal_name"),
            ),
        ),
        Step(
            key="representative",
            title="Authorised representative",
            description="Confirm the person signing on behalf of the business.",
            fields=(
                Field(
                    name="rep_full_name",
                    label="Full legal name",
                    required=True,
                    pattern=NAME_PATTERN,
                    pattern_message=NAME_MESSAGE,
                ),
                Field(
                    name="rep_national_id",
                    label=cfg.person_id_label,
                    help_text=cfg.person_id_help,
                    pattern=cfg.person_id_pattern,
                    pattern_message=f"Enter a valid {cfg.person_id_label}.",
                    required=True,
                    sensitive=True,
                ),
                Field(
                    name="rep_role",
                    label="Role / title",
                    required=True,
                    pattern=FREE_LABEL_PATTERN,
                    pattern_message=FREE_LABEL_MESSAGE,
                ),
                Field(
                    name="signatory_rights",
                    label="Confirmed signatory rights for this application?",
                    type=FieldType.SELECT,
                    choices=YES_NO,
                    required=True,
                ),
            ),
            integration=IntegrationSpec(
                check_type="identity",
                input_fields=("rep_full_name", "rep_national_id"),
            ),
        ),
        Step(
            key="authority_check",
            title="Signatory authority verification",
            description="We'll confirm that the representative can sign for this business.",
            integration=IntegrationSpec(
                check_type="authority",
                input_fields=("rep_full_name", "rep_national_id", "signatory_rights"),
            ),
        ),
        Step(
            key="ubo",
            title="Beneficial owners",
            description="List the beneficial owner(s) with 25%+ ownership. We'll screen them for sanctions/PEP exposure.",
            fields=(
                Field(
                    name="ubo_names",
                    label="Beneficial owner name(s), comma-separated",
                    required=True,
                    pattern=r"^[A-Za-zÀ-ÖØ-öø-ÿ][A-Za-zÀ-ÖØ-öø-ÿ' \-\.,]{1,199}$",
                    pattern_message="Enter one or more names, separated by commas (letters only).",
                ),
                Field(
                    name="ubo_total_ownership_pct",
                    label="Combined ownership % of listed owners",
                    type=FieldType.NUMBER,
                    required=True,
                    min_value=25,
                    max_value=100,
                ),
            ),
            integration=IntegrationSpec(
                check_type="sanctions",
                input_fields=("ubo_names",),
            ),
        ),
        _consent_step(),
        Step(
            key="business_profile",
            title="Business activity & expected usage",
            fields=(
                Field(
                    name="sector",
                    label="Business sector / industry",
                    required=True,
                    pattern=FREE_LABEL_PATTERN,
                    pattern_message=FREE_LABEL_MESSAGE,
                ),
                Field(
                    name="annual_turnover",
                    label=f"Annual turnover ({cfg.currency})",
                    type=FieldType.NUMBER,
                    required=True,
                    min_value=0,
                ),
                Field(
                    name="expected_usage",
                    label="Expected use of the account/credit facility",
                    type=FieldType.TEXTAREA,
                    required=True,
                    min_length=10,
                    max_length=1000,
                ),
            ),
        ),
        Step(
            key="credit_check",
            title="Business credit & bank verification",
            description=f"We'll run a {cfg.credit_bureau_name} business check and verify the settlement account.",
            fields=(
                Field(
                    name="requested_amount",
                    label=f"Requested credit amount ({cfg.currency})",
                    type=FieldType.NUMBER,
                    required=True,
                    min_value=1,
                ),
                Field(
                    name="iban",
                    label="Settlement account IBAN",
                    required=True,
                    sensitive=True,
                    pattern=IBAN_PATTERN,
                    pattern_message=IBAN_MESSAGE,
                ),
            ),
            integration=IntegrationSpec(
                check_type="credit",
                input_fields=("credit_subject_reference", "annual_turnover", "requested_amount"),
            ),
        ),
        Step(
            key="bank_verification",
            title="Settlement account verification",
            description="We'll verify the IBAN you provided matches the business name on record.",
            fields=(),
            integration=IntegrationSpec(
                check_type="bank",
                input_fields=("iban", "legal_name"),
            ),
        ),
        Step(key="review", title="Review & submit", kind="review"),
    )
    return Flow(country=cfg.code, account_type="business", steps=steps)


def _build_registry():
    registry = {}
    for cfg in COUNTRIES.values():
        registry[(cfg.code, "individual")] = build_individual_flow(cfg)
        registry[(cfg.code, "business")] = build_business_flow(cfg)
    return registry


FLOWS = _build_registry()


def get_flow(country: str, account_type: str) -> Flow:
    try:
        return FLOWS[(country, account_type)]
    except KeyError:
        raise ValueError(f"No flow configured for country={country!r} account_type={account_type!r}")
