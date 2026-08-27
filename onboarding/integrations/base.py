"""
Shared machinery for the mock external integrations.

Design goals (mirroring what a real integration layer needs):
  * typed request/response objects (dataclasses) rather than raw dicts
  * deterministic outcomes given the same input, so the demo and the test
    suite behave predictably
  * an easy way to force a specific outcome for a demo/test ("magic
    values") without making the whole thing random
  * a place to simulate latency/timeouts and retries (used by the bank
    client) so the flow's error handling has something real to do
"""
from __future__ import annotations

import hashlib
import random
import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class IntegrationRequest:
    check_type: str
    payload: dict
    request_id: str


@dataclass
class IntegrationResponse:
    outcome: str
    details: dict = field(default_factory=dict)
    latency_ms: int = 0
    attempt_count: int = 1


def deterministic_bucket(seed: str, buckets: tuple) -> str:
    """Map an arbitrary string to one of `buckets` deterministically, using
    a hash so the same input always lands in the same bucket. This stands
    in for "the real service's business logic" without needing real rules
    or randomness that would make the demo/tests flaky."""
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()
    index = int(digest, 16) % len(buckets)
    return buckets[index]


def magic_override(*values: Any) -> str | None:
    """Lets a demo user or a test force a specific outcome by typing a
    keyword into any of the watched input fields, e.g. a full legal name of
    'Fail Example' always fails the identity check. Returns a generic token that
    each client maps to its own domain-appropriate outcome via
    `OVERRIDE_MAP`. Falls through to None (no override) for ordinary input."""
    joined = " ".join(str(v) for v in values if v).upper().replace(" ", "").replace("-", "")
    if "CONFIRMEDHIT" in joined:
        return "CONFIRMED_HIT"
    if "FAIL" in joined:
        return "FAIL"
    if "REVIEW" in joined:
        return "REVIEW"
    if "TIMEOUT" in joined:
        return "TIMEOUT"
    return None


class BaseIntegrationClient:
    check_type = "base"

    def call(self, payload: dict, request_id: str) -> IntegrationResponse:
        start = time.monotonic()
        response = self._call(payload)
        response.latency_ms = response.latency_ms or int((time.monotonic() - start) * 1000)
        return response

    def _call(self, payload: dict) -> IntegrationResponse:
        raise NotImplementedError
