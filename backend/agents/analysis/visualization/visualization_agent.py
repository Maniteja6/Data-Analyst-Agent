"""VisualizationAgent — selects chart type and generates Vega-Lite specs.

Called after the SQLAgent or PythonAgent produces rows so the InsightAgent
can embed charts alongside narrative explanations.

For real-time applications: the generated Vega-Lite spec dict is returned
directly in the Socket.IO ``chat:complete`` event payload under the
``visualizations`` key. The React frontend passes it to ``VegaEmbed``.
"""

from __future__ import annotations

from typing import Any

import structlog
from backend.agents.analysis.visualization.chart_type_selector import (
    CAT_TYPES,
    DATE_TYPES,
    NUMERIC_TYPES,
    select_chart_type,
)
from backend.agents.analysis.visualization.vega_spec_generator import (
    build_bar_spec,
    build_histogram_spec,
    build_line_spec,
    build_scatter_spec,
)
from backend.agents.base.agent_context import AgentContext
from backend.agents.base.base_agent import BaseAgent

logger = structlog.get_logger(__name__)


class VisualizationAgent(BaseAgent):
    """Produces Vega-Lite v5 chart specifications from query result rows.

    Args:
        llm_client: Optional LLM client for chart title generation.
    """

    MAX_DATA_POINTS = 500  # cap data sent to the frontend

    def __init__(self, llm_client: Any = None) -> None:  # noqa: ANN401
        super().__init__("visualization")
        self._llm = llm_client

    async def _execute(
        self,
        context: AgentContext,
        data: list[dict] | None = None,
        user_intent: str = "",
        title: str = "",
        **kwargs: Any,  # noqa: ANN401
    ) -> dict:
        """Generate a Vega-Lite chart spec from result rows.

        Args:
            context:     Shared pipeline state (schema used for semantic types).
            data:        Rows from SQLAgent or PythonAgent result.
            user_intent: Natural-language description of what the user asked for.
            title:       Optional chart title override.

        Returns:
            Dict with keys: spec, chart_type, x, y, data_point_count, error.
        """
        if not data:
            return {
                "spec": None,
                "chart_type": None,
                "data_point_count": 0,
                "error": "No data provided to VisualizationAgent",
            }

        schema = context.schema or {}
        col_map = {c["name"]: c.get("semantic_type", "unknown") for c in schema.get("columns", [])}

        # Build semantic type map for the result columns only
        result_col_types = {key: col_map.get(key, "unknown") for key in data[0]}

        # Select chart type
        chart_info = select_chart_type(
            col_types=result_col_types,
            intent=user_intent,
            row_count=len(data),
        )

        mark = chart_info.get("mark", "bar")
        x_type = chart_info.get("x_type", "nominal")
        y_type = chart_info.get("y_type", "quantitative")
        horizontal = chart_info.get("orient") == "horizontal"

        # Pick x and y columns based on type priority
        keys = list(data[0].keys())
        x_col = self._pick_col(keys, result_col_types, x_type)
        y_col = self._pick_col(keys, result_col_types, y_type, exclude=x_col)

        # Generate chart title via LLM if not provided
        chart_title = title or await self._generate_title(user_intent, x_col, y_col)

        # Cap data points for frontend performance
        plot_data = data[: self.MAX_DATA_POINTS]

        # Build the spec
        if mark == "line":
            spec = build_line_spec(plot_data, x_col, y_col, title=chart_title)
        elif mark == "point":
            color_col = next(
                (
                    k
                    for k, t in result_col_types.items()
                    if t in CAT_TYPES and k not in (x_col, y_col)
                ),
                None,
            )
            spec = build_scatter_spec(
                plot_data, x_col, y_col, color_col=color_col, title=chart_title
            )
        elif chart_info.get("is_histogram"):
            spec = build_histogram_spec(
                plot_data,
                x_col,
                bin_count=chart_info.get("bin_count", 20),
                title=chart_title,
            )
        else:
            spec = build_bar_spec(
                plot_data,
                x_col,
                y_col,
                title=chart_title,
                horizontal=horizontal,
            )

        logger.info(
            "visualization_agent_complete",
            chart_type=mark,
            x=x_col,
            y=y_col,
            data_points=len(plot_data),
        )

        return {
            "spec": spec,
            "chart_type": mark,
            "x": x_col,
            "y": y_col,
            "data_point_count": len(plot_data),
            "truncated": len(data) > self.MAX_DATA_POINTS,
            "error": None,
        }

    @staticmethod
    def _pick_col(
        keys: list[str],
        col_types: dict[str, str],
        preferred_type: str,
        exclude: str | None = None,
    ) -> str:
        """Pick the best column for an axis based on the preferred Vega type."""
        type_priority: dict[str, frozenset] = {
            "temporal": DATE_TYPES,
            "quantitative": NUMERIC_TYPES,
            "nominal": CAT_TYPES,
        }
        preferred_set = type_priority.get(preferred_type, frozenset())
        for key in keys:
            if key == exclude:
                continue
            if col_types.get(key) in preferred_set:
                return key
        # Fallback: first non-excluded key
        return next((k for k in keys if k != exclude), keys[0] if keys else "x")

    async def _generate_title(self, intent: str, x: str, y: str) -> str:
        """Generate a concise chart title from the user intent."""
        if not intent:
            return f"{y} by {x}"
        if not self._llm:
            return f"{y} by {x}"
        try:
            from backend.infrastructure.llm.model_id_registry import get_model_id

            prompt = (
                f"Write a short chart title (5 words max) for a chart showing "
                f"'{y}' on the y-axis and '{x}' on the x-axis. "
                f"User asked: '{intent}'. "
                "Return ONLY the title string."
            )
            return await self._llm.complete(prompt=prompt, model_id=get_model_id("intent"))
        except Exception:
            return f"{y} by {x}"
