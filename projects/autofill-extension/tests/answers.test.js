// Unit tests for the answer engine (content/answers.js). Run: node --test tests/*.test.js
'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');
const fs = require('node:fs');
const A = require('../content/answers.js');

const CANDIDATE = JSON.parse(fs.readFileSync(path.join(__dirname, 'fixtures', 'candidate.json'), 'utf8'));
const RESUME = { filename: 'Alex-Rivera-Resume.pdf', base64: 'JVBERi0=' };

const bank = (opts, files, job) => new A.AnswerBank(CANDIDATE.profile, CANDIDATE.rules,
  files || { resume: RESUME, cover_letter: null }, job || {}, opts);
const q = (label, required, type, options, name) => ({
  label, required: !!required, fields: [{ type, name: name || '', options: options || [] }],
});
const one = (b, question) => b.plan([question])[0];

test('contact fields come from the profile, by Greenhouse name and by anchored label', () => {
  const b = bank();
  assert.equal(one(b, q('First Name', true, 'input_text', [], 'first_name')).value, 'Alex');
  const full = one(b, q('Full name', true, 'input_text'));
  assert.equal(full.value, 'Alex Rivera');
  assert.equal(full.source, 'profile');
  assert.equal(one(b, q('Email', true, 'input_text')).value, 'alex.rivera@example.com');
  assert.equal(one(b, q('Phone', true, 'input_text')).value, '+12175550100');
  assert.equal(one(b, q('Address', false, 'input_text')).value, '100 Main St, Springfield, Illinois 62701');
  const preferred = one(b, q('Preferred name', false, 'input_text'));
  assert.equal(preferred.status, 'skip'); // "Preferred name" is not "Name"
  assert.equal(preferred.why, 'no-rule');
});

test('ASK rule: required -> ask (blocking), optional -> skip; never answered', () => {
  const b = bank();
  const req = one(b, q('Will you now or in the future require sponsorship?', true, 'radio', ['Yes', 'No']));
  assert.equal(req.status, 'ask');
  assert.equal(req.blocking, true);
  assert.equal(req.value, null);
  assert.equal(req.why, 'ask-rule');
  assert.equal(req.note, 'decide per job');
  const opt = one(b, q('Desired salary', false, 'input_text'));
  assert.equal(opt.status, 'skip');
  assert.equal(opt.why, 'ask-rule');
});

test('a list answer is alternative wordings: the first that names exactly one option wins', () => {
  const b = bank();
  const g = one(b, q('Gender', false, 'native_select', ['Male', 'Female', 'Decline To Self Identify']));
  assert.equal(g.status, 'fill');
  assert.equal(g.value, 'Decline To Self Identify');
  const g2 = one(b, q('Gender', false, 'native_select', ['Man', 'Woman', "I don't wish to answer"]));
  assert.equal(g2.value, "I don't wish to answer");
  const v = one(b, q('Veteran status', false, 'native_select', ['I am a veteran', 'I am not a veteran', 'Decline to self-identify']));
  assert.equal(v.status, 'no-option'); // "No" must not match inside "not"; no wording names one option
});

test('lookbehind rule: (?<!trans)gender does not answer the transgender question', () => {
  const b = bank();
  const t = one(b, q('Do you identify as transgender?', true, 'radio', ['Yes', 'No', 'Decline']));
  assert.equal(t.status, 'ask');
  assert.match(t.source, /transgender/);
  assert.match(one(b, q('Gender identity', false, 'radio', ['Male', 'Female', 'Decline'])).source, /\(\?<!trans\)gender/);
});

test('"No" never matches inside "not"; ambiguous matches are refused', () => {
  assert.equal(A.matchOption('No', ['I am a veteran', 'I am not a veteran']), null);
  assert.equal(A.matchOption('not a veteran', ['I am a veteran', 'I am not a veteran']), 'I am not a veteran');
  assert.equal(A.matchOption('Yes', ['Yes, full time', 'Yes, part time']), null);
  assert.equal(A.matchOption('united states', ['United States of America', 'United Kingdom']), 'United States of America');
});

test('years questions: more than you have -> No; fewer -> ask (skill-specific)', () => {
  const b = bank();
  const seven = one(b, q('Do you have a minimum of 7 years of experience building software?', true, 'yesno', ['Yes', 'No']));
  assert.deepEqual([seven.status, seven.value], ['fill', 'No']);
  const two = one(b, q('Do you have at least 2 years of experience with dbt?', true, 'yesno', ['Yes', 'No']));
  assert.equal(two.status, 'ask');
  assert.equal(two.why, 'years');
  const lazy = one(b, q('Do you have at least 10 years of experience?', true, 'combobox', null));
  assert.deepEqual(lazy.value, ['No']); // a dropdown: picked once it is opened
});

test('per-job answers by exact (normalised) label win over rules', () => {
  const b = bank({}, null, { 'Why do you want to work at Acme?': 'I like their data team.', 'How did you hear about us?': 'Referral' });
  assert.equal(one(b, q('Why do you want to work at Acme?*', true, 'textarea')).value, 'I like their data team.'); // punctuation ignored
  assert.equal(one(b, q('Why Acme?', true, 'textarea')).status, 'missing'); // a different label is a different question
  assert.equal(one(b, q('why do you want to work at acme', true, 'textarea')).value, 'I like their data team.');
  const heard = one(b, q('How did you hear about us?', true, 'native_select', ['LinkedIn', 'Referral']));
  assert.equal(heard.value, 'Referral');
  assert.equal(heard.source, 'job answers');
});

test('files: resume from the packs, missing when none', () => {
  const r = one(bank(), q('Resume/CV', true, 'input_file', [], 'resume'));
  assert.equal(r.status, 'fill');
  assert.equal(r.value.filename, 'Alex-Rivera-Resume.pdf');
  const none = one(bank({}, { resume: null }), q('Resume/CV', true, 'input_file', [], 'file-upload-input-ref'));
  assert.equal(none.status, 'missing');
  assert.equal(none.why, 'no-file');
  // "Attach or paste": the textarea next to a file input is dropped.
  const both = bank().plan([{ label: 'Resume', required: true, fields: [{ type: 'input_file', name: 'resume' }, { type: 'textarea', name: 'resume_text' }] }]);
  assert.equal(both.length, 1);
});

test('no rule: required -> missing (needs you), optional -> skip', () => {
  const b = bank();
  assert.equal(one(b, q('Favourite colour', true, 'input_text')).status, 'missing');
  assert.equal(one(b, q('Favourite colour', false, 'input_text')).why, 'no-rule');
});

test('multi-select: all wanted, or exactly one of alternative wordings', () => {
  const b = new A.AnswerBank(CANDIDATE.profile, [
    { match: 'certification', answer: ['CFA'] },
    { match: 'race', answer: ['Decline to self-identify', 'I prefer not to say'] },
  ], {}, {});
  assert.deepEqual(one(b, q('Certifications', false, 'multi_value_multi_select', ['CFA', 'CPA'])).value, ['CFA']);
  assert.deepEqual(one(b, q('Race', false, 'multi_value_multi_select', ['Asian', 'White', 'I prefer not to say'])).value, ['I prefer not to say']);
});

test('extension extras fill split address and location fields only where no rule exists', () => {
  const b = bank();
  assert.equal(one(b, q('Address Line 1', true, 'input_text')).value, '100 Main St');
  assert.equal(one(b, q('Address Line 2', false, 'input_text')).status, 'skip');
  assert.equal(one(b, q('City', true, 'input_text')).value, 'Springfield');
  assert.equal(one(b, q('State', true, 'native_select', ['Idaho', 'Illinois', 'Indiana'])).value, 'Illinois');
  assert.equal(one(b, q('Country', true, 'native_select', ['Canada', 'United States of America'])).value, 'United States of America');
  assert.deepEqual(one(b, q('Country', true, 'combobox', null)).value, ['United States', 'United States of America', 'United States', 'USA', 'US']);
  assert.equal(one(b, q('LinkedIn Profile', false, 'input_text')).value, 'https://www.linkedin.com/in/alex-rivera-example');
  assert.equal(one(b, q('Postal Code', true, 'input_text')).value, '62701');
  const strict = bank({ extras: false });
  assert.equal(one(strict, q('City', true, 'input_text')).status, 'missing'); // exactly answers.py
  assert.equal(one(strict, q('Address Line 1', true, 'input_text')).value, '100 Main St, Springfield, Illinois 62701');
});

test('lazy dropdowns get the candidate list; single checkboxes get true/false', () => {
  const b = bank();
  assert.deepEqual(one(b, q('How Did You Hear About Us?', true, 'combobox', null)).value, ['LinkedIn', 'Job Board']);
  assert.equal(one(b, q('I have read and agree to the privacy notice', true, 'checkbox', ['I agree'])).value, true);
  const ask = one(b, q('Are you legally authorized to work in the US?', true, 'combobox', null));
  assert.deepEqual(ask.value, ['Yes']);
});

test('pyRegex translates Python-only syntax and rejects what JavaScript cannot run', () => {
  assert.ok(A.pyRegex('(?i)^veteran').test('Veteran status'));
  assert.ok(A.pyRegex('(?P<n>\\d+) years (?P=n)').test('5 years 5'));
  assert.ok(A.pyRegex('\\Agender\\Z').test('Gender'));
  assert.ok(!A.pyRegex('\\Agender\\Z').test('Gender identity'));
  assert.throws(() => A.pyRegex('a++'));
  const b = new A.AnswerBank({}, [{ match: '(unclosed', answer: 'x' }, { match: 'ok', answer: 'y' }], {}, {});
  assert.equal(b.ruleErrors.length, 1);
  assert.equal(b.rules.length, 1);
});

test('pickLocation: city must start the suggestion; state by code or name', () => {
  const texts = ['West Springfield, MA, USA', 'Springfield, Missouri, United States', 'Springfield, IL, USA'];
  assert.equal(A.pickLocation(texts, 'Springfield, IL'), 2);
  assert.equal(A.pickLocation(texts, 'Springfield, Missouri'), 1);
  assert.equal(A.pickLocation(['Springfield, Illinois, United States'], 'Springfield, IL'), 0);
  assert.equal(A.pickLocation(texts, 'Chicago, IL'), null);
});

test('dates and degrees for Workday sections', () => {
  assert.deepEqual(A.parseDate('Jun 2024'), { month: 6, year: 2024 });
  assert.deepEqual(A.parseDate('05/2023'), { month: 5, year: 2023 });
  assert.deepEqual(A.parseDate('2021-09'), { month: 9, year: 2021 });
  assert.deepEqual(A.parseDate(''), { month: null, year: null });
  const alts = A.degreeAlternatives('MS');
  assert.equal(alts[0], 'MS');
  assert.equal(A.pickOption(alts, ["Bachelor's Degree", "Master's Degree", 'Doctorate']), "Master's Degree");
  assert.equal(A.pickOption(alts, ['Bachelor of Science', 'Master of Science', 'MBA']), 'Master of Science');
});

test('values print like Python str() so both fillers type the same text', () => {
  const b = new A.AnswerBank({}, [{ match: 'over 18', answer: true }, { match: 'years', answer: 3 }], {}, {});
  assert.equal(one(b, q('Are you over 18?', true, 'input_text')).value, 'True');
  assert.equal(one(b, q('Total years', true, 'input_text')).value, '3');
});
