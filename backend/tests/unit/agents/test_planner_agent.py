"""Unit tests for PlannerAgent and ExecutionPlan."""
import pytest


@pytest.mark.unit
class TestExecutionPlan:

    def test_create_default_plan_has_required_agents(self):
        from backend.domain.intelligence.entities.execution_plan import ExecutionPlan
        plan = ExecutionPlan.create_default(
            plan_id="p1", session_id="s1", dataset_id="d1", has_datetime=True,
        )
        agent_names = {t.agent.value for t in plan.tasks}
        assert "schema"    in agent_names
        assert "profiling" in agent_names
        assert "insight"   in agent_names
        assert "forecast"  in agent_names   # because has_datetime=True

    def test_create_default_plan_no_forecast_without_datetime(self):
        from backend.domain.intelligence.entities.execution_plan import ExecutionPlan
        plan = ExecutionPlan.create_default(
            plan_id="p2", session_id="s1", dataset_id="d1", has_datetime=False
        )
        agent_names = {t.agent.value for t in plan.tasks}
        assert "forecast" not in agent_names

    def test_plan_validates_no_cycles(self):
        from backend.domain.intelligence.entities.execution_plan import ExecutionPlan
        plan = ExecutionPlan.create_default("p3", "s1", "d1")
        plan.validate()   # should not raise

    def test_get_ready_tasks_respects_dependencies(self):
        from backend.domain.intelligence.entities.execution_plan import ExecutionPlan
        plan  = ExecutionPlan.create_default("p4", "s1", "d1")
        ready = plan.get_ready_tasks(completed_ids=set())
        assert all(len(t.depends_on) == 0 for t in ready)

    def test_plan_marks_complete_after_all_tasks_succeed(self):
        from backend.domain.intelligence.entities.execution_plan import ExecutionPlan, PlanStatus
        plan = ExecutionPlan.create_default("p5", "s1", "d1", has_datetime=False)
        plan.begin()
        for task in plan.tasks:
            plan.record_task_complete(task.id, duration_ms=100)
        assert plan.status == PlanStatus.COMPLETE

    def test_failed_task_skips_dependents(self):
        from backend.domain.intelligence.entities.execution_plan import ExecutionPlan
        from backend.domain.intelligence.entities.task_node import TaskStatus

        plan = ExecutionPlan.create_default("p6", "s1", "d1")
        plan.begin()
        # Fail the first no-dependency task
        first_task = next(t for t in plan.tasks if len(t.depends_on) == 0)
        plan.record_task_failed(first_task.id, error="test error")
        # Its dependents should be SKIPPED
        skipped = [t for t in plan.tasks if t.status == TaskStatus.SKIPPED]
        assert len(skipped) > 0
