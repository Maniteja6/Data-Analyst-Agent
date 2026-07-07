"""Schema inference — fast rule-based typing + LLM disambiguation.

TypeInferencer:      sync, < 5ms for 50 columns; 13 semantic types.
SemanticClassifier:  batches all ambiguous columns into ONE Haiku call.
SchemaAgent:         orchestrates both; emits schema:column_classified per column.
"""

from backend.agents.data.schema.schema_agent import SchemaAgent
from backend.agents.data.schema.semantic_classifier import SemanticClassifier
from backend.agents.data.schema.type_inferencer import infer_all_columns, infer_column

__all__ = ["SchemaAgent", "infer_column", "infer_all_columns", "SemanticClassifier"]
