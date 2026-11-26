"""Fixture coverage for manual completion without launching provider sessions."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('complete', ROOT / 'scripts/manual/complete.py')
complete = importlib.util.module_from_spec(spec)
spec.loader.exec_module(complete)


@pytest.fixture
def repo(tmp_path):
    root = tmp_path / 'repo'
    root.mkdir()
    def git(*args):
        subprocess.run(['git', '-C', str(root), *args], check=True, capture_output=True)
    git('init')
    git('config', 'user.email', 'fixture@example.invalid')
    git('config', 'user.name', 'Fixture')
    (root / 'app.py').write_text('pass\n')
    git('add', '.')
    git('commit', '-m', 'fixture baseline')
    return root


def reconcile(repo):
    state = complete.snapshot(repo)
    return {'fingerprint': state['fingerprint'], 'expected_paths': [r['path'] for r in state['files']],
            'validation_scope': {k: {'commands': ['tests']} for k in ('test', 'typecheck', 'lint', 'build', 'runtime')},
            'documentation': {a: {'status': 'not_applicable', 'reason': 'fixture changes no authoritative fact'} for a in complete.AREAS}}


COMMANDS = [{'name': 'tests', 'kind': 'test', 'run': 'python3 -c "exit(0)"', 'required': True}]


def check(repo, tmp_path, rec=None, commands=COMMANDS, run=False):
    return complete.evaluate(repo, tmp_path / 'evidence.json', rec or reconcile(repo), commands, run)


def test_success_and_commit_recommendation(repo, tmp_path):
    (repo / 'app.py').write_text('print(1)\n')
    result = check(repo, tmp_path, run=True)
    assert result['status'] == 'PASS'
    assert result['commit_recommendation_required']
    rec = reconcile(repo)
    rec['human_requested_commit'] = True
    assert not check(repo, tmp_path, rec)['commit_recommendation_required']


def test_skipped_validation(repo, tmp_path):
    (repo / 'app.py').write_text('print(1)\n')
    assert 'required validation missing or stale' in check(repo, tmp_path)['issues']


def test_failed_validation(repo, tmp_path):
    commands = [{**COMMANDS[0], 'run': 'exit 1'}]
    assert check(repo, tmp_path, commands=commands, run=True)['status'] == 'NEEDS_ATTENTION'


def test_missing_reconciliation(repo, tmp_path):
    (repo / 'README.md').write_text('Changed behavior\n')
    rec = reconcile(repo)
    del rec['documentation']['changelog']
    assert check(repo, tmp_path, rec, commands=[])['status'] == 'NEEDS_ATTENTION'


def test_no_docs_required(repo, tmp_path):
    (repo / 'README.md').write_text('Typo correction\n')
    assert check(repo, tmp_path, commands=[])['status'] == 'PASS'


def test_secret_file_blocks_validation(repo, tmp_path):
    (repo / '.env').write_text('PLACEHOLDER=example\n')
    assert check(repo, tmp_path, run=True)['status'] == 'NEEDS_ATTENTION'
    assert not (tmp_path / 'evidence.json').exists()


def test_analysis_only(repo, tmp_path):
    result = check(repo, tmp_path, commands=[])
    assert result['status'] == 'PASS'
    assert not result['commit_recommendation_required']


def test_stale_validation(repo, tmp_path):
    check(repo, tmp_path, run=True)
    (repo / 'app.py').write_text('print(2)\n')
    assert check(repo, tmp_path)['status'] == 'NEEDS_ATTENTION'


def test_unexpected_and_staged_files(repo, tmp_path):
    rec = reconcile(repo)
    (repo / 'new.py').write_text('pass\n')
    subprocess.run(['git', '-C', str(repo), 'add', 'new.py'], check=True)
    result = check(repo, tmp_path, rec, run=True)
    assert result['files'][0]['status'] == 'A '
    assert any('unacknowledged' in issue for issue in result['issues'])


def test_autobuild_noop(tmp_path):
    result = subprocess.run(['python3', str(ROOT / 'scripts/manual/complete.py')], cwd=tmp_path,
                            env={**os.environ, 'AUTOBUILD_RUN_ID': 'fixture'}, capture_output=True, text=True)
    assert result.returncode == 0
    assert json.loads(result.stdout)['status'] == 'SKIP'


@pytest.mark.parametrize('provider', ['claude', 'codex'])
def test_adapter_integration(provider):
    text = (ROOT / f'runtime/{provider}/adapter.fragment.md').read_text()
    assert '~/.agents/manual-completion/complete.py' in text
    assert 'NEEDS_ATTENTION' in text
    assert 'GIT.md' in text
    manifest = (ROOT / 'scripts/setup/links.manifest').read_text()
    assert 'scripts/manual' in manifest


def test_required_runtime_applicability(repo, tmp_path):
    (repo / 'app.py').write_text('print(1)\n')
    rec = reconcile(repo)
    del rec['validation_scope']['runtime']
    assert 'reconcile validation applicability: runtime' in check(repo, tmp_path, rec, run=True)['issues']


def test_updated_document_requires_changed_path(repo, tmp_path):
    rec = reconcile(repo)
    rec['documentation']['changelog'] = {'status': 'updated', 'reason': 'claimed', 'paths': ['CHANGELOG.md']}
    assert check(repo, tmp_path, rec, commands=[])['status'] == 'NEEDS_ATTENTION'


def test_installed_adapters_and_shared_entrypoint(tmp_path):
    import sys
    sys.path.insert(0, str(ROOT / 'scripts/setup'))
    from runtime_guards import reconcile as install_adapters
    reports = install_adapters(ROOT, tmp_path, ['claude', 'codex'], apply=True)
    assert not any(r.startswith('CONFLICT') for r in reports)
    for provider, name in [('claude', 'CLAUDE.md'), ('codex', 'AGENTS.md')]:
        text = (tmp_path / f'.{provider}' / name).read_text()
        assert '~/.agents/manual-completion/complete.py' in text


def test_unborn_repo(tmp_path):
    subprocess.run(['git', 'init', str(tmp_path / 'new')], check=True, capture_output=True)
    assert complete.snapshot(tmp_path / 'new')['files'] == []


def test_unsafe_validation_spec_rejected(repo, tmp_path):
    with pytest.raises(ValueError):
        check(repo, tmp_path, commands=[{**COMMANDS[0], 'name': '../escape'}], run=True)


def test_in_progress_git_operation(repo, tmp_path):
    (repo / '.git' / 'CHERRY_PICK_HEAD').write_text('fixture\n')
    assert 'Git operation in progress' in check(repo, tmp_path, commands=[])['issues']


def test_unresolved_conflict(repo, tmp_path):
    # Real merge conflict; only fixture repositories create branches or commits.
    def git(*args, check=True):
        return subprocess.run(['git', '-C', str(repo), *args], check=check, capture_output=True)
    original = git('branch', '--show-current').stdout.decode().strip()
    git('checkout', '-b', 'other')
    (repo / 'app.py').write_text('other\n')
    git('commit', '-am', 'other')
    git('checkout', original)
    (repo / 'app.py').write_text('main\n')
    git('commit', '-am', 'main')
    assert git('merge', 'other', check=False).returncode == 1
    assert 'unresolved Git conflicts' in check(repo, tmp_path, commands=[])['issues']


def test_validation_command_change_invalidates_evidence(repo, tmp_path):
    check(repo, tmp_path, run=True)
    commands = [{**COMMANDS[0], 'run': 'python3 -c "exit(1)"'}]
    assert 'required validation missing or stale' in check(repo, tmp_path, commands=commands)['issues']


# --- Run ordering and evidence reuse (2026-11-25) ---

def counting_commands(tmp_path, exit_code=0):
    """A command that records each execution in a file outside the repository."""
    counter = tmp_path / 'runs.log'
    script = f"open({str(counter)!r}, 'a').write('x'); raise SystemExit({exit_code})"
    return counter, [{'name': 'tests', 'kind': 'test', 'command': ['python3', '-c', script], 'required': True}]


def executions(counter):
    return len(counter.read_text()) if counter.exists() else 0


def test_stale_reconciliation_blocks_validation(repo, tmp_path):
    counter, commands = counting_commands(tmp_path)
    rec = reconcile(repo)
    (repo / 'app.py').write_text('print(1)\n')  # reconciliation fingerprint is now stale
    result = check(repo, tmp_path, rec, commands=commands, run=True)
    assert result['validation_run'] == 'blocked'
    assert 'documentation reconciliation missing or stale' in result['issues']
    assert executions(counter) == 0
    assert not (tmp_path / 'evidence.json').exists()


def test_unacknowledged_file_blocks_validation(repo, tmp_path):
    counter, commands = counting_commands(tmp_path)
    (repo / 'app.py').write_text('print(1)\n')
    rec = reconcile(repo)
    rec['expected_paths'] = []
    result = check(repo, tmp_path, rec, commands=commands, run=True)
    assert result['validation_run'] == 'blocked'
    assert executions(counter) == 0


def test_conflict_and_secret_file_block_validation(repo, tmp_path):
    counter, commands = counting_commands(tmp_path)
    (repo / '.git' / 'MERGE_HEAD').write_text('fixture\n')
    (repo / '.env').write_text('PLACEHOLDER=example\n')
    result = check(repo, tmp_path, commands=commands, run=True)
    assert result['validation_run'] == 'blocked'
    assert 'Git operation in progress' in result['issues']
    assert any(issue.startswith('secret-like files') for issue in result['issues'])
    assert executions(counter) == 0


def test_run_validation_reuses_fresh_passing_evidence(repo, tmp_path):
    counter, commands = counting_commands(tmp_path)
    (repo / 'app.py').write_text('print(1)\n')
    first = check(repo, tmp_path, commands=commands, run=True)
    assert (first['status'], first['validation_run']) == ('PASS', 'executed')
    second = check(repo, tmp_path, commands=commands, run=True)
    assert (second['status'], second['validation_run']) == ('PASS', 'reused')
    assert second['validation'] == first['validation']
    assert second['commit_recommendation_required']
    assert executions(counter) == 1


def test_failed_evidence_is_rerun(repo, tmp_path):
    counter, commands = counting_commands(tmp_path, exit_code=1)
    (repo / 'app.py').write_text('print(1)\n')
    assert check(repo, tmp_path, commands=commands, run=True)['status'] == 'NEEDS_ATTENTION'
    again = check(repo, tmp_path, commands=commands, run=True)
    assert (again['validation_run'], again['validation_run_reason']) == ('executed', 'stored run did not pass')
    assert executions(counter) == 2


def test_repository_change_is_rerun(repo, tmp_path):
    counter, commands = counting_commands(tmp_path)
    (repo / 'app.py').write_text('print(1)\n')
    check(repo, tmp_path, commands=commands, run=True)
    (repo / 'app.py').write_text('print(2)\n')
    again = check(repo, tmp_path, commands=commands, run=True)
    assert (again['status'], again['validation_run']) == ('PASS', 'executed')
    assert again['validation_run_reason'] == 'repository changed since the stored run'
    assert executions(counter) == 2


def test_command_change_is_rerun(repo, tmp_path):
    counter, commands = counting_commands(tmp_path)
    (repo / 'app.py').write_text('print(1)\n')
    check(repo, tmp_path, commands=commands, run=True)
    changed = [{**commands[0], 'timeout_seconds': 60}]
    again = check(repo, tmp_path, commands=changed, run=True)
    assert again['validation_run_reason'] == 'validation commands changed'
    assert executions(counter) == 2


def test_environment_change_is_rerun(repo, tmp_path, monkeypatch):
    counter, commands = counting_commands(tmp_path)
    (repo / 'app.py').write_text('print(1)\n')
    check(repo, tmp_path, commands=commands, run=True)
    monkeypatch.setenv('DATABASE_URL', 'postgresql://fixture.invalid/db')
    again = check(repo, tmp_path, commands=commands, run=True)
    assert again['validation_run_reason'] == 'environment changed since the stored run'
    assert executions(counter) == 2


def test_volatile_shell_variables_do_not_block_reuse(repo, tmp_path, monkeypatch):
    counter, commands = counting_commands(tmp_path)
    (repo / 'app.py').write_text('print(1)\n')
    check(repo, tmp_path, commands=commands, run=True)
    monkeypatch.setenv('PWD', '/elsewhere')
    monkeypatch.setenv('OLDPWD', '/before')
    assert check(repo, tmp_path, commands=commands, run=True)['validation_run'] == 'reused'
    assert executions(counter) == 1


def test_old_evidence_is_rerun(repo, tmp_path):
    counter, commands = counting_commands(tmp_path)
    (repo / 'app.py').write_text('print(1)\n')
    check(repo, tmp_path, commands=commands, run=True)
    evidence = tmp_path / 'evidence.json'
    record = json.loads(evidence.read_text())
    record['recorded_at'] = '2020-01-01T00:00:00+00:00'
    evidence.write_text(json.dumps(record))
    again = check(repo, tmp_path, commands=commands, run=True)
    assert again['validation_run'] == 'executed'
    assert 'reuse window' in again['validation_run_reason']
    assert executions(counter) == 2


def test_evidence_without_reuse_metadata_is_rerun(repo, tmp_path):
    counter, commands = counting_commands(tmp_path)
    (repo / 'app.py').write_text('print(1)\n')
    check(repo, tmp_path, commands=commands, run=True)
    evidence = tmp_path / 'evidence.json'
    record = json.loads(evidence.read_text())
    del record['environment'], record['recorded_at']  # evidence written before reuse existed
    evidence.write_text(json.dumps(record))
    assert check(repo, tmp_path, commands=commands, run=True)['validation_run'] == 'executed'
    assert executions(counter) == 2


def test_fresh_validation_always_runs(repo, tmp_path):
    counter, commands = counting_commands(tmp_path)
    (repo / 'app.py').write_text('print(1)\n')
    check(repo, tmp_path, commands=commands, run=True)
    again = complete.evaluate(repo, tmp_path / 'evidence.json', reconcile(repo), commands, True, True)
    assert (again['validation_run'], again['validation_run_reason']) == ('executed', 'fresh validation requested')
    assert executions(counter) == 2


def test_check_without_run_reports_not_requested(repo, tmp_path):
    counter, commands = counting_commands(tmp_path)
    (repo / 'app.py').write_text('print(1)\n')
    check(repo, tmp_path, commands=commands, run=True)
    result = check(repo, tmp_path, commands=commands)
    assert (result['status'], result['validation_run']) == ('PASS', 'not_requested')
    assert check(repo, tmp_path, commands=[])['validation_run'] == 'not_applicable'
    assert executions(counter) == 1


def test_cli_fresh_validation_flag(repo, tmp_path):
    counter, commands = counting_commands(tmp_path)
    (repo / 'app.py').write_text('print(1)\n')
    (tmp_path / 'rec.json').write_text(json.dumps(reconcile(repo)))
    (tmp_path / 'cmds.json').write_text(json.dumps(commands))
    def cli(*extra):
        done = subprocess.run([sys.executable, str(ROOT / 'scripts/manual/complete.py'), '--root', str(repo),
                               '--evidence', str(tmp_path / 'evidence.json'), '--reconciliation', str(tmp_path / 'rec.json'),
                               '--commands', str(tmp_path / 'cmds.json'), '--run-validation', *extra],
                              capture_output=True, text=True)
        return json.loads(done.stdout)
    assert cli()['validation_run'] == 'executed'
    assert cli()['validation_run'] == 'reused'
    assert cli('--fresh-validation')['validation_run'] == 'executed'
    assert executions(counter) == 2
