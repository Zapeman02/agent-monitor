# Agent Monitor e2e
Needs Node >= 20, python3 and Chromium (`/usr/bin/chromium`, override with `CHROMIUM=...`).
1. `cd tests/e2e && npm install` (once; pins playwright-core 1.65.0)
2. `node tests/e2e/run.mjs` from the repo root; exits non-zero on failure, prints `ok` at the end.
3. Each scenario starts its own server (random port, temp config/projects dir, fake claude) and kills it after.
4. Screenshots land in `tests/e2e/artifacts/` (gitignored); `m2.png` = graph + chat.
5. M3 (permission card -> allow -> handback) is a placeholder in run.mjs (`scenarioM3`).
