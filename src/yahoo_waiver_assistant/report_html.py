"""Small escaped renderer for our report headings, tables, lists and paragraphs."""
import html
import re


def render_html(markdown: str) -> str:
    def inline(text):
        return re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', html.escape(text))

    lines = markdown.splitlines()
    body = []
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if not line:
            i += 1
            continue
        if line.startswith('|'):
            rows = []
            while i < len(lines) and lines[i].strip().startswith('|'):
                # Names escape pipe characters in the Markdown renderer.
                cells = re.split(r'(?<!\\)\|', lines[i].strip().strip('|'))
                cells = [c.strip().replace('\\|', '|') for c in cells]
                if not all(re.fullmatch(r':?-+:?', c) for c in cells):
                    tag = 'th' if not rows else 'td'
                    rows.append('<tr>' + ''.join(f'<{tag}>{inline(c)}</{tag}>' for c in cells) + '</tr>')
                i += 1
            body.append('<div class="table"><table>' + ''.join(rows) + '</table></div>')
            continue
        heading = re.match(r'^(#{1,6}) (.*)', line)
        if heading:
            level = len(heading[1])
            body.append(f'<h{level}>{inline(heading[2])}</h{level}>')
        elif line.startswith('- '):
            body.append('<p class="item">• ' + inline(line[2:]) + '</p>')
        else:
            body.append('<p>' + inline(line) + '</p>')
        i += 1
    return ('<!doctype html><html lang="en"><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            '<title>Your fantasy football update</title><style>'
            'body{margin:32px auto;max-width:1100px;padding:0 20px;background:#f5f7fa;'
            'color:#192438;font:16px/1.6 system-ui}h1{margin-top:40px;color:#164b59}'
            'h2{margin-top:30px}table{border-collapse:collapse;width:100%;background:white}'
            'th,td{padding:10px 12px;border-bottom:1px solid #dce2e9;text-align:left}'
            'th{background:#e6edf1}.table{overflow:auto;margin:20px 0}.item{margin:8px 0}'
            '</style><body>' + ''.join(body) + '</body></html>')
