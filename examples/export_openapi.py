"""Regenerate the checked-in contract from its single source of truth."""
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import desktop_contract

if __name__ == '__main__':
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    target = ROOT / 'openapi.json'
    target.write_text(json.dumps(desktop_contract.openapi(), ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(target)
