/**
 * Capture README screenshots of the redesigned app against the demo backend.
 * Drives the local Vite dev server (5173) with system Chrome via puppeteer-core.
 */
import puppeteer from "puppeteer-core";
import { mkdirSync } from "node:fs";

const OUT = "/Users/yameen/Documents/Projects/Verdict/docs/assets";
const APP = "http://localhost:5173";
const EMAIL = "analyst@verdict.app";
const PASSWORD = "green-verdict-screenshots-1";

mkdirSync(OUT, { recursive: true });

const browser = await puppeteer.launch({
  executablePath: "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
  headless: "new",
  args: ["--no-first-run", "--window-size=1560,1000"],
});

const page = await browser.newPage();
await page.setViewport({ width: 1560, height: 1000, deviceScaleFactor: 2 });
page.setDefaultTimeout(45_000);

const log = (msg) => console.log(`[shot] ${msg}`);

async function clickByText(selector, text) {
  const handles = await page.$$(selector);
  for (const handle of handles) {
    const label = (await handle.evaluate((el) => el.textContent || "")).trim();
    if (label.toLowerCase().includes(text.toLowerCase())) {
      await handle.click();
      return true;
    }
  }
  return false;
}

// --- login ---
await page.goto(APP, { waitUntil: "networkidle2" });
await page.waitForSelector('input[type="email"]');
await page.type('input[type="email"]', EMAIL);
await page.type('input[type="password"]', PASSWORD);
await page.keyboard.press("Enter");
await page.waitForSelector("nav", { timeout: 30_000 });
log("logged in");

// --- let the chart + panels load real data ---
await page.waitForFunction(
  () => document.body.innerText.toLowerCase().includes("range high"),
  { timeout: 60_000 },
);
await new Promise((r) => setTimeout(r, 2500));
log("chart loaded");

// --- run the timing agent so decision lines + panels populate ---
if (await clickByText("button", "Should I buy")) {
  await page
    .waitForFunction(
      () => document.body.innerText.toLowerCase().includes("confidence"),
      { timeout: 90_000 },
    )
    .catch(() => log("timing did not finish; continuing"));
  await new Promise((r) => setTimeout(r, 1500));
  log("timing done");
}

// --- full research run (uses the configured LLM key) ---
const analyzeClicked = await clickByText("button", "Analyze");
if (analyzeClicked) {
  log("analyze started");
  await page
    .waitForFunction(
      () => document.body.innerText.toLowerCase().includes("company overview"),
      { timeout: 240_000, polling: 2_000 },
    )
    .catch(() => log("analyze did not finish; continuing without a report"));
  await new Promise((r) => setTimeout(r, 3_000));
  log("analyze finished (or timed out)");
}

// --- shot 1: dashboard top (nav + picker + chart header) ---
await page.evaluate(() => window.scrollTo(0, 0));
await new Promise((r) => setTimeout(r, 800));
await page.screenshot({
  path: `${OUT}/verdict-live-dashboard.png`,
  clip: { x: 0, y: 0, width: 1560, height: 980 },
});
log("dashboard captured");

// --- shot 2: the chart panel alone ---
const chartSection = await page.$("section.overflow-hidden.rounded-lg");
if (chartSection) {
  await chartSection.scrollIntoView();
  await new Promise((r) => setTimeout(r, 800));
  await chartSection.screenshot({ path: `${OUT}/verdict-live-chart.png` });
  log("chart captured");
}

// --- shot 3: planning panels (position tracker + return ranges + alerts) ---
const planning = await page.evaluateHandle(() => {
  const headings = [...document.querySelectorAll("h3")];
  const anchor = headings.find((h) => h.textContent?.includes("Position tracker"));
  return anchor?.closest("div.grid")?.parentElement ?? null;
});
const planningEl = planning.asElement();
if (planningEl) {
  await planningEl.scrollIntoView();
  await new Promise((r) => setTimeout(r, 800));
  const grid = await page.evaluateHandle(() => {
    const headings = [...document.querySelectorAll("h3")];
    const anchor = headings.find((h) => h.textContent?.includes("Position tracker"));
    return anchor?.closest("div.grid") ?? null;
  });
  const gridEl = grid.asElement();
  if (gridEl) {
    await gridEl.screenshot({ path: `${OUT}/verdict-live-planning-panels.png` });
    log("planning panels captured");
  }
}

// --- shot 4: scoreboard tab ---
await clickByText("nav button", "scoreboard");
await new Promise((r) => setTimeout(r, 3_500));
await page.evaluate(() => window.scrollTo(0, 0));
await page.screenshot({
  path: `${OUT}/verdict-live-scoreboard.png`,
  clip: { x: 0, y: 0, width: 1560, height: 900 },
});
log("scoreboard captured");

await browser.close();
log("all done");
