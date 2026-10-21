/*
 * Service worker. The popup asks it to fill a tab; it
 *   1. reads the profile pack and the job pack from chrome.storage.local,
 *   2. injects the content files into every frame of the tab (iCIMS / embedded Greenhouse
 *      forms are iframes on another host),
 *   3. runs AutofillRun in each frame and keeps the frames that found something,
 *   4. stores the combined report as `lastRun` so the popup can show it even if it was closed.
 * Content scripts are injected only when you press Fill: nothing runs on pages otherwise,
 * and nothing is sent anywhere (no fetch / network calls in this extension).
 */
'use strict';

const CONTENT_FILES = [
  'content/answers.js',
  'content/dom.js',
  'content/collect.js',
  'content/adapters/generic.js',
  'content/adapters/workday.js',
  'content/adapters/greenhouse.js',
  'content/adapters/lever-ashby.js',
  'content/adapters/icims.js',
  'content/adapters/smartrecruiters.js',
  'content/adapters/oracle.js',
  'content/content.js',
];

async function fillTab(tabId) {
  const { profilePack, jobPack } = await chrome.storage.local.get(['profilePack', 'jobPack']);
  if (!profilePack) throw new Error('Load a profile pack first.');
  const tab = await chrome.tabs.get(tabId);
  const run1 = (target) => chrome.scripting.executeScript({ target, files: CONTENT_FILES })
    .then(() => chrome.scripting.executeScript({
      target,
      func: (p, j) => globalThis.AutofillRun({ profilePack: p, jobPack: j }),
      args: [profilePack, jobPack || null],
    }));
  let results;
  let note = '';
  try {
    results = await run1({ tabId, allFrames: true });
  } catch (e) {
    // A frame the extension may not touch (an error page, a sandboxed ad) fails the whole
    // all-frames call: fall back to the main frame and say so.
    note = `could not reach every frame (${e.message}); filled the main frame only`;
    results = await run1({ tabId, frameIds: [0] });
  }
  const frames = results
    .map((r) => r.result)
    .filter((f) => f && (f.top || f.items.length || f.error));
  if (note && frames[0]) frames[0].items.unshift({ label: 'Frames', status: 'info', reason: note, notice: true });
  const run = { at: new Date().toISOString(), tabId, url: tab.url, title: tab.title, frames };
  await chrome.storage.local.set({ lastRun: run });
  return run;
}

chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  if (msg && msg.type === 'fill') {
    fillTab(msg.tabId).then(
      (run) => sendResponse({ ok: true, run }),
      (e) => sendResponse({ ok: false, error: e.message || String(e) }),
    );
    return true; // answer asynchronously
  }
  return false;
});
