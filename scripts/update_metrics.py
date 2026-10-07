#!/usr/bin/env python3
"""Public-only GitHub portfolio metrics. Python standard library; no PAT required in CI."""
from __future__ import annotations
import collections
import datetime as dt
import html
import json
import math
import os
from pathlib import Path
import re
import time
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
OWNER = 'honestTai'
API = 'https://api.github.com'
FONT = 'system-ui,-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif'


def get(path, accept='application/vnd.github+json'):
    headers = {'Accept': accept, 'X-GitHub-Api-Version': '2022-11-28', 'User-Agent': 'honestTai-public-portfolio'}
    if os.environ.get('GH_TOKEN'):
        headers['Authorization'] = 'Bearer ' + os.environ['GH_TOKEN']
    for attempt in range(4):
        try:
            with urllib.request.urlopen(urllib.request.Request(API + path, headers=headers), timeout=40) as response:
                return json.load(response)
        except urllib.error.HTTPError as exc:
            # Installation-scoped Actions tokens can be denied access to other public
            # repositories. Retry only the same public endpoint without credentials.
            if exc.code in (403, 404) and 'Authorization' in headers and exc.headers.get('X-RateLimit-Remaining') != '0':
                del headers['Authorization']
                continue
            if exc.code not in (429, 500, 502, 503, 504) or attempt == 3:
                raise
            time.sleep(2 ** attempt * 2)
        except (TimeoutError, urllib.error.URLError):
            if attempt == 3:
                raise
            time.sleep(2 ** attempt * 2)
    raise RuntimeError('unreachable')


def pages(path):
    result = []
    for page in range(1, 10001):
        sep = '&' if '?' in path else '?'
        data = get(f'{path}{sep}per_page=100&page={page}')
        if not isinstance(data, list):
            raise ValueError('Expected a GitHub list response')
        result.extend(data)
        if len(data) < 100:
            return result
    raise RuntimeError('Pagination limit reached; refusing partial metrics')


def write(path, text):
    path = ROOT / path
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(text, encoding='utf-8')
    tmp.replace(path)


def json_text(value):
    return json.dumps(value, indent=2, ensure_ascii=False) + '\n'


def esc(value):
    return html.escape(str(value), quote=True)


def text(x, y, value, size=14, color='#9aabc2', weight=400, extra=''):
    return f'<text x="{x}" y="{y}" font-size="{size}" fill="{color}" font-weight="{weight}" {extra}>{esc(value)}</text>'


def svg(body, title, height=350):
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="960" height="{height}" viewBox="0 0 960 {height}" role="img" aria-labelledby="title desc">
<title id="title">{esc(title)}</title><desc id="desc">Public GitHub API data. See the linked methodology for coverage and timing.</desc>
<rect x="1" y="1" width="958" height="{height-2}" rx="20" fill="#0B1A13" stroke="#24402F"/>
<g font-family="{FONT}">{body}</g></svg>\n'''


def retained_series(events, start, end):
    counts = collections.Counter(event[:10] for event in events)
    total = 0
    values = [(start, 0)]
    for day, count in sorted(counts.items()):
        total += count
        values.append((day, total))
    if values[-1][0] != end:
        values.append((end, total))
    return values


def panel(series, x, title, color, end, empty_label=None):
    left, top, width, height = x + 34, 156, 366, 100
    out = text(x, 128, title, 14, '#dce6f5', 600)
    if not series:
        return out + text(x + 20, 214, empty_label or 'No public events returned', 13)
    begin = dt.date.fromisoformat(series[0][0])
    finish = dt.date.fromisoformat(end)
    span = max(1, (finish - begin).days)
    maximum = max(1, max(value for _, value in series))
    for value in sorted({round(maximum * n / 2) for n in range(3)}):
        yy = top + height - height * value / maximum
        out += f'<path d="M{left} {yy}H{left+width}" stroke="#1C3527" stroke-dasharray="3 5"/>'
        out += text(left-10, yy+4, value, 11, extra='text-anchor="end"')
    points = [(left + width * (dt.date.fromisoformat(day) - begin).days / span, top + height - height * value / maximum) for day, value in series]
    if len(set(day for day, _ in series)) >= 2:
        line = f'M{points[0][0]:.1f},{points[0][1]:.1f}'
        for px, py in points[1:]:
            line += f'H{px:.1f}V{py:.1f}'
        area = line + f'L{points[-1][0]:.1f},{top+height}H{points[0][0]:.1f}Z'
        out += f'<path d="{area}" fill="{color}" fill-opacity=".09"/><path d="{line}" stroke="{color}" stroke-width="2.5" fill="none"/>'
    else:
        out += text(left+24, top+38, 'First snapshot saved.', 14)
        out += text(left+24, top+58, 'A trend needs another day.', 12)
    px, py = points[-1]
    out += f'<circle cx="{px:.1f}" cy="{py:.1f}" r="4" fill="{color}"/>'
    out += text(left, 280, series[0][0], 11)
    out += text(left+width, 280, end, 11, extra='text-anchor="end"')
    return out


def chart(repo, daily, now, retained=True):
    name, stars, forks = repo['name'], repo['stars'], repo['forks']
    end = now[:10]
    body = text(28, 34, name, 19, '#f0f5ff', 650)
    body += text(28, 66, f'{stars} STARS', 17, '#A8FF57', 650)
    body += text(190, 66, f'{forks} FORKS', 17, '#45DCC3', 650)
    body += text(348, 66, f"{repo['open_issues_and_prs']} OPEN ISSUES + PRs", 12)
    body += text(930, 32, f'UTC {end}', 11, extra='text-anchor="end"')
    body += f'<path d="M28 88H932M479 110V287" stroke="#24402F"/>'
    if retained:
        star_asof = repo.get('star_history_observed_at', now)
        fork_asof = repo.get('fork_history_observed_at', now)
        star_end = star_asof[:10] if star_asof else end
        fork_end = fork_asof[:10] if fork_asof else end
        st = retained_series(repo['star_dates'], repo['created_at'][:10], star_end) if star_asof else []
        ft = retained_series(repo['fork_dates'], repo['created_at'][:10], fork_end) if fork_asof else []
        body += panel(st, 28, 'Retained stars · by original star date', '#A8FF57', star_end, 'Event history unavailable')
        body += panel(ft, 508, 'Visible forks · by creation date', '#45DCC3', fork_end, 'Event history unavailable')
        body += text(28, 315, f"Event snapshots: stars {(star_asof or 'unavailable')[:10]} · forks {(fork_asof or 'unavailable')[:10]}. Not historical net totals.", 12)
        body += text(28, 337, f"Coverage: {len(repo['star_dates'])}/{stars} stars · {len(repo['fork_dates'])}/{forks} forks. Deleted / unstarred events unavailable.", 11)
    else:
        st = [(row['date'], row['repos'][name]['stars']) for row in daily if name in row['repos']]
        ft = [(row['date'], row['repos'][name]['forks']) for row in daily if name in row['repos']]
        body += panel(st, 28, 'Observed star totals · daily snapshots', '#A8FF57', end)
        body += panel(ft, 508, 'Observed fork totals · daily snapshots', '#45DCC3', end)
        body += text(28, 321, 'Actual observed totals. No backfill. Missing collection days are not observations.', 12)
    return svg(body, f'{name}: Star and Fork {"retained-event history" if retained else "daily observations"}')


def upsert_daily(history, repos, now):
    row = {'date': now[:10], 'observed_at': now, 'repos': {r['name']: {'stars': r['stars'], 'forks': r['forks']} for r in repos}}
    return sorted([r for r in history if r['date'] != row['date']] + [row], key=lambda r: r['date'])


def update_directory(path, repos, featured, zh=False):
    source = (ROOT / path).read_text()
    rows = []
    for r in sorted(repos, key=lambda r: (r['is_fork'], -r['stars'], r['name'].lower())):
        config = featured.get(r['name'], {})
        description = config.get('zh' if zh else 'en') or r['description'] or ('公开仓库' if zh else 'Public repository')
        description = description.replace('|', '\\|').replace('\n', ' ')
        kind = ('Fork · 上游衍生' if zh else 'Fork') if r['is_fork'] else ('个人主页' if r['name'] == OWNER and zh else 'Profile' if r['name'] == OWNER else '项目' if zh else 'Project')
        if r['archived']:
            kind += ' · Archived'
        link = f'https://github.com/{OWNER}/{r["name"]}'
        rows.append(f'| [**{r["name"]}**]({link}) | {description} | {kind} | {r["stars"]} | {r["forks"]} | [↗]({link}#project-activity) |')
    header = '| 仓库 | 简介 | 类型 | Stars | Forks | 趋势 |' if zh else '| Repository | What it does | Type | Stars | Forks | Trends |'
    table = header + '\n| :--- | :--- | :--- | ---: | ---: | :---: |\n' + '\n'.join(rows)
    pattern = r'<!-- PUBLIC-REPOS:START -->.*?<!-- PUBLIC-REPOS:END -->'
    replacement = '<!-- PUBLIC-REPOS:START -->\n\n' + table + '\n\n<!-- PUBLIC-REPOS:END -->'
    if len(re.findall(pattern, source, flags=re.S)) != 1:
        raise ValueError(f'{path}: expected exactly one public repository block')
    write(path, re.sub(pattern, lambda _: replacement, source, flags=re.S))


def event_history(fetch, cached, observed_at, now):
    """Optional event history may need broader access than public aggregate counts.

    Never transfer a personal token into CI to work around installation scope.
    Preserve dated evidence on explicit auth denials, not transient or rate errors.
    """
    try:
        return fetch(), now
    except urllib.error.HTTPError as exc:
        if exc.code not in (401, 403) or exc.headers.get('X-RateLimit-Remaining') == '0':
            raise
        print(f'Event-history HTTP {exc.code}: preserving dated snapshot {observed_at or "unavailable"}; current totals still collected.')
        return cached, observed_at


def main():
    now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')
    config = json.loads((ROOT / 'data/projects.json').read_text())
    # Public user endpoint, not /user/repos. Explicit visibility and owner checks.
    raw = pages(f'/users/{OWNER}/repos?type=owner&sort=full_name')
    public = [r for r in raw if not r['private'] and r['owner']['login'].lower() == OWNER.lower() and r.get('visibility', 'public') == 'public']
    if not public:
        raise ValueError('Empty public repository response; refusing to erase the portfolio')
    latest_path = ROOT / 'data/latest.json'
    previous = json.loads(latest_path.read_text()) if latest_path.exists() else {'repos': []}
    previous_repos = {r['name']: r for r in previous['repos']}
    repos = []
    for r in public:
        old = previous_repos.get(r['name'], {})
        star_dates, star_asof = event_history(
            lambda: sorted(s['starred_at'] for s in star_pages(f'/repos/{OWNER}/{r["name"]}/stargazers')),
            old.get('star_dates', []), old.get('star_history_observed_at', previous.get('observed_at') if old else None), now)
        fork_dates, fork_asof = event_history(
            lambda: sorted(f['created_at'] for f in pages(f'/repos/{OWNER}/{r["name"]}/forks') if not f.get('private', False)),
            old.get('fork_dates', []), old.get('fork_history_observed_at', previous.get('observed_at') if old else None), now)
        repos.append({'name': r['name'], 'description': r['description'], 'is_fork': r['fork'], 'archived': r['archived'], 'created_at': r['created_at'], 'stars': r['stargazers_count'], 'forks': r['forks_count'], 'open_issues_and_prs': r['open_issues_count'], 'language': r['language'], 'pushed_at': r['pushed_at'], 'star_dates': star_dates, 'fork_dates': fork_dates, 'star_history_observed_at': star_asof, 'fork_history_observed_at': fork_asof})
    # Current repository collection must succeed. Optional event auth denials retain dated evidence.
    # No user IDs or credentials are stored.
    history_path = ROOT / 'data/daily.json'
    history = json.loads(history_path.read_text()) if history_path.exists() else []
    history = upsert_daily(history, repos, now)
    for r in repos:
        write(f'assets/metrics/{r["name"]}.svg', chart(r, history, now))
        write(f'assets/metrics/{r["name"]}-daily.svg', chart(r, history, now, False))
        badge = text(28, 37, 'PUBLIC FORK' if r['is_fork'] else 'PUBLIC PROJECT', 12, '#45DCC3', 600)
        badge += text(215, 37, f"★ {r['stars']} stars", 15, '#A8FF57', 600)
        badge += text(370, 37, f"⑂ {r['forks']} forks", 15, '#9BE8D6', 600)
        badge += text(530, 37, r['language'] or 'Documentation', 13, '#dce6f5')
        badge += text(740, 37, 'Pushed ' + r['pushed_at'][:10], 12)
        write(f'assets/badges/{r["name"]}.svg', svg(badge, f'{r["name"]} public repository summary', 64))
    body = text(32, 34, 'THE PUBLIC WORKBENCH', 12, '#A8FF57', 600)
    values = [(len(repos), 'PUBLIC REPOSITORIES'), (sum(r['stars'] for r in repos), 'STARS ACROSS REPOS'), (sum(r['forks'] for r in repos), 'FORKS ACROSS REPOS')]
    for i, (number, label) in enumerate(values):
        x = 32 + i*312
        body += text(x, 93, number, 44, '#f0f5ff', 700) + text(x, 122, label, 11)
    body += text(32, 157, f'Public repositories only · Includes forked repositories · Updated {now[:10]} UTC', 11)
    write('assets/overview.svg', svg(body, 'Public repository overview', 180))
    for name, zh in [('README.md', False), ('README.zh-CN.md', True)]:
        update_directory(name, repos, config, zh)
    index = '# Public repository metrics\n\n[Portfolio](../README.md) · [中文说明](METHODOLOGY.zh-CN.md) · [Methodology](METHODOLOGY.md)\n\n'
    index += f'Observed at **{now}**. All {len(repos)} public repositories, including forks.\n\n'
    for r in repos:
        name = r['name']
        index += f'## {name}\n\n[Repository](https://github.com/{OWNER}/{name})\n\n![Retained-event history](../assets/metrics/{name}.svg)\n\n![Observed daily totals](../assets/metrics/{name}-daily.svg)\n\n'
    write('data/README.md', index)
    write('data/latest.json', json_text({'observed_at': now, 'source': API, 'repos': repos}))
    write('data/daily.json', json_text(history))
    print(f'Updated {len(repos)} public repositories at {now}; {len(history)} daily snapshots.')


def star_pages(path):
    result = []
    for page in range(1, 10001):
        data = get(f'{path}?per_page=100&page={page}', accept='application/vnd.github.star+json')
        if not isinstance(data, list) or any('starred_at' not in s for s in data):
            raise ValueError('Stargazer timestamps unavailable; refusing invented history')
        result.extend(data)
        if len(data) < 100:
            return result
    raise RuntimeError('Stargazer pagination limit reached')


if __name__ == '__main__':
    main()
