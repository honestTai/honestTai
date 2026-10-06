# How these charts work

[中文](METHODOLOGY.zh-CN.md) · [All charts](README.md) · [Collector](../scripts/update_metrics.py)

## Two different views — deliberately not mixed

1. **Retained-event history** reconstructs a step chart from the original star dates of **current stargazers** and the creation dates of **currently visible forks**. It is useful immediately, but is **not historical net growth**. Unstars, deleted forks, unavailable forks and removed accounts cannot be recovered. The chart prints event coverage alongside repository totals; these may differ. Its shape can change when an old star is removed.
2. **Observed daily totals** records the actual `stargazers_count` and `forks_count` reported during each successful run. Collection begins on October 6, 2026. No earlier observations are fabricated. A single observation is a dot, not a trend. Missed days are not observations; horizontal connectors only carry the last observation forward for display. Same-day reruns replace that day's snapshot. GitHub scheduling is best effort, not real time.

The overview sums counts across **all public repositories owned by honestTai**, including forked repositories and the profile repository. These sums are **not unique people**. The issue badge counts **open issues plus pull requests**, as defined by the repository API. Charts label dates in UTC; the daily schedule is 01:23 UTC (09:23 UTC+8). Public metadata is fetched in sequential calls, not an atomic GitHub-wide snapshot.

## Scope, privacy and maintenance

- Only the public `GET /users/honestTai/repos` endpoint is used; private repositories are explicitly excluded.
- All public repositories are discovered automatically, including new, forked and archived repositories. Newly created repositories appear in the directory and metrics automatically; their README embed still needs to be added once.
- We store event timestamps and aggregate repository data, **not stargazer names, emails, tokens or private repository metadata**.
- The scheduled workflow uses its short-lived `GITHUB_TOKEN`, with write access limited to this profile repository. No personal access token or third-party stats service is needed. If GitHub denies this repository-scoped token access to a different public repository, the collector retries that public request without authentication; anonymous API rate limits apply. If those limits are reached, the run fails and the previous published assets remain intact.
- All API pages must succeed before output generation starts. Collection errors fail the workflow rather than publishing zero-filled data. Concurrent runs are serialized and pushes are never forced.
- SVGs are checked into this repository. GitHub's image cache can delay visible refreshes. Assets stay available if collection fails; check the printed date and the workflow status.
- Historical snapshots are preserved even if a repository is later renamed, deleted or made private. These snapshots only contain counts collected while it was public; current directory entries only show currently public repositories.
- GitHub may disable scheduled workflows after prolonged repository inactivity. Re-enable it in Actions if needed, or run **Refresh public portfolio** manually.

## Official API references

- [List repositories for a user](https://docs.github.com/en/rest/repos/repos#list-repositories-for-a-user)
- [List stargazers, including timestamp media type](https://docs.github.com/en/rest/activity/starring#list-stargazers)
- [List forks](https://docs.github.com/en/rest/repos/forks#list-forks)
- [Scheduled workflow behavior](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule)

For profile language switching, `README.md` is English and `README.zh-CN.md` is Chinese. GitHub README rendering does not run a JavaScript locale switcher; these are ordinary, accessible document links.
