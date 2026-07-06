"""Test suite for the DataPilot backend.

Test pyramid (3 layers + eval harness):
    unit/          (pytest -m unit)        No I/O, < 1s per test
        domain/    — Dataset state machine, KPICalculator, DataQualityScorer
        analytics/ — DataProfiler, AnomalyDetector, TrendAnalyzer
        agents/    — All 19 agents with MockLLMService + InMemoryCacheAdapter
                      test_bedrock_client.py  — retry handler + LLMResponse parsing
                      test_planner_agent.py   — ExecutionPlan DAG validation
                      test_schema_agent.py    — column type inference
                      test_sql_agent.py       — QueryBuilder + DuckDB execution
                      test_security_agent.py  — injection classifier + TokenTracker

    integration/   (pytest -m integration)  DuckDB + LocalStorage only
        test_upload_pipeline.py    — UploadDatasetUseCase with fake repo
        test_analysis_pipeline.py  — profiler → cleaner → anomaly detector
        test_chat_pipeline.py      — SendMessageUseCase with mock LLM
        test_report_generation.py  — JSON render + XLSX bytes validation
        test_bedrock_integration.py— SKIPPED unless FEATURE_BEDROCK=true

    e2e/           (pytest -m e2e)          E2E_ENABLED=true required
        test_full_lifecycle.py     — upload → job poll → delete → 404
        fixtures/
            sample_sales.csv           (15 rows, deliberate negative revenue)
            sample_financial.xlsx      (6 quarters, 6 columns)
            sample_timeseries.parquet  (90 days daily sales)

    evals/         (python -m backend.tests.evals.eval_runner)
        eval_runner.py             — aggregates suites, exits 1 if < 80% pass
        sql_agent_eval/            — 3 NL→SQL generation test cases
        insight_agent_eval/        — 2 KPI structural test cases
        forecast_agent_eval/       — 1 trend direction test case

Root conftest.py — 10 shared fixtures:
    sample_df           session-scoped polars/pandas DataFrame (15 rows)
    sample_df_with_nulls same + every 3rd revenue null (imputation tests)
    in_memory_cache     InMemoryCacheAdapter, cleared between tests
    local_storage       LocalStorageAdapter in pytest tmp_path
    mock_llm            MockLLMService with canned schema/insight/SQL/intent/
                        critic responses; records all calls in .calls
    null_job_service    NullJobAdapter — no Celery broker required
    fake_dataset        Dataset aggregate in UPLOADED status (events consumed)
    fake_session_id     UUID string
    fake_profile        DataProfile built from sample_df
    fake_conversation   Empty Conversation aggregate (events consumed)
    async_client        httpx.AsyncClient against FastAPI app with
                        cache/storage/job overrides

Test environment (APP_ENV=test, set in conftest.py before any imports):
    DATABASE_URL = sqlite+aiosqlite:///:memory:   no Postgres needed
    REDIS_URL    = memory://                      InMemoryCacheAdapter
    MockLLMService replaces BedrockLLMService     no AWS credentials needed
    NullJobAdapter replaces CeleryJobAdapter      no broker needed
    AgentContext._sio = MagicMock()               no Socket.IO server needed
    Feature flags:  FEATURE_KAFKA=false, FEATURE_CLICKHOUSE=false
"""
