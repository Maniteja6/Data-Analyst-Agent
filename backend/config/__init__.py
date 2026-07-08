"""Configuration — settings, feature flags, Bedrock config, and logging setup.

settings.py       — Settings (pydantic-settings BaseSettings); reads .env;
                     get_settings() lru_cache singleton.
feature_flags.py  — FeatureFlags dataclass; 13 flags (FEATURE_* env vars);
                     flags singleton; guards Kafka, RAG, Forecast, ML, etc.
bedrock_config.py — BedrockConfig; model IDs, pricing, context windows;
                     get_bedrock_config() singleton.
logging_config.py — configure_structlog(log_level); JSON renderer for prod,
                     console renderer for dev.
"""

from backend.config.feature_flags import FeatureFlags, flags
from backend.config.settings import Settings, get_settings

__all__ = ["get_settings", "Settings", "flags", "FeatureFlags"]
