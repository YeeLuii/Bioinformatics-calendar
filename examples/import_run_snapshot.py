# -*- coding: utf-8 -*-
"""Preview or import a local run-status snapshot. Never executes research commands."""
import argparse
import datetime
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

STATES = {'unknown', 'queued', 'running', 'succeeded', 'failed', 'cancelled'}


def timestamp(value):
    if not isinstance(value, str):
        raise ValueError('observed_at must be an ISO timestamp with a time zone')
    try:
        stamp = datetime.datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError as exc:
        raise ValueError('observed_at must be an ISO timestamp with a time zone') from exc
    if stamp.tzinfo is None:
        raise ValueError('observed_at requires a time zone, for example +08:00')
    return stamp


def prepare(snapshot, project, now=None):
    """Build a narrowly scoped patch, preserving research and adoption decisions."""
    if not isinstance(snapshot, dict) or snapshot.get('schema_version') != 1:
        raise ValueError('Unsupported run snapshot schema_version')
    allowed = {'schema_version', 'project_id', 'run_status', 'observed_at', 'source', 'run_id'}
    if set(snapshot) - allowed:
        raise ValueError('Unknown snapshot fields: ' + ', '.join(sorted(set(snapshot) - allowed)))
    pid = snapshot.get('project_id', '')
    if not isinstance(pid, str) or not re.fullmatch(r'[a-zA-Z0-9_-]{1,80}', pid):
        raise ValueError('Invalid project_id')
    if pid != project.get('id'):
        raise ValueError('Snapshot project_id does not match the registered project')
    status = snapshot.get('run_status')
    if status not in STATES:
        raise ValueError('Invalid run_status')
    observed = timestamp(snapshot.get('observed_at'))
    clock = now or datetime.datetime.now(datetime.timezone.utc)
    if observed > clock + datetime.timedelta(minutes=5):
        raise ValueError('Observation time is in the future; check the exporting host clock')
    previous = project.get('run_observed_at')
    if previous and observed < timestamp(previous):
        raise ValueError('Snapshot is older than the registered run observation')
    source = snapshot.get('source')
    if not isinstance(source, str) or not source.strip() or len(source) > 10000:
        raise ValueError('source is required (maximum 10000 characters)')
    run_id = snapshot.get('run_id', '')
    if not isinstance(run_id, str) or len(run_id) > 200:
        raise ValueError('run_id must be a short string')
    if any(ord(ch) < 32 for ch in source + run_id):
        raise ValueError('source and run_id cannot contain control characters')
    patch = {
        'run_status': status,
        'run_observed_at': snapshot['observed_at'],
        'run_source': source.strip() + (' (run: ' + run_id + ')' if run_id else ''),
    }
    if previous and observed == timestamp(previous) and any(project.get(k, '') != v for k, v in patch.items()):
        raise ValueError('Conflicting observations at the same time; inspect the source before updating')
    return {k: v for k, v in patch.items() if project.get(k, '') != v}


def main(argv=None):
    import desktop_runtime as runtime
    import desktop_services as services
    runtime.configure_console()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', required=True)
    parser.add_argument('--snapshot', required=True)
    parser.add_argument('--apply', action='store_true', help='Apply after reviewing the default preview')
    parser.add_argument('--expected-revision', type=int)
    args = parser.parse_args(argv)
    if args.apply and args.expected_revision is None:
        parser.error('--apply requires the --expected-revision shown in the preview')
    path = pathlib.Path(args.snapshot)
    if path.stat().st_size > 65536:
        raise ValueError('Run snapshot exceeds 64 KiB')
    snapshot = json.loads(path.read_text(encoding='utf-8-sig'))
    if not isinstance(snapshot, dict):
        raise ValueError('Run snapshot must be an object')
    runtime.configure(args.config)
    record = services.execute('project_get', {'project_id': snapshot.get('project_id')})
    patch = prepare(snapshot, record['project'])
    output = {'project_id': record['project']['id'], 'expected_revision': record['revision'],
              'changes': {k: {'before': record['project'].get(k, ''), 'after': v} for k, v in patch.items()},
              'applied': False, 'note': 'Recorded run observation only; research results have not been reviewed.'}
    if args.apply:
        if args.expected_revision != record['revision']:
            raise services.ConflictError('revision changed; preview again before applying')
        if patch:
            result = services.execute('project_update', {'project_id': record['project']['id'],
                'patch': patch, 'expected_revision': args.expected_revision})
            output.update(applied=True, revision=result['revision'])
        else:
            output['note'] = 'This observation is already registered; no changes made.'
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return output


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)
