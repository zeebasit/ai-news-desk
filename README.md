# AI News Desk

A zero-recurring-cost, mobile-friendly news dashboard that filters, ranks and deduplicates major news instead of dumping every article into a feed.

## Architecture
- GitHub Pages hosting
- GitHub Actions every 30 minutes
- Public RSS + Google News RSS discovery
- Trusted-source weighting
- Global disaster / protest / election / cyber / conflict / health / economy sweeps
- Open-source `all-MiniLM-L6-v2` semantic embeddings running inside GitHub Actions
- TF-IDF fallback if the semantic model cannot load
- Static JSON data file, no database
- No paid AI API

## Filtering philosophy
Importance determines inclusion, not geography. Core sections remain US/Canada, Europe/UK, Middle East, Tech, Norway, and Stavanger/Rogaland, but major events from any country can enter the feed.

The ranking engine is event-evidence based rather than entity-whitelist based. No named company, country, politician or individual is required for an event to qualify.

Each clustered event is evaluated using a combination of:
- semantic similarity to broad high-impact event archetypes
- independent trusted-source consensus
- rapid cross-source coverage / coverage velocity
- quantified human impact such as deaths, displacement or evacuations
- quantified financial impact such as unusually large market moves or transactions
- political, military, legal, infrastructure, health, cyber and supply-chain consequences
- Norway and Stavanger/Rogaland relevance
- noise and explainer penalties

A missed story should lead to a better general significance signal, not a special rule for that story or named entity.

## Duplicate handling
Articles are converted into semantic embeddings. Reports describing the same event are clustered and shown as one story card with multiple source links.

## Paywalled reporting
Only headline-level metadata and source links are used. The project does not copy full paywalled articles. Bloomberg and Financial Times links are marked with a lock when detected.

## GitHub Pages
Publish from:
- Branch: `main`
- Folder: `/docs`

The site URL will normally be:
`https://zeebasit.github.io/ai-news-desk/`

## Updating
The workflow runs at minute 07 and 37 of every hour. A manual `workflow_dispatch` trigger is also enabled.

## Cost
The project does not call OpenAI, Anthropic, Gemini, or another paid LLM/API. Semantic filtering runs on the GitHub Actions runner.

## Current phase
Phase 1 focuses on:
1. reliable collection
2. global event discovery
3. deduplication
4. significance ranking
5. mobile-friendly presentation

After 24–48 hours of real-world results, the ranking thresholds and source mix should be tuned using actual misses and false positives.
