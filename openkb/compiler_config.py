"""Resolvers for wiki compiler mode settings."""

from __future__ import annotations

import logging

logger = logging.getLogger("openkb.config")

DEFAULT_MODEL = "gpt-5.4"
DEFAULT_CONCEPT_UPDATE_MODE = "append"
DEFAULT_STRICT_ITEM_MODE = True
VALID_CONCEPT_UPDATE_MODES: tuple[str, ...] = ("rewrite", "append")


def resolve_concept_update_mode(config: dict) -> str:
    """Resolve ``concept_update_mode:`` — ``"append"`` (default, short note,
    see ``openkb.agent.compiler_notes``) or ``"rewrite"`` (full-page LLM
    rewrite on update). Invalid values fall back to ``"append"`` with a warning.
    """
    value = config.get("concept_update_mode", DEFAULT_CONCEPT_UPDATE_MODE)
    if value not in VALID_CONCEPT_UPDATE_MODES:
        logger.warning(
            "config: 'concept_update_mode' must be one of %s, got %r — using %r.",
            VALID_CONCEPT_UPDATE_MODES,
            value,
            DEFAULT_CONCEPT_UPDATE_MODE,
        )
        return DEFAULT_CONCEPT_UPDATE_MODE
    return value


def resolve_strict_item_mode(config: dict) -> bool:
    """Resolve ``strict_item_mode:`` — ``True`` by default.

    When ``True``, a brand-new concept/entity ``create`` item is dropped
    instead of kept whenever it looks like a bad/too-specific candidate:

    - a name longer than 3 words is dropped (see
      ``agent.compiler._filter_concept_items`` / ``_filter_entity_items`` /
      ``_MAX_NAME_WORDS``) — applies to both concepts and entities.
    - an entity whose LLM-returned ``type`` doesn't match the configured
      :func:`openkb.config.resolve_entity_types` vocabulary is dropped instead of being
      coerced to ``"other"`` — entities only, concepts have no ``type``.

    Set ``False`` to disable both checks. A non-bool value falls back to
    ``True`` with a warning.
    """
    value = config.get("strict_item_mode", DEFAULT_STRICT_ITEM_MODE)
    if not isinstance(value, bool):
        logger.warning(
            "config: 'strict_item_mode' must be a bool, got %r — using %r.",
            value,
            DEFAULT_STRICT_ITEM_MODE,
        )
        return DEFAULT_STRICT_ITEM_MODE
    return value


def resolve_consolidate_model(config: dict) -> str:
    """Resolve ``consolidate_model:`` — the model ``openkb consolidate`` runs.

    Unset (or explicit ``None``) means "use ``model``" and returns the fallback
    silently. The fallback is ``config["model"]`` when that is a non-empty
    string, else :data:`DEFAULT_MODEL`. A configured non-empty string wins
    (stripped); any other value — a non-string such as ``bool``/``int``/``list``
    or a blank string — warns and falls back.
    """
    model = config.get("model")
    fallback = model.strip() if isinstance(model, str) and model.strip() else DEFAULT_MODEL
    if "consolidate_model" not in config:
        return fallback
    value = config["consolidate_model"]
    if value is None:
        return fallback
    if isinstance(value, str) and value.strip():
        return value.strip()
    logger.warning(
        "config: 'consolidate_model' must be a non-empty string, got %r — using %r.",
        value,
        fallback,
    )
    return fallback
