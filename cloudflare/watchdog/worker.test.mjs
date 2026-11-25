import {test} from "node:test";
import assert from "node:assert/strict";
import {check} from "./worker.mjs";

const now=Date.parse("2026-11-25T07:00:00Z");
const env={GITHUB_TOKEN:"mock-only"};
function fixture(age,runs=[],statuses={}) {
  const calls=[];
  const request=async(url,options={})=>{
    calls.push({url,options});
    if(url.includes("news.json"))return new Response(JSON.stringify({generated_at:new Date(now-age*60000).toISOString()}),{status:statuses.feed||200});
    if(url.includes("/runs?"))return new Response(JSON.stringify({workflow_runs:runs}),{status:statuses.runs||200});
    return new Response(null,{status:statuses.dispatch||204});
  };
  return {calls,request};
}
test("fresh feed never dispatches",async()=>{const f=fixture(12);assert.equal((await check(env,now,f.request)).status,"fresh");assert.equal(f.calls.length,1)});
test("stale feed dispatches only designated workflow",async()=>{const f=fixture(60);assert.equal((await check(env,now,f.request)).status,"dispatched");assert.equal(f.calls.length,3);assert.match(f.calls[2].url,/update-news\.yml\/dispatches$/);assert.equal(f.calls[2].options.method,"POST");assert.deepEqual(JSON.parse(f.calls[2].options.body),{ref:"main"});assert.equal(f.calls[0].options.headers,undefined)});
test("active watchdog prevents duplicate dispatch",async()=>{const f=fixture(90,[{name:"News freshness watchdog",status:"in_progress"}]);assert.equal((await check(env,now,f.request)).status,"active");assert.equal(f.calls.length,2)});
test("recent failed collector imposes cooldown",async()=>{const f=fixture(90,[{name:"Update curated news",status:"completed",conclusion:"failure",created_at:new Date(now-60000).toISOString()}]);assert.equal((await check(env,now,f.request)).status,"cooldown")});
test("failed status request fails closed",async()=>{const f=fixture(90,[],{runs:403});await assert.rejects(check(env,now,f.request),/dispatch skipped/);assert.equal(f.calls.length,2)});
test("missing secret fails closed",async()=>{const f=fixture(90);await assert.rejects(check({},now,f.request),/Missing/);assert.equal(f.calls.length,0)});
test("failed dispatch not reported as success",async()=>{const f=fixture(90,[],{dispatch:403});await assert.rejects(check(env,now,f.request),/dispatch failed/)});
