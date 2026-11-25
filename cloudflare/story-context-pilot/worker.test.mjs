import { test } from "node:test";
import assert from "node:assert/strict";
import { DatabaseSync } from "node:sqlite";
import { storyContext } from "./worker.mjs";

function environment(response) {
  const db = new DatabaseSync(":memory:");
  let calls = 0;
  function prepare(sql, args = []) {
    return {
      bind: (...bound) => prepare(sql, bound),
      first: async () => db.prepare(sql).get(...args),
      run: async () => ({ meta: db.prepare(sql).run(...args) }),
    };
  }
  return {
    env: {
      STORY_CACHE: { prepare },
      AI: {
        async run(_model, input) {
          assert.equal(input.max_tokens, 12);
          calls += 1;
          return { response };
        },
      },
    },
    calls: () => calls,
    close: () => db.close(),
  };
}

test("one concurrent request generates and subsequent requests reuse the result", async (t) => {
  const fixture = environment("2");
  t.after(fixture.close);
  const results = await Promise.all([storyContext(fixture.env), storyContext(fixture.env)]);
  assert.deepEqual(results.map(({ status }) => status).sort(), ["generated", "limit"]);
  const cached = await storyContext(fixture.env);
  assert.equal(cached.status, "hit");
  assert.deepEqual(cached.context, results.find(({ status }) => status === "generated").context);
  assert.equal(fixture.calls(), 1);
});

test("an invalid selection cannot be cached or retried", async (t) => {
  const fixture = environment("9");
  t.after(fixture.close);
  assert.equal((await storyContext(fixture.env)).status, "invalid-selection");
  assert.equal((await storyContext(fixture.env)).status, "limit");
  assert.equal(fixture.calls(), 1);
});
