#!/usr/bin/env node
/**
 * Open every staged application in Chrome, fill what can be filled, and STOP.
 *
 * NEVER SUBMITS. This file contains no click, no press, no form.submit, no requestSubmit.
 * Fields are set by value and the resume by setInputFiles; nothing else touches the page.
 * tests/test_never_submit.py fails the build if any of those calls ever appear here.
 *
 * Usage: bin/apply            (all staged items)
 *        bin/apply --only 3    (first 3)
 *        bin/apply --list      (print the queue, open nothing)
 *        bin/apply --match fox (any staged item whose company or role contains "fox")
 *        bin/apply --all       (every staged item, not just those due within 14 days)
 */
import { createRequire } from 'module';
import { readFileSync, existsSync } from 'fs';
import { homedir } from 'os';
import { join, dirname } from 'path';
import { fileURLToPath } from 'url';

import { runWorkday } from './workday.mjs';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..');
const require = createRequire(join(homedir(), 'dev/career-ops/package.json'));
const { chromium } = require('playwright');

const args = process.argv.slice(2);
const only = args.includes('--only') ? Number(args[args.indexOf('--only') + 1]) : Infinity;
const queuePath = args.includes('--queue') ? args[args.indexOf('--queue') + 1] : join(ROOT, 'queue/queue.json');
const headless = args.includes('--headless'); // tests only
const queue = JSON.parse(readFileSync(queuePath, 'utf8'));
const match = args.includes('--match') ? args[args.indexOf('--match') + 1].toLowerCase() : '';
// Default: only what closes within 14 days at fit 3.5+. --match reaches every staged item; --all opens them all.
const items = queue.items.filter((it) => match ? `${it.company} ${it.role}`.toLowerCase().includes(match)
  : (args.includes('--all') || it.due14)).slice(0, only);

if (!items.length) {
  console.log(match ? `Nothing staged matches "${match}".` : 'Nothing due within 14 days. `bin/apply --all` opens everything staged.');
  process.exit(0);
}
console.log(`\nQueue built ${queue.built}: ${items.length} application(s)\n`);
items.forEach((it, i) => console.log(`${String(i + 1).padStart(2)}. ${it.company} | ${it.role}\n    ${it.ats}: ${it.form}${it.deadline ? `  | due ${it.deadline}` : ''}`));
if (args.includes('--list')) process.exit(0);
if (!existsSync(queue.resume)) console.log(`\nWARNING: Resume not found at ${queue.resume}; upload fields will be left empty.`);

// label text -> answer key. First match wins.
const RULES = [
  [/hispanic|latino/i, 'hispanic'],
  [/\brace\b|ethnic/i, 'race'],
  [/gender|\bsex\b/i, 'gender'],
  [/veteran/i, 'veteran'],
  [/disabilit/i, 'disability'],
  [/sexual orientation|transgender|pronoun/i, 'ask'],   // not in the answer set: leave for you
  [/why (do you want|are you interested|this (role|company|team))|why .{0,30}\b(us|here)\b|interest in (this|the) (role|position|company)/i, 'why'],
  [/previously (worked|been employed)|ever (been employed|worked)|former (employee|worker)|current or former|worked (here|for us) before|employed by/i, 'previous_employee'],
  [/18 years|age of 18|at least 18/i, 'adult'],
  [/device type|phone type/i, 'phone_type'],
  [/^\s*country\b|country\/territory/i, 'country'],
  [/first name|given name|preferred name/i, 'first_name'],
  [/last name|family name|surname/i, 'last_name'],
  [/^\s*(full |legal )?name\s*\*?\s*$/i, 'full_name'],
  [/e-?mail/i, 'email'],
  [/phone|mobile/i, 'phone'],
  [/linkedin/i, 'linkedin'],
  [/school|university|college|institution/i, 'school'],
  [/degree/i, 'degree'],
  [/major|field of study|discipline|concentration/i, 'major'],
  [/graduation year|year of graduation|class year|grad year/i, 'graduation_year'],
  [/graduat/i, 'graduation'],
  [/\bgpa\b|grade point/i, 'gpa'],
  [/year in school|class standing|academic standing|current year|year of study/i, 'class_standing'],
  [/authori[sz]ed to work|legally (eligible|authori[sz]ed)|eligible to work/i, 'work_authorized'],
  [/sponsor/i, 'sponsorship'],
  [/hear about|how did you (find|learn)|referral source/i, 'hear_about'],
  [/address line 1|street address|^\s*address\s*\*?$/i, 'address_line1'],
  [/zip|postal/i, 'zip'],
  [/\bcity\b/i, 'city'],
  [/\bstate\b/i, 'state'],
  [/location|where (are you|do you) (based|live)/i, 'location'],
];
const answerFor = (label, answers) => {
  for (const [re, key] of RULES) if (re.test(label)) return answers[key];
  return undefined;
};

async function fillFields(page, it, unfilled) {
  const answers = it.answers;
  let filled = 0;
  const fields = await page.locator('input:not([type=hidden]):not([type=submit]):not([type=button]), textarea, select').all();
  for (const f of fields) {
    try {
      if (!(await f.isVisible())) continue;
      const meta = await f.evaluate((el) => {
        const lab = (el.labels && el.labels[0] && el.labels[0].innerText) || el.getAttribute('aria-label') ||
          el.closest('label')?.innerText || el.closest('[class*=field],[class*=question]')?.querySelector('label,legend')?.innerText ||
          el.placeholder || el.name || el.id || '';
        return { label: lab.trim().slice(0, 140), tag: el.tagName, type: el.type, value: el.value, required: el.required };
      });
      if (meta.type === 'file') {
        if (/resume|cv/i.test(meta.label) && existsSync(queue.resume)) {
          await f.setInputFiles(queue.resume);
          filled++;
        }
        continue;
      }
      if (meta.type === 'checkbox' || meta.type === 'radio') continue; // left for you, visible in the panel
      if (meta.type === 'search' || /search/i.test(meta.label)) continue; // a site search box is not a form field
      const ans = answerFor(meta.label, answers);
      if (ans === undefined && answerFor(meta.label, { ask: '__ask__' }) === '__ask__') { unfilled.push(meta.label); continue; }
      if (ans === undefined) {
        if (meta.required && !meta.value) unfilled.push(meta.label);
        continue;
      }
      if (meta.tag === 'SELECT') {
        const opts = await f.locator('option').allInnerTexts();
        const want = opts.find((o) => o.trim().toLowerCase() === String(ans).toLowerCase()) ||
          opts.find((o) => o.toLowerCase().startsWith(String(ans).toLowerCase())) ||
          opts.find((o) => o.toLowerCase().includes(String(ans).toLowerCase()));
        if (want) { await f.selectOption({ label: want }); filled++; } else unfilled.push(meta.label);
      } else if (!meta.value) {
        await f.fill(String(ans));
        filled++;
      }
    } catch { /* a field that will not take a value is left for you */ }
  }
  return filled;
}

async function banner(page, it, n, unfilled) {
  const answers = it.answers;
  const miss = [...new Set(unfilled)].filter(Boolean);
  // Banner so it is obvious this tab was filled and still needs a human to submit.
  await page.evaluate(({ n, miss, company, role, answers }) => {
    const d = document.createElement('div');
    d.style.cssText = 'position:fixed;top:0;left:0;right:0;z-index:2147483647;background:#7a0000;color:#fff;' +
      'font:13px/1.4 -apple-system,sans-serif;padding:8px 14px;box-shadow:0 2px 6px rgba(0,0,0,.3)';
    // Built with textContent: company, role and field labels come from scraped pages.
    const b = document.createElement('b');
    b.textContent = 'NOT SUBMITTED.';
    const note = document.createElement('span');
    note.style.opacity = '.8';
    note.textContent = `Grad ${answers.graduation} · GPA ${answers.gpa} · authorized: ${answers.work_authorized} · sponsorship: ${answers.sponsorship}`;
    d.append(b, document.createTextNode(` ${company}: ${role}. Filled ${n} field(s). ` +
      (miss.length ? `Still needs you: ${miss.slice(0, 6).join(' · ')}. ` : '') +
      'Review every page, then press Submit yourself. '), note);
    document.body.appendChild(d);
  }, { n, miss, company: it.company, role: it.role, answers }).catch(() => {});
}

async function fillPage(page, it) {
  const unfilled = [];
  const filled = await fillFields(page, it, unfilled);
  await banner(page, it, filled, unfilled);
  return { filled, unfilled };
}

import { mkdtempSync, readlinkSync } from 'fs';
import { tmpdir } from 'os';
const profile = headless ? mkdtempSync(join(tmpdir(), 'scanner-test-')) : join(homedir(), '.internship-scanner/chrome-profile');
// One Chrome per profile: if an earlier `bin/apply` window is still open, wait for it to close.
const lockPid = () => { try { return Number(readlinkSync(join(profile, 'SingletonLock')).split('-').pop()); } catch { return 0; } };
const alive = (pid) => { if (!(pid > 0)) return false; try { process.kill(pid, 0); return true; } catch { return false; } };
if (!headless && alive(lockPid())) {
  console.log('\nAn earlier apply window is still open. Close that Chrome window and this will start.');
  while (alive(lockPid())) await new Promise((r) => setTimeout(r, 1500));
}
const ctx = await chromium.launchPersistentContext(profile, {
  // Playwright's own Chromium, never the Google Chrome app: a separate app with its own Dock icon, so it can't be
  // mistaken for your everyday Chrome (2026-10-06: a leftover window here looked like the real profiles had vanished).
  headless, viewport: null, args: ['--start-maximized'],
  // Let your own autofill extension run in this profile (install it once from the Chrome Web Store here).
  // The never-submit guard covers this script's clicks only, so the extension's auto-submit must stay off.
  ignoreDefaultArgs: ['--disable-extensions'],
});
for (const it of items) {
  const page = await ctx.newPage();
  try {
    // Workday: open the posting itself; the flow clicks Apply.
    const url = it.ats === 'workday' ? (it.posting || it.url).replace(/\/apply\/?$/, '') : it.url;
    await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 45000 });
    await page.waitForTimeout(2500);
    if (it.ats === 'workday') {
      const r = await runWorkday(page, it, { resume: queue.resume, fillFields, answerFor, log: console.log });
      await banner(page, it, r.filled, r.unfilled);
      console.log(`  ${it.company}: ${r.status}. Filled ${r.filled}.` +
        (r.unfilled.length ? ` Needs you: ${[...new Set(r.unfilled)].slice(0, 4).join(' | ')}` : ''));
      continue;
    }
    if (it.ats === 'handshake' || it.ats === 'icims') {
      console.log(`  ${it.company}: opened. ${it.form}`);
      continue;
    }
    const r = await fillPage(page, it);
    console.log(`  ${it.company}: filled ${r.filled}${r.unfilled.length ? `, needs you: ${r.unfilled.slice(0, 4).join(' | ')}` : ''}`);
  } catch (e) {
    console.log(`  ${it.company}: opened, could not fill (${String(e.message).slice(0, 80)})`);
  }
}
const blank = ctx.pages().find((p) => p.url() === 'about:blank');
if (blank && ctx.pages().length > 1) await blank.close();
if (headless) {
  globalThis.__report = await Promise.all(ctx.pages().map((p) => p.evaluate(() =>
    [...document.querySelectorAll('input,select,textarea')].map((e) => [e.name || e.id, e.type === 'file' ? e.files.length : e.value]))));
  console.log(JSON.stringify(globalThis.__report));
  console.log('SUBMITTED=' + (await ctx.pages()[0].evaluate(() => window.__submitted === true)));
  await ctx.close();
  process.exit(0);
}
console.log('\nEverything is open and NOT submitted. Close the Chrome window when you are done.');
await new Promise((res) => ctx.on('close', res));
