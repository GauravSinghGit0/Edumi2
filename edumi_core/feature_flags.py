"""
Feature Flags for Gradual Rollout and Blue-Green Architecture.
Allows safe migration of models, concurrency mechanisms, and database structures.
"""
from django.conf import settings

class FeatureFlags:
    """Centralized feature flag management"""

    # Phase 1: Domain extraction
    USE_NEW_ACADEMICS_APP = getattr(settings, 'FEATURE_USE_NEW_ACADEMICS_APP', False)
    USE_NEW_LIBRARY_APP = getattr(settings, 'FEATURE_USE_NEW_LIBRARY_APP', False)

    # Phase 2: Concurrency
    USE_ASYNC_FACE_TRACKING = getattr(settings, 'FEATURE_USE_ASYNC_FACE_TRACKING', False)

    # Phase 3: Database
    USE_PGVECTOR_RAG = getattr(settings, 'FEATURE_USE_PGVECTOR_RAG', False)

    @classmethod
    def is_enabled(cls, flag_name: str) -> bool:
        return getattr(cls, flag_name, getattr(settings, f"FEATURE_{flag_name}", False))
