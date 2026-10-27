"""Scoping-safety behavior for TaskTools.run_task and stop_task.

Covers the failure modes where a run can launch against more hosts than the
caller intended: `limit`/`inventory_id` ignored by the template, and scoping
options that never reach the payload. The tool must fail fast on the former
and make the effective invocation visible for the latter.
"""

import json
from unittest.mock import MagicMock

import pytest
import pytest_asyncio

from semaphore_mcp.tools.tasks import TaskTools


@pytest_asyncio.fixture
async def task_tools():
    mock_semaphore = MagicMock()
    mock_semaphore.run_task.return_value = {"id": 42}
    return TaskTools(mock_semaphore)


def template_with(overrides: dict, allow_args: bool = False) -> dict:
    return {
        "id": 7,
        "name": "t",
        "task_params": overrides,
        "allow_override_args_in_task": allow_args,
    }


class TestTagsMerge:
    def test_no_tags_serializes_list_arguments(self, task_tools):
        assert task_tools._merge_tags_into_arguments(None, ["--diff"]) == json.dumps(
            ["--diff"]
        )

    def test_tags_appended_to_list_arguments(self, task_tools):
        merged = json.loads(
            task_tools._merge_tags_into_arguments("web,deploy", ["--diff"])
        )
        assert merged == ["--diff", "--tags", "web,deploy"]

    def test_tags_appended_to_json_string_arguments(self, task_tools):
        merged = json.loads(
            task_tools._merge_tags_into_arguments("web", json.dumps(["--diff"]))
        )
        assert merged == ["--diff", "--tags", "web"]

    def test_tags_creates_arguments_when_absent(self, task_tools):
        merged = json.loads(task_tools._merge_tags_into_arguments("web", None))
        assert merged == ["--tags", "web"]


class TestOverrideGuard:
    @pytest.mark.asyncio
    async def test_refuses_limit_the_template_would_ignore(self, task_tools):
        task_tools.semaphore.get_template.return_value = template_with(
            {"allow_override_limit": False}
        )

        result = await task_tools.run_task(
            template_id=7, project_id=1, limit="webservers"
        )

        assert result["error"] == "refused_to_launch_unscoped"
        assert any("allow_override_limit" in detail for detail in result["details"])
        task_tools.semaphore.run_task.assert_not_called()

    @pytest.mark.asyncio
    async def test_refuses_inventory_override_the_template_would_ignore(
        self, task_tools
    ):
        task_tools.semaphore.get_template.return_value = template_with(
            {"allow_override_inventory": False}
        )

        result = await task_tools.run_task(template_id=7, project_id=1, inventory_id=3)

        assert result["error"] == "refused_to_launch_unscoped"
        task_tools.semaphore.run_task.assert_not_called()

    @pytest.mark.asyncio
    async def test_launches_when_override_is_enabled(self, task_tools):
        task_tools.semaphore.get_template.return_value = template_with(
            {"allow_override_limit": True, "allow_override_inventory": True},
            allow_args=True,
        )

        result = await task_tools.run_task(
            template_id=7, project_id=1, limit="webservers", tags="nginx"
        )

        assert "error" not in result
        _, kwargs = task_tools.semaphore.run_task.call_args
        assert kwargs["limit"] == "webservers"
        assert json.loads(kwargs["arguments"]) == ["--tags", "nginx"]

    @pytest.mark.asyncio
    async def test_refuses_arguments_the_template_would_drop(self, task_tools):
        task_tools.semaphore.get_template.return_value = template_with(
            {"allow_override_limit": True}
        )

        result = await task_tools.run_task(
            template_id=7, project_id=1, arguments=["--diff"]
        )

        assert result["error"] == "refused_to_launch_unscoped"
        assert any("allow_override_args_in_task" in d for d in result["details"])
        task_tools.semaphore.run_task.assert_not_called()

    @pytest.mark.asyncio
    async def test_refuses_tags_the_template_would_drop(self, task_tools):
        task_tools.semaphore.get_template.return_value = template_with(
            {"allow_override_limit": True}
        )

        result = await task_tools.run_task(template_id=7, project_id=1, tags="nginx")

        assert result["error"] == "refused_to_launch_unscoped"
        assert any("tags was provided" in d for d in result["details"])
        task_tools.semaphore.run_task.assert_not_called()

    @pytest.mark.asyncio
    async def test_template_introspection_failure_does_not_block(self, task_tools):
        task_tools.semaphore.get_template.side_effect = RuntimeError("boom")

        result = await task_tools.run_task(
            template_id=7, project_id=1, limit="webservers"
        )

        assert "error" not in result
        task_tools.semaphore.run_task.assert_called_once()

    @pytest.mark.asyncio
    async def test_unscoped_launch_skips_the_template_lookup(self, task_tools):
        await task_tools.run_task(template_id=7, project_id=1)

        task_tools.semaphore.get_template.assert_not_called()
        task_tools.semaphore.run_task.assert_called_once()


class TestEffectiveInvocation:
    @pytest.mark.asyncio
    async def test_response_echoes_exactly_what_was_sent(self, task_tools):
        result = await task_tools.run_task(
            template_id=7,
            project_id=1,
            diff=True,
            tags="nginx",
            message="scoped apply",
            environment={"FOO": "bar"},
        )

        effective = result["effective_invocation"]
        assert effective["template_id"] == 7
        assert effective["diff"] is True
        assert effective["limit"] is None
        assert effective["message"] == "scoped apply"
        assert effective["environment"] == '{"FOO": "bar"}'
        assert effective["arguments"] == json.dumps(["--tags", "nginx"])
        _, kwargs = task_tools.semaphore.run_task.call_args
        assert effective["arguments"] == kwargs["arguments"]
        assert kwargs["environment"] == {"FOO": "bar"}

    def test_tags_merges_into_an_existing_tags_flag(self, task_tools):
        merged = json.loads(
            task_tools._merge_tags_into_arguments(
                "web,deploy", '["--diff", "--tags", "web"]'
            )
        )
        assert merged == ["--diff", "--tags", "web,deploy"]


class TestArgumentsFormat:
    """Regression coverage from issue #4: the argument representation must be
    accepted at the MCP boundary AND serialize to exactly the JSON array
    Semaphore's TaskRunner requires — never a shell string or double-encoded
    JSON."""

    @pytest.mark.asyncio
    async def test_native_list_serializes_to_the_exact_json_array(self, task_tools):
        task_tools.semaphore.get_template.return_value = template_with(
            {}, allow_args=True
        )
        await task_tools.run_task(
            template_id=7,
            project_id=1,
            arguments=["--diff", "--tags", "app"],
        )

        _, kwargs = task_tools.semaphore.run_task.call_args
        assert kwargs["arguments"] == '["--diff", "--tags", "app"]'

    @pytest.mark.asyncio
    async def test_documented_json_string_passes_through_unchanged(self, task_tools):
        task_tools.semaphore.get_template.return_value = template_with(
            {}, allow_args=True
        )
        await task_tools.run_task(
            template_id=7,
            project_id=1,
            arguments='["--diff", "--tags", "app"]',
        )

        _, kwargs = task_tools.semaphore.run_task.call_args
        assert kwargs["arguments"] == '["--diff", "--tags", "app"]'

    @pytest.mark.asyncio
    async def test_non_string_array_elements_fail_fast_before_launch(self, task_tools):
        for bad in ('["--forks", 5]', "[null]", ["ok", 2]):
            result = await task_tools.run_task(
                template_id=7, project_id=1, arguments=bad
            )
            assert result["error"] == "invalid_arguments_format", bad
            task_tools.semaphore.run_task.assert_not_called()

    @pytest.mark.asyncio
    async def test_shell_string_fails_fast_before_launch(self, task_tools):
        result = await task_tools.run_task(
            template_id=7, project_id=1, arguments="--tags app"
        )

        assert result["error"] == "invalid_arguments_format"
        assert "JSON array" in result["details"][0]
        task_tools.semaphore.run_task.assert_not_called()

    @pytest.mark.asyncio
    async def test_double_encoded_string_fails_fast_before_launch(self, task_tools):
        result = await task_tools.run_task(
            template_id=7,
            project_id=1,
            arguments='"[\\"--diff\\"]"',
        )

        assert result["error"] == "invalid_arguments_format"
        task_tools.semaphore.run_task.assert_not_called()


class TestStopTaskStatus:
    @pytest.mark.asyncio
    async def test_returns_post_stop_status(self, task_tools):
        task_tools.semaphore.get_task.return_value = {
            "id": 42,
            "status": "stopped",
        }

        result = await task_tools.stop_task(project_id=1, task_id=42)

        assert result["stopped"] is True
        assert result["status"] == "stopped"
        assert result["task"]["id"] == 42

    @pytest.mark.asyncio
    async def test_status_fetch_failure_still_reports_stopped(self, task_tools):
        task_tools.semaphore.get_task.side_effect = RuntimeError("gone")

        result = await task_tools.stop_task(project_id=1, task_id=42)

        assert result["stopped"] is True
        assert result["status"] is None
