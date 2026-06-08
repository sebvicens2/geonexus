"""Canonical actor categories."""

from enum import Enum


class ActorType(str, Enum):
    """Kind of actor involved in events."""

    COUNTRY = "country"
    ORGANIZATION = "organization"
    ALLIANCE = "alliance"
    COMPANY = "company"
    CENTRAL_BANK = "central_bank"
    PERSON = "person"
    OTHER = "other"
