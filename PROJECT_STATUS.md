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

## Coverage hardening — merged into main
- Branch coverage-hardening-20261124: six broad RSS discovery sweeps; generic paired significance signals for strategic asset intervention, defence production agreements, frontier AI safety, first spaceflight milestones, record health/institutional trends, accidents with quantified human impact.
- Explicit analysis-only clusters are excluded; factual reports preferred as lead and analysis excluded from factual consensus. No named-entity exceptions.
- Empty collection or empty ranking of a previously populated feed fails rather than publishing a fresh empty feed.
- Added offline unit tests and read-only regression CI. These are synthetic checks, not proof of live RSS recall or semantic clustering quality.
- Offline regression CI passed: https://github.com/zeebasit/ai-news-desk/actions/runs/45408176599. PR #1 merged as 8fe50fcb247a27ae303c3ee3d60b1626dec85cdd; production refresh 45408282783 triggered. Live RSS recall, false positives, source quality and deduplication still require validation.

## Outstanding reliability work
- User constraints: no ChatGPT task automation, always-on computer/VM, external cron provider, new account, tokens, or notifications. Keep zero recurring cost and refresh as frequently as available free infrastructure permits. A genuinely independent authenticated scheduler cannot be configured within these constraints using the available GitHub-only tools. Keep the existing best-effort GitHub schedules; do not describe the watchdog as independent.
- A trigger must use least-privilege GitHub authorization, avoid duplicate refreshes, check generated_at freshness, and report unsuccessful refreshes. GitHub cron remains a fallback.
- Review partial collection failures, source-weight attribution, source coverage and watchlist discovery separately; avoid claiming verified production reliability until observed scheduled runs.

## Story Context — phase 1
- Decision: no VM, no subscription-powered agent, no paid generative API. Preserve normal ChatGPT/Work allowance. GitHub timers remain best-effort; a separate always-on agent would be needed for independent scheduling.
- Add a collapsed "Understand the story" section on Major/Critical or updated stories and on any story with matched earlier reporting. Browser expansion reads static metadata, with no AI call or user-driven backend requests.
- Context enrichment runs after ranking/continuity. Retains up to 300 dated trusted reports for 30 days, displays up to six earlier matched headlines, searches up to six eligible stories per refresh, and applies a 24-hour per-ID cooldown. Matching is conservative lexical/entity evidence; context failure must not stop feed publication.
- Explicitly label dates as publication dates, related reporting as incomplete, and do not claim causal explanations from headlines. No new long-form AI-generated summaries; source links and optional focused external background search only.
- Tests cover ranking isolation, history retention, related/unrelated stories, exclusions, budget and cooldown. Verify CI before merging and inspect actual context quality on production.
- Phase 2 only if needed: consider evidence-based extractive explanations or a local model. Any future generation must be cached, protected against anonymous consumption, and must not affect professional ChatGPT usage.

## Story Context — adaptive historical discovery
- Production feedback: an anniversary recap appeared as a major story but had no background; its generated query omitted the short event noun and it had not received a dedicated search within the six-request budget. This is a general search/ranking weakness, not a named-event exception.
- Ordinary searches progress through 30/180/365/730 days if no match is found; investigation/inquiry and other ongoing legal/dispute headlines start at 180 days. Explicit elapsed-time references use a date-anchored search near the approximate original event, followed by a broader range, bounded at 20 years. These are search parameters, not asserted event dates.
- Prioritize never-searched stories, then least recently searched; retain six requests per refresh, 30-minute unsuccessful-search cooldown and 24-hour successful/exhausted-search cooldown. Migrate old check records once. Retain up to 500 reports, including current-card context, bounded at 20 years.
- Extract event nouns regardless of length; remove generic recap wording. Conservatively match by shared entities, specific terms and, where appropriate, an estimated historical window. Reject exact headline duplicates and explicit opinions. Factual background explainers can be related sources.
- Explicit retrospective recap headlines are excluded as standalone factual leads unless they describe a new action. Genuine current decisions, inquiry findings and other material developments remain eligible. This is separate from the read-only context layer.
- UI distinguishes queued versus attempted searches and widens further-reading links. No VM, AI subscription, additional service or paid API.
- Limits: Google News RSS may not return older indexed articles; matching remains heuristic and dates are publication dates. A missing match is not evidence that no background exists. Validate live source retrieval and review for incorrect associations before widening matching further.

## Story Context — production regression repair
- Live feed at 14:27 UTC showed no historical matches on any card; a previously displayed Reuters background report was still present in the archive but failed the stricter overlap threshold. The Notable cards were excluded from both the discovery queue and the UI. The anniversary recap disappeared because it was classified as an analysis-only cluster.
- Remove context eligibility dependence on ranking: every selected card has an expandable context panel and can receive historical searches. Preserve bounded/fair queue and prefer date-anchored stories among equally eligible unsearched cards.
- Normalize function words and retain specific action/domain words; strengthen evidence using multiple shared named anchors plus an action. Test the actual rewritten-headline pair from the observed regression and an unrelated report.
- Retain trusted consequential explicit anniversary recaps as separately labelled Background cards (Notable internally, score capped at 40), rather than deleting them or treating old impact as breaking news. Other analysis-only clusters remain excluded; live events retain normal scoring and cannot consolidate into background cards.
- Reset search schema once to retry improved queries. Add offline regression cases covering restored known context, Notable search eligibility, recap priority and retained Background classification. Verify deployment and inspect actual feed; no guarantee that RSS supplies the original historical coverage.

## 2026-11-25 — overnight production incident
- Last published data before repair: 2026-11-24 20:52 UTC. Scheduled collector 45544485420 and watchdog recovery 45544792379 both ran on Nov 25 but failed in ranking, not scheduling alone. Logs show ValueError: math domain error from log10(0) on zero-fatality reporting. Some Google RSS requests also returned 429, but more than 1,100 articles were collected in each failed run.
- Filter out nonpositive fatality counts before logarithmic scoring; test zero, positive following zero, and regression suite before every production refresh. Keep the last good published feed on collection failure.
- Published feed had background matches on 5/29 cards (including restored Nvidia and six Hong Kong articles); remaining cards were queued or unmatched. Raise bounded historical search budget from six to twelve, improve compact queries and alternate on widening, retain previously accepted trusted context for matching story IDs. Record match counts in collector logs. No generative AI.
- Display stale status at 60 minutes and preserve in-memory feed on load error; update freshness display each minute. Browser refresh reloads published data, not a workflow trigger.
- GitHub schedule remains best-effort: overnight runs were hours apart. Do not claim 30-minute guaranteed freshness. Verify full collector run and published JSON after repair; evaluate context relevance separately.

## 2026-11-25 — Cloudflare watchdog and Workers AI pilots
- The authenticated Cloudflare dashboard showed Workers Free as the current plan. Web Analytics opened its first-site setup screen for the selected account. No AI News Desk Web Analytics property was visible there. No Cloudflare account settings or existing projects were changed.
- Ran `node --test worker.test.mjs` against the pilot branch files. All seven mocks passed, including the fresh, stale, active, cooldown, and failure cases. The Wrangler configuration disables both workers.dev and preview URLs, and the module exposes only a scheduled handler.
- The GitHub collector uses the shared `update-news` concurrency group. This serializes collector executions but does not make the watchdog's GitHub run lookup and dispatch atomic. Two overlapping checks, or a GitHub schedule starting between lookup and dispatch, can still produce an extra queued run. Exactly-once recovery has not been demonstrated.
- Cloudflare deployment, live cron execution, encrypted token installation, and live dispatch/recovery remain pending. A dedicated fine-grained token requires Actions read/write scoped to this repository. The token belongs only in Cloudflare's encrypted Worker secret and must never appear in this repository or chat.
- Workers AI and persistent caching have not been provisioned or tested. The dashboard lists 10,000 Workers AI neurons per day on Free and a Free D1 allowance. Validate in isolation with a hard daily inference cap, bounded source and output sizes, source-linked responses, and persistent cache hits before considering any production integration.
- Follow-up: the pilot branch now passes an opt-in recovery flag. Under the collector's existing concurrency group, the recovery job checks the timestamp in the current main checkout and exits before collection if the feed is already fresh. A duplicate queued workflow entry is still possible. Regular collector triggers keep their existing path.
- Re-ran all seven Worker mocks and separately validated the recovery check against fresh, stale, and invalid future timestamps. These are local results. The guarded workflow remains on the pilot branch; the Worker must not be enabled for dispatch until GitHub accepts this input on main.
