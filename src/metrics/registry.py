"""In-memory ``CustomCheckRegistry`` + default factory."""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from .checks import (
    GlossaryAdherenceCheck,
    LengthSanityCheck,
    MarkdownIntegrityCheck,
    PlaceholderRoundTripCheck,
    TagBalanceCheck,
)
from .lang_checks import (
    AspectConsistencyCheck,
    CaseAfterNegationCheck,
    ClassifierPresenceCheck,
    CompoundNounIntegrityCheck,
    DiacriticPresenceCheck,
    FormalityConsistencyCheck,
)
from .ports import CustomCheck, CustomCheckRegistry


class InMemoryCustomCheckRegistry(CustomCheckRegistry):
    def __init__(self, checks: Iterable[CustomCheck] = ()) -> None:
        self._checks: dict[str, CustomCheck] = {}
        for check in checks:
            self.register(check)

    def register(self, check: CustomCheck) -> None:
        self._checks[check.name] = check

    def get(self, name: str) -> CustomCheck:
        try:
            return self._checks[name]
        except KeyError as err:
            raise KeyError(f"custom check not registered: {name}") from err

    def resolve(self, names: Sequence[str]) -> list[CustomCheck]:
        return [self.get(name) for name in names]


def default_custom_check_registry() -> InMemoryCustomCheckRegistry:
    """Return a registry with all universal + language-specific checks."""
    return InMemoryCustomCheckRegistry(
        [
            GlossaryAdherenceCheck(),
            PlaceholderRoundTripCheck(),
            MarkdownIntegrityCheck(),
            TagBalanceCheck(),
            LengthSanityCheck(),
            DiacriticPresenceCheck(),
            FormalityConsistencyCheck(),
            ClassifierPresenceCheck(),
            CompoundNounIntegrityCheck(),
            CaseAfterNegationCheck(),
            AspectConsistencyCheck(),
        ]
    )
