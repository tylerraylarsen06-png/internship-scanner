/**
 * The only place in apply/ allowed to click. Everything else calls safeClick().
 *
 * 🔴 It will never press Submit. A click is refused when the element's text, aria-label, value or
 * Workday automation id says submit, send, finish, sign in, create account, accept, agree, withdraw or
 * delete, whatever list it is otherwise on. Buttons must also be on the allow-list by name. Dropdown
 * options and radio buttons inside a form field are allowed by kind, and still pass the refusal check.
 * tests/test_never_submit.py checks this file and runs mayClick() against the cases that matter.
 */
export const ALLOWED_BUTTON = /^(apply|apply now|apply manually|autofill with resume|use my last application|next|continue|save and continue|select files?|upload|add|add another)$/i;
export const FORBIDDEN = /(submit|send|finish|complete (my )?application|sign ?in|log ?in|create account|register|withdraw|delete|remove|accept|agree|consent|terms)/i;
const FORBIDDEN_IDS = /(submit|signin|createaccount|withdraw|delete|termsandconditions|agreement)/i;

export function mayClick({ text = '', label = '', value = '', aid = '', type = '' }, kind = 'button') {
  const said = `${text} ${label} ${value}`.replace(/\s+/g, ' ').trim();
  if (FORBIDDEN.test(said) || FORBIDDEN_IDS.test(aid)) return false;
  if (kind === 'option' || kind === 'radio' || kind === 'listbox') return said.length > 0 || aid.length > 0;
  if (type === 'submit' && !ALLOWED_BUTTON.test(said)) return false;
  return ALLOWED_BUTTON.test(text.trim()) || ALLOWED_BUTTON.test(label.trim()) || ALLOWED_BUTTON.test(value.trim());
}

export async function describe(locator) {
  return locator.evaluate((el) => ({
    text: (el.innerText || '').trim().slice(0, 80),
    label: (el.getAttribute('aria-label') || el.labels?.[0]?.innerText || el.closest('label')?.innerText || '').trim().slice(0, 120),
    value: el.tagName === 'INPUT' && el.type !== 'radio' && el.type !== 'checkbox' ? (el.value || '') : '',
    aid: el.getAttribute('data-automation-id') || '',
    type: el.getAttribute('type') || '',
  }));
}

export class RefusedClick extends Error {}

export async function safeClick(locator, kind = 'button') {
  const info = await describe(locator);
  if (!mayClick(info, kind)) throw new RefusedClick(`refused to click "${info.text || info.label || info.aid}"`);
  await locator.click();
}
