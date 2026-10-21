/*
 * The answer engine: decide the answer for one form field, or say exactly why there isn't one.
 *
 * A line-by-line port of projects/auto-apply/auto_apply/filler/answers.py, so the cloud filler
 * and this extension answer every question the same way:
 *   1. files (resume / cover letter) by field name or label,
 *   2. profile fields by field name (Greenhouse ids) and by anchored label ("First name"),
 *   3. "at least N years" yes/no questions derived from the years-of-experience rule,
 *   4. per-job answers by exact (normalised) label, then the ordered regex rules,
 *      where "ASK" means never answer and a list means alternative option wordings.
 *
 * Extension-only additions (each one only reached where answers.py would say "no approved
 * answer", so they never contradict it), all marked EXT below:
 *   - field types answers.py never sees: lazy dropdowns whose options appear only when opened
 *     ("combobox"), and single consent checkboxes ("checkbox");
 *   - address split into lines ("Address Line 1" gets the street only, not the full address);
 *   - profile fallbacks for city / state / country / LinkedIn / GitHub / website, which the
 *     split Workday-style forms ask for.
 *
 * Pure: no DOM, no chrome.* APIs. Runs in the content script and under `node --test`.
 */
(function (root) {
  'use strict';

  const ASK = 'ASK';

  // Greenhouse's standard field names -> profile path (answers.py _PROFILE_FIELDS).
  const PROFILE_FIELDS = {
    first_name: 'personalInformation.firstName',
    last_name: 'personalInformation.lastName',
    email: 'personalInformation.email',
    phone: 'personalInformation.phone',
  };

  const P = (k) => 'personalInformation.' + k;

  // answers.py _PROFILE_LABELS, tested against the normalised label (anchored at the start).
  const PROFILE_LABELS = [
    [/^(full |legal )?name$/, [P('firstName'), P('lastName')]],
    [/^first name$/, [P('firstName')]],
    [/^last name$/, [P('lastName')]],
    [/^(e ?mail|email address)$/, [P('email')]],
    [/^(phone|phone number|mobile|mobile phone)$/, [P('phone')]],
    [/^(zip|postal)\b/, [P('zipCode')]],
    [/^(please enter your )?(home |street |mailing )?address\b/, [P('address'), P('city'), P('state'), P('zipCode')]],
  ];

  // EXT: checked before PROFILE_LABELS. answers.py's anchored "address" pattern would put the
  // whole "street, city, state zip" into a box labelled "Address Line 1"; Lever/Ashby/Greenhouse
  // never split the address, Workday/iCIMS/Oracle always do.
  const EXT_LABELS_FIRST = [
    [/^(street |home )?address( line)? ?1$/, [P('address')]],
    [/^(street |home )?address( line)? ?2$/, null], // never filled from the profile
  ];

  // EXT: fallbacks used only where answers.py finds no approved answer.
  const EXT_LABELS_FALLBACK = [
    [/^(current )?(city|town)( of residence)?$/, P('city')],
    [/^(state|province|state province|state or province|region|state region)$/, P('state')],
    [/^(country|country region|country of residence)$/, P('country')],
    [/^county$/, P('county')],
    [/^linkedin( profile)?( url)?$/, P('linkedinUrl')],
    [/^github( profile)?( url)?$/, P('githubUrl')],
    [/^(website|personal website|portfolio|portfolio url|website url|personal site)$/, P('website')],
  ];

  // Field types where the answer must name exactly one of the options (answers.py _SINGLE_CHOICE).
  const SINGLE_CHOICE = ['multi_value_single_select', 'native_select', 'radio', 'yesno'];

  const US_STATES = {
    AL: 'Alabama', AK: 'Alaska', AZ: 'Arizona', AR: 'Arkansas', CA: 'California',
    CO: 'Colorado', CT: 'Connecticut', DE: 'Delaware', DC: 'District of Columbia',
    FL: 'Florida', GA: 'Georgia', HI: 'Hawaii', ID: 'Idaho', IL: 'Illinois',
    IN: 'Indiana', IA: 'Iowa', KS: 'Kansas', KY: 'Kentucky', LA: 'Louisiana',
    ME: 'Maine', MD: 'Maryland', MA: 'Massachusetts', MI: 'Michigan', MN: 'Minnesota',
    MS: 'Mississippi', MO: 'Missouri', MT: 'Montana', NE: 'Nebraska', NV: 'Nevada',
    NH: 'New Hampshire', NJ: 'New Jersey', NM: 'New Mexico', NY: 'New York',
    NC: 'North Carolina', ND: 'North Dakota', OH: 'Ohio', OK: 'Oklahoma', OR: 'Oregon',
    PA: 'Pennsylvania', RI: 'Rhode Island', SC: 'South Carolina', SD: 'South Dakota',
    TN: 'Tennessee', TX: 'Texas', UT: 'Utah', VT: 'Vermont', VA: 'Virginia',
    WA: 'Washington', WV: 'West Virginia', WI: 'Wisconsin', WY: 'Wyoming',
  };

  function norm(s) {
    return String(s == null ? '' : s).toLowerCase().replace(/[^a-z0-9]+/g, ' ').trim();
  }

  // Python's str() for the values a rule can hold, so text answers read the same in both fillers.
  function pyStr(v) {
    if (v === true) return 'True';
    if (v === false) return 'False';
    if (v === null || v === undefined) return 'None';
    return String(v);
  }

  function escapeRegex(s) {
    return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  }

  const labelOf = (o) => (typeof o === 'string' ? o : o.label);

  /**
   * The single option label an answer refers to: exact, then prefix, then whole words inside.
   * Whole words only: "No" must not pick "I am not a veteran" because "no" is inside "not".
   * Ambiguous (two options pass the same test) -> null: refuse rather than pick one.
   */
  function matchOption(answer, options) {
    const a = norm(answer);
    const labels = options.map(labelOf);
    const word = new RegExp('(?<![a-z0-9])' + escapeRegex(a) + '(?![a-z0-9])');
    const tests = [
      (l) => norm(l) === a,
      (l) => norm(l).startsWith(a),
      (l) => word.test(norm(l)),
    ];
    for (const test of tests) {
      const hits = labels.filter(test);
      if (hits.length === 1) return hits[0];
      if (hits.length > 1) return null;
    }
    return null;
  }

  /** A rule may list alternatives: the first one that names exactly one option wins. */
  function pickOption(answer, options) {
    const candidates = Array.isArray(answer) ? answer : [answer];
    for (const c of candidates) {
      const hit = matchOption(pyStr(c), options);
      if (hit) return hit;
    }
    return null;
  }

  /**
   * Index of the suggestion that is the place in `value` ("Springfield, IL"), or null
   * (domform.py pick_location): the city must start the suggestion, the state may be a code
   * or a full name. Never "West Springfield" for "Springfield".
   */
  function pickLocation(texts, value) {
    const words = (s) => String(s).toLowerCase().replace(/[^a-z0-9]+/g, ' ').trim();
    const [cityRaw, ...restParts] = String(value).split(',');
    const city = cityRaw.trim();
    const code = (restParts.join(',').split(',')[0] || '').trim().toUpperCase();
    const states = code ? new Set([code, (US_STATES[code] || code).toUpperCase()]) : null;
    for (let i = 0; i < texts.length; i++) {
      const parts = String(texts[i]).split(',').map((x) => x.trim());
      if (words(parts[0]) !== words(city)) continue;
      if (!states || parts.slice(1).some((x) => states.has(x.toUpperCase()))) return i;
    }
    return null;
  }

  /**
   * Python regex -> JavaScript RegExp (case-insensitive, like re.IGNORECASE).
   * Handles the differences a hand-written rule can hit: a leading (?i) flag group, named
   * groups (?P<name>...) and back-references (?P=name), \A and \Z anchors. Anything JavaScript
   * cannot express throws, so a bad rule is reported instead of silently never matching.
   */
  function pyRegex(pattern) {
    let src = String(pattern);
    let flags = 'i';
    const lead = /^\(\?([aiLmsux]+)\)/.exec(src);
    if (lead) {
      src = src.slice(lead[0].length);
      if (lead[1].includes('x')) throw new Error('verbose (?x) patterns are not supported');
      if (lead[1].includes('m')) flags += 'm';
      if (lead[1].includes('s')) flags += 's';
    }
    if (/\(\?[aiLmsux-]+[:)]/.test(src)) throw new Error('inline flags must be at the start');
    if (/\(\?>|[*+?}]\+/.test(src)) throw new Error('atomic groups / possessive quantifiers are not supported');
    if (/\(\?\(/.test(src)) throw new Error('conditional groups are not supported');
    src = src
      .replace(/\(\?P<([A-Za-z_][A-Za-z0-9_]*)>/g, '(?<$1>')
      .replace(/\(\?P=([A-Za-z_][A-Za-z0-9_]*)\)/g, '\\k<$1>')
      .replace(/(^|[^\\])\\A/g, '$1^')
      .replace(/(^|[^\\])\\Z/g, '$1$');
    return new RegExp(src, flags);
  }

  function getPath(obj, dotted) {
    let node = obj;
    for (const key of dotted.split('.')) {
      node = node && typeof node === 'object' && !Array.isArray(node) ? node[key] : undefined;
    }
    return node;
  }

  // `why` is extension-only: a stable code the popup turns into a reason
  // (ask-rule, no-rule, blank-rule, years, no-file, no-option, ok).
  function res(question, field, status, value, source, note, why) {
    return {
      question, field, status,
      value: value === undefined ? null : value,
      source: source || '',
      note: note || '',
      why: why || (status === 'fill' ? 'ok' : ''),
      get blocking() { return !!question.required && ['ask', 'missing', 'no-option'].includes(status); },
    };
  }

  const YES = /^(yes|y|true|i agree|agree|i accept|accept|i acknowledge|acknowledge|i consent|consent|checked|on)\b/i;
  const NO = /^(no|n|false|unchecked|off)\b/i;

  class AnswerBank {
    /**
     * @param profile   the profile JSON (personalInformation, workExperience, education, ...)
     * @param rules     [{match, answer, note}] in priority order
     * @param files     {resume: {filename, base64}|null, cover_letter: ...|null}
     * @param jobAnswers {"exact question label": answer}
     * @param opts      {extras: true} turns on the EXT fallbacks (off = exactly answers.py)
     */
    constructor(profile, rules, files, jobAnswers, opts) {
      this.profile = profile || {};
      this.files = files || {};
      this.extras = !opts || opts.extras !== false;
      this.ruleErrors = [];
      this.rules = [];
      for (const r of rules || []) {
        try {
          this.rules.push({ re: pyRegex(r.match), pattern: r.match, answer: r.answer, note: r.note || '' });
        } catch (e) {
          this.ruleErrors.push({ match: r.match, error: e.message });
        }
      }
      this.jobAnswers = {};
      for (const [k, v] of Object.entries(jobAnswers || {})) this.jobAnswers[norm(k)] = v;
    }

    profileValue(dotted) {
      return getPath(this.profile, dotted);
    }

    profileByLabel(label) {
      const key = norm(label);
      if (this.extras) {
        for (const [pattern, paths] of EXT_LABELS_FIRST) {
          if (pattern.test(key)) {
            if (!paths) return { none: true };
            const v = this.profileValue(paths[0]);
            return v ? String(v) : null;
          }
        }
      }
      for (const [pattern, paths] of PROFILE_LABELS) {
        if (pattern.test(key)) {
          const parts = paths.map((p) => this.profileValue(p));
          if (!parts.every(Boolean)) return null;
          if (parts.length === 4) return `${parts[0]}, ${parts[1]}, ${parts[2]} ${parts[3]}`;
          return parts.map(pyStr).join(' ');
        }
      }
      return null;
    }

    lookup(label) {
      const key = norm(label);
      if (Object.prototype.hasOwnProperty.call(this.jobAnswers, key)) {
        return { answer: this.jobAnswers[key], source: 'job answers', note: '' };
      }
      for (const r of this.rules) {
        r.re.lastIndex = 0;
        if (r.re.test(label)) return { answer: r.answer, source: `rule /${r.pattern}/`, note: r.note };
      }
      return null;
    }

    /** answers.py _years_threshold. `options` null = not known yet (EXT lazy dropdown). */
    yearsThreshold(q, f) {
      const m = /(?:minimum of|at least|\bover)\s+(\d+)\+?\s+years/i.exec(q.label);
      const found = this.lookup('years of experience');
      let first = null;
      if (found) first = Array.isArray(found.answer) && found.answer.length ? found.answer[0] : found.answer;
      if (!m || first === null || first === undefined || !/^\d+/.test(pyStr(first))) return null;
      const asked = parseInt(m[1], 10);
      const have = parseInt(/^\d+/.exec(pyStr(first))[0], 10);
      if (asked > have) {
        const source = `derived: asks ${asked} years, you have ${have}`;
        if (f.options == null) return res(q, f, 'fill', ['No'], source); // EXT: picked once opened
        const hit = matchOption('No', f.options);
        return hit ? res(q, f, 'fill', hit, source) : null;
      }
      return res(q, f, q.required ? 'ask' : 'skip', null, 'years rule',
        `asks ${asked} years; you have ${have} overall — confirm for this skill`, 'years');
    }

    /** EXT: profile values for split address / location / link questions. */
    extraByLabel(label, f) {
      const key = norm(label);
      for (const [pattern, path] of EXT_LABELS_FALLBACK) {
        if (!pattern.test(key)) continue;
        const v = this.profileValue(path);
        if (!v) return null;
        // A location look-up needs the state too, or "Springfield" could be any of 30 towns.
        if (path === P('city') && f && f.type === 'autocomplete' && this.profileValue(P('state'))) {
          return `${v}, ${this.profileValue(P('state'))}`;
        }
        if (path === P('country')) return countryAlternatives(String(v));
        if (path === P('state')) return stateAlternatives(String(v));
        return String(v);
      }
      return null;
    }

    resolveField(q, f) {
      const label = q.label || '';
      const name = f.name || '';
      if (f.type === 'input_file') {
        const lname = label.toLowerCase();
        const kind = name.includes('resume') || lname.includes('resume') ? 'resume'
          : name.includes('cover') || lname.includes('cover') ? 'cover_letter' : name;
        const file = this.files[kind];
        if (file) return res(q, f, 'fill', file, `file:${kind}`);
        return res(q, f, q.required ? 'missing' : 'skip', null, '', `no ${kind} file`, 'no-file');
      }

      if (Object.prototype.hasOwnProperty.call(PROFILE_FIELDS, name)) {
        const v = this.profileValue(PROFILE_FIELDS[name]);
        if (v) return res(q, f, 'fill', pyStr(v), 'profile');
      }
      if (f.type === 'input_text' || f.type === 'textarea') {
        const v = this.profileByLabel(label);
        if (v && v.none) return res(q, f, 'skip', null, 'profile', 'second address line is left blank', 'blank-rule');
        if (v) return res(q, f, 'fill', v, 'profile');
      }

      const lazy = f.type === 'combobox'; // EXT: options known only after opening
      if (SINGLE_CHOICE.includes(f.type) || lazy) {
        const derived = this.yearsThreshold(q, lazy ? { ...f, options: null } : f);
        if (derived) return derived;
      }

      let found = this.lookup(label);
      if (found === null && this.extras) {
        const v = this.extraByLabel(label, f);
        if (v) found = { answer: v, source: 'profile', note: '' };
      }
      if (found === null) {
        return res(q, f, q.required ? 'missing' : 'skip', null, '', 'no approved answer', 'no-rule');
      }
      const { answer, source, note } = found;
      if (answer === null || answer === undefined || answer === '') {
        return res(q, f, q.required ? 'missing' : 'skip', null, source, note || 'rule says leave blank', 'blank-rule');
      }
      if (answer === ASK) {
        return res(q, f, q.required ? 'ask' : 'skip', null, source, note || 'needs your answer', 'ask-rule');
      }

      if (lazy) {
        return res(q, f, 'fill', (Array.isArray(answer) ? answer : [answer]).map(pyStr), source, note);
      }
      if (f.type === 'checkbox') { // EXT: one box ("I agree to the privacy notice")
        const first = pyStr(Array.isArray(answer) ? answer[0] : answer);
        if (YES.test(first)) return res(q, f, 'fill', true, source, note);
        if (NO.test(first)) return res(q, f, 'fill', false, source, note);
        return res(q, f, 'no-option', answer, source, `'${first}' is not a yes/no answer for a checkbox`, 'no-option');
      }
      if (SINGLE_CHOICE.includes(f.type)) {
        const hit = pickOption(answer, f.options || []);
        if (hit === null) {
          return res(q, f, 'no-option', answer, source,
            `'${fmt(answer)}' matches no single option: ${fmt((f.options || []).map(labelOf).slice(0, 8))}`, 'no-option');
        }
        return res(q, f, 'fill', hit, source, note);
      }
      if (f.type === 'multi_value_multi_select') {
        const wanted = Array.isArray(answer) ? answer : [answer];
        const hits = wanted.map((a) => matchOption(pyStr(a), f.options || []));
        if (hits.includes(null)) {
          // A list can also be alternative wordings of one answer: accept exactly one hit.
          const ok = hits.filter(Boolean);
          if (ok.length === 1) return res(q, f, 'fill', ok, source, note);
          return res(q, f, 'no-option', answer, source, `options: ${fmt((f.options || []).map(labelOf).slice(0, 8))}`, 'no-option');
        }
        return res(q, f, 'fill', hits, source, note);
      }
      // A text box: answers.py writes str(answer); for a list of alternative wordings the
      // extension types the first one instead of Python's "['a', 'b']".
      return res(q, f, 'fill', Array.isArray(answer) ? pyStr(answer[0]) : pyStr(answer), source, note);
    }

    plan(questions) {
      const out = [];
      for (const q of questions) {
        let fields = q.fields || [];
        // "Attach or paste" questions offer a file input and a textarea; attaching is enough.
        if (fields.some((f) => f.type === 'input_file')) fields = fields.filter((f) => f.type === 'input_file');
        for (const f of fields) out.push(this.resolveField(q, f));
      }
      return out;
    }
  }

  // Python's repr() of a string, so notes read the same as answers.py's f-strings.
  function pyRepr(x) {
    if (typeof x !== 'string') return pyStr(x);
    const q = x.includes("'") && !x.includes('"') ? '"' : "'";
    let body = x.replace(/\\/g, '\\\\').replace(/\n/g, '\\n').replace(/\r/g, '\\r').replace(/\t/g, '\\t');
    if (q === "'") body = body.replace(/'/g, "\\'");
    return q + body + q;
  }

  function fmt(v) {
    if (Array.isArray(v)) return '[' + v.map(pyRepr).join(', ') + ']';
    return pyStr(v);
  }

  function countryAlternatives(c) {
    const n = norm(c);
    if (['united states', 'united states of america', 'usa', 'us', 'u s', 'u s a'].includes(n)) {
      return [c, 'United States of America', 'United States', 'USA', 'US'];
    }
    return [c];
  }

  function stateAlternatives(s) {
    const up = s.trim().toUpperCase();
    if (US_STATES[up]) return [US_STATES[up], up];
    const code = Object.keys(US_STATES).find((k) => norm(US_STATES[k]) === norm(s));
    return code ? [s, code] : [s];
  }

  /** "May 2023", "05/2023", "2023-05", "2023" -> {month: 5|null, year: 2023|null}. */
  const MONTHS = ['jan', 'feb', 'mar', 'apr', 'may', 'jun', 'jul', 'aug', 'sep', 'oct', 'nov', 'dec'];
  function parseDate(s) {
    const t = String(s || '').trim().toLowerCase();
    if (!t || /^(present|current|now)$/.test(t)) return { month: null, year: null };
    let m = /^([a-z]+)\.?\s+(\d{4})$/.exec(t);
    if (m) {
      const i = MONTHS.indexOf(m[1].slice(0, 3));
      return { month: i >= 0 ? i + 1 : null, year: +m[2] };
    }
    m = /^(\d{1,2})[/.-](\d{4})$/.exec(t);
    if (m) return { month: +m[1], year: +m[2] };
    m = /^(\d{4})[/.-](\d{1,2})(?:[/.-]\d{1,2})?$/.exec(t);
    if (m) return { month: +m[2], year: +m[1] };
    m = /^(\d{4})$/.exec(t);
    if (m) return { month: null, year: +m[1] };
    return { month: null, year: null };
  }

  /** Ways a degree is written on dropdowns, most specific first ("MS" -> "Master of Science", ...). */
  function degreeAlternatives(d) {
    const n = norm(d).replace(/\s+/g, '');
    const groups = [
      [/^(ms|msc|mse|mastersofscience|masterofscience)$/, ['Master of Science', "Master's Degree", 'Masters Degree', 'Master', 'MS', 'M.S.']],
      [/^(ma|masterofarts)$/, ['Master of Arts', "Master's Degree", 'Masters Degree', 'Master', 'MA']],
      [/^(mba)$/, ['MBA', 'Master of Business Administration', "Master's Degree", 'Master']],
      [/^(meng|me|mtech)$/, ['Master of Engineering', 'Master of Technology', "Master's Degree", 'Master']],
      [/^(bs|bsc|bachelorofscience)$/, ['Bachelor of Science', "Bachelor's Degree", 'Bachelors Degree', 'Bachelor', 'BS', 'B.S.']],
      [/^(ba|bachelorofarts)$/, ['Bachelor of Arts', "Bachelor's Degree", 'Bachelors Degree', 'Bachelor', 'BA']],
      [/^(btech|be|beng|bachelorofengineering|bacheloroftechnology)$/, ['Bachelor of Technology', 'Bachelor of Engineering', "Bachelor's Degree", 'Bachelors Degree', 'Bachelor']],
      [/^(phd|doctorate|doctorofphilosophy)$/, ['Doctor of Philosophy', 'PhD', 'Ph.D.', 'Doctorate', 'Doctoral Degree']],
      [/^(aa|as|associate|associates)$/, ["Associate's Degree", 'Associate Degree', 'Associate']],
    ];
    for (const [re, alts] of groups) if (re.test(n)) return [d, ...alts];
    return [d];
  }

  const api = {
    ASK, AnswerBank, matchOption, pickOption, pickLocation, pyRegex, norm, pyStr,
    parseDate, degreeAlternatives, countryAlternatives, stateAlternatives, US_STATES,
  };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.AutofillAnswers = api;
})(typeof globalThis !== 'undefined' ? globalThis : this);
