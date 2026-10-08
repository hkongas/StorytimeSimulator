let simulationControls = null;
let simulationMutation = false;
let nullLocationPreview = null;
let simulationLoadSequence = 0;

async function simulationRequest(storyId, path, payload) {
  const response = await fetch(`/api/stories/${encodeURIComponent(storyId)}/simulation/${path}`, payload === undefined
    ? {cache: 'no-store'}
    : {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload)});
  const data = await response.json();
  if (!response.ok) throw new Error(data.detail || 'Tarinan asetusten päivitys epäonnistui.');
  return data;
}

async function loadSimulationControls(storyId) {
  const sequence = ++simulationLoadSequence;
  simulationControls = null;
  nullLocationPreview = null;
  document.getElementById('nullLocationCandidates').replaceChildren();
  document.getElementById('applyNullLocationsBtn').disabled = true;
  renderSimulationControls();
  try {
    const controls = await simulationRequest(storyId, 'controls');
    if (currentStoryId !== storyId || sequence !== simulationLoadSequence) return;
    simulationControls = controls;
    renderSimulationControls();
    filterAndRenderCharacters();
    syncTurnControls();
  } catch (error) {
    if (currentStoryId === storyId) turnNotice(error.message);
  }
}

function renderSimulationControls() {
  const controls = simulationControls;
  const guidance = document.getElementById('plotGuidance');
  guidance.value = controls?.plot_guidance || 'balanced';
  guidance.disabled = !controls || simulationMutation || isGenerating;
  const panel = document.getElementById('playerContinuation');
  panel.classList.toggle('hidden', !controls?.player_failed && !controls?.ended);
  document.getElementById('continuationStatus').textContent = controls?.ended
    ? 'Tarinan lopetus on hyväksytty.'
    : 'Pelaajahahmo ei voi jatkaa. Valitse lopetus, toinen hahmo tai uusi haara aiemmasta tilannekuvasta.';
  const characters = document.getElementById('continuationCharacter');
  characters.replaceChildren(new Option('Valitse kelvollinen hahmo', ''));
  for (const character of controls?.eligible_characters || []) characters.add(new Option(character.name, character.id));
  const snapshots = document.getElementById('continuationSnapshot');
  snapshots.replaceChildren(new Option('Valitse aiempi tilannekuva', ''));
  for (const snapshot of controls?.snapshots || []) snapshots.add(new Option(snapshot.label, snapshot.id));
  document.getElementById('continueCharacterBtn').disabled = simulationMutation || isGenerating || !controls?.player_failed || controls?.ended || !controls?.eligible_characters?.length;
  document.getElementById('endStoryBtn').disabled = simulationMutation || isGenerating || !controls?.player_failed || controls?.ended;
  document.getElementById('branchSnapshotBtn').disabled = simulationMutation || isGenerating || !controls?.snapshots?.length;
  document.getElementById('nullLocationMigration').classList.toggle('hidden', currentMode === 'roleplay');
  document.getElementById('previewNullLocationsBtn').disabled = !controls || simulationMutation || isGenerating;
  document.getElementById('applyNullLocationsBtn').disabled = !nullLocationPreview?.candidates?.length || simulationMutation || isGenerating;
  document.querySelectorAll('#nullLocationCandidates select').forEach(select => select.disabled = simulationMutation || isGenerating);
}

function canSelectPlayerCharacter(characterId) {
  const character = currentStoryData?.characters?.find(item => item.id === characterId);
  const scene = currentStoryData?.active_scene;
  return Boolean(character && scene && character.status === 'active' && character.location_id &&
    character.location_id === scene.location_id && character.visibility_state !== 'hidden' &&
    scene.active_character_ids?.includes(characterId) && !simulationControls?.ended &&
    simulationControls?.eligible_characters?.some(item => item.id === characterId));
}

function canShowRoleplayCharacter(character) {
  if (character.is_player_controlled) return true;
  return Boolean(simulationControls?.known_character_ids?.includes(character.id) || canSelectPlayerCharacter(character.id));
}

async function updatePlotGuidance() {
  if (!simulationControls || simulationMutation || isGenerating) return;
  await mutateSimulation('plot-guidance', {preset: document.getElementById('plotGuidance').value,
    expected_revision: simulationControls.revision});
}

async function mutateSimulation(path, payload) {
  if (simulationMutation || isGenerating) return;
  const storyId = currentStoryId;
  simulationMutation = true;
  syncTurnControls();
  renderSimulationControls();
  try {
    const result = await simulationRequest(storyId, path, payload);
    if (currentStoryId !== storyId) return;
    await loadStory(result.story_id || storyId);
    if (path === 'continuation' && payload.action !== 'end') setMode('roleplay');
  } catch (error) {
    if (currentStoryId === storyId) {
      await loadSimulationControls(storyId);
      turnNotice(error.message);
    }
  } finally {
    simulationMutation = false;
    renderSimulationControls();
    syncTurnControls();
  }
}

async function continuePlayer(action) {
  if (!simulationControls) return;
  const payload = {action, expected_revision: simulationControls.revision};
  if (action === 'choose_character') {
    payload.character_id = document.getElementById('continuationCharacter').value;
    if (!payload.character_id) return turnNotice('Valitse ensin kelvollinen hahmo.');
  }
  if (action === 'branch') {
    payload.snapshot_id = document.getElementById('continuationSnapshot').value;
    if (!payload.snapshot_id) return turnNotice('Valitse ensin tilannekuva.');
  }
  await mutateSimulation('continuation', payload);
}

async function previewNullLocations() {
  const storyId = currentStoryId;
  const container = document.getElementById('nullLocationCandidates');
  container.replaceChildren();
  nullLocationPreview = null;
  document.getElementById('applyNullLocationsBtn').disabled = true;
  try {
    const preview = await simulationRequest(storyId, 'null-locations');
    if (currentStoryId !== storyId) return;
    nullLocationPreview = preview;
    if (!preview.candidates.length) container.textContent = 'Ei tarkistettavia vanhoja null-sijainteja.';
    for (const candidate of preview.candidates) {
      const label = document.createElement('label');
      label.textContent = `${candidate.name}${candidate.ambiguous ? ' — vaatii hyväksynnän' : ''} `;
      const select = document.createElement('select');
      select.dataset.characterId = candidate.character_id;
      select.add(new Option('Jätä sijainti tuntemattomaksi', ''));
      for (const location of candidate.locations) select.add(new Option(location.name, location.id));
      // Nothing is moved until the user explicitly selects and accepts a location.
      label.appendChild(select);
      container.appendChild(label);
    }
    document.getElementById('applyNullLocationsBtn').disabled = !preview.candidates.length;
  } catch (error) {
    if (currentStoryId === storyId) turnNotice(error.message);
  }
}

async function applyNullLocations() {
  if (!nullLocationPreview) return;
  const selections = {};
  document.querySelectorAll('#nullLocationCandidates select').forEach(select => {
    if (select.value) selections[select.dataset.characterId] = select.value;
  });
  if (!Object.keys(selections).length) return turnNotice('Valitse hyväksyttävät sijainnit. Muut jäävät tuntemattomiksi.');
  await mutateSimulation('null-locations', {expected_revision: nullLocationPreview.revision, selections});
}

function renderDecisionProgress(progress) {
  const element = document.getElementById('decisionGroupProgress');
  const group = progress.group_index;
  const count = progress.group_count;
  if (!Number.isInteger(group) || !Number.isInteger(count) || count < 1) return;
  const label = {sequential: 'peräkkäinen', parallel: 'rinnakkainen', combined: 'yhdistetty'}[progress.group_mode] || '';
  element.textContent = `Päätösryhmä ${group + 1}/${count}${label ? ` · ${label}` : ''}`;
}
