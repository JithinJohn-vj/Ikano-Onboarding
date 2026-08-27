from .address import AddressLookupClient
from .authority import SignatoryAuthorityClient
from .bank import BankAccountClient
from .company_registry import RegistryClient
from .credit import CreditBureauClient
from .identity import IdentityCheckClient
from .sanctions import SanctionsScreeningClient

INTEGRATIONS = {
    "identity": IdentityCheckClient(),
    "address": AddressLookupClient(),
    "authority": SignatoryAuthorityClient(),
    "registry": RegistryClient(),
    "sanctions": SanctionsScreeningClient(),
    "credit": CreditBureauClient(),
    "bank": BankAccountClient(),
}


def get_client(check_type: str):
    try:
        return INTEGRATIONS[check_type]
    except KeyError:
        raise ValueError(f"No mock integration registered for check_type={check_type!r}")
