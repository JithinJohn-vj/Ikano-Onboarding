"""
Everything that differs between Sweden, Spain and Poland lives here as plain
data. `definitions.py` has two builder functions (one for individuals, one
for businesses) that consume this config -- so adding a fourth market is a
matter of adding one `CountryConfig` entry, not writing new flow code.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class CountryConfig:
    code: str
    name: str

    # --- private individual identity ---
    person_id_label: str
    person_id_help: str
    person_id_pattern: str
    identity_provider_name: str  # e.g. "BankID"

    # --- business identity ---
    org_id_label: str
    org_id_help: str
    org_id_pattern: str
    registry_name: str  # e.g. "Bolagsverket"

    # --- shared ---
    credit_bureau_name: str
    address_region_label: str  # e.g. "County", "Province", "Voivodeship"
    postal_code_pattern: str
    postal_code_help: str
    currency: str


COUNTRIES = {
    "SE": CountryConfig(
        code="SE",
        name="Sweden",
        person_id_label="Personnummer",
        person_id_help="12 digits, e.g. 198506122384",
        person_id_pattern=r"^[0-9]{12}$",
        identity_provider_name="BankID",
        org_id_label="Organisation number",
        org_id_help="Format XXXXXX-XXXX, e.g. 556677-8899",
        org_id_pattern=r"^[0-9]{6}-[0-9]{4}$",
        registry_name="Bolagsverket",
        credit_bureau_name="UC (Upplysningscentralen)",
        address_region_label="County",
        postal_code_pattern=r"^[0-9]{3}\s?[0-9]{2}$",
        postal_code_help="Five digits, optionally with a space (e.g. 111 22).",
        currency="SEK",
    ),
    "ES": CountryConfig(
        code="ES",
        name="Spain",
        person_id_label="DNI / NIE",
        person_id_help="8 digits + letter (DNI) or letter+7 digits+letter (NIE)",
        person_id_pattern=r"^([0-9]{8}[A-Za-z]|[XYZxyz][0-9]{7}[A-Za-z])$",
        identity_provider_name="Cl@ve / DNIe",
        org_id_label="NIF",
        org_id_help="Letter + 7 digits + control character, e.g. B12345674",
        org_id_pattern=r"^[A-Za-z][0-9]{7}[A-Za-z0-9]$",
        registry_name="Registro Mercantil",
        credit_bureau_name="ASNEF / Experian ES",
        address_region_label="Province",
        postal_code_pattern=r"^[0-9]{5}$",
        postal_code_help="Five digits (e.g. 28013).",
        currency="EUR",
    ),
    "PL": CountryConfig(
        code="PL",
        name="Poland",
        person_id_label="PESEL",
        person_id_help="11 digits, e.g. 85061212345",
        person_id_pattern=r"^[0-9]{11}$",
        identity_provider_name="eID / mObywatel",
        org_id_label="NIP",
        org_id_help="10 digits, e.g. 1234563218",
        org_id_pattern=r"^[0-9]{10}$",
        registry_name="CEIDG / KRS",
        credit_bureau_name="BIK",
        address_region_label="Voivodeship",
        postal_code_pattern=r"^[0-9]{2}-[0-9]{3}$",
        postal_code_help="Five digits with a hyphen (e.g. 00-001).",
        currency="PLN",
    ),
}
