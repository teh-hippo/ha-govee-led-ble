"""Stable persisted and public identifiers for generic DIY effects."""

from typing import Final

PAINTED_EFFECT_CONTENT_KIND: Final = "h617a_painted"
SINGLE_EFFECT_CONTENT_KIND: Final = "h617a_single"
MULTI_EFFECT_CONTENT_KIND: Final = "h617a_multi"
GENERIC_DIY_CONTENT_KINDS: Final = frozenset(
    {PAINTED_EFFECT_CONTENT_KIND, SINGLE_EFFECT_CONTENT_KIND, MULTI_EFFECT_CONTENT_KIND}
)
