"""
LLM Factory Module (GAP-066).

Provides factory functions for creating LLM instances with automatic token tracking.
All pipeline layers should use these factories instead of direct ChatOpenAI/ChatAnthropic instantiation.

Usage:
    from src.common.llm_factory import create_tracked_llm, create_tracked_cv_llm

    # General pipeline LLM (OpenAI)
    llm = create_tracked_llm(layer="layer2")

    # CV generation LLM (Anthropic/OpenRouter/OpenAI based on config)
    cv_llm = create_tracked_cv_llm(layer="layer6_v2")

    # With custom parameters
    llm = create_tracked_llm(
        model="gpt-4o-mini",
        temperature=0.3,
        layer="layer4",
        run_id="run_123",
        job_id="job_456"
    )
"""

import logging
from typing import Any, List, Optional, Union

from langchain_core.callbacks import BaseCallbackHandler
from langchain_openai import ChatOpenAI

from src.common.config import Config
from src.common.token_tracker import (
    TokenTracker,
    TokenTrackingCallback,
    get_global_tracker,
    get_token_tracker_registry,
)

logger = logging.getLogger(__name__)

# Thread-local storage for run context
_current_run_id: Optional[str] = None
_current_job_id: Optional[str] = None


def set_run_context(run_id: Optional[str] = None, job_id: Optional[str] = None) -> None:
    """
    Set the current run context for token tracking.

    Call this at the start of a pipeline run to associate all subsequent
    LLM calls with the run_id and job_id.

    Args:
        run_id: Pipeline run identifier
        job_id: Job identifier
    """
    global _current_run_id, _current_job_id
    _current_run_id = run_id
    _current_job_id = job_id
    if run_id or job_id:
        logger.debug(f"Token tracking context set: run_id={run_id}, job_id={job_id}")


def clear_run_context() -> None:
    """Clear the current run context."""
    global _current_run_id, _current_job_id
    _current_run_id = None
    _current_job_id = None


def get_run_context() -> tuple[Optional[str], Optional[str]]:
    """Get the current run context (run_id, job_id)."""
    return _current_run_id, _current_job_id


def _create_tracking_callback(
    provider: str,
    layer: Optional[str] = None,
    tracker: Optional[TokenTracker] = None,
    run_id: Optional[str] = None,
    job_id: Optional[str] = None,
) -> TokenTrackingCallback:
    """
    Create a token tracking callback.

    Args:
        provider: LLM provider name ("openai", "anthropic", "openrouter")
        layer: Pipeline layer name for attribution
        tracker: Optional specific tracker (defaults to global)
        run_id: Optional run_id override (defaults to context)
        job_id: Optional job_id override (defaults to context)

    Returns:
        TokenTrackingCallback instance
    """
    if tracker is None:
        tracker = get_global_tracker()

    # Use context if not explicitly provided
    effective_run_id = run_id if run_id is not None else _current_run_id
    effective_job_id = job_id if job_id is not None else _current_job_id

    return TokenTrackingCallback(
        tracker=tracker,
        provider=provider,
        layer=layer,
        run_id=effective_run_id,
        job_id=effective_job_id,
    )


def create_tracked_llm(
    model: Optional[str] = None,
    temperature: Optional[float] = None,
    layer: Optional[str] = None,
    tracker: Optional[TokenTracker] = None,
    run_id: Optional[str] = None,
    job_id: Optional[str] = None,
    additional_callbacks: Optional[List[BaseCallbackHandler]] = None,
    **kwargs: Any,
) -> ChatOpenAI:
    """
    Create a ChatOpenAI instance with automatic token tracking.

    This is the primary factory for general pipeline LLM calls.
    Uses OpenAI API directly.

    Args:
        model: Model name (defaults to Config.DEFAULT_MODEL)
        temperature: Temperature (defaults to Config.ANALYTICAL_TEMPERATURE)
        layer: Pipeline layer name for cost attribution
        tracker: Optional specific tracker (defaults to global)
        run_id: Optional run_id (defaults to context)
        job_id: Optional job_id (defaults to context)
        additional_callbacks: Additional callbacks to add
        **kwargs: Additional ChatOpenAI parameters

    Returns:
        ChatOpenAI instance with token tracking callback

    Example:
        llm = create_tracked_llm(layer="layer2")
        response = llm.invoke([SystemMessage(content="..."), HumanMessage(content="...")])
    """
    # Use defaults from config if not provided
    effective_model = model or Config.DEFAULT_MODEL
    effective_temperature = temperature if temperature is not None else Config.ANALYTICAL_TEMPERATURE

    # Create tracking callback
    tracking_callback = _create_tracking_callback(
        provider="openai",
        layer=layer,
        tracker=tracker,
        run_id=run_id,
        job_id=job_id,
    )

    # Combine callbacks
    callbacks: List[BaseCallbackHandler] = [tracking_callback]
    if additional_callbacks:
        callbacks.extend(additional_callbacks)

    # Create LLM with tracking
    llm = ChatOpenAI(
        model=effective_model,
        temperature=effective_temperature,
        api_key=Config.get_llm_api_key(),
        base_url=Config.get_llm_base_url(),
        callbacks=callbacks,
        **kwargs,
    )

    logger.debug(
        f"Created tracked OpenAI LLM: model={effective_model}, "
        f"layer={layer}, run_id={run_id or _current_run_id}"
    )

    return llm


def create_tracked_cheap_llm(
    layer: Optional[str] = None,
    tracker: Optional[TokenTracker] = None,
    run_id: Optional[str] = None,
    job_id: Optional[str] = None,
    **kwargs: Any,
) -> ChatOpenAI:
    """
    Create a ChatOpenAI instance using the cheap model (gpt-4o-mini).

    Use this for simple/analytical tasks that don't need high intelligence.

    Args:
        layer: Pipeline layer name for cost attribution
        tracker: Optional specific tracker (defaults to global)
        run_id: Optional run_id (defaults to context)
        job_id: Optional job_id (defaults to context)
        **kwargs: Additional ChatOpenAI parameters

    Returns:
        ChatOpenAI instance with cheap model and token tracking
    """
    return create_tracked_llm(
        model=Config.CHEAP_MODEL,
        temperature=Config.ANALYTICAL_TEMPERATURE,
        layer=layer,
        tracker=tracker,
        run_id=run_id,
        job_id=job_id,
        **kwargs,
    )


def create_tracked_cv_llm(
    layer: Optional[str] = None,
    tracker: Optional[TokenTracker] = None,
    run_id: Optional[str] = None,
    job_id: Optional[str] = None,
    additional_callbacks: Optional[List[BaseCallbackHandler]] = None,
    **kwargs: Any,
) -> Union[ChatOpenAI, Any]:
    """
    Create an LLM instance for CV generation with automatic token tracking.

    Respects configuration priority: Anthropic > OpenRouter > OpenAI
    Uses the CV-specific model and temperature settings.

    Args:
        layer: Pipeline layer name for cost attribution (e.g., "layer6_v2")
        tracker: Optional specific tracker (defaults to global)
        run_id: Optional run_id (defaults to context)
        job_id: Optional job_id (defaults to context)
        additional_callbacks: Additional callbacks to add
        **kwargs: Additional LLM parameters

    Returns:
        LLM instance (ChatAnthropic or ChatOpenAI) with token tracking

    Example:
        cv_llm = create_tracked_cv_llm(layer="layer6_v2")
        response = cv_llm.invoke([SystemMessage(content="..."), HumanMessage(content="...")])
    """
    provider = Config.get_cv_llm_provider()
    model = getattr(Config, "CV_MODEL", Config.DEFAULT_MODEL)
    temperature = getattr(Config, "CV_TEMPERATURE", Config.ANALYTICAL_TEMPERATURE)

    # Create tracking callback for appropriate provider
    tracking_callback = _create_tracking_callback(
        provider=provider,
        layer=layer,
        tracker=tracker,
        run_id=run_id,
        job_id=job_id,
    )

    # Combine callbacks
    callbacks: List[BaseCallbackHandler] = [tracking_callback]
    if additional_callbacks:
        callbacks.extend(additional_callbacks)

    if provider == "anthropic":
        # Import here to avoid dependency if not using Anthropic
        try:
            from langchain_anthropic import ChatAnthropic

            llm = ChatAnthropic(
                model=model,
                temperature=temperature,
                api_key=Config.get_cv_llm_api_key(),
                callbacks=callbacks,
                **kwargs,
            )
            logger.debug(
                f"Created tracked Anthropic LLM: model={model}, "
                f"layer={layer}, run_id={run_id or _current_run_id}"
            )
            return llm
        except ImportError:
            logger.warning("langchain-anthropic not installed, falling back to OpenAI")
            provider = "openai"

    # OpenRouter or OpenAI (both use ChatOpenAI)
    llm = ChatOpenAI(
        model=model,
        temperature=temperature,
        api_key=Config.get_cv_llm_api_key(),
        base_url=Config.get_cv_llm_base_url(),
        callbacks=callbacks,
        **kwargs,
    )

    logger.debug(
        f"Created tracked {provider} LLM: model={model}, "
        f"layer={layer}, run_id={run_id or _current_run_id}"
    )

    return llm


def create_tracked_llm_with_tier(
    tier_config: Any,
    operation: str,
    layer: Optional[str] = None,
    tracker: Optional[TokenTracker] = None,
    run_id: Optional[str] = None,
    job_id: Optional[str] = None,
    **kwargs: Any,
) -> Union[ChatOpenAI, Any]:
    """
    Create an LLM instance based on tier configuration and operation type.

    This supports the tiered processing system (GAP-045) where different
    operations use different models based on the tier.

    Args:
        tier_config: TierConfig object with model assignments
        operation: Operation type ("cv", "role", "research", "pain_points")
        layer: Pipeline layer name for cost attribution
        tracker: Optional specific tracker (defaults to global)
        run_id: Optional run_id (defaults to context)
        job_id: Optional job_id (defaults to context)
        **kwargs: Additional LLM parameters

    Returns:
        LLM instance with appropriate model for the tier/operation

    Example:
        from src.common.tiering import get_tier_config, ProcessingTier

        tier_config = get_tier_config(ProcessingTier.GOLD)
        cv_llm = create_tracked_llm_with_tier(tier_config, "cv", layer="layer6_v2")
    """
    # Default to analytical temperature for most operations
    temperature = Config.ANALYTICAL_TEMPERATURE

    # Determine model and temperature based on operation
    if operation == "cv":
        model = tier_config.cv_model
        temperature = getattr(Config, "CV_TEMPERATURE", 0.33)
        provider = "anthropic" if "claude" in model.lower() else "openai"
    elif operation == "role":
        model = tier_config.role_model
        provider = "openai"  # Role models are always OpenAI in current config
    elif operation == "research":
        model = tier_config.research_model
        provider = "openai"
    elif operation == "pain_points":
        model = tier_config.research_model  # Use research model for pain points
        provider = "openai"
    else:
        # Default to research model for unknown operations
        model = tier_config.research_model
        provider = "openai"
        logger.warning(f"Unknown operation '{operation}', using research model")

    # Create tracking callback
    tracking_callback = _create_tracking_callback(
        provider=provider,
        layer=layer,
        tracker=tracker,
        run_id=run_id,
        job_id=job_id,
    )

    callbacks: List[BaseCallbackHandler] = [tracking_callback]

    # Create appropriate LLM
    if provider == "anthropic" and "claude" in model.lower():
        try:
            from langchain_anthropic import ChatAnthropic

            llm = ChatAnthropic(
                model=model,
                temperature=temperature,
                api_key=Config.ANTHROPIC_API_KEY,
                callbacks=callbacks,
                **kwargs,
            )
            logger.debug(
                f"Created tiered Anthropic LLM: model={model}, operation={operation}, "
                f"layer={layer}, run_id={run_id or _current_run_id}"
            )
            return llm
        except ImportError:
            logger.warning("langchain-anthropic not installed, falling back to OpenAI")

    # OpenAI
    llm = ChatOpenAI(
        model=model,
        temperature=temperature,
        api_key=Config.get_llm_api_key(),
        base_url=Config.get_llm_base_url(),
        callbacks=callbacks,
        **kwargs,
    )

    logger.debug(
        f"Created tiered OpenAI LLM: model={model}, operation={operation}, "
        f"layer={layer}, run_id={run_id or _current_run_id}"
    )

    return llm


# Convenience aliases
create_openai_llm = create_tracked_llm
create_cv_llm = create_tracked_cv_llm
