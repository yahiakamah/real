# -*- coding: utf-8 -*-
"""Engine-internal exceptions. These are caught by the controller and turned
into human-friendly messages -- tracebacks, SQL and internals are never leaked
to the user (see spec section 30)."""


class AiEngineError(Exception):
    """Base class for all engine errors."""


class ModelNotAllowed(AiEngineError):
    """The AI tried to touch a model not registered / enabled in the semantic layer."""


class FieldNotAllowed(AiEngineError):
    """The AI tried to use a field that is disabled or not registered."""


class QueryValidationError(AiEngineError):
    """The AI produced a query plan that failed validation (bad operator, etc.)."""


class ProviderError(AiEngineError):
    """The upstream AI provider failed or returned an unusable response."""
