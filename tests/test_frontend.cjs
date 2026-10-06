const assert = require('node:assert/strict');
const { execFileSync } = require('node:child_process');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const appPath = path.join(__dirname, '..', 'web', 'static', 'app.js');

if (process.argv.includes('--check-timestamps')) {
  const context = vm.createContext({ document: { addEventListener() {} }, Date });
  vm.runInContext(fs.readFileSync(appPath, 'utf8'), context);
  for (const utc of ['2026-01-06T23:30:45Z', '2026-07-06T23:30:45Z']) {
    for (const seconds of [false, true]) {
      const options = { hour: '2-digit', minute: '2-digit' };
      if (seconds) options.second = '2-digit';
      const expected = new Date(utc).toLocaleTimeString([], options);
      for (const value of [utc, utc.slice(0, -1), utc.slice(0, -1).replace('T', ' '), utc.replace('Z', '.000Z')]) {
        assert.equal(context.formatLocalTimestamp(value, seconds), expected);
      }
    }
  }
  assert.equal(context.formatLocalTimestamp('2026-07-07T02:30:45+03:00', true),
    context.formatLocalTimestamp('2026-07-06 23:30:45', true));
  assert.equal(context.formatLocalTimestamp('not-a-date'), 'not-a-date');
  assert.equal(context.formatLocalTimestamp(null), '-');
  assert.equal(context.formatLocalTimestamp(''), '-');
} else {
  for (const timezone of ['Europe/Helsinki', 'America/New_York', 'UTC']) {
    test(`timestamps use the computer timezone: ${timezone}`, () => {
      execFileSync(process.execPath, [__filename, '--check-timestamps'], {
        env: { ...process.env, TZ: timezone },
        stdio: 'pipe',
      });
    });
  }

  test('catchup is optional and remains separate from historical prose', () => {
    const app = fs.readFileSync(appPath, 'utf8');
    assert.match(app, /data\.character_catchups\?\.\[selectedPlayer\.id\]/);
    assert.match(app, /text\.textContent = catchup\.recap/);
    assert.match(app, /if \(!confirm\(/);
    assert.match(app, /expected_revision: currentStoryData\.revision/);
    assert.match(app, /if \(currentStoryId === storyId\) await loadStory\(storyId\)/);
  });

  test('reading controls and stable tail remain outside generated prose', () => {
    const html = fs.readFileSync(path.join(__dirname, '..', 'web', 'static', 'index.html'), 'utf8');
    const css = fs.readFileSync(path.join(__dirname, '..', 'web', 'static', 'style.css'), 'utf8');
    const app = fs.readFileSync(appPath, 'utf8');
    assert.ok(html.indexOf('class="reading-toolbar"') < html.indexOf('id="storyScrollArea"'));
    assert.ok(html.indexOf('id="storyTail"') > html.indexOf('id="proseStream"'));
    assert.ok(html.indexOf('id="turnProgress"') > html.indexOf('id="storyTail"'));
    assert.ok(html.indexOf('id="choicesContainer"') > html.indexOf('id="storyTail"'));
    assert.match(css, /\.story-tail \{ height: 320px; overflow-y: auto;/);
    assert.match(app, /tail\.prepend\(writingArea\)/);
    assert.match(app, /tail\.querySelector\('\.story-writing-area'\)\?\.remove\(\)/);
    assert.match(css, /\.memory-list \{ max-height: 240px; overflow-y: auto;/);
    assert.match(app, /class="memory-list"[^\n]*tabindex="0" aria-label=/);
  });
}

if (!process.argv.includes('--check-timestamps')) test('extra reaction opt-in is independent of roleplay auto-continue and survives request retry', async () => {
  const turns = fs.readFileSync(path.join(__dirname, '..', 'web', 'static', 'turns.js'), 'utf8');
  const html = fs.readFileSync(path.join(__dirname, '..', 'web', 'static', 'index.html'), 'utf8');
  const checkbox = html.match(/<input[^>]+id="extraReactionCycle"[^>]*>/)[0];
  assert.doesNotMatch(checkbox, /checked|hidden/);
  assert.ok(html.indexOf('id="extraReactionCycle"') < html.indexOf('id="autoControls"'));
  for (const mode of ['novel', 'simulation', 'roleplay']) {
    for (const enabled of [false, true]) {
      const elements = new Map();
      const document = {getElementById(id) {
        if (!elements.has(id)) elements.set(id, {value: '', checked: id === 'extraReactionCycle' && enabled});
        return elements.get(id);
      }};
      let submitted;
      const context = vm.createContext({document, sessionStorage: {getItem() {return null;}},
        addEventListener() {}, crypto: {randomUUID() {return 'request';}}, Date, currentStoryId: 'story', currentMode: mode,
        renderChoices() {}, showTurnProgress() {}, savePendingTurns() {}, syncTurnControls() {}});
      vm.runInContext(turns, context);
      vm.runInContext('savePendingTurns = () => {}; syncTurnControls = () => {}; showTurnProgress = () => {}; submitPendingTurn = async record => { submittedRecord = record; };', context);
      await context.advanceStory();
      submitted = context.submittedRecord;
      assert.equal(submitted.payload.extra_reaction_cycle, enabled);
      assert.equal(submitted.payload.mode, mode);
      document.getElementById('extraReactionCycle').checked = !enabled;
      assert.equal(submitted.payload.extra_reaction_cycle, enabled);
    }
  }
});
