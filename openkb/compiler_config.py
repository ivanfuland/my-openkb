"""Resolvers for wiki compiler mode settings."""

from __future__ import annotations

import logging

logger = logging.getLogger("openkb.config")

VALID_CONCEPT_UPDATE_MODES: tuple[str, ...] = ("rewrite", "append")


def resolve_concept_update_mode(config: dict) -> str:
    """Resolve ``concept_update_mode:`` — ``"rewrite"`` (default, full-page
    LLM rewrite on update) or ``"append"`` (short note instead, see
    ``openkb.agent.compiler_notes``). Invalid values degrade to ``"rewrite"``
    with a warning.
    """
    value = config.get("concept_update_mode", "rewrite")
    if value not in VALID_CONCEPT_UPDATE_MODES:
        logger.warning(
            "config: 'concept_update_mode' must be one of %s, got %r — using 'rewrite'.",
            VALID_CONCEPT_UPDATE_MODES,
            value,
        )
        return "rewrite"
    return value


def resolve_strict_item_mode(config: dict) -> bool:
    """Resolve ``strict_item_mode:`` — ``False`` by default.

    When ``True``, a brand-new concept/entity ``create`` item is dropped
    instead of kept whenever it looks like a bad/too-specific candidate:

    - a name longer than 3 words is dropped (see
      ``agent.compiler._filter_concept_items`` / ``_filter_entity_items`` /
      ``_MAX_NAME_WORDS``) — applies to both concepts and entities.
    - an entity whose LLM-returned ``type`` doesn't match the configured
      :func:`openkb.config.resolve_entity_types` vocabulary is dropped instead of being
      coerced to ``"other"`` — entities only, concepts have no ``type``.

    All gates are opt-in together under this single flag. A non-bool value
    degrades to ``False`` with a warning (matches
    :func:`resolve_concept_update_mode`'s degrade-on-malformed-value
    behavior).
    """
    value = config.get("strict_item_mode", False)
    if not isinstance(value, bool):
        logger.warning(
            "config: 'strict_item_mode' must be a bool, got %r — using False.",
            value,
        )
        return False
    return value
