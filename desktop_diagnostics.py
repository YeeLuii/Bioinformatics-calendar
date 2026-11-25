"""Read-only local diagnostics and explicit navigation-only migration mappings."""
import pathlib
import re
import desktop_runtime as rt
from desktop_storage import read_json, write_json


def clean_mappings(mappings):
    if not isinstance(mappings, list) or len(mappings) > 100:
        raise ValueError('路径映射最多 100 条')
    clean = []; seen = set()
    for m in mappings:
        if not isinstance(m, dict) or set(m) != {'host', 'from', 'to'} or m['host'] not in {'local', 'server'}:
            raise ValueError('映射需要 host、from 和 to')
        for key in ('from', 'to'):
            value = m[key]
            if not isinstance(value, str) or not value or len(value) > 4096 or re.search(r'[\x00-\x1f\x7f]', value):
                raise ValueError('映射路径为空、过长或包含控制字符')
            if not (pathlib.PurePosixPath(value).is_absolute() or (m['host'] == 'local' and pathlib.PureWindowsPath(value).is_absolute())):
                raise ValueError('映射路径必须为绝对路径')
        key = (m['host'], m['from'].replace('\\', '/').rstrip('/'))
        if m['host'] == 'local': key = (key[0], key[1].lower())
        if key in seen: raise ValueError('同一来源路径不能重复映射')
        seen.add(key); clean.append(dict(m))
    return clean


def mapped(value, host, mappings):
    s = value.replace('\\', '/')
    for m in sorted(mappings, key=lambda x: len(x['from']), reverse=True):
        if m['host'] != host: continue
        old = m['from'].replace('\\', '/').rstrip('/')
        a, b = (s.lower(), old.lower()) if host == 'local' else (s, old)
        if a == b or a.startswith(b + '/'):
            return m['to'].replace('\\', '/').rstrip('/') + s[len(old):]
    return s


def locations(mappings):
    import desktop_repository as repository
    source = read_json(rt.path('desktop_data.json'), {})
    projects = {p['id']: dict(p) for p in source.get('projects', [])}
    for p in repository.overrides()['projects']: projects[p['id']] = {**projects.get(p['id'], {}), **p}
    result = []
    for p in projects.values():
        entries = []
        if p.get('local'): entries.append({'kind': 'local', 'path': p['local'], 'label': '本地目录'})
        if p.get('remote'): entries.append({'kind': 'server', 'path': p['remote'], 'label': '服务器目录'})
        entries += p.get('addresses', [])
        for entry in entries:
            kind = entry['kind']; original = entry['path']
            path = original if kind == 'url' else mapped(original, kind, mappings)
            if kind == 'local':
                foreign = pathlib.PureWindowsPath(path).is_absolute() and not pathlib.Path(path).is_absolute()
                if not foreign and not pathlib.Path(path).is_absolute(): path = str(rt.WORKSPACE_ROOT / path)
                try: status = 'available' if pathlib.Path(path).is_dir() else 'missing_at_path'
                except OSError: status = 'unverified'
            else: status = 'unverified'
            result.append({'project_id': p['id'], 'label': entry.get('label') or kind, 'kind': kind, 'original_path': original, 'path': path, 'status': status})
    return result


def inspect():
    config = read_json(rt.CONFIG_PATH, rt.CONFIG)
    mappings = config.get('path_mappings', [])
    import sqlite3, ssl
    checks = [
        {'kind': 'workspace', 'status': 'ok', 'label': '工作区', 'detail': str(rt.DATA_DIR)},
        {'kind': 'runtime', 'status': 'ok', 'label': '标准库', 'detail': 'SQLite / TLS 可导入；不安装额外依赖'},
        {'kind': 'mcp', 'status': 'unknown', 'label': 'MCP 客户端加载', 'detail': '当前接口不推断其他客户端是否加载；请在客户端调用 workspace_status 验证。'},
        {'kind': 'server', 'status': 'unverified', 'label': '远程位置', 'detail': '此检查不连接服务器，不将不可达解释为目录不存在。'},
    ]
    return {'checked_at': rt.now(), 'checks': checks, 'locations': locations(mappings), 'path_mappings': mappings, 'config_revision': config.get('_mapping_revision', 0)}


def preview(mappings):
    mappings = clean_mappings(mappings)
    config = read_json(rt.CONFIG_PATH, rt.CONFIG)
    before = locations(config.get('path_mappings', [])); after = locations(mappings)
    changes = [{'project_id': a['project_id'], 'label': a['label'], 'before': b['path'], 'after': a['path']} for b, a in zip(before, after) if b['path'] != a['path']]
    return {'locations': after, 'changes': changes, 'config_revision': config.get('_mapping_revision', 0)}


def save(mappings, expected_revision):
    from desktop_services import ConflictError
    mappings = clean_mappings(mappings)
    with rt.workspace_lock():
        cfg = read_json(rt.CONFIG_PATH, rt.CONFIG)
        if cfg.get('_mapping_revision', 0) != expected_revision:
            raise ConflictError('路径映射 revision 冲突，请重新检查')
        # Back up only workspace configuration, never any client credentials.
        if rt.CONFIG_PATH.is_file():
            rt.CONFIG_PATH.with_suffix('.mapping-backup.json').write_bytes(rt.CONFIG_PATH.read_bytes())
        cfg['path_mappings'] = mappings
        cfg['_mapping_revision'] = expected_revision + 1
        write_json(rt.CONFIG_PATH, cfg)
        rt.CONFIG.update(cfg)
    return inspect()
