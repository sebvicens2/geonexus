"""Canonical asset classes."""

from enum import Enum


class AssetType(str, Enum):
    """Financial asset class."""

    COMMODITY = "commodity"
    FX = "fx"
    EQUITY = "equity"
    INDEX = "index"
    BOND = "bond"
    RATE = "rate"
    CRYPTO = "crypto"
    OTHER = "other"
