"""LLM adapters — AWS Bedrock batch + streaming + embedding.

BedrockLLMService:  production ILLMService; composes three adapters:
                    BedrockConverseAdapter (batch), BedrockStreamAdapter (stream),
                    BedrockEmbeddingAdapter (Titan Embed v2).
MockLLMService:     test double; set_response(substring, canned_response).
NullLLMService:     always returns ""; for AI-disabled environments.
get_model_id(role): routes FAST_AGENT_ROLES → Haiku, all others → Sonnet.
"""

from backend.infrastructure.llm.llm_port import ILLMService, MockLLMService
from backend.infrastructure.llm.model_id_registry import get_model_id

__all__ = ["ILLMService", "MockLLMService", "get_model_id"]
