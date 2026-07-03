"""Unit tests for SQLAgent (mocked LLM + DuckDB)."""
import pytest


@pytest.mark.unit
class TestSQLAgent:

    @pytest.mark.asyncio
    async def test_sql_agent_executes_generated_query(self, sample_df, mock_llm):
        mock_llm.set_response("SQL", "SELECT SUM(revenue) AS total FROM df")
        try:
            from backend.agents.sql_agent import SQLAgent
            from backend.analytics_engine.sql_engine.duckdb_manager import DuckDBManager
            agent  = SQLAgent(llm=mock_llm, db=DuckDBManager())
            result = await agent.run(
                df=sample_df,
                user_question="What is the total revenue?",
                intent={"intent": "statistical_question", "requires_sql": True},
            )
            assert "rows" in result or "sql" in result
        except ImportError:
            pytest.skip("SQLAgent not yet implemented")


@pytest.mark.unit
class TestQueryBuilder:

    def test_aggregate_builds_sum_query(self):
        from backend.analytics_engine.sql_engine.query_builder import QueryBuilder
        qb  = QueryBuilder()
        sql = qb.aggregate(table="df", agg_func="SUM", column="revenue")
        assert "SUM" in sql.upper()
        assert '"revenue"' in sql

    def test_aggregate_rejects_unknown_function(self):
        from backend.analytics_engine.sql_engine.query_builder import QueryBuilder
        with pytest.raises(ValueError):
            QueryBuilder().aggregate(table="df", agg_func="DROP TABLE", column="x")

    def test_filter_rows_builds_where_clause(self):
        from backend.analytics_engine.sql_engine.query_builder import QueryBuilder
        sql = QueryBuilder().filter_rows(
            table="df",
            filters=[{"column": "region", "op": "=", "value": "North"}],
        )
        assert "WHERE" in sql
        assert "'North'" in sql

    def test_column_names_are_quoted(self):
        from backend.analytics_engine.sql_engine.query_builder import QueryBuilder
        sql = QueryBuilder().top_n(table="df", rank_column="revenue", n=5)
        assert '"revenue"' in sql
