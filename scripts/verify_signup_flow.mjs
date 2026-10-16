/** Disposable Chrome profile, synthetic accounts; Google UI is a local test double. */
import assert from "node:assert/strict";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { createRequire } from "node:module";
const require = createRequire(new URL("../frontend/package.json", import.meta.url));
const { default: puppeteer } = await import(require.resolve("puppeteer-core"));

const base = process.argv[2];
assert(base?.startsWith("https://verdict.test:"), "Use the disposable release-test origin only");
const root = fileURLToPath(new URL("../", import.meta.url));
const manifest = JSON.parse(await readFile(`${root}frontend/src/lib/legalManifest.json`, "utf8"));
const browser = await puppeteer.launch({
  executablePath: process.env.VERDICT_TEST_CHROME ?? "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
  headless: true, acceptInsecureCerts: true,
  args: ["--host-resolver-rules=MAP verdict.test 127.0.0.1", "--no-proxy-server"],
});
const evidence = {origin:"disposable local TLS instance", email_flow:"pending", google_flow:"pending", live_google_verified:false};
async function clickText(page, text) {
  await page.waitForFunction(t => [...document.querySelectorAll("button")].some(b => b.textContent.trim() === t), {}, text);
  await page.evaluate(t => {
    const button = [...document.querySelectorAll("button")].find(b => b.textContent.trim() === t);
    if (!button || button.disabled) throw Error(`Missing/enabled button: ${t}`);
    button.click();
  }, text);
}
async function input(page, label, value) {
  const handle = await page.evaluateHandle(t => [...document.querySelectorAll("label")].find(l => l.firstChild?.textContent.trim() === t)?.querySelector("input"), label);
  assert(await handle.asElement(), `Input ${label}`);
  await handle.asElement().type(value); await handle.dispose();
}
async function checkAgreement(page, buttonText) {
  await page.waitForSelector("#signup-agreement-heading");
  assert.equal(await page.$eval('input[type="checkbox"]', e => e.checked), false);
  assert(await page.evaluate(t => [...document.querySelectorAll("button")].find(b => b.textContent.trim() === t)?.disabled, buttonText));
  for (const title of ["Terms of Service", "Risk & Data Disclosure", "Privacy Policy"]) {
    assert(await page.evaluate(t => [...document.querySelectorAll("summary")].some(e => e.textContent.includes(t)), title));
  }
  await page.$eval("details:not([open])", e => e.open = true);
  assert(await page.$eval('details[open] div[tabindex="0"]', e => e.clientHeight > 0 && e.scrollHeight >= e.clientHeight));
}
try {
  const context = await browser.createBrowserContext();
  const page = await context.newPage();
  await page.setViewport({width:1100,height:1200,deviceScaleFactor:1});
  let creations = 0;
  page.on("request", req => { if(req.url().endsWith("/api/auth/register") && req.method()==="POST") creations++; });
  await page.goto(base, {waitUntil:"networkidle0"});
  await clickText(page,"New here? Create an account");
  await input(page,"Email","browser-flow@example.com");
  await input(page,"Password","A-long-browser-password-123");
  await input(page,"Confirm password","A-long-browser-password-123");
  await clickText(page,"Review account agreement");
  await checkAgreement(page,"I agree — create my account");
  assert.equal(creations,0);
  await clickText(page,"Open Terms of Service in full");
  await page.waitForSelector('[role="dialog"]');
  assert(await page.$eval('[role="dialog"]', e => e.innerText.includes("Your decisions are yours")));
  await page.keyboard.press("Escape");
  await page.waitForSelector('[role="dialog"]',{hidden:true});
  await page.click('input[type="checkbox"]');
  await clickText(page,"Back without creating an account");
  assert.equal(creations,0);
  assert.equal(await page.$eval('input[type="email"]', e=>e.value),"browser-flow@example.com");
  await clickText(page,"Review account agreement");
  await checkAgreement(page,"I agree — create my account");
  await page.setViewport({width:390,height:844,deviceScaleFactor:1});
  assert(await page.evaluate(()=>document.documentElement.scrollWidth <= window.innerWidth), "Mobile horizontal overflow");
  await page.setViewport({width:1100,height:1200,deviceScaleFactor:1});
  await page.evaluate(()=>{for(const d of document.querySelectorAll("details")) d.open=d.querySelector("summary").textContent.includes("Terms");window.scrollTo(0,0);});
  await mkdir(`${root}docs/security-audit`,{recursive:true});
  await page.screenshot({path:`${root}docs/security-audit/signup-agreement.png`,fullPage:true});
  await page.click('input[type="checkbox"]');
  const response = page.waitForResponse(r=>r.url().endsWith("/api/auth/register") && r.request().method()==="POST");
  await clickText(page,"I agree — create my account");
  const created = await response; assert.equal(created.status(),201, created.status() === 201 ? "" : await created.text());
  const payload = JSON.parse(created.request().postData());
  assert.equal(payload.legal_acceptance.accepted,true);
  assert.equal(payload.legal_acceptance.content_sha256,manifest.content_sha256);
  const me = await page.evaluate(async()=>{const r=await fetch("/api/auth/me");return {status:r.status,body:await r.json()};});
  assert.equal(me.status,200);assert.equal(me.body.user.email,"browser-flow@example.com");
  evidence.email_flow="PASS: separate step, readable inline/modal documents, initially unchecked, disabled action, Back creates nothing and clears acceptance, mobile fit, accepted signup returns 201 and authenticated session";
  await context.close();

  const googleContext = await browser.createBrowserContext();
  const gp = await googleContext.newPage();
  await gp.setViewport({width:1100,height:1200});
  let nonceCount=0;const googlePosts=[];
  await gp.setRequestInterception(true);
  gp.on("request", async req=>{
    const url = new URL(req.url());
    if(req.url()==="https://accounts.google.com/gsi/client") {
      return req.respond({status:200,contentType:"application/javascript",body:`window.google={accounts:{id:{initialize:o=>{window.syntheticGoogle=o;},renderButton:(el,o)=>{const b=document.createElement('button');b.type='button';b.textContent=o.text==='signup_with'?'Synthetic Google signup':'Synthetic Google sign-in';b.onclick=()=>window.syntheticGoogle.callback({credential:'synthetic.'+window.syntheticGoogle.nonce});el.append(b);}}}};`});
    }
    const respond=(status,body)=>req.respond({status,contentType:"application/json",body:JSON.stringify(body)});
    if(url.pathname==="/api/auth/status") return respond(200,{bootstrap_required:false,public_signup_enabled:true,password_reset_available:false,google_client_id:"synthetic-client",legal_manifest:manifest});
    if(url.pathname==="/api/auth/me") return respond(401,{detail:"Synthetic unsigned visitor"});
    if(url.pathname==="/api/auth/google/nonce") return respond(200,{nonce:`challenge-${++nonceCount}`});
    if(url.pathname==="/api/auth/google") {
      const body=JSON.parse(req.postData());googlePosts.push(body);
      return respond(body.legal_acceptance?401:428,{detail:body.legal_acceptance?"Synthetic test stops before live Google verification":"Current agreement required"});
    }
    if(url.origin!==new URL(base).origin) return req.abort();
    return req.continue();
  });
  await gp.goto(base,{waitUntil:"networkidle0"});
  await clickText(gp,"Synthetic Google sign-in");
  await checkAgreement(gp,"I agree — continue to Google signup");
  assert.equal(googlePosts.length,1);assert.equal(googlePosts[0].legal_acceptance,undefined);
  await gp.click('input[type="checkbox"]');
  await clickText(gp,"I agree — continue to Google signup");
  await clickText(gp,"Synthetic Google signup");
  await gp.waitForFunction(()=>document.body.innerText.includes("Synthetic test stops"));
  assert.equal(googlePosts.length,2);assert.equal(googlePosts[1].legal_acceptance.accepted,true);
  assert.equal(googlePosts[1].legal_acceptance.content_sha256,manifest.content_sha256);
  assert.notEqual(googlePosts[0].credential,googlePosts[1].credential);assert(nonceCount>=2);
  evidence.google_flow="PASS with local GIS/API doubles: unknown login 428 opens unchecked agreement; acceptance precedes signup button and sends current versions with a fresh challenge. Real Google login not attempted; backend separately tests locally signed JWTs.";
  await googleContext.close();
  await writeFile(`${root}docs/security-audit/signup-flow-validation.json`,JSON.stringify(evidence,null,2)+"\n");
  console.log(JSON.stringify(evidence,null,2));
} finally { await browser.close(); }
