// Scheduled-only watchdog. No inbound HTTP trigger and no credentials in source.
const API = "https://api.github.com/repos/zeebasit/ai-news-desk/actions";
const FEED = "https://zeebasit.github.io/ai-news-desk/data/news.json";
const ACTIVE = new Set(["queued","in_progress","waiting","requested","pending"]);
const RELEVANT = new Set(["Update curated news","News freshness watchdog"]);
const MIN = 60_000;

export async function check(env, now = Date.now(), request = fetch) {
  const dispatchEnabled = env.DISPATCH_ENABLED === "true";
  if (dispatchEnabled && !env.GITHUB_TOKEN) throw new Error("Missing encrypted GITHUB_TOKEN");
  const feedResponse = await request(FEED+"?watchdog="+now, {cache:"no-store"});
  if (!feedResponse.ok) throw new Error("Published feed unavailable; dispatch skipped");
  const feed = await feedResponse.json();
  const published = Date.parse(feed.generated_at);
  if (!Number.isFinite(published) || published>now+5*MIN) throw new Error("Invalid feed timestamp; dispatch skipped");
  const age = (now-published)/MIN;
  if (age<50) return {status:"fresh",age};
  if (!dispatchEnabled) return {status:"stale-observed",age};
  const headers = {"Authorization":"Bearer "+env.GITHUB_TOKEN,"Accept":"application/vnd.github+json","User-Agent":"ai-news-desk-watchdog","X-GitHub-Api-Version":"2022-11-28"};
  const runsResponse=await request(API+"/runs?branch=main&per_page=30",{headers});
  if (!runsResponse.ok) throw new Error("Cannot inspect GitHub runs; dispatch skipped");
  const runs=await runsResponse.json();
  if (!Array.isArray(runs.workflow_runs)) throw new Error("Invalid workflow response; dispatch skipped");
  const relevant=runs.workflow_runs.filter(r=>RELEVANT.has(r.name));
  if (relevant.some(r=>ACTIVE.has(r.status))) return {status:"active",age};
  // Back off after recent collector attempts, including failed runs, to prevent retry storms.
  if (relevant.some(r=>r.name==="Update curated news" && now-Date.parse(r.created_at)<15*MIN)) return {status:"cooldown",age};
  const dispatch=await request(API+"/workflows/update-news.yml/dispatches",{
    method:"POST",headers:{...headers,"Content-Type":"application/json"},
    body:JSON.stringify({ref:"main",inputs:{watchdog_recovery:true}})
  });
  if (!dispatch.ok) throw new Error("GitHub workflow dispatch failed: "+dispatch.status);
  return {status:"dispatched",age};
}

export default {
  async scheduled(controller, env) {
    const result=await check(env);
    console.log(JSON.stringify(result));
  }
};
