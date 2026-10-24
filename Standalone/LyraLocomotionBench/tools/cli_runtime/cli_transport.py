"""Tclaude subprocess transport. No direct API path and no controller retries."""
from __future__ import annotations
import base64
import datetime as dt
import hashlib
import json
import mimetypes
import os
from pathlib import Path
import shutil
import signal
import subprocess
import tempfile
import time

ACTUAL_MODEL = "deepseek-v4-pro-202606"
CLI_ALIAS = "claude-deepseek-v4-pro[1m]"
ROOT = Path(__file__).resolve().parents[1]


def sha(data):
    return hashlib.sha256(data).hexdigest()


def cli_command():
    node = shutil.which("node")
    wrapper = Path(os.environ.get("APPDATA", Path.home() / "AppData/Roaming")) / "npm/node_modules/@tencent/tclaude/bin/tclaude.js"
    if not node or not wrapper.is_file():
        raise FileNotFoundError("Existing node/tclaude wrapper installation was not found")
    return [node, str(wrapper)]


def process_env(max_tokens):
    env = {key: value for key, value in os.environ.items()
           if not key.upper().startswith(("CODEX_", "OPENAI_", "ANTHROPIC_", "CLAUDE_CODE_"))}
    # Verified in the installed Claude binary's BQt/dHe configuration path.
    # This establishes the requested CLI setting, not observed provider enforcement.
    env["CLAUDE_CODE_MAX_OUTPUT_TOKENS"] = str(max_tokens)
    return env


def fingerprint():
    command = cli_command()
    version = subprocess.run(command + ["--version"], capture_output=True, timeout=30,
                             creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
    if version.returncode:
        raise RuntimeError("Cannot identify the installed CLI version")
    files = [Path(command[0]), Path(command[1])]
    native = Path(command[1]).parents[1] / "node_modules/@tencent/tclaude-win32-x64/tclaude.exe"
    if native.exists():
        files.append(native)
    return dict(protocol="tclaude_cli", requested_cli_alias=CLI_ALIAS, expected_actual_model=ACTUAL_MODEL,
        version=version.stdout.decode("utf-8", errors="replace").strip(),
        executable_files=[{"path": str(p), "sha256": sha(p.read_bytes())} for p in files],
        safe_mode=True, tools=[], mcp_servers=[], setting_sources=[], session_persistence=False,
        system_prompt_mode="replace", reasoning_effort_requested="medium",
        output_token_limit_env="CLAUDE_CODE_MAX_OUTPUT_TOKENS=8192",
        output_token_limit_effective_at_provider="not_observable_from_cli_result",
        controller_retries=0, upstream_retry_count="not_fully_observable",
        retry_policy="One CLI invocation per clip, no controller retries or fallback model; CLI/daemon internals may retry and are not claimed zero.",
        image_transport="Anthropic base64 image blocks through stream-json; model vision acceptance is a separate gate")


def build_input(user, images):
    if not images:
        return user.encode("utf-8"), [], "text"
    content = [{"type": "text", "text": user}]
    hashes = []
    for item in images:
        path = Path(item)
        data = path.read_bytes()
        mime = mimetypes.guess_type(path.name)[0]
        if mime not in {"image/png", "image/jpeg", "image/webp", "image/gif"}:
            raise ValueError("Unsupported image file format")
        content.append({"type": "image", "source": {"type": "base64", "media_type": mime,
                        "data": base64.b64encode(data).decode("ascii")}})
        hashes.append(sha(data))
    message = {"type": "user", "message": {"role": "user", "content": content},
               "parent_tool_use_id": None, "session_id": ""}
    return (json.dumps(message, ensure_ascii=False) + "\n").encode("utf-8"), hashes, "stream-json"


def execute_process(command, stdin, env, cwd, timeout):
    """Own the entire subprocess tree before it executes application code."""
    started = time.monotonic()
    if os.name == "nt":
        try:
            from .cli_windows_job import WindowsJob
        except ImportError:
            from cli_windows_job import WindowsJob
        with WindowsJob() as job:
            process = job.popen(command, cwd=cwd, env=env, stdin=subprocess.PIPE,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            timed_out = False
            try:
                stdout, stderr = process.communicate(stdin, timeout=timeout)
            except subprocess.TimeoutExpired:
                timed_out = True
                job.terminate()
                stdout, stderr = process.communicate(timeout=15)
            # The launcher may exit before descendants. Terminate only this job.
            active_at_exit = job.active_processes
            job.terminate()
            cleanup = job.active_processes == 0
            return dict(stdout=stdout, stderr=stderr, exit_code=process.returncode, timed_out=timed_out,
                        process_cleanup_confirmed=cleanup, active_descendants_at_launcher_exit=active_at_exit,
                        elapsed_seconds=time.monotonic() - started)
    process = subprocess.Popen(command, cwd=cwd, env=env, stdin=subprocess.PIPE,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
    timed_out = False
    try:
        stdout, stderr = process.communicate(stdin, timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
        os.killpg(process.pid, signal.SIGKILL)
        stdout, stderr = process.communicate(timeout=15)
    finally:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    return dict(stdout=stdout, stderr=stderr, exit_code=process.returncode, timed_out=timed_out,
                process_cleanup_confirmed=process.poll() is not None,
                elapsed_seconds=time.monotonic() - started)


def parse_output(stdout, stderr, expected=ACTUAL_MODEL):
    events, other_lines = [], []
    for line in stdout.decode("utf-8", errors="replace").splitlines():
        try:
            event = json.loads(line)
            if isinstance(event, dict):
                events.append(event)
            else:
                other_lines.append(line)
        except ValueError:
            if line.strip():
                other_lines.append(line)
    init = [e for e in events if e.get("type") == "system" and e.get("subtype") == "init"]
    assistants = [e for e in events if e.get("type") == "assistant"]
    models = sorted({e.get("message", {}).get("model") for e in assistants if e.get("message", {}).get("model")})
    results = [e for e in events if e.get("type") == "result"]
    final = results[-1] if results else {}
    tool_uses = [block for event in assistants for block in event.get("message", {}).get("content", [])
                 if block.get("type") == "tool_use"]
    tools = sorted({tool for event in init for tool in event.get("tools", [])})
    mcp = [server for event in init for server in event.get("mcp_servers", [])]
    text = final.get("result") or "\n".join(block.get("text", "") for event in assistants
        for block in event.get("message", {}).get("content", []) if block.get("type") == "text")
    isolated = bool(init) and not tools and not mcp and not tool_uses
    completed = len(results) == 1 and final.get("subtype") == "success" and final.get("is_error") is False
    identity_ok = models == [expected]
    one_turn = final.get("num_turns") == 1
    raw_usage = final.get("usage") or {}
    usage = dict(raw_usage)
    usage["input_tokens_uncached"] = raw_usage.get("input_tokens", 0)
    usage["input_tokens"] = sum(raw_usage.get(k, 0) for k in ("input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens"))
    usage["total_tokens"] = usage["input_tokens"] + usage.get("output_tokens", 0)
    errors = []
    if not identity_ok:
        errors.append(f"Actual assistant model mismatch: {models}")
    if not isolated:
        errors.append("Tool/MCP isolation was not verified")
    if not completed:
        errors.append("Missing or unsuccessful final CLI result")
    if completed and not one_turn:
        errors.append("Expected exactly one model turn")
    return dict(ok=completed and identity_ok and isolated and one_turn and bool(text),
        actual_model=models[0] if len(models) == 1 else None, model_matches=identity_ok,
        status="completed" if completed else "cli_error", text=text, usage=usage,
        error="; ".join(errors) if errors else None, http_status=None,
        raw_response={"events": events, "stdout_jsonl": stdout.decode("utf-8", errors="replace"),
                      "stderr": stderr.decode("utf-8", errors="replace"), "non_json_stdout_lines": other_lines},
        cli_audit={"assistant_models": models, "init_models": [e.get("model") for e in init],
            "tools": tools, "mcp_servers": mcp, "tool_call_count": len(tool_uses),
            "num_turns": final.get("num_turns"), "isolation_verified": isolated,
            "reported_model_usage": final.get("modelUsage"), "raw_usage": raw_usage,
            "controller_retries": 0, "upstream_retry_count": None,
            "upstream_retry_observability": "CLI/daemon internal retries cannot be completely inferred from event stream"})


def call_model(model, system, user, images=None, max_tokens=8192, *, reasoning_effort="medium",
               timeout=240, image_detail="original"):
    started = time.monotonic()
    result = dict(requested_model=model, route="tclaude_cli", requested_cli_alias=CLI_ALIAS,
        started_utc=dt.datetime.now(dt.timezone.utc).isoformat(), ok=False, text="", actual_model=None,
        model_matches=False, http_status=None, status="not_sent", usage=None, error=None,
        automatic_retries=0, reasoning_effort=reasoning_effort, reasoning_effort_applied=None,
        max_output_tokens_requested=max_tokens, max_output_tokens_applied=None,
        max_output_tokens_configuration=f"CLAUDE_CODE_MAX_OUTPUT_TOKENS={max_tokens}",
        image_detail_requested=image_detail, image_detail_applied=None, image_count=len(images or []))
    try:
        if model != ACTUAL_MODEL:
            raise ValueError(f"This CLI adapter only routes the verified model {ACTUAL_MODEL}")
        stdin, image_hashes, input_format = build_input(user, images or [])
        command = cli_command() + ["-p", "--model", CLI_ALIAS, "--effort", reasoning_effort,
            "--safe-mode", "--tools", "", "--setting-sources", "", "--strict-mcp-config",
            "--mcp-config", '{"mcpServers":{}}', "--no-chrome", "--disable-slash-commands",
            "--no-session-persistence", "--output-format", "stream-json", "--verbose",
            "--system-prompt", system]
        if input_format == "stream-json":
            command += ["--input-format", "stream-json", "--replay-user-messages"]
        result.update(stdin_sha256=sha(stdin), system_sha256=sha(system.encode("utf-8")),
                      user_sha256=sha(user.encode("utf-8")), image_sha256=image_hashes,
                      cli_argv=command, input_format=input_format)
        with tempfile.TemporaryDirectory(prefix="animmark-cli-") as cwd:
            execution = execute_process(command, stdin, process_env(max_tokens), cwd, timeout)
        result.update(parse_output(execution.pop("stdout"), execution.pop("stderr"), model))
        result.update(execution)
        if result["timed_out"]:
            result.update(ok=False, status="timeout", error="CLI request exceeded the time budget; owned process tree terminated")
        elif result["exit_code"] != 0 or not result["process_cleanup_confirmed"]:
            result.update(ok=False, status="cli_error", error="CLI exit/owned process-tree cleanup was unsuccessful")
    except Exception as exc:
        result.update(ok=False, status="transport_error", error=f"{type(exc).__name__}: {exc}")
    result["elapsed_seconds"] = round(time.monotonic() - started, 3)
    return result
