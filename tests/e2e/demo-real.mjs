// Manual real-claude demo (costs money): node tests/e2e/demo-real.mjs <cwd> <shotdir>
import { chromium } from "playwright-core";
import { execFileSync } from "node:child_process";
const [cwd, shots] = process.argv.slice(2);
const url = execFileSync(process.env.HOME + "/.local/bin/agent-monitor", ["--print-url"]).toString().trim();
const browser = await chromium.launch({ executablePath: process.env.CHROMIUM });
const page = await (await browser.newContext({ viewport: { width: 1440, height: 900 } })).newPage();
await page.goto(url);
await page.getByTestId("new-session").click();
await page.getByTestId("cwd").fill(cwd);
await page.waitForFunction(() => !document.querySelector("[data-testid=prompt]").disabled);
await page.getByTestId("prompt").fill("/cdt:orchestration T1: Summarize README.md in one sentence. Use exactly one Explore subagent to read the file.");
await page.getByTestId("prompt").press("Enter");
let n = 0, permShot = false, agentShot = false;
for (let t = 0; t < 360; t++) {
  await page.waitForTimeout(1000);
  const card = page.getByTestId("perm-card").first();
  if (await card.count()) {
    if (!permShot) { await page.screenshot({ path: `${shots}/2-permission.png` }); permShot = true; }
    console.log("perm:", (await card.innerText()).slice(0, 200).replace(/\n/g, " "));
    if (await card.getByTestId("perm-expand").count()) await card.getByTestId("perm-expand").click();
    await card.getByTestId("perm-allow").click();
  }
  const g = await page.evaluate(() => (typeof cy !== "undefined" && cy) ? cy.nodes().map(n => n.data("kind") + ":" + (n.data("status") || "")) : []);
  if (!agentShot && g.length > 1) { await page.waitForTimeout(1500); await page.screenshot({ path: `${shots}/1-agent-running.png` }); agentShot = true; console.log("nodes", g); }
  const done = await page.locator('[data-testid=chat-msg][data-role=result]').count();
  if (done) { console.log("result after", t, "s; nodes", g); break; }
}
await page.waitForTimeout(2000);
await page.screenshot({ path: `${shots}/3-done.png` });
await page.getByRole("button", { name: "List" }).click().catch(() => {});
await page.waitForTimeout(500);
await page.screenshot({ path: `${shots}/4-list-chat.png` });
await browser.close();
