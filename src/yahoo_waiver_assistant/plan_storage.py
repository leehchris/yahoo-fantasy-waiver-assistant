from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from .planning import render_upcoming_plan


def save_plan(plan: dict, directory: Path = Path('data/private')) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / (datetime.now(timezone.utc).strftime('upcoming-plan-%Y%m%dT%H%M%SZ-')
                        + uuid4().hex[:8] + '.json')
    contents = {path: json.dumps(plan, indent=2, ensure_ascii=False) + '\n',
                path.with_suffix('.md'): render_upcoming_plan(plan)}
    for target, content in contents.items():
        fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'w', encoding='utf-8') as output:
            output.write(content)
    return path
