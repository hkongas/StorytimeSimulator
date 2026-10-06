const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const staticDir = path.join(__dirname, '..', 'web', 'static');

function setup(bible = {}) {
  const elements = new Map();
  const element = id => {
    if (!elements.has(id)) elements.set(id, {
      innerHTML: '', textContent: '', attributes: {},
      classList: { add() {}, remove() {} },
      setAttribute(key, value) { this.attributes[key] = value; },
    });
    return elements.get(id);
  };
  const context = vm.createContext({
    currentStoryId: 'story-1',
    currentStoryData: { bible: { secret_truths: [], clocks: [], offscreen_agents: [], ...bible },
      characters: [{ id: 'a', name: 'Alice <A>' }, { id: 'b', name: 'Bob' }] },
    localStorage: { getItem() { return 'fi'; }, setItem() {} },
    document: { addEventListener() {}, getElementById: element, querySelectorAll() { return []; }, documentElement: {} },
    escapeHtml: value => String(value ?? '').replaceAll('&', '&amp;').replaceAll('<', '&lt;')
      .replaceAll('>', '&gt;').replaceAll('"', '&quot;').replaceAll("'", '&#039;'),
    alert(message) { throw new Error(message); },
  });
  for (const file of ['i18n.js', 'bible.js']) vm.runInContext(fs.readFileSync(path.join(staticDir, file), 'utf8'), context);
  return { context, element };
}

const world = {
  items: [
    { id: 'letter', name: '<script>letter</script>', holder_character_id: 'a', location_id: null, state: 'sealed & intact' },
    { id: 'key', name: 'Key', holder_character_id: null, location_id: 'hall', state: '' },
    { id: 'coin', name: 'Coin', holder_character_id: null, location_id: null, state: '' },
  ],
  relationships: [{ character_a: 'a', character_b: 'b', attitude: 'friendly <ally>', trust: 0, summary: 'Old & close friends' }],
  locations: [{ id: 'hall', name: 'Main <hall>' }],
};

test('items and directed relationships render actual fields with escaped names and zero trust', () => {
  const { context, element } = setup(world);
  context.renderBible(context.currentStoryData);
  const html = element('bibleWorldDisplay').innerHTML;
  assert.match(html, /Esineet/);
  assert.match(html, /&lt;script&gt;letter&lt;\/script&gt;/);
  assert.match(html, /sealed &amp; intact/);
  assert.match(html, /Haltija: Alice &lt;A&gt;/);
  assert.match(html, /Paikka: Main &lt;hall&gt;/);
  assert.match(html, /Haltijaa tai paikkaa ei tiedetä/);
  assert.match(html, /Alice &lt;A&gt; → Bob/);
  assert.match(html, /Asenne: friendly &lt;ally&gt;/);
  assert.match(html, /Luottamus: 0 \(−1 … 1\)/);
  assert.match(html, /Old &amp; close friends/);
  assert.doesNotMatch(html, /<script>/);
});

test('missing world state has localized empty sections and language switching rerenders', () => {
  const { context, element } = setup();
  context.renderBible(context.currentStoryData);
  assert.equal((element('bibleWorldDisplay').innerHTML.match(/Ei kirjauksia\./g) || []).length, 2);
  context.setLanguage('en');
  assert.match(element('bibleWorldDisplay').innerHTML, /Items/);
  assert.match(element('bibleWorldDisplay').innerHTML, /Character relationships/);
  assert.equal(element('bibleWorldDisplay').attributes['aria-label'], 'Items and relationships');
});

test('unknown character and location identifiers remain readable', () => {
  const { context, element } = setup({ items: [{ id: 'x', name: 'X', holder_character_id: 'unknown', location_id: 'unknown-place' }],
    relationships: [{ character_a: 'unknown', character_b: 'b', trust: -1 }] });
  context.renderBible(context.currentStoryData);
  assert.match(element('bibleWorldDisplay').innerHTML, /Haltija: unknown/);
  assert.match(element('bibleWorldDisplay').innerHTML, /Paikka: unknown-place/);
  assert.match(element('bibleWorldDisplay').innerHTML, /unknown → Bob/);
  assert.match(element('bibleWorldDisplay').innerHTML, /Luottamus: -1/);
});

test('secret editor roundtrip preserves read-only arrays omitted from PUT response', async () => {
  const { context, element } = setup(world);
  const before = JSON.stringify(world);
  context.startBibleEdit();
  let payload;
  context.fetch = async (url, options) => {
    assert.equal(url, '/api/stories/story-1/bible');
    payload = JSON.parse(options.body);
    return { ok: true, json: async () => ({ bible: payload, revision: 4 }) };
  };
  await context.saveBible();
  assert.deepEqual(Object.keys(payload).sort(), ['clocks', 'offscreen_agents', 'secret_truths']);
  for (const key of ['items', 'relationships', 'locations']) {
    assert.equal(JSON.stringify(context.currentStoryData.bible[key]), JSON.stringify(world[key]));
  }
  assert.equal(JSON.stringify(world), before);
  assert.match(element('bibleWorldDisplay').innerHTML, /Alice &lt;A&gt; → Bob/);
  assert.equal(context.currentStoryData.revision, 4);
});

test('world state refreshes during editing and accepts newer world state from PUT', async () => {
  const { context, element } = setup(world);
  context.startBibleEdit();
  context.currentStoryData.bible.items = [{ id: 'new', name: 'New item', state: 'changed' }];
  context.renderBible(context.currentStoryData);
  assert.match(element('bibleWorldDisplay').innerHTML, /New item/);
  context.fetch = async () => ({ ok: true, json: async () => ({ bible: { secret_truths: [], clocks: [], offscreen_agents: [], items: [] }, revision: 5 }) });
  await context.saveBible();
  assert.equal(context.currentStoryData.bible.items.length, 0);
  assert.doesNotMatch(element('bibleWorldDisplay').innerHTML, /New item/);
});

test('read-only world sections inherit existing secrets and roleplay visibility gates', () => {
  const html = fs.readFileSync(path.join(staticDir, 'index.html'), 'utf8');
  const css = fs.readFileSync(path.join(staticDir, 'style.css'), 'utf8');
  assert.ok(html.indexOf('id="bibleWorldDisplay"') > html.indexOf('id="tabDirector"'));
  assert.ok(html.indexOf('id="bibleWorldDisplay"') < html.indexOf('</aside>', html.indexOf('id="tabDirector"')));
  assert.match(css, /body:not\(\[data-secrets="true"\]\) #tabDirector/);
  assert.match(css, /body\[data-mode="roleplay"\] #tabDirector/);
  assert.doesNotMatch(html.match(/<section id="bibleWorldDisplay"[^>]*>/)[0], /onclick/);
});
