/**
 * Internship Master: the write path for the scanner, bound to the Google Sheet.
 *
 * GET  ?token=...          -> every row on every tab, as JSON (the scanner reads your edits)
 * POST {token, rows:[...]} -> upsert by key. Appends new rows, fills empty cells, never deletes,
 *                             never overwrites a column you own, never moves a row out of
 *                             APPLIED or RULED OUT.
 * onEdit                   -> set Status to "applied" and the row moves to APPLIED with today's
 *                             date; "passed" / "rejected" / "ruled out" moves it to RULED OUT.
 *
 * Setup: run setup() once from the editor, copy the token from the log, then
 * Deploy > New deployment > Web app (Execute as: Me, Who has access: Anyone with the link).
 */
const COLS = ['company', 'role', 'tier', 'class_year', 'opens', 'deadline', 'location', 'link', 'source',
  'verified', 'fit', 'status', 'date_found', 'decision_maker', 'dm_email', 'outreach_status', 'notes', 'key'];
const HEAD = ['Company', 'Role', 'Tier', 'Class-year eligibility', 'Opens', 'Deadline', 'Location', 'Link',
  'Source', 'Verified on firm page', 'Fit (1-5)', 'Status', 'Date found', 'Decision maker', 'Their email',
  'Outreach status', 'Notes', 'key'];
const TABS = ['URGENT', 'URGENT (SUB 3)', 'PIPELINE', 'APPLIED', 'RULED OUT'];
const LOCKED = ['APPLIED', 'RULED OUT'];
const USER_OWNED = ['status', 'decision_maker', 'dm_email', 'outreach_status', 'notes'];
const STATUS_COL = COLS.indexOf('status') + 1;

function setup() {
  const ss = SpreadsheetApp.getActive();
  TABS.forEach(t => {
    const sh = ss.getSheetByName(t) || ss.insertSheet(t);
    if (sh.getLastRow() === 0) sh.appendRow(HEAD);
    const rule = SpreadsheetApp.newDataValidation().requireValueInList(
      ['new', 'staged', 'applied', 'interviewing', 'offer', 'rejected', 'passed', 'ruled out'], true)
      .setAllowInvalid(true).build();
    sh.getRange(2, STATUS_COL, Math.max(sh.getMaxRows() - 1, 1), 1).setDataValidation(rule);
    sh.setFrozenRows(1);
    sh.hideColumns(COLS.indexOf('key') + 1);
  });
  const props = PropertiesService.getScriptProperties();
  if (!props.getProperty('TOKEN')) props.setProperty('TOKEN', Utilities.getUuid());
  Logger.log('TOKEN = ' + props.getProperty('TOKEN'));
}

function auth_(token) {
  if (!token || token !== PropertiesService.getScriptProperties().getProperty('TOKEN')) throw new Error('bad token');
}

function json_(o) {
  return ContentService.createTextOutput(JSON.stringify(o)).setMimeType(ContentService.MimeType.JSON);
}

function readAll_() {
  const ss = SpreadsheetApp.getActive();
  const out = [];
  TABS.forEach(t => {
    const sh = ss.getSheetByName(t);
    const vals = sh.getDataRange().getValues();
    for (let i = 1; i < vals.length; i++) {
      const o = { tab: t, _row: i + 1 };
      COLS.forEach((c, j) => { o[c] = vals[i][j] instanceof Date ? Utilities.formatDate(vals[i][j], 'America/Los_Angeles', 'yyyy-MM-dd') : String(vals[i][j]); });
      if (o.key) out.push(o);
    }
  });
  return out;
}

function doGet(e) {
  try {
    auth_(e.parameter.token);
    return json_({ ok: true, rows: readAll_().map(r => { delete r._row; return r; }) });
  } catch (err) {
    return json_({ ok: false, error: String(err) });
  }
}

function doPost(e) {
  const lock = LockService.getScriptLock();
  lock.waitLock(30000);
  try {
    const body = JSON.parse(e.postData.contents);
    auth_(body.token);
    return json_(upsert_(body.rows || []));
  } catch (err) {
    return json_({ ok: false, error: String(err) });
  } finally {
    lock.releaseLock();
  }
}

function upsert_(rows) {
  const ss = SpreadsheetApp.getActive();
  const stats = { ok: true, appended: 0, updated: 0, moved: 0 };
  let index = {};
  readAll_().forEach(r => { index[r.key] = r; });
  rows.forEach(r => {
    const want = TABS.indexOf(r.tab) >= 0 ? r.tab : 'PIPELINE';
    const cur = index[r.key];
    if (!cur) {
      ss.getSheetByName(want).appendRow(COLS.map(c => r[c] == null ? '' : r[c]));
      stats.appended++;
      index[r.key] = Object.assign({ tab: want, _row: ss.getSheetByName(want).getLastRow() }, r);
      return;
    }
    const sh = ss.getSheetByName(cur.tab);
    let changed = false;
    COLS.forEach((c, j) => {
      const v = r[c] == null ? '' : String(r[c]);
      if (v === '' || v === cur[c]) return;
      if (USER_OWNED.indexOf(c) >= 0 && cur[c] !== '') return;
      sh.getRange(cur._row, j + 1).setValue(v);
      cur[c] = v;
      changed = true;
    });
    if (changed) stats.updated++;
    if (want !== cur.tab && LOCKED.indexOf(cur.tab) < 0 && want !== 'APPLIED') {
      moveRow_(sh, cur._row, ss.getSheetByName(want));
      stats.moved++;
      index = {};
      readAll_().forEach(x => { index[x.key] = x; });
    }
  });
  return stats;
}

function moveRow_(from, rowNum, to) {
  const vals = from.getRange(rowNum, 1, 1, COLS.length).getValues()[0];
  to.appendRow(vals);
  from.deleteRow(rowNum);
}

function onEdit(e) {
  const sh = e.range.getSheet();
  if (TABS.indexOf(sh.getName()) < 0 || e.range.getColumn() !== STATUS_COL || e.range.getRow() < 2) return;
  const v = String(e.value || '').toLowerCase().trim();
  const ss = sh.getParent();
  const row = e.range.getRow();
  const notesCol = COLS.indexOf('notes') + 1;
  const today = Utilities.formatDate(new Date(), 'America/Los_Angeles', 'yyyy-MM-dd');
  if (v === 'applied' && sh.getName() !== 'APPLIED') {
    const n = sh.getRange(row, notesCol);
    n.setValue(('Applied ' + today + '. ' + n.getValue()).trim());
    moveRow_(sh, row, ss.getSheetByName('APPLIED'));
  } else if (['passed', 'rejected', 'ruled out'].indexOf(v) >= 0 && LOCKED.indexOf(sh.getName()) < 0) {
    // an APPLIED row keeps its place and just carries the new status
    const n = sh.getRange(row, notesCol);
    n.setValue(('RULED OUT: ' + v + ' ' + today + '. ' + n.getValue()).trim());
    moveRow_(sh, row, ss.getSheetByName('RULED OUT'));
  }
}
