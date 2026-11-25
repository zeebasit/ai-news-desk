# Cloudflare watchdog pilot

Status: deployed to Workers Free in observation mode. The scheduled Worker logs freshness without contacting GitHub Actions.

Existing GitHub Pages, GitHub Actions collector, and analytics are unchanged.

## Deployment (Workers Free only)

1. Confirm the Cloudflare account is on Workers Free and has an available Cron Trigger. Do not enable a paid plan.
2. In GitHub, create a fine-grained personal access token limited to `zeebasit/ai-news-desk` with Actions: Read and write (Metadata read is implicit), a finite expiration date, and no additional repository permissions.
3. Deploy this directory with Wrangler from an authenticated Cloudflare environment (`npx wrangler deploy`). Alternatively create a scheduled Worker in the dashboard, using worker.mjs as its module, and configure the cron expression `*/5 * * * *`.
4. Set the token as a Worker encrypted secret named GITHUB_TOKEN (`npx wrangler secret put GITHUB_TOKEN` or the dashboard secret editor). Never commit, log, or paste the token into chat. Ensure no public HTTP route or preview URL is enabled.
5. Make the guarded workflow input available on main, then enable DISPATCH_ENABLED only after installing the encrypted secret. Observe a scheduled run with a fresh feed (no dispatch). Test the stale case in the local mocked suite (`node --test worker.test.mjs`), then confirm real recovery on a naturally stale feed. Check GitHub's workflow_dispatch run and published generated_at. Inspect logs and verify no duplicate active refreshes. Existing GitHub concurrency remains the final guard.

The watchdog checks every five minutes, dispatches only if published data is at least 50 minutes old, checks active collector and watchdog runs, and applies a 15-minute cooldown after collector attempts. It fails closed if data or workflow status cannot be read. This is independent scheduling, not independent processing; GitHub Actions must still be available. Check actual runtime against Cloudflare's free CPU limit. No paid features or AI are activated here.

Rollback: remove the Cloudflare Cron Trigger, delete the pilot Worker and revoke its dedicated GitHub token. No production changes required.

Workers AI and D1 are intentionally deferred until authenticated account inspection and an isolated source-grounded AI pilot with strict no-cost controls.
