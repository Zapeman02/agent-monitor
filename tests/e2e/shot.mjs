// Manual screenshot of the installed app's default view: node tests/e2e/shot.mjs <out.png> [w] [h]
import { chromium } from "playwright-core";
import { execFileSync } from "node:child_process";
const [out, w = 1440, h = 900] = process.argv.slice(2);
const url = execFileSync(process.env.HOME + "/.local/bin/agent-monitor", ["--print-url"]).toString().trim();
const b = await chromium.launch({ executablePath: "/usr/bin/chromium" });
const p = await (await b.newContext({ viewport: { width: +w, height: +h } })).newPage();
await p.goto(url); await p.waitForTimeout(3500);
if (process.env.CLICK) { await p.click(process.env.CLICK); await p.waitForTimeout(800); }
if (process.env.TAP) { await p.evaluate(id => cy.getElementById(id).emit("tap"), process.env.TAP); await p.waitForTimeout(800); }
await p.screenshot({ path: out }); await b.close();
