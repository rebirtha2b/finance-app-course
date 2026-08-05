"""Price providers.

`get_provider()` is the single seam the rest of the app uses, so tests can
substitute a fake without patching import paths all over the codebase.
"""

from __future__ import annotations

from app.services.prices.base import (
    PriceProvider,
    PriceProviderError,
    Quote,
    SecurityInfo,
)
from app.services.prices.yfinance_provider import YFinanceProvider

_provider: PriceProvider = YFinanceProvider()


def get_provider() -> PriceProvider:
    return _provider


def set_provider(provider: PriceProvider) -> None:
    """Swap the active provider (tests, or a future config-driven choice)."""
    global _provider
    _provider = provider


__all__ = [
    "PriceProvider",
    "PriceProviderError",
    "Quote",
    "SecurityInfo",
    "YFinanceProvider",
    "get_provider",
    "set_provider",
]
