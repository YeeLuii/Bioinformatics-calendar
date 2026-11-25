"""Create a synthetic workspace. Never reads or copies private research data."""
import argparse
import datetime
import json
import pathlib
import sqlite3
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import desktop_manage as manage
import desktop_runtime as rt
import desktop_state as state


def create(destination, day, port=8841):
    dest = pathlib.Path(destination).resolve()
    if dest.exists():
        raise ValueError('目标目录已存在，请选择新的演示目录。')
    manage.init(dest)
    config = rt.read_json(dest / 'workspace.json')
    config['port'] = port
    rt.write_json(dest / 'workspace.json', config)
    rt.configure(dest / 'workspace.json')
    stamp = day.isoformat() + 'T09:00:00+08:00'
    descriptions = [
        ('rnaseq', 'RNA-seq 样本质控', '检查测序质量和重复样本的一致性。', '质控完成，等待复核', 'QC v2', '复核样本分组与离群样本', True),
        ('metabolomics', '代谢组处理比较', '比较不同处理条件下的代谢物变化。', '差异分析完成', '比较分析 v1', '检查图注与筛选阈值', False),
        ('validation', '候选基因验证', '整理候选基因和后续验证安排。', '候选清单已整理', '候选表 v3', '确认材料与实验时间', True),
        ('figures', '论文图表整理', '统一已采用图表的版本和说明。', '图表待核对', '图表包 v2', '核对图中缩写和统计说明', False),
        ('pilot', '预实验设计', '为下一阶段分析准备输入和比较方案。', '准备输入数据', '方案 v1', '补充样本信息表', False),
        ('notes', '分析记录归档', '集中记录脚本版本、运行条件和复核事项。', '整理记录中', '记录 v1', '核对脚本和运行记录', False),
    ]
    projects = []
    for pid, name, summary, status, version, todo, server in descriptions:
        folder = dest / 'results' / pid
        folder.mkdir(parents=True)
        (folder / 'README.md').write_text('# ' + name + '\n\n这是虚构演示材料，不含真实研究数据。\n', encoding='utf-8')
        projects.append(dict(id=pid, name=name, summary=summary, status=status,
            current_version=version, scope='演示数据；用于说明项目组织方式，不代表科学结论。',
            todo=todo, local='results/' + pid,
            remote='/srv/research/demo/' + pid if server else '',
            ssh_alias='demo-cluster' if server else '', counts={},
            source='results/' + pid + '/README.md', observed_at=stamp,
            reviewed_at=stamp if pid == 'metabolomics' else '',
            research_stage='结果复核' if pid in {'rnaseq','metabolomics','figures'} else '准备与分析',
            run_status='succeeded' if pid in {'rnaseq','metabolomics'} else 'unknown',
            run_observed_at=stamp if pid in {'rnaseq','metabolomics'} else '',
            run_source='演示运行记录' if pid in {'rnaseq','metabolomics'} else '',
            adoption_status='adopted' if pid == 'metabolomics' else 'exploratory'))
    bundles = []
    rows = []
    definitions = [
        ('qc-report', 'rnaseq', '样本质量与重复一致性报告', 'exploratory', 'QC v2'),
        ('comparison', 'metabolomics', '处理比较结果与说明', 'paper', '比较分析 v1'),
        ('candidates', 'validation', '候选基因整理表', 'intermediate', '候选表 v3'),
        ('run-notes', 'notes', '运行条件与检查记录', 'logs', '记录 v1'),
    ]
    for bid, pid, name, category, version in definitions:
        p = next(p for p in projects if p['id'] == pid)
        filename = dest / 'results' / pid / (bid + '.md')
        filename.write_text('# ' + name + '\n\n演示文件。这里可以保存真实项目的版本、结果范围、来源和复核事项。\n\n当前示例未执行任何科学分析。\n', encoding='utf-8')
        fid = 'file-' + bid
        location = dict(id=fid, path=str(filename), host='local', project_id=pid, availability='available_at_scan')
        bundles.append(dict(id=bid, project_id=pid, name=name, category=category,
            current_version=version, scope=p['scope'], todo=p['todo'], file_count=1,
            review_status='reviewed', reviewed_at=stamp, evidence=['虚构演示：' + filename.name],
            locations=[location], remote=[]))
        p['counts'][category] = 1
        rows.append(dict(**location, category=category, bundle_id=bid, object_type='file',
            current_version=version, version_state='演示版本', basis='虚构示例，仅演示分类',
            scope=p['scope'], todo=p['todo'], evidence='examples/create_demo.py',
            observed_at=stamp, reviewed_at=stamp))
    columns = ['id','path','project_id','category','host','bundle_id','object_type','current_version',
               'availability','version_state','basis','scope','todo','evidence','observed_at','reviewed_at']
    with sqlite3.connect(dest / 'data/files.sqlite') as db:
        db.execute('CREATE TABLE files (' + ','.join(k + ' TEXT' + (' PRIMARY KEY' if k == 'id' else '') for k in columns) + ')')
        db.executemany('INSERT INTO files VALUES (' + ','.join('?' for _ in columns) + ')', [[r[k] for k in columns] for r in rows])
    rt.write_json(dest / 'data/desktop_active.json', {'db': 'files.sqlite'})
    counts = {c: sum(p['counts'].get(c, 0) for p in projects) for c in rt.CATEGORIES}
    rt.write_json(dest / 'data/desktop_data.json', dict(updated_at=stamp, projects=projects,
        bundles=bundles, counts=counts, local_files=len(rows), server_entries=0))
    cards = state.initial()['cards']
    positions = {'rnaseq': ('do', .08, .13), 'metabolomics': ('do', .60, .58),
                 'validation': ('plan', .08, .15), 'figures': ('delegate', .12, .20),
                 'pilot': ('later', .12, .20), 'notes': ('inbox', 0, 0)}
    for card in cards:
        zone, x, y = positions[card['target']]
        card.update(zone=zone, x=x, y=y)
    cards.append(dict(id='folder-analysis', type='folder', target='', title='方法与记录', folder='', zone='plan', x=.60, y=.60))
    next(c for c in cards if c['target'] == 'notes')['folder'] = 'folder-analysis'
    todos = [
        dict(id='todo-qc', title='检查重复样本与分组', date=day.isoformat(), card='p-rnaseq', done=False),
        dict(id='todo-figures', title='复核比较图与图注', date=day.isoformat(), card='p-metabolomics', done=False),
        dict(id='todo-backup', title='保存本周分析记录', date=day.isoformat(), card='p-notes', done=True),
        dict(id='todo-plan', title='确认候选验证材料', date=(day+datetime.timedelta(days=2)).isoformat(), card='p-validation', done=False),
    ]
    for task in todos:
        task.update(project_id=task['card'][2:], start_date=task['date'],
                    status='done' if task['done'] else 'todo', progress=100 if task['done'] else 0,
                    dependencies=[], milestone=False, repeat='none', notes='')
    todos[0].update(start_date=(day-datetime.timedelta(days=2)).isoformat(), status='doing', progress=60)
    todos[1].update(start_date=(day-datetime.timedelta(days=1)).isoformat(), status='doing', progress=30)
    todos[2]['repeat'] = 'weekly'
    todos.extend([
        dict(id='todo-analysis', title='完成候选表达复核', project_id='validation',
             start_date=(day+datetime.timedelta(days=3)).isoformat(), date=(day+datetime.timedelta(days=7)).isoformat(),
             card='p-validation', done=False, status='todo', progress=0, dependencies=['todo-plan'],
             milestone=False, repeat='none', notes='先确认验证材料，再整理表达与文献支持。'),
        dict(id='todo-milestone', title='候选方案确认', project_id='validation',
             start_date=(day+datetime.timedelta(days=8)).isoformat(), date=(day+datetime.timedelta(days=8)).isoformat(),
             card='p-validation', done=False, status='todo', progress=0, dependencies=['todo-analysis'],
             milestone=True, repeat='none', notes='完成复核后确认下一阶段方案。'),
        dict(id='todo-record', title='检查本周分析记录', project_id='notes',
             start_date=(day+datetime.timedelta(days=4)).isoformat(), date=(day+datetime.timedelta(days=4)).isoformat(),
             card='p-notes', done=False, status='todo', progress=0, dependencies=[],
             milestone=False, repeat='weekly', notes='记录输入、脚本版本和结果位置。'),
    ])
    state.save(dict(revision=0, cards=cards, todos=todos))
    print('Synthetic demo ready: ' + str(dest / 'workspace.json'))


if __name__ == '__main__':
    rt.configure_console()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--destination', required=True)
    parser.add_argument('--date', type=datetime.date.fromisoformat, default=datetime.date.today())
    parser.add_argument('--port', type=int, default=8841)
    args = parser.parse_args()
    create(args.destination, args.date, args.port)
