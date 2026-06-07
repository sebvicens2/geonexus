"""The Asset node."""

from __future__ import annotations

from typing import Any, ClassVar

from pydantic import BaseModel, Field

from eventgraph.core.node import NodeKind
from eventgraph.ontology.asset_types import AssetType


class Asset(BaseModel):
    """A tradable instrument that events can ultimately impact.

    Attributes:
        ticker: Stable symbol, used as the identifier (e.g. ``"XAU_USD"``).
        asset_class: Class from the controlled vocabulary.
        name: Optional human-readable name.
        region: Optional geography the asset is most tied to.
        metadata: Arbitrary extra payload.
    """

    kind: ClassVar[NodeKind] = NodeKind.ASSET

    ticker: str
    asset_class: AssetType = AssetType.OTHER
    name: str | None = None
    region: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def node_id(self) -> str:
        """Namespaced identifier used as the graph node key."""
        return f"{self.kind.value}:{self.ticker}"
