"""QueryBuilder — constructs safe DuckDB queries from structured intent."""

from __future__ import annotations

from typing import Any


class QueryBuilder:
    """Builds parameterised DuckDB SELECT statements from structured intent dicts.

    The SQL Agent generates a structured intent dict after understanding the
    user's question. The QueryBuilder converts that intent into a DuckDB
    query, ensuring column names are properly quoted to prevent injection.

    Usage::

        builder = QueryBuilder()
        sql = builder.aggregate(
            table="df",
            agg_func="SUM",
            column="revenue",
            group_by=["region"],
            filters=[{"column": "year", "op": "=", "value": 2024}],
            order_by=[{"column": "revenue_sum", "desc": True}],
            limit=10,
        )
    """

    _ALLOWED_AGG_FUNCS = frozenset(
        {
            "SUM",
            "AVG",
            "COUNT",
            "MIN",
            "MAX",
            "MEDIAN",
            "STDDEV",
            "VAR_POP",
            "FIRST",
            "LAST",
            "LIST",
            "COUNT_STAR",
        }
    )
    _ALLOWED_OPS = frozenset(
        {"=", "!=", "<", "<=", ">", ">=", "LIKE", "IN", "IS NULL", "IS NOT NULL"}
    )

    # ── Query builders ────────────────────────────────────────────────────

    def aggregate(
        self,
        table: str,
        agg_func: str,
        column: str | None,
        group_by: list[str] | None = None,
        filters: list[dict] | None = None,
        order_by: list[dict] | None = None,
        limit: int = 1000,
    ) -> str:
        """Build a GROUP BY aggregation query."""
        agg_func = agg_func.upper()
        if agg_func not in self._ALLOWED_AGG_FUNCS:
            raise ValueError(f"Unsupported aggregation function: {agg_func!r}")

        select_parts = []
        if group_by:
            select_parts.extend(self._quote(c) for c in group_by)
        if column:
            alias = f"{agg_func.lower()}_{column}"
            select_parts.append(f"{agg_func}({self._quote(column)}) AS {self._quote(alias)}")
        elif agg_func == "COUNT_STAR":
            select_parts.append("COUNT(*) AS count_star")

        where_clause = self._build_where(filters)
        group_clause = "GROUP BY " + ", ".join(self._quote(c) for c in group_by) if group_by else ""
        order_clause = self._build_order_by(order_by)

        return self._build_select(
            table=table,
            select_list=", ".join(select_parts) or "*",
            where=where_clause,
            group_by=group_clause,
            order_by=order_clause,
            limit=limit,
        )

    def filter_rows(
        self,
        table: str,
        filters: list[dict],
        columns: list[str] | None = None,
        limit: int = 1000,
    ) -> str:
        """Build a filtered SELECT query."""
        select_list = ", ".join(self._quote(c) for c in columns) if columns else "*"
        return self._build_select(
            table=table,
            select_list=select_list,
            where=self._build_where(filters),
            limit=limit,
        )

    def top_n(
        self,
        table: str,
        rank_column: str,
        n: int = 10,
        group_by: list[str] | None = None,
        ascending: bool = False,
    ) -> str:
        """Build a TOP-N query ranked by a column."""
        select_list = ", ".join(self._quote(c) for c in group_by) if group_by else "*"
        order_dir = "ASC" if ascending else "DESC"
        # select_list/table/rank_column are all routed through self._quote()
        # (identifier-escaping), order_dir is a hardcoded ASC/DESC literal, and
        # n is coerced to int — nothing here is raw string interpolation of
        # untrusted values.
        return (
            f"SELECT {select_list} FROM {self._quote(table)} "  # noqa: S608
            f"ORDER BY {self._quote(rank_column)} {order_dir} "
            f"LIMIT {int(n)}"
        )

    # ── Private helpers ───────────────────────────────────────────────────

    def _build_where(self, filters: list[dict] | None) -> str:
        if not filters:
            return ""
        clauses = []
        for f in filters:
            col = self._quote(f["column"])
            op = f["op"].upper()
            val = f.get("value")
            if op not in self._ALLOWED_OPS:
                continue
            if op in ("IS NULL", "IS NOT NULL"):
                clauses.append(f"{col} {op}")
            elif op == "IN":
                vals = ", ".join(self._literal(v) for v in val)
                clauses.append(f"{col} IN ({vals})")
            else:
                clauses.append(f"{col} {op} {self._literal(val)}")
        return "WHERE " + " AND ".join(clauses) if clauses else ""

    def _build_order_by(self, order_by: list[dict] | None) -> str:
        if not order_by:
            return ""
        parts = []
        for o in order_by:
            col = self._quote(o["column"])
            dir = "DESC" if o.get("desc") else "ASC"
            parts.append(f"{col} {dir}")
        return "ORDER BY " + ", ".join(parts)

    def _build_select(
        self,
        table: str,
        select_list: str,
        where: str = "",
        group_by: str = "",
        order_by: str = "",
        limit: int = 1000,
    ) -> str:
        parts = [
            f"SELECT {select_list}",
            f"FROM {self._quote(table)}",
            where,
            group_by,
            order_by,
            f"LIMIT {int(limit)}" if limit else "",
        ]
        return " ".join(p for p in parts if p)

    @staticmethod
    def _quote(name: str) -> str:
        """Double-quote a column or table name, escaping internal quotes."""
        safe = name.replace('"', '""')
        return f'"{safe}"'

    @staticmethod
    def _literal(value: Any) -> str:  # noqa: ANN401
        """Convert a Python value to a SQL literal string."""
        if value is None:
            return "NULL"
        if isinstance(value, bool):
            return "TRUE" if value else "FALSE"
        if isinstance(value, int | float):
            return str(value)
        safe = str(value).replace("'", "''")
        return f"'{safe}'"
