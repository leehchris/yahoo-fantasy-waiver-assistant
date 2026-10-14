"""Unique owner-only files in the ignored private directory."""
import json
import os
from pathlib import Path
from datetime import datetime, timezone
from uuid import uuid4


def save_output(payload, markdown, prefix, directory=Path('data/private')):
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / (datetime.now(timezone.utc).strftime(prefix + '-%Y%m%dT%H%M%SZ-') + uuid4().hex[:8] + '.json')
    for target, content in [(path, json.dumps(payload, indent=2, ensure_ascii=False) + '\n'),
                            (path.with_suffix('.md'), markdown)]:
        fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            f.write(content)
    return path
