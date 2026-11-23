"""Small, dependency-free client for the stable project API."""
import argparse
import json
import sys
from urllib.error import HTTPError
from urllib.parse import quote, urlsplit
from urllib.request import Request, urlopen


def call(base, path, method='GET', body=None, token=None):
    headers = {'Content-Type': 'application/json'}
    if token:
        headers['X-Desk-Token'] = token
    data = None if body is None else json.dumps(body, ensure_ascii=False).encode('utf-8')
    with urlopen(Request(base + path, data=data, headers=headers, method=method), timeout=10) as response:
        return json.load(response)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', default='http://127.0.0.1:8828')
    parser.add_argument('action', choices=['list', 'create-example', 'summary'])
    parser.add_argument('--project-id', default='api-example')
    args = parser.parse_args()
    base = args.base.rstrip('/')
    parsed = urlsplit(base)
    if parsed.scheme != 'http' or parsed.hostname not in {'127.0.0.1', 'localhost'}:
        parser.error('Use a local AI4S HTTP address.')
    try:
        if args.action == 'list':
            result = call(base, '/api/v1/projects')
        elif args.action == 'summary':
            result = call(base, '/api/v1/projects/' + quote(args.project_id, safe='') + '/summary')
        else:
            token = call(base, '/api/overview')['token']
            revision = call(base, '/api/v1/projects')['revision']
            result = call(base, '/api/v1/projects', 'POST', {
                'expected_revision': revision,
                'project': {'id': args.project_id, 'name': 'API 示例项目',
                            'summary': '演示如何通过 HTTP 登记分析项目。',
                            'status': '准备输入数据', 'todo': '检查样本信息表'}
            }, token)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except HTTPError as error:
        print(f'HTTP {error.code}: ' + error.read().decode('utf-8'), file=sys.stderr)
        raise SystemExit(1)


if __name__ == '__main__':
    main()

