/*
 * Popup: load the packs (once for the profile pack, per job for the job pack), press Fill,
 * show what happened. Packs are validated here, before they are stored.
 */
'use strict';

const $ = (id) => document.getElementById(id);
const A = globalThis.AutofillAnswers;

function kb(n) {
  return n > 1024 * 1024 ? `${(n / 1024 / 1024).toFixed(1)} MB` : `${Math.round(n / 1024)} KB`;
}

function b64Bytes(b64) {
  return Math.floor((b64.length * 3) / 4) - (b64.endsWith('==') ? 2 : b64.endsWith('=') ? 1 : 0);
}

function checkFile(file, what) {
  if (!file) return;
  if (typeof file.filename !== 'string' || typeof file.base64 !== 'string' || !file.base64) {
    throw new Error(`${what}: needs "filename" and "base64"`);
  }
  if (!atob(file.base64.slice(0, 8)).startsWith('%PDF-')) throw new Error(`${what}: not a PDF`);
}

/** Validate a profile pack; returns the list of rule problems (shown, not fatal). */
function checkProfilePack(p) {
  if (!p || p.kind !== 'autofill-profile-pack') throw new Error('Not a profile pack (kind must be "autofill-profile-pack"). Make one with: python -m auto_apply.fillpack profile ...');
  if (!p.profile || !p.profile.personalInformation) throw new Error('Profile pack has no profile.personalInformation');
  if (!Array.isArray(p.rules)) throw new Error('Profile pack has no "rules" list');
  checkFile(p.defaultResume, 'defaultResume');
  const bank = new A.AnswerBank(p.profile, p.rules, {}, {});
  return bank.ruleErrors;
}

function checkJobPack(j) {
  if (!j || j.kind !== 'autofill-job-pack') throw new Error('Not a job pack (kind must be "autofill-job-pack"). Make one with: python -m auto_apply.fillpack job ...');
  if (j.answers && (typeof j.answers !== 'object' || Array.isArray(j.answers))) throw new Error('Job pack "answers" must be {"exact label": answer}');
  checkFile(j.resume, 'resume');
}

async function readJson(input) {
  const file = input.files[0];
  input.value = '';
  if (!file) return null;
  try {
    return JSON.parse(await file.text());
  } catch (e) {
    throw new Error(`${file.name} is not valid JSON: ${e.message}`);
  }
}

function showError(msg) {
  $('error').hidden = !msg;
  $('error').textContent = msg || '';
}

async function currentTab() {
  const forced = new URLSearchParams(location.search).get('tab'); // used by the tests
  if (forced) return chrome.tabs.get(Number(forced));
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  return tab;
}

function hostOf(url) {
  try { return new URL(url).hostname; } catch (e) { return ''; }
}

async function render() {
  const { profilePack, jobPack, lastRun } = await chrome.storage.local.get(['profilePack', 'jobPack', 'lastRun']);
  const tab = await currentTab();

  if (profilePack) {
    const pi = profilePack.profile.personalInformation || {};
    const name = [pi.firstName, pi.lastName].filter(Boolean).join(' ') || 'unnamed';
    const parts = [name, `${profilePack.rules.length} rules`];
    if (profilePack.createdAt) parts.push(`made ${profilePack.createdAt.slice(0, 10)}`);
    $('profile-status').textContent = parts.join(' · ');
  } else {
    $('profile-status').textContent = 'Not loaded';
  }

  if (jobPack) {
    const job = jobPack.job || {};
    $('job-status').textContent = [job.title, job.company].filter(Boolean).join(' @ ') || 'loaded';
    const n = Object.keys(jobPack.answers || {}).length;
    if (n) $('job-status').textContent += ` · ${n} job answers`;
  } else {
    $('job-status').textContent = 'Not loaded';
  }
  $('job-clear').hidden = !jobPack;

  const resume = (jobPack && jobPack.resume) || (profilePack && profilePack.defaultResume);
  $('resume-status').textContent = resume
    ? `Resume: ${resume.filename} (${kb(b64Bytes(resume.base64))}, ${jobPack && jobPack.resume ? 'job pack' : 'profile default'})`
    : 'Resume: none loaded';

  const warn = [];
  if (jobPack && jobPack.job && jobPack.job.url && tab && hostOf(jobPack.job.url) && hostOf(jobPack.job.url) !== hostOf(tab.url)) {
    warn.push(`This job pack is for ${hostOf(jobPack.job.url)}; this tab is ${hostOf(tab.url) || 'not a web page'}.`);
  }
  if (profilePack && profilePack._ruleErrors && profilePack._ruleErrors.length) {
    warn.push(`${profilePack._ruleErrors.length} rule(s) cannot run here: ${profilePack._ruleErrors.map((e) => e.match).join(', ')}`);
  }
  $('pack-warning').hidden = !warn.length;
  $('pack-warning').textContent = warn.join(' ');

  $('fill').disabled = !profilePack;
  if (lastRun && tab && lastRun.tabId === tab.id) renderRun(lastRun);
}

function li(item) {
  const el = document.createElement('li');
  if (item.status === 'info') el.className = 'info';
  const label = document.createElement('div');
  label.className = 'label';
  label.textContent = item.label + (item.required && !item.notice ? ' *' : '');
  const detail = document.createElement('div');
  detail.className = 'detail';
  detail.textContent = item.status === 'filled' ? `${item.value}${item.source ? ' · ' + item.source : ''}` : item.reason || '';
  el.append(label, detail);
  return el;
}

function renderRun(run) {
  const all = run.frames.flatMap((f) => f.items);
  const by = (s) => all.filter((i) => i.status === s);
  const needs = by('needs');
  const infos = by('info');
  const filled = by('filled');
  const skipped = by('skipped');

  $('results').hidden = false;
  $('summary').innerHTML = '';
  for (const [cls, text] of [['filled', `Filled ${filled.length}`], ['needs', `Needs you ${needs.length}`], ['skipped', `Skipped ${skipped.length}`]]) {
    const chip = document.createElement('span');
    chip.className = `chip ${cls}`;
    chip.textContent = text;
    $('summary').append(chip);
  }
  const frames = run.frames.filter((f) => f.items.length || f.error);
  $('frames').textContent = (frames.length ? frames : run.frames)
    .map((f) => `${f.adapter}${f.page ? ' · ' + f.page : ''}${f.top ? '' : ' (iframe)'}${f.error ? ' · error: ' + f.error : ''}`)
    .join(' | ');

  $('needs-block').hidden = !(needs.length || infos.length);
  $('needs-count').textContent = needs.length;
  $('needs-list').replaceChildren(...needs.map(li), ...infos.map(li));
  $('filled-count').textContent = filled.length;
  $('filled-list').replaceChildren(...filled.map(li));
  $('skipped-count').textContent = skipped.length;
  $('skipped-list').replaceChildren(...skipped.map(li));
}

$('profile-file').addEventListener('change', async (e) => {
  showError('');
  try {
    const pack = await readJson(e.target);
    if (!pack) return;
    const ruleErrors = checkProfilePack(pack);
    pack._ruleErrors = ruleErrors;
    await chrome.storage.local.set({ profilePack: pack });
    await render();
  } catch (err) { showError(err.message); }
});

$('job-file').addEventListener('change', async (e) => {
  showError('');
  try {
    const pack = await readJson(e.target);
    if (!pack) return;
    checkJobPack(pack);
    await chrome.storage.local.set({ jobPack: pack });
    await render();
  } catch (err) { showError(err.message); }
});

$('job-clear').addEventListener('click', async () => {
  await chrome.storage.local.remove('jobPack');
  await render();
});

$('fill').addEventListener('click', async () => {
  showError('');
  const tab = await currentTab();
  if (!tab || !/^https?:|^file:/.test(tab.url || '')) { showError('Open the application page first.'); return; }
  $('fill').disabled = true;
  $('fill').textContent = 'Filling…';
  try {
    const res = await chrome.runtime.sendMessage({ type: 'fill', tabId: tab.id });
    if (!res || !res.ok) throw new Error((res && res.error) || 'no answer from the extension');
    renderRun(res.run);
  } catch (err) {
    showError(err.message);
  } finally {
    $('fill').disabled = false;
    $('fill').textContent = 'Fill this page';
  }
});

render().catch((e) => showError(e.message));
