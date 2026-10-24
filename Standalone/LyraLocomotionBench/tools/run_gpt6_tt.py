"""Append a native Claude -> TT Switch GPT-6 run without changing old candidates."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import uuid

import run_models as shared
from audit_tt_route import read_session

ROOT = shared.ROOT
OLD = ROOT / 'runs/locomotion-20261023-high-r1'
RUN = ROOT / 'runs/locomotion-20261023-gpt6-high-r1'
CLI = Path.home() / '.vscode/extensions/anthropic.claude-code-2.1.289-win32-x64/resources/native-binary/claude.exe'
MODEL = 'gpt-6-astra'
SETTINGS = Path.home() / '.tclaude/settings.json'
PROVIDER_ID = '224f9110-b327-4200-ab5b-91924603d544'

def utc():
    return datetime.now(timezone.utc).isoformat()

def routed_environment(max_tokens):
    settings = shared.load(SETTINGS)
    source = settings['env']
    if source.get('ANTHROPIC_BASE_URL') != 'http://127.0.0.1:15721':
        raise ValueError('TT Switch base URL changed; re-audit route before running')
    if source.get('ANTHROPIC_DEFAULT_OPUS_MODEL') != MODEL:
        raise ValueError('Current TT Switch model mapping differs from verified GPT-6 Astra')
    env = shared.cli_transport.process_env(max_tokens)
    for name in ('ANTHROPIC_BASE_URL', 'ANTHROPIC_AUTH_TOKEN', 'ANTHROPIC_API_KEY'):
        if name in source:
            env[name] = str(source[name])
    # Credentials stay in this subprocess environment, never in saved records.
    return env

def command(system, session, with_tools):
    cmd = [str(CLI), '-p', '--model', MODEL, '--effort', 'high', '--safe-mode',
           '--tools', 'Bash,Read,Write' if with_tools else '',
           '--permission-mode', 'dontAsk', '--setting-sources', '',
           '--strict-mcp-config', '--mcp-config', '{"mcpServers":{}}',
           '--no-chrome', '--disable-slash-commands', '--no-session-persistence',
           '--output-format', 'stream-json', '--verbose', '--system-prompt', system,
           '--session-id', session]
    if with_tools:
        cmd += ['--allowedTools', 'Bash,Read,Write']
    return cmd

def successful_probe_tools(audit, expected_content):
    calls = {call['id']: call for call in audit.get('tool_calls', [])}
    successful = set()
    for result in audit.get('tool_results', []):
        call = calls.get(result.get('tool_use_id'))
        if not call or result.get('is_error', False):
            continue
        name = call.get('name')
        if name in {'Read', 'Bash'} and expected_content not in json.dumps(result.get('content', ''), ensure_ascii=False):
            continue
        successful.add(name)
    return successful

def probe(name, with_tools):
    folder = RUN / 'probes' / name
    folder.mkdir(parents=True, exist_ok=False)
    workspace = Path(tempfile.mkdtemp(prefix='lyra-gpt6-probe-')).resolve()
    session = str(uuid.uuid4())
    if with_tools:
        expected_content = 'LOCAL_TOOL_OK_' + uuid.uuid4().hex
        (workspace/'probe.txt').write_text(expected_content, 'utf-8')
        system = 'This is an infrastructure probe. Only access files in the current directory. Do not use network or external task data.'
        user = ('Use Read to read probe.txt, then use Bash to print that same local file, '
                'then use Write to save probe-answer.txt with exactly the content read from probe.txt. '
                'Finally reply with exactly BENCH_TOOLS_OK.')
    else:
        system = 'This is a connectivity probe. Reply with exactly BENCH_ROUTE_OK. Do not use tools.'
        user = 'BENCH_ROUTE_OK'
    cmd = command(system, session, with_tools)
    shared.save(folder/'invocation.json', dict(session_id=session, started_utc=utc(),
        workspace=str(workspace), cli_argv=cmd, expected_model=MODEL, contains_task_data=False))
    env = shared.runtime.workspace_environment(routed_environment(1024 if not with_tools else 8192),workspace)
    execution = shared.runtime.execute_logged(cmd,user.encode('utf-8'),env,workspace,folder,
                                             180 if with_tools else 120,['probe-answer.txt'],interval=5)
    stdout, stderr = (folder/'stdout.jsonl').read_bytes(), (folder/'stderr.txt').read_bytes()
    parsed = (shared.cli_agent_transport.parse_output(stdout,stderr,MODEL,workspace) if with_tools
              else shared.cli_transport.parse_output(stdout,stderr,MODEL))
    parsed.pop('raw_response',None)
    passed = bool(parsed['ok'] and parsed['text'].strip()==('BENCH_TOOLS_OK' if with_tools else 'BENCH_ROUTE_OK')
                  and execution['exit_code']==0 and not execution['timed_out'] and execution['process_cleanup_confirmed'])
    if with_tools:
        output=workspace/'probe-answer.txt'
        successful = successful_probe_tools(parsed.get('cli_audit', {}), expected_content)
        parsed['successful_probe_tools'] = sorted(successful)
        passed = passed and output.exists() and output.read_text('utf-8').strip()==expected_content and successful=={'Bash','Read','Write'}
    parsed.update(execution,session_id=session,probe_passed=bool(passed),effort_requested='high',
                  effort_applied=None,probe_contains_task_data=False)
    shared.save(folder/'result.json',parsed)
    print(json.dumps({'probe':name,'passed':passed,'actual_model':parsed.get('actual_model'),'session_id':session}),flush=True)
    return bool(passed)

def probe_pair(suffix=''):
    selection = dict(started_utc=utc(), passed=False, probes={})
    shared.save(RUN/'current-probes.json', selection)
    for kind, with_tools in [('connectivity', False), ('local-tools', True)]:
        name = kind + suffix
        passed = probe(name, with_tools)
        result = shared.load(RUN/'probes'/name/'result.json')
        selection['probes'][kind] = dict(name=name, session_id=result['session_id'], passed=passed)
        if not passed:
            break
    selection['passed'] = len(selection['probes']) == 2 and all(row['passed'] for row in selection['probes'].values())
    shared.save(RUN/'current-probes.json', selection)
    shared.save(RUN/'probes'/('attempt'+(suffix or '-initial')+'.json'), selection)
    return selection['passed']

def validate_selection(selection):
    if not selection.get('passed'):
        raise ValueError('Latest infrastructure probe pair did not pass')
    rows = selection.get('probes', {})
    if set(rows) != {'connectivity', 'local-tools'}:
        raise ValueError('Both infrastructure probe kinds are required')
    if len({row['session_id'] for row in rows.values()}) != 2:
        raise ValueError('Infrastructure probes must have separate sessions')

def audit_probes(selection):
    validate_selection(selection)
    audited = []
    for row in selection['probes'].values():
        folder = RUN/'probes'/row['name']
        parsed = shared.load(folder/'result.json')
        if not parsed['probe_passed'] or parsed['actual_model'] != MODEL or parsed['session_id'] != row['session_id']:
            raise ValueError('Probe response identity is unverified')
        audit = read_session(Path.home()/'.tt-switch/tt-switch.db', row['session_id'], MODEL, PROVIDER_ID)
        audit_path = folder/('route-audit-'+uuid.uuid4().hex[:8]+'.json')
        shared.save(audit_path, audit)
        if not (audit['record_count'] > 0 and audit['all_records_match_expected_model']
                and audit['all_records_match_expected_provider']
                and all(record['status_code'] == 200 and record['has_error'] is False for record in audit['records'])):
            raise ValueError('TT Switch proxy metadata does not confirm a clean expected route')
        audited.append(dict(session_id=row['session_id'], path=str(audit_path), sha256=shared.sha(audit_path)))
    shared.save(RUN/'route-approval.json', dict(probes_verified=True, actual_model=MODEL,
        verified_probe_session_ids=[row['session_id'] for row in audited], audits=audited, audited_utc=utc()))
    print(json.dumps({'route_verified':True,'actual_model':MODEL,'probe_count':len(audited)}),flush=True)

def frozen_inputs():
    archive, freeze, files = shared.verify_package()
    oldplan=shared.load(OLD/'plan.json')
    system=(OLD/'opus/system-prompt.txt').read_bytes()
    user=(OLD/'opus/user-prompt.txt').read_bytes()
    for key,data in [('system_sha256',system),('user_sha256',user)]:
        if hashlib.sha256(data).hexdigest()!=oldplan[key]:
            raise ValueError('Historical prompt hash mismatch')
    if system != shared.SYSTEM.encode('utf-8'):
        raise ValueError('Shared system prompt drift')
    if oldplan['candidate_zip_sha256']!=shared.sha(archive) or oldplan['rubric_sha256']!=freeze['rubric_sha256']:
        raise ValueError('Prior package/rubric mismatch')
    return oldplan, files, system.decode('utf-8'), user.decode('utf-8')

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase',choices=['prepare','reprobe','audit','run'])
    args=parser.parse_args()
    oldplan,files,system,user=frozen_inputs()
    if args.phase=='prepare':
        RUN.mkdir(parents=True,exist_ok=False)
        version=subprocess.run([str(CLI),'--version'],capture_output=True,timeout=30,
                               creationflags=subprocess.CREATE_NO_WINDOW,check=True).stdout.decode('utf-8').strip()
        plan={**oldplan,'run_id':RUN.name,'models':['gpt6'],'expected_model':MODEL,
              'started_utc':utc(),'baseline_run':str(OLD),'transport':'native_claude_via_tt_switch',
              'native_cli':str(CLI),'native_cli_version':version,'native_cli_sha256':shared.sha(CLI),
              'formal_session_id':str(uuid.uuid4()),'base_url':'http://127.0.0.1:15721',
              'global_settings_changed':False,'transport_difference':'Claude Code 2.1.289 via TT Switch; baseline TClaude kernel 2.1.295'}
        shared.save(RUN/'plan.json',plan)
        return 0 if probe_pair() else 2
    plan=shared.load(RUN/'plan.json')
    if args.phase=='reprobe':
        suffix='-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')+'-'+uuid.uuid4().hex[:8]
        return 0 if probe_pair(suffix) else 2
    selection=shared.load(RUN/'current-probes.json')
    if args.phase=='audit':
        audit_probes(selection)
        return 0
    validate_selection(selection)
    for row in selection['probes'].values():
        name=row['name']
        parsed=shared.load(RUN/'probes'/name/'result.json')
        if not parsed['probe_passed'] or parsed['session_id'] != row['session_id']:
            raise ValueError('Infrastructure probe not passed')
    route=shared.load(RUN/'route-approval.json')
    if route.get('probes_verified') is not True or route.get('actual_model')!=MODEL:
        raise ValueError('Independent TT Switch probe route audit missing')
    if set(route.get('verified_probe_session_ids', [])) != {row['session_id'] for row in selection['probes'].values()}:
        raise ValueError('Independent route audit does not match latest probe sessions')
    if shared.sha(CLI)!=plan['native_cli_sha256']:
        raise ValueError('Native CLI changed since probe')
    request=SimpleNamespace(effort=oldplan['effort_requested'],timeout=oldplan['timeout_seconds'],
                            max_output_tokens=oldplan['max_output_tokens_per_turn_requested'])
    fingerprint=dict(protocol='native_claude_via_tt_switch',version=plan['native_cli_version'],
        executable_files=[{'path':str(CLI),'sha256':shared.sha(CLI)}],base_url=plan['base_url'],
        session_id=plan['formal_session_id'],controller_retries=0,tools=['Bash','Read','Write'],
        model_source='fresh assistant response plus separately audited TT Switch proxy rows',
        transport_difference=plan['transport_difference'],wrapper_sha256=shared.sha(Path(__file__)))
    record=shared.run_one('gpt6',RUN,files,user,request,fingerprint,model_identity=(MODEL,MODEL),
        command_override=command(system,plan['formal_session_id'],True),
        env_override=routed_environment(request.max_output_tokens),
        extra_snapshot_files=[__file__, ROOT/'tools/audit_tt_route.py'], canonical_workspace=True)
    shared.save(RUN/'result.json',dict(run_id=RUN.name,records={'gpt6':record},
        candidate_zip_unchanged=shared.sha(ROOT/'dist/LyraLocomotionBench-candidate.zip')==oldplan['candidate_zip_sha256'],
        rubric_unchanged=shared.sha(ROOT/'evaluator/rubric.json')==oldplan['rubric_sha256']))
    return 0 if record['ok'] else 2

if __name__=='__main__':
    raise SystemExit(main())
