"""HyDEExpander — Hypothetical Document Embedding query expansion.

Real-time design:
    HyDE is called inside every chat query before the Qdrant search.
    Target latency: < 300ms (Haiku, max_tokens=150).

    Instead of embedding the user's raw question ("what is the revenue
    trend?"), HyDE first generates a short hypothetical answer
    ("The revenue column shows an upward trend with a mean of $42K…"),
    then embeds that hypothetical answer. This dramatically improves
    retrieval quality for statistical questions because the embedding space
    for answers is much closer to the actual document vectors than
    question embeddings.

When to skip HyDE:
    - ``use_hyde=False`` (can be set per-query for latency-sensitive paths)
    - ``llm_client`` is None (test/offline mode)
    - The query already looks like an answer (long, contains numbers)

Reference:
    Gao et al. (2022) "Precise Zero-Shot Dense Retrieval without Relevance Labels"
    https://arxiv.org/abs/2212.10496
"""

from __future__ import annotations

from typing import Any

import structlog
from backend.infrastructure.llm.model_id_registry import get_model_id

logger = structlog.get_logger(__name__)

_SYSTEM = (
    "You are a data analytics expert. "
    "Write a 2-3 sentence hypothetical data insight that would answer the question. "
    "Be specific about column names and numbers."
)

# If the query is longer than this, it likely already contains context
_QUERY_LENGTH_SKIP_THRESHOLD = 200


class HyDEExpander:
    """Expands a user query into a hypothetical answer for better RAG retrieval.

    Args:
        llm_client: Async LLM client (Claude Haiku for speed).
                    When None, returns the original query unchanged.
        use_hyde:   Global on/off switch (default True).
                    Can be overridden per-call.
    """

    def __init__(self, llm_client: Any = None, use_hyde: bool = True) -> None:  # noqa: ANN401
        self._llm = llm_client
        self._use_hyde = use_hyde

    async def expand(
        self,
        query: str,
        schema_summary: str = "",
        use_hyde: bool | None = None,
    ) -> str:
        """Expand a query into a hypothetical answer for embedding.

        Args:
            query:          The user's natural-language question.
            schema_summary: Brief description of available columns
                            (injected into the HyDE prompt to improve specificity).
            use_hyde:       Override the instance-level use_hyde setting.

        Returns:
            The hypothetical answer string (or original query when HyDE is skipped).
        """
        should_use = self._use_hyde if use_hyde is None else use_hyde

        # Skip conditions
        if not should_use or not self._llm:
            return query

        if len(query) > _QUERY_LENGTH_SKIP_THRESHOLD:
            logger.debug("hyde_skipped_long_query", length=len(query))
            return query

        schema_hint = (
            f"\nDataset columns available: {schema_summary[:300]}" if schema_summary else ""
        )

        prompt = (
            f"The user is analysing a business dataset.{schema_hint}\n\n"
            f"Question: {query}\n\n"
            "Write a 2-3 sentence hypothetical data insight that would answer "
            "this question. Include specific column names and plausible numbers."
        )

        try:
            expanded = await self._llm.complete(
                prompt=prompt,
                system=_SYSTEM,
                model_id=get_model_id("schema"),  # Haiku for speed
                max_tokens=150,
            )
            result = expanded.strip()
            logger.debug(
                "hyde_expanded",
                original_len=len(query),
                expanded_len=len(result),
            )
            return result
        except Exception as exc:
            logger.debug("hyde_expansion_failed", error=str(exc))
            return query  # fall back to original query

    async def expand_multi(
        self,
        query: str,
        schema_summary: str = "",
        n: int = 2,
    ) -> list[str]:
        """Generate N hypothetical answers for multi-vector retrieval.

        Returns a list of expanded queries. The Retriever then embeds each
        and averages the vectors before searching Qdrant (reduces variance).

        Args:
            query:          The user's question.
            schema_summary: Column context hint.
            n:              Number of hypothetical answers to generate (default 2).

        Returns:
            List of expanded strings. Falls back to [query] on failure.
        """
        if not self._llm or n <= 1:
            expanded = await self.expand(query, schema_summary)
            return [expanded]

        import asyncio

        tasks = [self.expand(query, schema_summary) for _ in range(n)]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        valid = [r for r in results if isinstance(r, str)]
        return valid if valid else [query]
