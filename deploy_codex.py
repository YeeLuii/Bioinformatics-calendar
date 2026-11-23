"""Register MCP through the official CLI, with byte-preserving backup/rollback."""
import json
import os
import pathlib
import re
import shutil
import subprocess
import tempfile
import uuid


class DeploymentError(RuntimeError):
    pass


def codex_command(explicit=None):
    found = explicit or shutil.which('codex')
    if not found:
        return None
    path = pathlib.Path(found).resolve()
    if path.suffix.lower() in {'.cmd', '.bat', '.ps1'}:
        # Execute npm's actual entry point, avoiding a shell and its quoting rules.
        entry = path.parent / 'node_modules/@openai/codex/bin/codex.js'
        node = shutil.which('node')
        if node and entry.is_file():
            return [node, str(entry)]
        raise DeploymentError('Codex shell launcher cannot be resolved safely; use --codex with codex.exe.')
    return [str(path)]


def run_cli(command, args):
    return subprocess.run(command + args, capture_output=True, timeout=30,
                          creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))


def validate_bytes(raw):
    if raw is None:
        return
    try:
        text = raw.decode('utf-8')
    except UnicodeDecodeError:
        raise DeploymentError('Codex config is not UTF-8; it was not modified.')
    if text.startswith('\ufeff') or re.search(r'\r(?!\n)', text):
        raise DeploymentError('Codex config has a BOM or invalid CR/CRCRLF line endings; it was not modified.')
    try:
        import tomllib
    except ImportError:
        return  # Python 3.9/3.10: the official CLI performs full parsing below.
    try:
        tomllib.loads(text)
    except ValueError:
        raise DeploymentError('Codex config is not valid TOML; it was not modified.')


def read_optional(path):
    return path.read_bytes() if path.exists() else None


def atomic_restore(path, previous, expected):
    if read_optional(path) != expected:
        raise DeploymentError('Codex config changed concurrently; automatic rollback was skipped. Use the saved backup.')
    if previous is None:
        if path.exists():
            path.unlink()
        return
    with tempfile.NamedTemporaryFile(dir=path.parent, prefix='.ai4s-restore-', delete=False) as f:
        temporary = pathlib.Path(f.name)
        f.write(previous)
        f.flush()
        os.fsync(f.fileno())
    try:
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def matches(record, python, arguments):
    transport = record.get('transport', {})
    if transport.get('type') != 'stdio' or record.get('enabled') is False:
        return False
    return (os.path.normcase(transport.get('command', '')) == os.path.normcase(str(python))
            and transport.get('args') == arguments)


def register(python, script, config, mode='auto', explicit=None, replace=False, *, home=None, runner=run_cli):
    if mode == 'off':
        return {'status': 'disabled'}
    command = codex_command(explicit)
    if not command:
        if mode == 'required':
            raise DeploymentError('Codex CLI is unavailable. Install the CLI or pass --codex; config.toml was not edited.')
        return {'status': 'cli_unavailable', 'action_required': 'Install Codex CLI, then rerun deploy; no config was edited.'}
    root = pathlib.Path(home) if home is not None else pathlib.Path(os.environ.get('CODEX_HOME') or pathlib.Path.home() / '.codex')
    target = root / 'config.toml'
    if target.is_symlink():
        raise DeploymentError('Codex config is a symbolic link; automatic registration is disabled.')
    before = read_optional(target)
    validate_bytes(before)
    check = runner(command, ['mcp', 'list', '--json'])
    if check.returncode:
        raise DeploymentError('Codex could not parse its existing config or does not support mcp list --json; no changes made.')
    try:
        records = json.loads(check.stdout)
        if not isinstance(records, list) or not all(isinstance(r, dict) for r in records):
            raise ValueError()
    except (ValueError, TypeError):
        raise DeploymentError('Unsupported Codex CLI JSON response; no changes made.')
    arguments = ['-B', str(script), '--config', str(config)]
    existing = next((r for r in records if r.get('name') == 'ai4s'), None)
    if existing and matches(existing, python, arguments):
        return {'status': 'already_configured'}
    if existing and not replace:
        raise DeploymentError('An ai4s MCP entry already points elsewhere. Use --replace-mcp only if replacement is intended.')
    root.mkdir(parents=True, exist_ok=True)
    backup = root / ('config.toml.ai4s-backup-' + uuid.uuid4().hex)
    if before is not None:
        with backup.open('xb') as f:
            f.write(before)
        if os.name != 'nt':
            backup.chmod(0o600)
    if read_optional(target) != before:
        raise DeploymentError('Codex config changed before registration; no changes made.')
    after = before
    try:
        try:
            added = runner(command, ['mcp', 'add', 'ai4s', '--', str(python), *arguments])
        finally:
            after = read_optional(target)
        if added.returncode:
            raise DeploymentError('Official Codex MCP registration failed.')
        validate_bytes(after)
        if after is None:
            raise DeploymentError('Codex did not create its configuration.')
        checked = runner(command, ['mcp', 'list', '--json'])
        if checked.returncode:
            raise DeploymentError('Codex configuration validation failed after registration.')
        updated = json.loads(checked.stdout)
        if not isinstance(updated, list) or not all(isinstance(r, dict) for r in updated):
            raise DeploymentError('Unsupported Codex CLI verification response.')
        entry = next((r for r in updated if r.get('name') == 'ai4s'), {})
        others = lambda rows: sorted((r for r in rows if r.get('name') != 'ai4s'), key=lambda r: r.get('name', ''))
        if not matches(entry, python, arguments) or others(updated) != others(records):
            raise DeploymentError('MCP registration did not preserve the expected entries.')
        if read_optional(target) != after:
            raise DeploymentError('Codex config changed during verification.')
    except (DeploymentError, OSError, ValueError, TypeError, subprocess.SubprocessError) as error:
        atomic_restore(target, before, after)
        raise DeploymentError('MCP configuration failed; the original bytes were restored. ' + str(error)) from error
    return {'status': 'registered', 'backup': str(backup) if before is not None else None,
            'reload_client': True}
