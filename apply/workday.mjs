/**
 * Workday: Apply -> (you sign in) -> Autofill with Resume -> fill each page -> Save and Continue,
 * stopping on the Review page. Every click goes through guard.safeClick, which refuses Submit.
 */
import { safeClick, describe, RefusedClick } from './guard.mjs';

const SIGN_IN = '[data-automation-id="signInContent"], [data-automation-id="createAccountLink"], [data-automation-id="signInLink"], input[type="password"]';
const NEXT = '[data-automation-id="bottom-navigation-next-button"], [data-automation-id="pageFooterNextButton"]';
const ERRORS = '[data-automation-id="errorMessage"], [data-automation-id="errorBanner"], [data-automation-id="inputAlert"]';

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function visible(page, sel) {
  const l = page.locator(sel).first();
  return (await l.count()) > 0 && (await l.isVisible().catch(() => false)) ? l : null;
}

async function waitForAny(page, sels, ms = 15000) {
  const end = Date.now() + ms;
  while (Date.now() < end) {
    for (const s of sels) if (await visible(page, s)) return s;
    await sleep(400);
  }
  return null;
}

async function heading(page) {
  for (const sel of ['[data-automation-id="progressBarActiveStep"]', '[data-automation-id="pageHeader"]', 'h2']) {
    const h = await visible(page, sel);
    if (h) return (await h.innerText().catch(() => '')).replace(/current step \d+ of \d+\s*/i, '').trim();
  }
  return '';
}

/** Pause until you have signed in or created the account in this tab. Nothing is typed here. */
async function waitForSignIn(page, it, log) {
  if (!(await visible(page, SIGN_IN))) return true;
  await page.bringToFront();
  log(`  ${it.company}: sign in (or create the account) in the front tab. Waiting up to 10 minutes...`);
  const end = Date.now() + 10 * 60 * 1000;
  while (Date.now() < end) {
    await sleep(1500);
    if (!(await visible(page, SIGN_IN))) return true;
  }
  return false;
}

/** Workday dropdowns are buttons that open a listbox. */
async function fillListboxes(page, answerFor, answers, unfilled) {
  let n = 0;
  for (const btn of await page.locator('button[aria-haspopup="listbox"]').all()) {
    try {
      if (!(await btn.isVisible())) continue;
      const info = await describe(btn);
      const current = info.text.toLowerCase();
      if (current && !/select one|^$/.test(current)) continue; // already chosen (autofill or you)
      const label = info.label || (await btn.evaluate((el) =>
        el.closest('[data-automation-id^="formField"]')?.querySelector('label')?.innerText || ''));
      const ans = answerFor(label, answers);
      if (ans === undefined) { if (/required|\*/i.test(label)) unfilled.push(label.replace(/select one|required/gi, '').trim()); continue; }
      await safeClick(btn, 'listbox');
      await page.locator('[role="option"]').first().waitFor({ timeout: 4000 });
      const opts = page.locator('[role="option"]');
      const texts = await opts.allInnerTexts();
      const want = texts.findIndex((t) => t.trim().toLowerCase() === String(ans).toLowerCase()) >= 0
          ? texts.findIndex((t) => t.trim().toLowerCase() === String(ans).toLowerCase())
          : texts.findIndex((t) => t.toLowerCase().startsWith(String(ans).toLowerCase()));
      if (want >= 0) { await safeClick(opts.nth(want), 'option'); n++; }
      else { await page.keyboard.press('Escape'); unfilled.push(label); }
      await sleep(300);
    } catch (e) { if (e instanceof RefusedClick) unfilled.push(String(e.message)); }
  }
  return n;
}

/** Yes/No radio questions ("Have you previously worked for...", work authorization, sponsorship). */
async function fillRadios(page, answerFor, answers, unfilled) {
  let n = 0;
  for (const group of await page.locator('fieldset, [role="radiogroup"]').all()) {
    try {
      if (!(await group.isVisible())) continue;
      const radios = group.locator('input[type="radio"]');
      if (!(await radios.count())) continue;
      if (await group.locator('input[type="radio"]:checked').count()) continue;
      const q = (await group.evaluate((el) => el.querySelector('legend')?.innerText || el.getAttribute('aria-label') ||
        el.closest('[data-automation-id^="formField"]')?.querySelector('label')?.innerText || '')).trim();
      const ans = answerFor(q, answers);
      if (ans === undefined) { unfilled.push(q.slice(0, 80)); continue; }
      for (const r of await radios.all()) {
        const lab = await r.evaluate((el) => (el.labels?.[0]?.innerText || el.getAttribute('aria-label') || '').trim());
        if (lab.toLowerCase() === String(ans).toLowerCase()) { await safeClick(r, 'radio'); n++; break; }
      }
    } catch (e) { if (e instanceof RefusedClick) unfilled.push(String(e.message)); }
  }
  return n;
}

/** "How did you hear about us": Workday's nested prompt. Try a careers-site answer; otherwise leave it to you. */
async function fillSource(page, unfilled) {
  const field = await visible(page, '[data-automation-id="formField-source"], [data-automation-id="formField-sourceDropdown"], [data-automation-id*="source" i] [data-automation-id="multiselectInputContainer"]');
  if (!field) return 0;
  const already = await field.locator('[data-automation-id="selectedItem"]').count();
  if (already) return 0;
  try {
    const opener = field.locator('[data-automation-id="multiselectInputContainer"], input').first();
    await safeClick(opener, 'listbox');
    await sleep(1200);
    const pick = async () => {
      const opts = page.locator('[data-automation-id="promptOption"], [role="option"]');
      const texts = await opts.allInnerTexts();
      const i = texts.findIndex((t) => /career (site|website)|company (career|web)|fox careers|corporate website|website/i.test(t));
      if (i < 0) return false;
      await safeClick(opts.nth(i), 'option');
      await sleep(1200);
      return true;
    };
    if (await pick()) {
      await pick(); // nested categories: a second level sometimes follows the first
      await page.keyboard.press('Escape');
      return 1;
    }
    await page.keyboard.press('Escape');
  } catch (e) { /* fall through to you */ }
  unfilled.push('How did you hear about us');
  return 0;
}

/** A page you have to finish: wait until you click Save and Continue himself, then carry on. */
async function waitForHuman(page, it, h, why, log) {
  await page.bringToFront();
  log(`  ${it.company}: needs you on "${h}": ${why}. Fill it and click Save and Continue; I will carry on from the next page.`);
  const end = Date.now() + 15 * 60 * 1000;
  while (Date.now() < end) {
    await sleep(2000);
    const now = await heading(page);
    if (now && now !== h) return true;
  }
  return false;
}

export async function runWorkday(page, it, { resume, fillFields, answerFor, log }) {
  const unfilled = [];
  let filled = 0;
  // 1. Apply on the posting page.
  const apply = await waitForAny(page, ['[data-automation-id="adventureButton"]', 'a:has-text("Apply")'], 15000);
  if (apply) await safeClick(page.locator(apply).first());
  // 2. Sign-in wall, if any, is yours.
  const step = await waitForAny(page, [SIGN_IN, '[data-automation-id="autofillWithResume"]', '[data-automation-id="applyManually"]', NEXT], 15000);
  if (step === SIGN_IN && !(await waitForSignIn(page, it, log))) return { status: 'waiting for sign-in timed out', filled, unfilled };
  // 3. Autofill with Resume where the tenant offers it, otherwise Apply Manually (Fox offers only that
  //    and Use My Last Application). Either leads to the sign-in step.
  const AUTO = '[data-automation-id="autofillWithResume"]', MANUAL = '[data-automation-id="applyManually"]';
  const choice = await waitForAny(page, [AUTO, MANUAL, NEXT, SIGN_IN], 15000);
  if (choice === AUTO || choice === MANUAL) {
    await safeClick(page.locator(await visible(page, AUTO) ? AUTO : MANUAL).first());
    await waitForAny(page, [SIGN_IN, NEXT, 'input[type="file"]'], 20000);
  }
  if (await waitForSignIn(page, it, log) === false) return { status: 'sign-in timed out', filled, unfilled };
  await waitForAny(page, [NEXT, 'input[type="file"]'], 20000);
  // 4. Page loop: fill, upload the resume on whichever page asks for it, Save and Continue, until Review.
  let uploaded = false;
  for (let pageNo = 0; pageNo < 10; pageNo++) {
    await sleep(1500);
    const h = await heading(page);
    const fileInput = page.locator('input[type="file"]').first();
    if (!uploaded && (await fileInput.count())) {
      await fileInput.setInputFiles(resume);
      uploaded = true;
      filled++;
      log(`  ${it.company}: resume uploaded on "${h}", waiting for Workday to read it...`);
      await sleep(6000);
    }
    if (/review/i.test(h)) return { status: 'stopped at Review: check every page, then press Submit yourself', filled, unfilled };
    filled += await fillFields(page, it, unfilled);
    filled += await fillListboxes(page, answerFor, it.answers, unfilled);
    filled += await fillRadios(page, answerFor, it.answers, unfilled);
    filled += await fillSource(page, unfilled);
    const next = await visible(page, NEXT);
    if (!next) return { status: `stopped on "${h}": no Next button found`, filled, unfilled };
    const label = (await next.innerText().catch(() => '')).trim();
    if (/submit/i.test(label)) return { status: 'stopped at Submit: review, then press it yourself', filled, unfilled };
    try {
      await safeClick(next);
    } catch (e) {
      return { status: `stopped: ${e.message}`, filled, unfilled };
    }
    await sleep(2500);
    if (await visible(page, ERRORS)) {
      const err = (await page.locator(ERRORS).first().innerText().catch(() => '')).slice(0, 140).replace(/\s+/g, ' ');
      if (!(await waitForHuman(page, it, h, err, log))) return { status: `needs you on "${h}": ${err}`, filled, unfilled };
    }
  }
  return { status: 'stopped after 10 pages', filled, unfilled };
}
