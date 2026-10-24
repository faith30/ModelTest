"""One independent TClaude invocation per model, with untouched artifact archives.

The inherited CLI has no hard OS sandbox. Tool access is constrained by the
common prompt and audited separately; no isolation guarantee is implied.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "tools/cli_runtime"
sys.path.insert(0, str(RUNTIME))
import cli_transport
import cli_agent_transport
import paired_runtime as runtime

MODELS = {
    "opus": ("claude-opus-5-5[1m]", "claude-opus-5-5"),
    "deepseek": ("claude-deepseek-v4-pro[1m]", "deepseek-v4-pro-202606"),
}
EDITABLE = {"src/build_assets.py", "src/controller.py", "assets/authored_assets.json", "config/animation_graph.json"}
REQUIRED = sorted(EDITABLE | {"IMPLEMENTATION.md"})
SYSTEM = (
    "你正在独立完成游戏动画开发任务。仅使用当前工作目录中的任务、接口和原始素材。"
    "可以使用Bash、Read、Write；不要访问网络、父目录、其他工作目录、原UE工程、裁判、参考答案、历史结果或其他模型交付。"
    "允许编辑src/build_assets.py、src/controller.py、assets/authored_assets.json、config/animation_graph.json，"
    "并在当前目录新增实现模块、加工结果、说明和自查文件。raw/、TASK_ZH.md、INTERFACE.md、LICENSE-Lyra.md、PACKAGE_MANIFEST.json不可改。"
    "不使用UE，不读取本题未提供的外部数据。辅助脚本放.work/，临时文件放.tmp/；所有任务相关读写留在当前目录。"
    "可以用pwd确认当前目录，或读取ASSET_TASK_WORKSPACE。先保存有实质内容的首版，再完善；最终交付必须落盘，不能只回复文字。"
    "最后以中文简述交付文件与局限。"
)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, data):
    runtime.save(path, data)


def load(path):
    return json.loads(path.read_text("utf-8-sig"))


def verify_package():
    archive = ROOT / "dist/LyraLocomotionBench-candidate.zip"
    freeze = load(ROOT / "evaluator/benchmark-freeze.json")
    if sha(archive) != freeze["candidate_zip_sha256"]:
        raise ValueError("Candidate ZIP changed after preparation freeze")
    if sha(ROOT / "evaluator/rubric.json") != freeze["rubric_sha256"]:
        raise ValueError("Rubric changed after preparation freeze")
    with zipfile.ZipFile(archive) as package:
        manifest = json.loads(package.read("PACKAGE_MANIFEST.json"))
        if set(package.namelist()) != set(manifest["files"]) | {"PACKAGE_MANIFEST.json"}:
            raise ValueError("Candidate package contains unexpected files")
        files = {}
        for name in package.namelist():
            runtime.relative_name(name)
            data = package.read(name)
            if name in manifest["files"] and hashlib.sha256(data).hexdigest() != manifest["files"][name]:
                raise ValueError("Package content hash mismatch: " + name)
            files[name] = data
    return archive, freeze, files


def probe(model, destination, effort):
    destination.mkdir(parents=True, exist_ok=False)
    alias, expected = MODELS[model]
    system = "This is a connectivity probe. Reply with exactly BENCH_ROUTE_OK. Do not use tools."
    command = cli_transport.cli_command() + ["-p", "--model", alias, "--effort", effort,
        "--safe-mode", "--tools", "", "--setting-sources", "", "--strict-mcp-config",
        "--mcp-config", '{"mcpServers":{}}', "--no-chrome", "--disable-slash-commands",
        "--no-session-persistence", "--output-format", "stream-json", "--verbose", "--system-prompt", system]
    workspace = Path(tempfile.mkdtemp(prefix="lyra-route-probe-"))
    execution = cli_transport.execute_process(command, b"BENCH_ROUTE_OK", cli_transport.process_env(1024), workspace, 120)
    stdout, stderr = execution.pop("stdout"), execution.pop("stderr")
    (destination / "stdout.jsonl").write_bytes(stdout)
    (destination / "stderr.txt").write_bytes(stderr)
    result = cli_transport.parse_output(stdout, stderr, expected)
    result.pop("raw_response", None)
    result.update(execution, requested_alias=alias, expected_model=expected, effort_requested=effort,
                  actual_effort_observed=None, probe_contains_task_data=False)
    result["probe_passed"] = bool(result["ok"] and result["text"].strip() == "BENCH_ROUTE_OK"
                                    and not result["timed_out"] and result["exit_code"] == 0
                                    and result["process_cleanup_confirmed"])
    save(destination / "result.json", result)
    print(json.dumps({"probe": model, "passed": result["probe_passed"], "actual_model": result["actual_model"],
                      "error": result.get("error")}, ensure_ascii=False), flush=True)
    return result


def run_one(model, batch, files, user, args, fingerprint, *, model_identity=None,
            command_override=None, env_override=None, extra_snapshot_files=(), canonical_workspace=False):
    alias, expected = model_identity if model_identity is not None else MODELS[model]
    run = batch / model
    run.mkdir(exist_ok=False)
    snapshot = run / "controller_snapshot"
    snapshot.mkdir()
    shutil.copyfile(__file__, snapshot / "run_models.py")
    for file in RUNTIME.glob("*.py"):
        shutil.copyfile(file, snapshot / file.name)
    for file in extra_snapshot_files:
        file = Path(file)
        shutil.copyfile(file, snapshot / file.name)
    workspace = Path(tempfile.mkdtemp(prefix="lyra-answer-"))
    if canonical_workspace:
        workspace = workspace.resolve()
    for name, data in files.items():
        path = workspace / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    base_env = env_override if env_override is not None else cli_transport.process_env(args.max_output_tokens)
    env = runtime.workspace_environment(base_env, workspace)
    command = list(command_override) if command_override is not None else runtime.command_for(cli_transport.cli_command(), model, args.effort, SYSTEM)
    (run / "system-prompt.txt").write_bytes(SYSTEM.encode("utf-8"))
    (run / "user-prompt.txt").write_bytes(user.encode("utf-8"))
    immutable = {name: hashlib.sha256(data).hexdigest() for name, data in files.items() if name not in EDITABLE}
    record = {"schema_version": 1, "model": model, "requested_alias": alias, "expected_model": expected,
              "started_utc": datetime.now(timezone.utc).isoformat(), "status": "running", "ok": False,
              "workspace_path": str(workspace), "timeout_seconds": args.timeout,
              "effort_requested": args.effort, "effort_applied": None,
              "max_output_tokens_requested": args.max_output_tokens, "max_output_tokens_applied": None,
              "controller_invocations": 1, "controller_retries": 0, "human_followups": 0,
              "hard_os_sandbox": False, "access_audit": "pending",
              "system_sha256": hashlib.sha256(SYSTEM.encode()).hexdigest(),
              "user_sha256": hashlib.sha256(user.encode()).hexdigest(),
              "immutable_inputs": immutable, "editable_scaffolds": sorted(EDITABLE), "required_artifacts": REQUIRED,
              "cli_argv": command, "fingerprint": {**fingerprint, "requested_cli_alias": alias,
                  "expected_actual_model": expected, "reasoning_effort_requested": args.effort,
                  "tools": ["Bash", "Read", "Write"], "output_token_limit_env": f"CLAUDE_CODE_MAX_OUTPUT_TOKENS={args.max_output_tokens}"},
              "controller_files": {path.name: sha(path) for path in snapshot.glob("*.py")}}
    save(run / "running.json", record)
    print(json.dumps({"model": model, "status": "running", "workspace": str(workspace)}), flush=True)
    try:
        execution = runtime.execute_logged(command, user.encode("utf-8"), env, workspace, run,
                                           args.timeout, REQUIRED, interval=5)
        parsed = cli_agent_transport.parse_output((run / "stdout.jsonl").read_bytes(),
                   (run / "stderr.txt").read_bytes(), expected, workspace)
        parsed.pop("raw_response", None)
        record.update(parsed)
        record.update(execution)
        if execution["timed_out"]:
            record.update(status="timeout", ok=False)
        elif execution["exit_code"] != 0 or not execution["process_cleanup_confirmed"]:
            record.update(status="cli_error", ok=False)
    except Exception as exc:
        record.update(status="controller_error", ok=False, error=f"{type(exc).__name__}: {exc}")
    finally:
        record["archive"] = runtime.archive_workspace(workspace, run / "candidate")
        current, skipped = runtime.file_inventory(run / "candidate")
        record["immutable_inputs_unchanged"] = all(current.get(name) == value for name, value in immutable.items())
        record["artifacts"] = {name: {"exists": name in current, "sha256": current.get(name),
            "changed_from_template": name in current and current[name] != hashlib.sha256(files.get(name, b"")).hexdigest()}
            for name in REQUIRED}
        record["all_required_artifacts_changed"] = all(x["changed_from_template"] for x in record["artifacts"].values())
        record["nonregular_files_skipped"] = skipped or record["archive"]["skipped_links_or_nonregular_files"]
        record["quality_score"] = None
        record["completed_utc"] = datetime.now(timezone.utc).isoformat()
        save(run / "result.json", record)
        (run / "FINAL_ANSWER.txt").write_text(record.get("text", ""), "utf-8")
    print(json.dumps({"model": model, "status": record["status"], "actual_model": record.get("actual_model"),
                      "seconds": record.get("elapsed_seconds"), "artifacts_changed": record["all_required_artifacts_changed"]}), flush=True)
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--models", nargs="+", choices=sorted(MODELS), default=["opus", "deepseek"])
    parser.add_argument("--effort", choices=["low", "medium", "high"], default="high")
    parser.add_argument("--timeout", type=int, default=2700)
    parser.add_argument("--max-output-tokens", type=int, default=8192)
    args = parser.parse_args()
    if not args.run_id or any(c not in "abcdefghijklmnopqrstuvwxyz0123456789-_" for c in args.run_id):
        raise ValueError("Use a safe unique lowercase run ID")
    if len(args.models) != len(set(args.models)) or args.timeout < 60 or args.max_output_tokens < 1024:
        raise ValueError("Invalid or duplicate run settings")
    archive, freeze, files = verify_package()
    batch = ROOT / "runs" / args.run_id
    batch.mkdir(parents=True, exist_ok=False)
    fingerprint = cli_transport.fingerprint()
    user = files["TASK_ZH.md"].decode("utf-8-sig") + (
        f"\n\n本次统一总时限为{args.timeout}秒。请先阅读INTERFACE.md，尽量在前180秒保存实质首版，最后预留120秒检查交付。"
        "题目中的四个骨架文件允许修改，raw/和题面接口不可改。可以增加实现模块、自查脚本和加工输出。"
        "只在当前目录处理题包；不使用UE或网络。要求的5个交付文件必须落盘，最终再用中文说明。"
        "\n本机Python路径：" + sys.executable.replace("\\", "/")
    )
    plan = {"schema_version": 1, "run_id": args.run_id, "models": args.models, "effort_requested": args.effort,
            "timeout_seconds": args.timeout, "max_output_tokens_per_turn_requested": args.max_output_tokens,
            "candidate_zip": str(archive), "candidate_zip_sha256": sha(archive), "rubric_sha256": freeze["rubric_sha256"],
            "system_sha256": hashlib.sha256(SYSTEM.encode()).hexdigest(), "user_sha256": hashlib.sha256(user.encode()).hexdigest(),
            "hard_os_sandbox": False, "scope_audit_required": True, "controller_retries": 0,
            "started_utc": datetime.now(timezone.utc).isoformat()}
    save(batch / "plan.json", plan)
    probes = {}
    with ThreadPoolExecutor(max_workers=len(args.models)) as pool:
        futures = {pool.submit(probe, model, batch / "probes" / model, args.effort): model for model in args.models}
        for future in as_completed(futures):
            model = futures[future]
            try:
                probes[model] = future.result()
            except Exception as exc:
                probes[model] = {"probe_passed": False, "status": "infrastructure_blocked", "error": str(exc)}
    save(batch / "probes.json", probes)
    records = {}
    with ThreadPoolExecutor(max_workers=len(args.models)) as pool:
        futures = {pool.submit(run_one, model, batch, files, user, args, fingerprint): model
                   for model in args.models if probes[model]["probe_passed"]}
        for model in args.models:
            if not probes[model]["probe_passed"]:
                records[model] = {"status": "infrastructure_blocked", "quality_score": None, "probe": probes[model]}
        for future in as_completed(futures):
            model = futures[future]
            try:
                records[model] = future.result()
            except Exception as exc:
                records[model] = {"status": "controller_error", "quality_score": None, "error": str(exc)}
    result = {"run_id": args.run_id, "records": records, "candidate_zip_unchanged": sha(archive) == plan["candidate_zip_sha256"],
              "rubric_unchanged": sha(ROOT / "evaluator/rubric.json") == plan["rubric_sha256"]}
    save(batch / "result.json", result)
    return 0 if all(row.get("ok") for row in records.values()) else 2


if __name__ == "__main__":
    raise SystemExit(main())
