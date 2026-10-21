// Reads {profile, rules, files, jobAnswers, extras, questions} on stdin, prints the answer
// engine's resolutions as JSON. Used by test_parity.py to compare with answers.py.
'use strict';
const A = require('../content/answers.js');
let input = '';
process.stdin.on('data', (d) => { input += d; });
process.stdin.on('end', () => {
  const x = JSON.parse(input);
  const bank = new A.AnswerBank(x.profile, x.rules, x.files, x.jobAnswers, { extras: x.extras });
  const out = bank.plan(x.questions).map((r) => ({
    label: r.question.label, type: r.field.type, status: r.status, value: r.value, source: r.source, note: r.note,
  }));
  process.stdout.write(JSON.stringify(out));
});
