"""DeepSeek CLI agent with explicit local tools; independent of older transports."""
from __future__ import annotations
import datetime as dt
import json
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile
import time

try:
    from . import cli_transport
except ImportError:
    import cli_transport

ACTUAL_MODEL = cli_transport.ACTUAL_MODEL
CLI_ALIAS = cli_transport.CLI_ALIAS
ALLOWED_TOOLS = ("Bash", "Read", "Write")


def python_path():
    path = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local")) / "Programs/Python/Python314/python.exe"
    return path.resolve() if path.is_file() else Path(sys.executable).resolve()


def fingerprint():
    metadata = cli_transport.fingerprint()
    metadata.update(protocol="tclaude_cli_agent", tools=list(ALLOWED_TOOLS),
        allowed_tools=list(ALLOWED_TOOLS), permission_mode="dontAsk", hard_os_sandbox=False,
        workspace_location="fresh system temporary directory for each clip",
        workspace_initial_files=["pose.json"], python_executable=str(python_path()),
        max_model_turns=None, timeout_seconds=600,
        scope_review="Visible tool calls and saved scripts require independent review; not an OS access guarantee")
    return metadata


def parse_output(stdout, stderr, expected=ACTUAL_MODEL, workspace=None):
    events, non_json = [], []
    for line in stdout.decode("utf-8", errors="replace").splitlines():
        try:
            event = json.loads(line)
            if isinstance(event, dict):
                events.append(event)
            else:
                non_json.append(line)
        except ValueError:
            if line.strip():
                non_json.append(line)
    init = [event for event in events if event.get("type") == "system" and event.get("subtype") == "init"]
    assistants = [event for event in events if event.get("type") == "assistant"]
    reported_models = sorted({event.get("message", {}).get("model") for event in assistants if event.get("message", {}).get("model")})
    actual_models = sorted({event.get("message", {}).get("model") for event in assistants
        if event.get("message", {}).get("model") and not event.get("isSynthetic") and
        not event.get("isApiErrorMessage") and not event["message"]["model"].startswith("<")})
    results = [event for event in events if event.get("type") == "result"]
    final = results[-1] if results else {}
    tool_calls = []
    for index, event in enumerate(events):
        if event.get("type") == "assistant":
            for block in event.get("message", {}).get("content", []):
                if block.get("type") == "tool_use":
                    tool_calls.append({"event_index": index, **block})
    tool_results, synthetic = [], []
    for index, event in enumerate(events):
        if event.get("type") != "user":
            continue
        content = event.get("message", {}).get("content", [])
        if event.get("type") == "user":
            if event.get("isSynthetic"):
                synthetic.append({"event_index": index, "content": content})
            if isinstance(content, list):
                tool_results.extend({"event_index": index, **block} for block in content
                                    if isinstance(block, dict) and block.get("type") == "tool_result")
    tools = sorted({tool for event in init for tool in event.get("tools", [])})
    mcp = [server for event in init for server in event.get("mcp_servers", [])]
    tool_configuration_ok = bool(init) and tools == sorted(ALLOWED_TOOLS) and not mcp
    unexpected_tools = sorted({call.get("name", "") for call in tool_calls} - set(ALLOWED_TOOLS))
    completed = len(results) == 1 and final.get("subtype") == "success" and final.get("is_error") is False
    identity_ok = actual_models == [expected]
    text = final.get("result") if isinstance(final.get("result"), str) else ""
    if completed and not text:
        for event in reversed(assistants):
            pieces = [block.get("text", "") for block in event.get("message", {}).get("content", []) if block.get("type") == "text"]
            if pieces:
                text = "\n".join(pieces)
                break
    raw_usage = final.get("usage")
    usage = None
    if isinstance(raw_usage, dict) and isinstance(raw_usage.get("input_tokens"), (int, float)) and isinstance(raw_usage.get("output_tokens"), (int, float)):
        usage = dict(raw_usage)
        usage["input_tokens_uncached"] = raw_usage["input_tokens"]
        usage["input_tokens"] = sum(raw_usage.get(key, 0) for key in ("input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens"))
        usage["total_tokens"] = usage["input_tokens"] + usage["output_tokens"]
    direct_outside = []
    if workspace:
        workspace = Path(workspace).resolve()
        for call in tool_calls:
            if call.get("name") in {"Read", "Write"}:
                value = (call.get("input") or {}).get("file_path")
                if isinstance(value, str):
                    path = Path(value)
                    resolved = (path if path.is_absolute() else workspace / path).resolve()
                    if not resolved.is_relative_to(workspace):
                        direct_outside.append({"id": call.get("id"), "tool": call["name"], "path": value})
    synthetic_count = sum("Output token limit hit" in json.dumps(event["content"], ensure_ascii=False) for event in synthetic)
    errors = []
    if not identity_ok:
        errors.append(f"Assistant model identity mismatch: {actual_models}")
    if not completed:
        errors.append("Missing or unsuccessful final CLI result")
    if not tool_configuration_ok or unexpected_tools:
        errors.append("Advertised/called tools or MCP differ from the explicit configuration")
    if direct_outside:
        errors.append("A visible Read/Write tool requested a file outside the task workspace")
    return dict(ok=completed and identity_ok and tool_configuration_ok and not unexpected_tools and not direct_outside and bool(text),
        actual_model=actual_models[0] if len(actual_models) == 1 else None, model_matches=identity_ok,
        status="scope_violation" if direct_outside else "completed" if completed else "cli_error",
        text=text, usage=usage, http_status=None, error="; ".join(errors) if errors else None,
        raw_response={"events": events, "stdout_jsonl": stdout.decode("utf-8", errors="replace"),
                      "stderr": stderr.decode("utf-8", errors="replace"), "non_json_stdout_lines": non_json},
        cli_audit=dict(assistant_models=reported_models, actual_models=actual_models,
            init_models=[event.get("model") for event in init], tools=tools, mcp_servers=mcp,
            tool_configuration_verified=tool_configuration_ok, tool_calls=tool_calls, tool_results=tool_results,
            tool_call_count=len(tool_calls), num_turns=final.get("num_turns"),
            synthetic_user_messages=synthetic, synthetic_user_count=len(synthetic),
            output_limit_continuation_count=synthetic_count, raw_usage=raw_usage,
            reported_model_usage=final.get("modelUsage"), direct_file_requests_outside_workspace=direct_outside,
            external_access_audit_status="requires_independent_tool_and_script_review",
            hard_os_sandbox=False, controller_retries=0, upstream_retry_count=None))


def archive_workspace(workspace, destination):
    """Archive regular workspace files without following links outside it."""
    workspace, destination = Path(workspace).resolve(), Path(destination)
    destination.mkdir(parents=True, exist_ok=False)
    files, skipped = [], []
    for current, directories, names in os.walk(workspace, followlinks=False):
        kept = []
        for name in directories:
            path = Path(current) / name
            if path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction()):
                skipped.append(path.relative_to(workspace).as_posix())
            else:
                kept.append(name)
        directories[:] = kept
        for name in names:
            path = Path(current) / name
            relative = path.relative_to(workspace)
            if path.is_symlink() or not path.resolve().is_relative_to(workspace) or not path.is_file():
                skipped.append(relative.as_posix())
                continue
            data = path.read_bytes()
            target = destination / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            files.append({"path": relative.as_posix(), "sha256": cli_transport.sha(data), "size_bytes": len(data)})
    return {"files": files, "skipped_links_or_nonregular_files": skipped}


def call_model(model, system, user, pose_bytes, artifact_dir, *, max_tokens=8192,
               reasoning_effort="medium", timeout=600):
    started = time.monotonic()
    result = dict(requested_model=model, requested_cli_alias=CLI_ALIAS, route="tclaude_cli_agent",
        started_utc=dt.datetime.now(dt.timezone.utc).isoformat(), ok=False, status="not_sent", text="",
        actual_model=None, model_matches=False, http_status=None, usage=None, error=None,
        max_output_tokens_requested=max_tokens, max_output_tokens_applied=None,
        max_output_tokens_configuration=f"CLAUDE_CODE_MAX_OUTPUT_TOKENS={max_tokens}",
        reasoning_effort_requested=reasoning_effort, reasoning_effort_applied=None,
        automatic_retries=0, hard_os_sandbox=False, timeout_seconds=timeout)
    artifact_dir = Path(artifact_dir)
    try:
        if model != ACTUAL_MODEL:
            raise ValueError("Unverified model identity for this CLI agent adapter")
        command = cli_transport.cli_command() + ["-p", "--model", CLI_ALIAS, "--effort", reasoning_effort,
            "--safe-mode", "--tools", ",".join(ALLOWED_TOOLS), "--allowedTools", ",".join(ALLOWED_TOOLS),
            "--permission-mode", "dontAsk", "--setting-sources", "", "--strict-mcp-config",
            "--mcp-config", '{"mcpServers":{}}', "--no-chrome", "--disable-slash-commands",
            "--no-session-persistence", "--output-format", "stream-json", "--verbose", "--system-prompt", system]
        result.update(cli_argv=command, system_sha256=cli_transport.sha(system.encode("utf-8")),
                      user_sha256=cli_transport.sha(user.encode("utf-8")), pose_sha256=cli_transport.sha(pose_bytes))
        with tempfile.TemporaryDirectory(prefix="animmark-agent-") as temporary:
            workspace = Path(temporary)
            result["workspace_path"] = str(workspace)
            (workspace / "pose.json").write_bytes(pose_bytes)
            try:
                execution = cli_transport.execute_process(command, user.encode("utf-8"),
                    cli_transport.process_env(max_tokens), workspace, timeout)
                result.update(parse_output(execution.pop("stdout"), execution.pop("stderr"), model, workspace))
                result.update(execution)
                if result["timed_out"]:
                    result.update(ok=False, status="timeout", error="CLI agent exceeded timeout; owned process tree terminated")
                elif result["exit_code"] != 0 or not result["process_cleanup_confirmed"]:
                    result.update(ok=False, status="cli_error", error="CLI exit/owned process-tree cleanup unsuccessful")
            finally:
                result["workspace_archive"] = archive_workspace(workspace, artifact_dir / "workspace")
    except Exception as exc:
        result.update(ok=False, status="transport_error", error=f"{type(exc).__name__}: {exc}")
    result["elapsed_seconds"] = round(time.monotonic() - started, 3)
    return result
