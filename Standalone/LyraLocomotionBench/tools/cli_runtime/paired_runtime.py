"""Run one frozen asset package through independent, comparable local CLI agents.

This controller owns process trees, not filesystem/network access. Workspace
instructions and redirected temporary directories reduce accidental scope errors;
they are not an OS sandbox. Review tools and saved scripts independently.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import datetime as dt
import hashlib
import importlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import stat
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
TRANSPORT = Path('D:/AnimationLoopBench/runs/loop-repair-opus55-cli-20261023-01/controller_snapshot')
TRANSPORT_FILES = ('cli_transport.py', 'cli_agent_transport.py', 'cli_windows_job.py')
MODELS = {
    'deepseek': ('deepseek-v4-pro-202606', 'claude-deepseek-v4-pro[1m]', 'DeepSeek'),
    'opus': ('claude-opus-5-5', 'claude-opus-5-5[1m]', 'Claude Opus 5.5'),
}
HISTORY = {
    'deepseek': ROOT/'runs/locomotion-context-deepseek-20261023-01/result.json',
    'opus': Path('D:/AnimationLoopBench/evidence/opus55-route-probe-20261023/result.json'),
}
SYSTEM = ('你正在独立制作游戏资产。使用当前任务目录中提供的需求和输入，自主完成任务并保存交付文件。'
    '可以使用Bash、Read、Write。所有任务数据、辅助脚本、缓存和交付文件只读写当前任务工作目录内；'
    '不要访问网络、父目录、源工程、评分器、参考答案、历史结果或其他模型的工作目录。'
    '当前目录可用pwd确认，也可从环境变量ASSET_TASK_WORKSPACE读取；辅助脚本放在.work/，临时文件放在.tmp/。'
    'TEMP、TMP、TMPDIR已指向当前任务内的.tmp，不要另建工作目录外的临时文件夹。'
    '不要修改提供的输入文件；按格式文件保存原始作品。先保存有实际内容的首版，再逐步完善并保留最终文件。'
    '最终用中文简要说明交付和局限。')


def read(path):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError('Duplicate JSON key: ' + key)
            result[key] = value
        return result
    return json.loads(Path(path).read_text(encoding='utf-8-sig'), object_pairs_hook=pairs,
                      parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))


def digest(data):
    return hashlib.sha256(data).hexdigest()


def sha(path):
    return digest(Path(path).read_bytes())


def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.writing')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
    temporary.replace(path)


def relative_name(name):
    if not isinstance(name, str) or not name or '\\' in name or ':' in name:
        raise ValueError('Package and output paths must use safe relative POSIX names')
    path = PurePosixPath(name)
    if path.is_absolute() or path.as_posix() != name or any(part in ('', '.', '..') for part in path.parts):
        raise ValueError('Unsafe relative file path: ' + name)
    if path.parts[0].casefold() in ('.tmp', '.work'):
        raise ValueError('Reserved workspace directory: ' + name)
    return name


def regular_within(path, root):
    """Do not read archive links, junctions, hardlinks or outside targets."""
    path, root = Path(path).absolute(), Path(root).absolute()
    try:
        relative = path.relative_to(root)
        current = root.resolve()
        for part in relative.parts:
            current = current / part
            if current.is_symlink() or (hasattr(current, 'is_junction') and current.is_junction()):
                return False
        info = path.stat()
        return path.resolve().is_relative_to(root.resolve()) and stat.S_ISREG(info.st_mode) and info.st_nlink == 1
    except (ValueError, OSError):
        return False


def file_inventory(root):
    root = Path(root).resolve()
    files, skipped = {}, []
    for current, directories, names in os.walk(root, followlinks=False):
        kept = []
        for name in directories:
            path = Path(current)/name
            if path.is_symlink() or (hasattr(path, 'is_junction') and path.is_junction()):
                skipped.append(path.relative_to(root).as_posix())
            else:
                kept.append(name)
        directories[:] = kept
        for name in names:
            path = Path(current)/name
            relative = path.relative_to(root).as_posix()
            if regular_within(path, root):
                files[relative] = sha(path)
            else:
                skipped.append(relative)
    return files, skipped


def validate_freeze(path):
    path = Path(path).resolve()
    freeze = read(path)
    if type(freeze.get('schema_version')) is not int or freeze['schema_version'] != 1:
        raise ValueError('Freeze schema_version must be integer 1')
    if not isinstance(freeze.get('task_id'), str) or not freeze['task_id']:
        raise ValueError('Freeze needs task_id')
    for key in ('reference_answers_included', 'scorer_code_included'):
        if freeze.get(key) is not False:
            raise ValueError('Candidate freeze must explicitly exclude ' + key)
    package = Path(freeze['package_path'])
    if not package.is_absolute() or not package.is_dir() or package.is_symlink() or package.is_junction():
        raise ValueError('package_path must identify a regular absolute directory')
    package = package.resolve()
    files = freeze.get('files')
    if not isinstance(files, dict) or not files:
        raise ValueError('Freeze needs a nonempty file-to-SHA256 mapping')
    folded = set()
    for name, value in files.items():
        relative_name(name)
        if name.casefold() in folded:
            raise ValueError('Case-insensitive package collision')
        folded.add(name.casefold())
        if not isinstance(value, str) or len(value) != 64 or any(c not in '0123456789abcdef' for c in value):
            raise ValueError('Invalid SHA256 for ' + name)
    actual, skipped = file_inventory(package)
    if skipped or actual != files:
        raise ValueError('Frozen package changed, has undeclared files, or contains links')
    prompt_file = relative_name(freeze.get('task_prompt_file', 'TASK_ZH.txt'))
    if prompt_file not in files:
        raise ValueError('Task prompt must be included in frozen files')
    outputs = freeze.get('output_files')
    if not isinstance(outputs, list) or not outputs:
        raise ValueError('Freeze needs output_files')
    output_names = [relative_name(name) for name in outputs]
    if len(set(name.casefold() for name in output_names)) != len(output_names):
        raise ValueError('Duplicate output path')
    if any(left.casefold().startswith(right.casefold() + '/') for left in output_names for right in output_names if left != right):
        raise ValueError('Output file/directory collision')
    if any(name.casefold() in folded for name in output_names):
        raise ValueError('An input file cannot automatically become a delivered answer')
    for output in output_names:
        if any(name.casefold().startswith(output.casefold() + '/') or output.casefold().startswith(name.casefold() + '/') for name in files):
            raise ValueError('Input/output path collision')
    bindings = freeze.get('evaluation_files', {})
    if not isinstance(bindings, dict):
        raise ValueError('evaluation_files must be an evaluator-only path/hash object')
    for name, expected in bindings.items():
        private = Path(name)
        if not private.is_absolute() or private.resolve().is_relative_to(package) or sha(private) != expected:
            raise ValueError('Evaluation binding is invalid, changed or inside candidate package')
    return freeze, package


def prompts(freeze, package, timeout):
    user = (package/freeze.get('task_prompt_file', 'TASK_ZH.txt')).read_text(encoding='utf-8-sig')
    first = min(180, max(15, timeout//4))
    reserve = min(120, max(10, timeout//10))
    user += ('\n\n请阅读本目录的格式说明和清单，并自行选择如何完成任务。'
        f'本次任务总时限为{timeout}秒；尽量在前{first}秒保存首版实际作品，最后预留{reserve}秒检查交付。'
        '\n可用Python：' + sys.executable.replace('\\', '/') + '。'
        '\n要求交付路径：' + '、'.join(freeze['output_files']) + '。')
    return SYSTEM, user


def command_for(base, model, effort, system):
    return list(base) + ['-p', '--model', MODELS[model][1], '--effort', effort, '--safe-mode',
        '--tools', 'Bash,Read,Write', '--allowedTools', 'Bash,Read,Write', '--permission-mode', 'dontAsk',
        '--setting-sources', '', '--strict-mcp-config', '--mcp-config', '{"mcpServers":{}}',
        '--no-chrome', '--disable-slash-commands', '--no-session-persistence',
        '--output-format', 'stream-json', '--verbose', '--system-prompt', system]


def workspace_environment(base, workspace):
    env = dict(base)
    temporary = Path(workspace)/'.tmp'
    temporary.mkdir()
    (Path(workspace)/'.work').mkdir()
    for name in ('TEMP', 'TMP', 'TMPDIR'):
        env[name] = str(temporary)
    env['ASSET_TASK_WORKSPACE'] = str(Path(workspace))
    env['PYTHONUTF8'] = '1'
    env['PYTHONDONTWRITEBYTECODE'] = '1'
    return env


def archive_workspace(workspace, destination):
    destination.mkdir(parents=True, exist_ok=False)
    files, skipped = file_inventory(workspace)
    saved = []
    for name, expected in sorted(files.items()):
        source = workspace/name
        if not regular_within(source, workspace):
            skipped.append(name)
            continue
        data = source.read_bytes()
        if digest(data) != expected:
            raise ValueError('Workspace changed after process cleanup: ' + name)
        target = destination/name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        saved.append({'path': name, 'sha256': expected, 'size_bytes': len(data)})
    return {'files': saved, 'skipped_links_or_nonregular_files': sorted(set(skipped))}


def observe_outputs(workspace, run, outputs, elapsed, previous, observations):
    for name in outputs:
        path = workspace/name
        if not regular_within(path, workspace):
            continue
        try:
            before = path.stat()
            data = path.read_bytes()
            after = path.stat()
        except OSError:
            continue
        signature = digest(data)
        if previous.get(name) == signature:
            continue
        previous[name] = signature
        snapshot = f'output_observations/{len(observations):04d}/{name}'
        target = run/snapshot
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        observations.append({'path': name, 'elapsed_seconds': round(elapsed, 3),
            'sha256': signature, 'size_bytes': len(data), 'snapshot': snapshot,
            'stable_stat_during_read': (before.st_size, before.st_mtime_ns) == (after.st_size, after.st_mtime_ns),
            'scoring_source': False})


def execute_logged(command, stdin, env, workspace, run, timeout, outputs, *, interval=1.0):
    """One process tree and deadline; input pipe cannot block the deadline thread."""
    if os.name != 'nt':
        raise RuntimeError('Local CLI runner requires Windows; input/scoring artifacts remain portable')
    from cli_windows_job import WindowsJob
    started = time.monotonic()
    observations, previous = [], {}
    next_observation = started
    # A file stdin avoids an unbounded blocking write to a child that never reads.
    with (run/'stdin.bin').open('wb') as handle:
        handle.write(stdin)
    with (run/'stdin.bin').open('rb') as input_handle, \
            (run/'stdout.jsonl').open('wb', buffering=0) as stdout, \
            (run/'stderr.txt').open('wb', buffering=0) as stderr, WindowsJob() as job:
        process = job.popen(command, cwd=workspace, env=env, stdin=input_handle, stdout=stdout, stderr=stderr)
        timed_out = False
        try:
            while process.poll() is None:
                now = time.monotonic()
                if now-started >= timeout:
                    timed_out = True
                    break
                if now >= next_observation:
                    observe_outputs(workspace, run, outputs, now-started, previous, observations)
                    save(run/'progress.json', {'elapsed_seconds':round(now-started, 3),
                        'remaining_seconds':max(0, round(timeout-(now-started), 3)),
                        'stdout_bytes':(run/'stdout.jsonl').stat().st_size,
                        'delivery_observations':observations})
                    next_observation = now + interval
                time.sleep(min(0.1, max(0, timeout-(time.monotonic()-started))))
        finally:
            active_at_exit = job.active_processes
            job.terminate()
            process.wait(timeout=15)
            cleanup = job.active_processes == 0
    observe_outputs(workspace, run, outputs, time.monotonic()-started, previous, observations)
    result = {'exit_code':process.returncode, 'timed_out':timed_out, 'process_cleanup_confirmed':cleanup,
        'active_processes_at_launcher_exit':active_at_exit,
        'elapsed_seconds':time.monotonic()-started, 'delivery_observations':observations}
    save(run/'execution.json', result)
    return result


def historical_route(model):
    path = HISTORY[model]
    if not path.is_file():
        return {'fresh_connectivity_verified':False, 'historical_evidence_available':False}
    record = read(path)
    return {'fresh_connectivity_verified':False, 'historical_evidence_available':True,
        'evidence_path':str(path), 'evidence_sha256':sha(path),
        'historical_actual_model':record.get('actual_model'),
        'historical_requested_alias':record.get('requested_cli_alias'),
        'historical_model_matches':record.get('model_matches'),
        'note':'Historical routing evidence only; this task has made no extra model probe.'}


def run_one(pair_id, model, freeze_path, freeze, package, effort, timeout, base, fingerprint, transport, *,
            command_override=None, env_override=None):
    expected, alias, label = MODELS[model]
    run_id = pair_id + '-' + model
    run = ROOT/'runs'/run_id
    run.mkdir(parents=True, exist_ok=False)
    snapshot = run/'controller_snapshot'
    snapshot.mkdir()
    shutil.copyfile(__file__, snapshot/Path(__file__).name)
    for name in TRANSPORT_FILES:
        shutil.copyfile(TRANSPORT/name, snapshot/name)
    shutil.copyfile(freeze_path, run/'candidate-freeze.json')
    system, user = prompts(freeze, package, timeout)
    (run/'system-prompt.txt').write_bytes(system.encode('utf-8'))
    (run/'user-prompt.txt').write_bytes(user.encode('utf-8'))
    (run/'prompt.txt').write_bytes((system+'\n\n'+user).encode('utf-8'))
    command = command_for(base, model, effort, system)
    record = {'schema_version':1, 'run_id':run_id, 'pair_id':pair_id, 'task_id':freeze['task_id'],
        'model_label':label, 'requested_model':expected, 'requested_cli_alias':alias,
        'status':'prepared', 'ok':False, 'reasoning_effort_requested':effort,
        'reasoning_effort_applied':None, 'max_output_tokens_requested':8192, 'max_output_tokens_applied':None,
        'provider_effort_observability':'not_observable_from_cli_result', 'timeout_seconds':timeout,
        'automatic_retries':0, 'controller_invocations':1, 'hard_os_sandbox':False,
        'reference_answers_provided':False, 'scorer_code_provided':False,
        'input_files':freeze['files'], 'output_files':freeze['output_files'],
        'candidate_freeze_sha256':sha(freeze_path), 'evaluation_files':freeze.get('evaluation_files', {}),
        'system_sha256':digest(system.encode('utf-8')), 'user_sha256':digest(user.encode('utf-8')),
        'fingerprint':{**fingerprint, 'requested_cli_alias':alias, 'expected_actual_model':expected,
            'reasoning_effort_requested':effort, 'tools':['Bash','Read','Write'], 'image_transport':'package files',
            'retry_policy':'One fresh CLI per task/model; no controller retry or model fallback'},
        'historical_route':historical_route(model), 'cli_argv':command,
        'controller_files':{p.name:sha(p) for p in snapshot.glob('*.py')},
        'started_utc':dt.datetime.now(dt.timezone.utc).isoformat(),
        'content_policy':{'controller_normalization':'none; original files retained byte-for-byte',
            'metadata_notes':'non-scoring metadata under the new task protocol',
            'external_helper_scope':'separate operation-scope measure; not automatically a content-score failure',
            'answer_leakage':'requires independent tool/script audit; never inferred solely from a temp helper'},
        'independent_access_audit':'pending'}
    save(run/'preflight.json', record)
    with tempfile.TemporaryDirectory(prefix='asset-task-'+model+'-') as temporary:
        workspace = Path(temporary).resolve()
        for name, expected_hash in freeze['files'].items():
            target = workspace/name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(package/name, target)
            if sha(target) != expected_hash:
                raise ValueError('Copied input hash differs: ' + name)
        env = workspace_environment(env_override if env_override is not None else transport[0].process_env(8192), workspace)
        record['initial_workspace_archive'] = archive_workspace(workspace, run/'initial_workspace')
        record.update(workspace_path=str(workspace), status='running',
            workspace_environment={key:env[key] for key in ('TEMP','TMP','TMPDIR','ASSET_TASK_WORKSPACE','PYTHONUTF8','PYTHONDONTWRITEBYTECODE')})
        save(run/'running.json', record)
        print(json.dumps({'run_id':run_id, 'status':'running', 'expected_model':expected}), flush=True)
        try:
            execution = execute_logged(command_override or command, user.encode('utf-8'), env, workspace, run, timeout, freeze['output_files'])
            parsed = transport[1].parse_output((run/'stdout.jsonl').read_bytes(), (run/'stderr.txt').read_bytes(), expected, workspace)
            parsed.pop('raw_response', None)
            record.update(parsed)
            # Preserve transport/scope facts; artifact quality is scored separately.
            record.update(execution)
            if execution['timed_out']:
                record.update(ok=False, status='timeout', error='Task deadline exceeded; owned process tree terminated')
            elif execution['exit_code'] != 0 or not execution['process_cleanup_confirmed']:
                record.update(ok=False, status='cli_error', error='CLI exit or process-tree cleanup failed')
        except Exception as exc:
            record.update(ok=False, status='transport_error', error=f'{type(exc).__name__}: {exc}')
        finally:
            record['workspace_archive'] = archive_workspace(workspace, run/'workspace')
            final_inputs = {name:sha(run/'workspace'/name) if (run/'workspace'/name).is_file() else None for name in freeze['files']}
            record['input_files_unchanged'] = final_inputs == freeze['files']
            record['changed_or_missing_inputs'] = [name for name in freeze['files'] if final_inputs[name] != freeze['files'][name]]
            record['artifacts'] = {name:{'exists':(run/'workspace'/name).is_file(),
                'sha256':sha(run/'workspace'/name) if (run/'workspace'/name).is_file() else None} for name in freeze['output_files']}
            record['candidate_exists'] = all(item['exists'] for item in record['artifacts'].values())
            record['candidate_sha256'] = record['artifacts'].get('result.json', {}).get('sha256')
            record['finished_utc'] = dt.datetime.now(dt.timezone.utc).isoformat()
            record['record_files'] = {name:sha(run/name) for name in ('stdout.jsonl','stderr.txt','stdin.bin') if (run/name).is_file()}
            save(run/'result.json', record)
            (run/'final-answer.txt').write_text(record.get('text',''), encoding='utf-8')
    return record


def load_transport():
    sys.path.insert(0, str(TRANSPORT))
    return importlib.import_module('cli_transport'), importlib.import_module('cli_agent_transport')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--freeze', type=Path, required=True)
    parser.add_argument('--run-id', required=True)
    parser.add_argument('--model', choices=('deepseek','opus','both'), default='both')
    parser.add_argument('--effort', choices=('medium','high'), default='medium')
    parser.add_argument('--timeout', type=int, default=1200)
    parser.add_argument('--prepare-only', action='store_true', help='Validate and print the plan; no task/model invocation or run directory')
    args = parser.parse_args()
    if not args.run_id or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-' for c in args.run_id):
        raise ValueError('Unsafe run ID')
    if not 60 <= args.timeout <= 3600:
        raise ValueError('Timeout must be between 60 and 3600 seconds')
    freeze_path = args.freeze.resolve()
    freeze, package = validate_freeze(freeze_path)
    transport = load_transport()
    fingerprint = transport[0].fingerprint()  # --version only, never a model request.
    base = transport[0].cli_command()
    models = list(MODELS) if args.model == 'both' else [args.model]
    system, user = prompts(freeze, package, args.timeout)
    plan = {'schema_version':1, 'pair_id':args.run_id, 'task_id':freeze['task_id'], 'models':models,
        'concurrency':'one process tree per model; both models run concurrently',
        'effort_requested':args.effort, 'max_output_tokens_requested':8192, 'timeout_seconds':args.timeout,
        'fresh_route_probe':False, 'hard_os_sandbox':False, 'candidate_freeze_sha256':sha(freeze_path),
        'system_sha256':digest(system.encode('utf-8')), 'user_sha256':digest(user.encode('utf-8')),
        'input_files':freeze['files'], 'evaluation_files':freeze.get('evaluation_files', {}),
        'routes':{model:historical_route(model) for model in models},
        'run_paths':{model:str(ROOT/'runs'/(args.run_id+'-'+model)) for model in models},
        'cli_version':fingerprint['version'], 'controller_sha256':sha(Path(__file__))}
    if args.prepare_only:
        print(json.dumps(plan, ensure_ascii=False, indent=2))
        return 0
    pair = ROOT/'runs'/args.run_id
    if pair.exists() or any(Path(path).exists() for path in plan['run_paths'].values()):
        raise ValueError('Pair/run ID already exists; never overwrite or resume a prior candidate run')
    pair.mkdir(parents=True)
    save(pair/'plan.json', plan)
    with ThreadPoolExecutor(max_workers=len(models)) as pool:
        futures = {model:pool.submit(run_one, args.run_id, model, freeze_path, freeze, package,
            args.effort, args.timeout, base, fingerprint, transport) for model in models}
        records = {}
        for model, future in futures.items():
            try:
                record = future.result()
                records[model] = {key:record.get(key) for key in ('run_id','status','ok','actual_model','elapsed_seconds',
                    'candidate_exists','candidate_sha256','input_files_unchanged','artifacts')}
            except Exception as exc:
                records[model] = {'status':'controller_error', 'ok':False, 'error':f'{type(exc).__name__}: {exc}'}
    final = {'pair_id':args.run_id, 'records':records, 'candidate_freeze_sha256':sha(freeze_path),
        'freeze_file_unchanged':sha(freeze_path) == plan['candidate_freeze_sha256'],
        'candidate_package_unchanged':file_inventory(package) == (freeze['files'], []),
        'evaluation_files_unchanged':all(sha(Path(name)) == value for name, value in freeze.get('evaluation_files', {}).items())}
    save(pair/'result.json', final)
    print(json.dumps(final, ensure_ascii=False), flush=True)
    bound = all(final[key] for key in ('freeze_file_unchanged','candidate_package_unchanged','evaluation_files_unchanged'))
    return 0 if bound and all(value.get('ok') and value.get('candidate_exists') for value in records.values()) else 2


if __name__ == '__main__':
    raise SystemExit(main())
