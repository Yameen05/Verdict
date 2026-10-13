/** Production UI regression fixtures. All API requests terminate at this server.
 * Run after npm run build: node scripts/research-fixtures.mjs
 * Screenshots go outside the product repository, under /tmp by default.
 */
import assert from "node:assert/strict";
import { createServer } from "node:http";
import { readFileSync, existsSync, mkdirSync } from "node:fs";
import { resolve, dirname, extname } from "node:path";
import { fileURLToPath } from "node:url";
import puppeteer from "puppeteer-core";
const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const dist = resolve(root,"dist");
const result = JSON.parse(readFileSync(resolve(root,"scripts/fixtures/research.json"),"utf8"));
const issued = new Date().toISOString();
const entry = (id, outcome, model, days=7) => ({
  id, ticker:"NVDA", outcome, model, prediction_kind:outcome === "failed" ? "none" : "ai", analysis_status:outcome === "failed" ? "failed" : "complete", analysis_warning:null, tracking_eligible:outcome !== "failed", recommendation:outcome === "failed" ? "Failed" : "Sell",
  confidence:outcome === "failed" ? null : 75, horizon_days:days, horizon_assumed:false,
  created_at:issued, due_at:new Date(Date.parse(issued)+days*86400000).toISOString(),
  price_at_run:226.32,price_at_horizon:null,return_pct:null,evaluated_at:null,price_bar_at:null,
  status_reason:outcome === "failed" ? "Failed to assess. Filing review failed: service authentication or configuration failed. Excluded from prediction scores." : "The selected holding period has not ended.",
});
const scoreboard = {
  entries:[entry(101,"hit","gemini-2.5-flash"),entry(102,"in_progress","gemini-2.5-flash"),entry(103,"in_progress","gemini-3.8-flash",30),entry(104,"failed","gemini-2.5-flash"),entry(105,"unscored","gemini-2.5-flash"),entry(106,"in_progress","gemini-2.0-flash")],
  summary:{total_runs:6,scored:1,hits:1,in_progress:3,awaiting_price:0,unscored:1,failed:1,hit_rate:1,avg_return_buy_pct:null,rule:"Fixture grading rule."},
  server_time:issued,
};
scoreboard.entries.find(e=>e.id===102).prediction_kind="partial_ai";
scoreboard.entries.find(e=>e.id===102).analysis_status="incomplete";
scoreboard.entries.find(e=>e.id===102).confidence=null;
scoreboard.entries.find(e=>e.id===102).analysis_warning="Filing review failed: per-minute quota. Original prediction remains tracked.";
scoreboard.entries.find(e=>e.id===106).prediction_kind="rules_based";
scoreboard.entries.find(e=>e.id===106).analysis_status="incomplete";
scoreboard.entries.find(e=>e.id===106).confidence=null;
scoreboard.entries.find(e=>e.id===106).recommendation="Buy";
scoreboard.entries.find(e=>e.id===106).analysis_warning="AI review failed. This was an explicitly issued rules-based prediction.";
const out = process.env.FIXTURE_SCREENSHOTS ?? "/tmp/verdict-research-fixtures";
mkdirSync(out,{recursive:true});
let failure = null;
let askFailure = null;
let streams = [];
const apiRequests = [];
const server = createServer((req,res) => {
  const path = new URL(req.url,"http://fixture").pathname;
  if (path.startsWith("/api/")) {
    apiRequests.push(path);
    res.setHeader("Content-Type","application/json");
    if (/\/research\/.+\/stream$/.test(path)) {
      if (failure) {res.writeHead(failure.status);res.end(JSON.stringify({detail:failure.detail}));return;}
      res.writeHead(200,{"Content-Type":"text/event-stream","Cache-Control":"no-cache"});
      res.write('event: started\ndata: {"ticker":"AAPL","request_id":"fixture"}\n\n');
      streams.push(res);req.on("close",()=>{streams=streams.filter(s=>s!==res)});return;
    }
    if (path === "/api/research/ask") {res.writeHead(askFailure?.status ?? 200);res.end(JSON.stringify(askFailure ? {detail:askFailure.detail} : {answer:"Fixture answer",cost_usd:0,request_id:"fixture"}));return;}
    let body;
    if (path === "/api/auth/me") body={user:{id:1,email:"fixture@example.test",role:"owner"},csrf_token:"fixture"};
    else if (path === "/api/health/ready") body={status:"ready",checks:{}};
    else if (path === "/api/health/config") body={environment:"fixture",llm:{provider:"Google",model:"gemini-3.8-flash",configured:true,rate_limit:"5 RPM"},embeddings:{model:"gemini-embedding-001",configured:true},sources:{newsapi:false,vectorstore:"fixture",signals:{},signals_cache_seconds:300},quotas:{research_cache_minutes:360,daily_runs_per_user:100,daily_runs_global:100}};
    else if (path.includes("/capabilities")) body={ticker:"AAPL",asset_type:"stock",has_earnings:true,has_sec_filings:true,has_insider_data:true};
    else if (path === "/api/research/scoreboard") body=scoreboard;
    else if (path.startsWith("/api/research/scoreboard/")) {
      const saved = scoreboard.entries.find(e=>String(e.id)===path.split("/").at(-1));
      body={entry:saved,justification:"Fixture original analysis",duration_ms:1000,cost_usd:0,request_id:"fixture",result:null,payload:{},rule:scoreboard.summary.rule};
    }
    else if (path.includes("/research/history/")) body={ticker:"AAPL",runs:[]};
    else if (path.includes("watchlist")) body={tickers:[]};
    else if (path.includes("positions")) body={position:null};
    else if (path.includes("alerts")) body={alerts:[]};
    else if (path.includes("levels")) body={prices:[]};
    else if (path.includes("verdict")) body={recommendation:null};
    else {res.writeHead(404);body={detail:"Fixture endpoint unavailable"};}
    res.end(JSON.stringify(body));return;
  }
  const target = resolve(dist,`.${path === "/" ? "/index.html" : path}`);
  if (!target.startsWith(dist+"/") || !existsSync(target)) {res.writeHead(404);res.end();return;}
  const types={".html":"text/html",".js":"text/javascript",".css":"text/css",".svg":"image/svg+xml"};
  res.setHeader("Content-Type",types[extname(target)]??"application/octet-stream");res.end(readFileSync(target));
});
await new Promise(resolve=>server.listen(0,"127.0.0.1",resolve));
const url = `http://127.0.0.1:${server.address().port}`;
const browser = await puppeteer.launch({executablePath:process.env.CHROME_PATH ?? "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",headless:true,args:["--no-first-run"]});
const page = await browser.newPage();
page.setDefaultTimeout(10_000);
const errors=[];const blocked=[];
page.on("pageerror",e=>errors.push(String(e)));
await page.setRequestInterception(true);
page.on("request",req=>{
  if(req.url().startsWith(url) || req.url().startsWith("data:")) req.continue();
  else {blocked.push(req.url());req.abort();}
});
const click = async text => {
  const buttons=await page.$$("button");
  for(const button of buttons) if(await button.boundingBox() && await button.evaluate((el,t)=>el.textContent.trim()===t,text)){await button.click();return;}
  throw new Error(`No button ${text}`);
};
const percent = async n => page.waitForFunction(n=>document.querySelector('[role="progressbar"]')?.getAttribute("aria-valuenow")===String(n),{},n);
const text = () => page.evaluate(()=>document.body.innerText);
const emit = (event,data) => {assert.equal(streams.length,1);streams[0].write(`event: ${event}\ndata: ${JSON.stringify(data)}\n\n`);};
const finish = (payload=result,cached=false) => {
  const stream=streams[0];emit("completed",{result:payload,cached,request_id:"fixture",duration_ms:1000,cost:{total_usd:0},persisted_id:1});stream.end();
};
try {
  await page.setViewport({width:1440,height:1000});
  await page.goto(url,{waitUntil:"networkidle0"});
  // Tailwind utilities must resolve the app palette in both themes.
  const themeColors = await page.evaluate(() => {
    const shell = document.querySelector("aside").parentElement;
    const colors = () => {
      const style = getComputedStyle(shell);
      return [style.backgroundColor, style.color];
    };
    const dark = colors();
    document.documentElement.dataset.theme = "light";
    const light = colors();
    document.documentElement.dataset.theme = "dark";
    return {dark, light};
  });
  assert.deepEqual(themeColors.dark, ["rgb(15, 13, 11)", "rgb(237, 232, 223)"]);
  assert.deepEqual(themeColors.light, ["rgb(248, 245, 238)", "rgb(50, 43, 33)"]);
  await click("Analyze");await percent(0);
  emit("progress",{kind:"provider_wait",id:"queue1",reason:"queue",phase:"started"});
  await page.waitForFunction(()=>document.body.innerText.includes("queued for the next AI request slot"));
  emit("progress",{kind:"filing_question",index:2});await percent(10);
  emit("node_completed",{node:"metrics_agent",payload:{metrics:{status:"ok"}}});await percent(20);
  emit("progress",{kind:"filing_question",index:2});await percent(20);
  emit("progress",{kind:"provider_wait",id:"capacity1",reason:"capacity",phase:"started"});
  await page.waitForFunction(()=>document.body.innerText.includes("Google is busy"));
  await page.screenshot({path:resolve(out,"desktop-wait.png"),fullPage:true});
  await page.setViewport({width:390,height:844});
  await page.screenshot({path:resolve(out,"mobile-wait.png"),fullPage:true});
  assert(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth),"mobile overflow");
  await click("Cancel");await percent(20);
  await click("Analyze");await percent(0);
  finish();await percent(100);
  await page.waitForSelector('[aria-label="Confidence 50 out of 100"]');
  await page.screenshot({path:resolve(out,"complete.png"),fullPage:true});
  await click("Analyze");await percent(0);
  const legacy=structuredClone(result);legacy.report.degraded=true;legacy.report.recommendation="Hold";legacy.report.confidence=50;
  legacy.sec={...legacy.sec,status:"error",error:"503 PRIVATE-secret"};
  emit("progress",{kind:"filing_question",index:0});await percent(10);finish(legacy);
  await page.waitForFunction(()=>document.body.innerText.includes("Confidence: Failed to assess"));
  assert.equal(await page.$('[aria-label="Confidence 50 out of 100"]'),null);
  assert(!(await text()).includes("PRIVATE-secret"));
  assert.notEqual(await page.$eval('[role="progressbar"]',el=>el.getAttribute("aria-valuenow")),"100");
  await page.screenshot({path:resolve(out,"failed-legacy.png"),fullPage:true});
  await click("Analyze");await percent(0);
  const partial=structuredClone(result);partial.report.recommendation="Sell";partial.report.confidence=80;
  partial.sec={...partial.sec,status:"error",error:"503 PRIVATE-secret"};
  finish(partial);
  await page.waitForFunction(()=>document.body.innerText.includes("Original prediction: Sell"));
  assert((await text()).includes("Confidence: Not assessed"));
  assert.equal(await page.$('[aria-label="Confidence 80 out of 100"]'),null);
  assert.notEqual(await page.$eval('[role="progressbar"]',el=>el.getAttribute("aria-valuenow")),"100");
  await page.screenshot({path:resolve(out,"restored-partial-report.png"),fullPage:true});
  for(const [status,detail,expected] of [
    [429,{kind:"app_daily_limit",message:"fixture"},"Verdict's daily limit"],
    [429,{kind:"provider_daily_limit",message:"fixture"},"daily AI quota"],
    [429,{kind:"provider_token_limit",window:"day",message:"fixture"},"daily limit"],
    [429,{kind:"provider_rate_limit",retry_after_seconds:13,message:"fixture"},"13 seconds"],
    [429,{kind:"provider_limit",message:"fixture"},"short wait may not help"],
    [503,{kind:"provider_busy",message:"fixture"},"temporarily busy"],
    [504,{kind:"timeout",message:"fixture"},"timed out"],
    [502,{kind:"connection",message:"fixture"},"could not reach"],
    [502,{kind:"configuration",message:"fixture"},"configuration needs attention"],
  ]) {
    failure={status,detail};await click("Analyze");
    await page.waitForFunction(expected=>document.body.innerText.includes(expected),{},expected);
    await page.waitForFunction(()=>[...document.querySelectorAll("button")].some(el=>el.textContent.trim()==="Analyze"&&!el.disabled));
    assert((await text()).includes("Failed to assess"));await percent(0);
  }
  failure=null;await click("Analyze");await percent(0);finish(result,true);
  await page.waitForFunction(()=>document.body.innerText.includes("Loaded a saved report"));
  assert.equal(await page.$('[role="progressbar"]'),null);
  askFailure={status:503,detail:{kind:"provider_busy",message:"PRIVATE-secret"}};
  await page.setViewport({width:1440,height:1000});
  await click("Ask analyst");
  await page.waitForSelector('input[placeholder^="Ask anything"]');
  await page.type('input[placeholder^="Ask anything"]',"Explain the result");await click("Send");
  await page.waitForFunction(()=>document.body.innerText.includes("Couldn't get a response"));
  assert((await text()).includes("Google is temporarily busy"));assert(!(await text()).includes("PRIVATE-secret"));
  await click("Track record");
  await page.waitForFunction(()=>document.body.innerText.includes("Completed (1)"));
  await click("In progress (3)");
  await page.waitForFunction(()=>document.querySelectorAll("tbody tr").length===3);
  assert((await text()).includes("remaining"));
  await page.click('[aria-label="View details for NVDA run 102"]');
  await page.waitForFunction(()=>document.querySelector("dialog")?.innerText.includes("gemini-2.5-flash"));
  await click("Close details");
  await page.click('[aria-label="View details for NVDA run 103"]');
  await page.waitForFunction(()=>document.querySelector("dialog")?.innerText.includes("gemini-3.8-flash"));
  await click("Close details");
  await click("Failed to assess (1)");
  await page.waitForFunction(()=>document.querySelector("tbody")?.innerText.includes("Filing review failed"));
  assert((await page.$eval("tbody",el=>el.innerText)).includes("Confidence: Failed to assess"));
  assert(!(await page.$eval("tbody",el=>el.innerText)).includes("75% confidence"));
  await page.screenshot({path:resolve(out,"track-record-failed-desktop.png"),fullPage:true});
  await page.setViewport({width:390,height:844});
  await page.screenshot({path:resolve(out,"track-record-failed-mobile.png"),fullPage:true});
  assert(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth),"track record mobile overflow");
  await click("In progress (3)");
  await page.waitForFunction(()=>document.querySelectorAll("tbody tr").length===3);
  await page.screenshot({path:resolve(out,"track-record-open-mobile.png"),fullPage:true});
  await click("Unscored (1)");
  await page.waitForFunction(()=>document.querySelectorAll("tbody tr").length===1);
  assert((await text()).includes("original issue price"));
  await page.select('[aria-label="Prediction type"]',"partial_ai");
  await click("In progress (1)");
  await page.waitForFunction(()=>document.querySelectorAll("tbody tr").length===1);
  assert((await page.$eval("tbody",el=>el.innerText)).includes("NVDA · Sell"));
  assert((await page.$eval("tbody",el=>el.innerText)).includes("Confidence: Not assessed"));
  assert((await text()).includes("Original prediction remains tracked"));
  await page.evaluate(()=>window.scrollTo(0,0));
  await page.screenshot({path:resolve(out,"restored-partial-track-mobile.png"),fullPage:true});
  await page.setViewport({width:1440,height:1000});
  await page.screenshot({path:resolve(out,"restored-partial-track-desktop.png"),fullPage:true});
  await page.select('[aria-label="Prediction type"]',"rules_based");
  await page.waitForFunction(()=>document.querySelector("tbody")?.innerText.includes("NVDA · Buy"));
  assert((await text()).includes("Rules-based"));
  assert(!(await page.$eval("tbody",el=>el.innerText)).includes("75% confidence"));
  assert.deepEqual(errors,[],`Browser errors: ${errors.join(", ")}`);
  assert(blocked.every(url=>url.startsWith("https://fonts.googleapis.com/") || url.startsWith("https://fonts.gstatic.com/")), "Unexpected external API request");
  console.log(JSON.stringify({passed:true,scenarios:27,apiRequests:apiRequests.length,externalRequests:0,blockedFontRequests:blocked.length,screenshots:out}));
} finally {await browser.close();for(const stream of streams) stream.end();await new Promise(resolve=>server.close(resolve));}
