const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');
const staticDir = path.join(__dirname, '..', 'web', 'static');

function setup() {
  const progress = {textContent: ''};
  const context = vm.createContext({
    document: {getElementById: () => progress},
    currentStoryData: {
      active_scene: {location_id: 'room', active_character_ids: ['known', 'null', 'hidden', 'away', 'dead']},
      characters: [
        {id: 'known', status: 'active', location_id: 'room', visibility_state: 'visible'},
        {id: 'null', status: 'active', location_id: null},
        {id: 'hidden', status: 'active', location_id: 'room', visibility_state: 'hidden'},
        {id: 'away', status: 'active', location_id: 'street'},
        {id: 'dead', status: 'dead', location_id: 'room'},
      ],
    },
  });
  vm.runInContext(fs.readFileSync(path.join(staticDir, 'simulation.js'), 'utf8'), context);
  vm.runInContext("simulationControls={ended:false,eligible_characters:['known','null','hidden','away','dead'].map(id=>({id})),known_character_ids:[]}", context);
  return {context, progress};
}

test('player choice independently enforces presence, location, status and visibility', () => {
  const {context} = setup();
  assert.equal(context.canSelectPlayerCharacter('known'), true);
  for (const id of ['null', 'hidden', 'away', 'dead']) assert.equal(context.canSelectPlayerCharacter(id), false);
  context.currentStoryData.active_scene.active_character_ids = [];
  assert.equal(context.canSelectPlayerCharacter('known'), false);
});

test('roleplay hides unknown identities and known hidden identities remain unselectable', () => {
  const {context} = setup();
  for (const character of context.currentStoryData.characters.slice(1)) assert.equal(context.canShowRoleplayCharacter(character), false);
  vm.runInContext("simulationControls.known_character_ids=['hidden']", context);
  const hidden = context.currentStoryData.characters[2];
  assert.equal(context.canShowRoleplayCharacter(hidden), true);
  assert.equal(context.canSelectPlayerCharacter('hidden'), false);
  hidden.is_player_controlled = true;
  assert.equal(context.canShowRoleplayCharacter(hidden), true);
});

test('ended story cannot select players and group progress excludes private details', () => {
  const {context, progress} = setup();
  vm.runInContext('simulationControls.ended=true', context);
  assert.equal(context.canSelectPlayerCharacter('known'), false);
  context.renderDecisionProgress({group_index: 0, group_count: 2, group_mode: 'parallel', private_thought: 'secret'});
  assert.equal(progress.textContent, 'Päätösryhmä 1/2 · rinnakkainen');
  assert.ok(!progress.textContent.includes('secret'));
});

test('visibility editor offers the exact backend values and sends them', () => {
  const html = fs.readFileSync(path.join(staticDir, 'index.html'), 'utf8');
  const app = fs.readFileSync(path.join(staticDir, 'app.js'), 'utf8');
  assert.match(html, /id="editCharVisibility"[\s\S]*?value="visible"[\s\S]*?value="hidden"/);
  assert.match(app, /visibility_state: document.getElementById\("editCharVisibility"\).value/);
  assert.match(app, /currentMode === 'roleplay' && !canShowRoleplayCharacter\(c\)/);
});
