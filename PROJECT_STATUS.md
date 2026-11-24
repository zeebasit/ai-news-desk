# AI News Desk — project checkpoint

Updated: 2026-11-24.

## Requirements
- Zero recurring cost; GitHub Pages (/docs on main), public RSS and Google News RSS, GitHub Actions, open-source MiniLM semantic scoring with TF-IDF fallback. No paid API.
- Keep six core sections (US/Canada, Europe/UK, Middle East, Tech, Norway, Stavanger/Rogaland) and admit consequential events globally. Retain watchlist for major imminent events.
- Rank event significance, not named countries, organisations or individuals. Use missed headlines only as regression examples, never hard-coded overrides.
- Prefer factual event reports; merge duplicate coverage and avoid redundant opinion/explainer cards. Preserve source links and headline-level metadata.

## Baseline observed on main
- Latest refresh commit at review: 3db7c276000cbf9bc4e90e6d112c8d745e8d412f.
- Primary collector schedule minute 07/37; GitHub watchdog minute 12/27/42/57, stale threshold 50 min. Both use GitHub scheduling, so they are not independent.
- Latest observed successful watchdog run 45382946368 (push, 11:18 UTC); latest primary successful run 45382287113 (push, 11:14 UTC). Scheduled recovery was not demonstrated.
- Existing regression checks cover monetary magnitudes, trusted-source consensus, coverage momentum and rewritten headline continuity.

## Coverage hardening branch
- Branch coverage-hardening-20261124: six broad RSS discovery sweeps; generic paired significance signals for strategic asset intervention, defence production agreements, frontier AI safety, first spaceflight milestones, record health/institutional trends, accidents with quantified human impact.
- Explicit analysis-only clusters are excluded; factual reports preferred as lead and analysis excluded from factual consensus. No named-entity exceptions.
- Empty collection or empty ranking of a previously populated feed fails rather than publishing a fresh empty feed.
- Added offline unit tests and read-only regression CI. These are synthetic checks, not proof of live RSS recall or semantic clustering quality.
- Validate CI before merging; inspect new feed, false positives, source quality, deduplication and actual missed headlines after deployment.

## Outstanding reliability work
- Independent external zero-cost schedule/heartbeat, not another GitHub cron. External service needs its own account/authorization or existing always-on runner. No credentials belong in repository or browser-facing code.
- A trigger must use least-privilege GitHub authorization, avoid duplicate refreshes, check generated_at freshness, and report unsuccessful refreshes. GitHub cron remains a fallback.
- Review partial collection failures, source-weight attribution, source coverage and watchlist discovery separately; avoid claiming verified production reliability until observed scheduled runs.
