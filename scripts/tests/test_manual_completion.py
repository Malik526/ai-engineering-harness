"""Fixture coverage for manual completion without launching provider sessions."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess

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
