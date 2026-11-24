"""Additional named project locations; legacy primary locations stay compatible."""
import pathlib
import re
import urllib.parse
import desktop_runtime as rt


def clean_addresses(value):
    if not isinstance(value, list) or len(value) > 50:
        raise ValueError('附加地址须为列表，最多50项')
    result, seen = [], set()
    for entry in value:
        if not isinstance(entry, dict) or set(entry) - {'id', 'label', 'kind', 'path', 'ssh_alias'}:
            raise ValueError('地址字段无效')
        if not all(isinstance(entry.get(k, ''), str) for k in ['id', 'label', 'kind', 'path', 'ssh_alias']):
            raise ValueError('地址字段须为文本')
        item = {k: entry.get(k, '').strip() for k in ['id', 'label', 'kind', 'path', 'ssh_alias']}
        if not re.fullmatch(r'[a-zA-Z0-9_-]{1,80}', item['id']) or item['id'] in seen:
            raise ValueError('地址ID无效或重复')
        if item['kind'] not in {'local', 'server', 'url'} or not item['path']:
            raise ValueError('请选择地址类型并填写地址')
        if len(item['label']) > 200 or len(item['path']) > 4096 or len(item['ssh_alias']) > 200:
            raise ValueError('地址内容过长')
        if any(ord(c) < 32 for c in item['path']):
            raise ValueError('地址不能包含换行或控制字符')
        alias = item['ssh_alias']
        if alias and (alias.startswith('-') or not re.fullmatch(r'[\w.@:-]+', alias)):
            raise ValueError('SSH 别名无效')
        if item['kind'] != 'server' and alias:
            raise ValueError('仅服务器地址可填写 SSH 别名')
        if item['kind'] == 'url':
            url = urllib.parse.urlsplit(item['path'])
            if url.scheme not in {'http', 'https'} or not url.hostname or url.username or url.password:
                raise ValueError('网页地址须为不含账号密码的 http/https 链接')
        if item['kind'] == 'server' and not item['path'].startswith('/'):
            raise ValueError('服务器目录须使用绝对路径')
        seen.add(item['id'])
        result.append(item)
    return result


def location(project, entry):
    kind = entry['kind']
    value = str(rt.local_path(entry['path'])) if kind == 'local' else (
        rt.remap(entry['path'], 'server') if kind == 'server' else entry['path'])
    return {
        'id': 'project:' + project['id'] + ':address:' + entry['id'],
        'project_id': project['id'], 'host': kind, 'path': value, 'label': entry['label'],
        'object_type': 'url' if kind == 'url' else 'directory',
        'availability': ('available' if pathlib.Path(value).is_dir() else 'missing_at_path') if kind == 'local' else 'unverified',
        'ssh_alias': (entry['ssh_alias'] or project.get('ssh_alias', '')) if kind == 'server' else ''
    }
