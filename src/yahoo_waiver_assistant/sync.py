"""Read-only Yahoo capture and one-commit private GitHub publication.

Uses existing gh authentication, never prints credentials, and refuses public repos.
No old report is selected by file modification time. A failed capture publishes nothing.
"""
import argparse
import base64
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from .chatgpt_feed import build_feed
from .cli import _services
from .freshness import validate_snapshot
from .snapshot import create_snapshot, save_snapshot
from .report import build_report, render_report


def gh_api(endpoint, *, payload=None, method='POST'):
    command = ['gh', 'api', endpoint]
    if payload is not None:
        command += ['--method', method, '--input', '-']
    result = subprocess.run(command, input=json.dumps(payload) if payload is not None else None,
                            capture_output=True, text=True, check=False)
    if result.returncode:
        # stderr can include sensitive server details; keep it out of scheduled logs.
        raise RuntimeError('GitHub API request failed; check gh authentication and repository permissions')
    return json.loads(result.stdout)


def publish(repository, snapshot, *, api=gh_api):
    quality = validate_snapshot(snapshot)
    prefix = f'repos/{repository}'
    meta = api(prefix)
    if meta.get('private') is not True or meta.get('full_name', '').lower() != repository.lower():
        raise ValueError('Refusing publication: destination is not confirmed private and matching')
    branch = meta['default_branch']
    head = api(f'{prefix}/git/ref/heads/{branch}')['object']['sha']
    tree = api(f'{prefix}/git/commits/{head}')['tree']['sha']
    report = build_report(snapshot)
    feed = build_feed(snapshot)
    status = {'status': 'verified', 'read_only': True, **quality,
              'published_at': datetime.now(timezone.utc).isoformat(),
              'projection_coverage': snapshot.get('data_quality', {})}
    files = {'latest-snapshot.json': snapshot, 'latest-feed.json': feed,
             'latest-report.json': report, 'sync-status.json': status,
             'latest-report.md': render_report(report)}
    entries = []
    for name, value in files.items():
        content = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
        blob = api(f'{prefix}/git/blobs', payload={'encoding': 'base64',
                   'content': base64.b64encode(content.encode('utf-8')).decode('ascii')})
        entries.append({'path': 'yahoo/' + name, 'mode': '100644', 'type': 'blob', 'sha': blob['sha']})
    new_tree = api(f'{prefix}/git/trees', payload={'base_tree': tree, 'tree': entries})['sha']
    commit = api(f'{prefix}/git/commits', payload={'message': 'Synchronize verified read-only Yahoo snapshot',
                 'tree': new_tree, 'parents': [head]})['sha']
    # Non-forced ref update rejects concurrent publication instead of overwriting it.
    api(f'{prefix}/git/refs/heads/{branch}', payload={'sha': commit, 'force': False}, method='PATCH')
    return status


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repository', default='leehchris/yahoo-fantasy-private-data')
    parser.add_argument('--team-key')
    parser.add_argument('--expected-week', type=int)
    args = parser.parse_args()
    status_path = Path('data/private/sync-status.json')
    status_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        # Check GitHub access/privacy before a lengthy Yahoo capture.
        if gh_api(f'repos/{args.repository}').get('private') is not True:
            raise ValueError('Destination must be private')
        _, _, client = _services()
        snapshot = create_snapshot(client, args.team_key)
        validate_snapshot(snapshot, expected_week=args.expected_week)
        save_snapshot(snapshot)
        status = publish(args.repository, snapshot)
        status_path.write_text(json.dumps(status, indent=2), encoding='utf-8')
        print('Verified Yahoo snapshot published. No Yahoo transactions submitted.')
    except Exception as exc:
        status_path.write_text(json.dumps({'status': 'failed', 'error_type': type(exc).__name__,
            'attempted_at': datetime.now(timezone.utc).isoformat()}), encoding='utf-8')
        raise SystemExit('Yahoo sync failed. Previous published capture was preserved; check local authentication/network access.') from None


if __name__ == '__main__':
    main()
