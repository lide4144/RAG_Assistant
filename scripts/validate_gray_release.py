from __future__ import annotations

import argparse
from pathlib import Path

import yaml


def main() -> int:
    parser = argparse.ArgumentParser(description='Validate gray release config flags')
    parser.add_argument('--config', default='configs/default.yaml')
    args = parser.parse_args()

    cfg = yaml.safe_load(Path(args.config).read_text(encoding='utf-8')) or {}

    required = {
        'rewrite_parallel_candidates_enabled': True,
        'rewrite_arbitration_enabled': True,
    }
    failed = []
    for key, expected in required.items():
        if cfg.get(key) != expected:
            failed.append(f'{key} expected {expected}, got {cfg.get(key)!r}')

    legacy_flag = bool(cfg.get('rewrite_legacy_strategy_enabled', False))

    if failed:
        print('GRAY_RELEASE_CHECK: FAIL')
        for row in failed:
            print(f'- {row}')
        return 1

    print('GRAY_RELEASE_CHECK: PASS')
    print(f'- rewrite_legacy_strategy_enabled={legacy_flag}')
    print('- rollback command: venv/bin/python scripts/validate_gray_release.py --config configs/default.yaml')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
