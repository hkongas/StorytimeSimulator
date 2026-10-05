let pendingTurns;
try { pendingTurns = JSON.parse(sessionStorage.getItem('storytime.pendingTurns') || '{}'); }
catch { pendingTurns = {}; }
const pollingTurns = new Set();
let activeTurnEditor = null;
let editorSaving = false;
let authoredTurn = null;
let authoredBusy = false;

async function openAuthoredTurn() {
  if (!currentStoryId || isGenerating || authoredTurn) return;
  if (!await finishTurnEditor()) return;
  document.getElementById('autoContinue').checked = false;
  authoredTurn = {storyId: currentStoryId, preview: null};
  document.getElementById('authoredStatus').textContent = '';
  document.getElementById('authoredChanges').replaceChildren();
  document.getElementById('authoredPreview').classList.add('hidden');
  document.getElementById('authoredAcceptBtn').classList.add('hidden');
  document.getElementById('authoredAnalyzeBtn').classList.remove('hidden');
  document.getElementById('authoredProse').contentEditable = 'plaintext-only';
  const panel = document.getElementById('authoredTurnModal');
  panel.removeAttribute('aria-modal');
  panel.setAttribute('role', 'region');
  document.querySelector('.story-writing-area').appendChild(panel);
  panel.classList.remove('hidden');
  document.getElementById('authoredProse').focus({preventScroll: true});
  syncTurnControls();
}

async function closeAuthoredTurn() {
  if (authoredBusy) return;
  if (authoredTurn?.preview) {
    const record = authoredTurn;
    try { await fetch(`/api/stories/${record.storyId}/authored-turns/previews/${record.preview.preview_id}`, {method: 'DELETE'}); }
    catch {}
  }
  authoredTurn = null;
  document.getElementById('authoredTurnModal').classList.add('hidden');
  syncTurnControls();
}

function setAuthoredBusy(busy) {
  authoredBusy = busy;
  for (const id of ['authoredAnalyzeBtn', 'authoredAcceptBtn', 'authoredCancelBtn']) document.getElementById(id).disabled = busy;
  document.querySelector('#authoredTurnModal .modal-close').disabled = busy;
  document.getElementById('authoredProse').contentEditable = busy || Boolean(authoredTurn?.preview) ? 'false' : 'plaintext-only';
  syncTurnControls();
}

function renderAuthoredPreview(preview) {
  const changes = document.getElementById('authoredChanges');
  changes.replaceChildren();
  function section(title, lines) {
    const heading = document.createElement('h4');
    heading.textContent = title;
    const list = document.createElement('ul');
    for (const line of lines.length ? lines : ['Ei muutoksia.']) {
      const item = document.createElement('li');
      item.textContent = line;
      list.append(item);
    }
    changes.append(heading, list);
  }
  section('Tapahtumat ja havaitsijat', preview.events.map(event => `${event.description} [${event.witnesses.join(', ') || 'Vain kertoja'}]`));
  section('Hahmojen tilat', preview.character_updates.map(update => `${update.character_id}: ${[
    update.physical_state && `Fyysinen tila: ${update.physical_state}`,
    update.mental_state && `Henkinen tila: ${update.mental_state}`,
    update.status && `Status: ${update.status}`
  ].filter(Boolean).join('; ') || 'Tila ennallaan'}`));
  section('Jatkuvuustiivistelmä', [preview.summary]);
  section('Maailman faktat jatkon jälkeen', preview.world_facts);
  section('Avoimet juonilangat', preview.plot_threads);
  section('Kohtaus', [
    `Paikka: ${preview.scene_location || currentStoryData.active_scene?.location || 'Ennallaan'}`,
    `Tavoite: ${preview.scene_goal || currentStoryData.active_scene?.scene_goal || 'Ennallaan'}`,
    `Läsnä: ${preview.active_character_ids.join(', ') || 'Ei hahmoja'}`,
    `Seuraavat päätöksentekijät: ${preview.decision_character_ids.join(', ') || 'Ei nimetty'}`,
    `Luvun loppu: ${preview.chapter_end ? 'Kyllä' : 'Ei'}`
  ]);
  document.getElementById('authoredPreview').classList.remove('hidden');
  document.getElementById('authoredAnalyzeBtn').classList.add('hidden');
  document.getElementById('authoredAcceptBtn').classList.remove('hidden');
}

async function analyzeAuthoredTurn() {
  if (!authoredTurn || authoredBusy) return;
  const prose = document.getElementById('authoredProse').innerText;
  if (!prose.trim()) return;
  const record = authoredTurn;
  setAuthoredBusy(true);
  document.getElementById('authoredStatus').textContent = 'Analysoidaan tapahtumia ja tilamuutoksia...';
  try {
    const response = await fetch(`/api/stories/${record.storyId}/authored-turns/preview`, {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({prose, expected_revision: currentStoryData.revision})
    });
    if (!response.ok) throw new Error((await response.json()).detail || 'Analyysi epäonnistui.');
    record.preview = await response.json();
    renderAuthoredPreview(record.preview);
    document.getElementById('authoredStatus').textContent = 'Tarkista ehdotus ennen hyväksyntää. Tarinaa ei ole vielä muutettu.';
  } catch (error) {
    document.getElementById('authoredStatus').textContent = error.message;
  } finally { setAuthoredBusy(false); }
}

async function acceptAuthoredTurn() {
  if (!authoredTurn?.preview || authoredBusy) return;
  const record = authoredTurn;
  setAuthoredBusy(true);
  try {
    const response = await fetch(`/api/stories/${record.storyId}/authored-turns/accept`, {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({preview_id: record.preview.preview_id})
    });
    if (!response.ok) throw new Error((await response.json()).detail || 'Tallennus epäonnistui.');
    const result = await response.json();
    authoredTurn = null;
    document.getElementById('authoredTurnModal').classList.add('hidden');
    document.getElementById('authoredProse').textContent = '';
    document.body.appendChild(document.getElementById('authoredTurnModal'));
    setAuthoredBusy(false);
    await loadStory(record.storyId);
    turnNotice(['Oma jatkokappale tallennettu.', ...(result.data.warnings || [])].join(' '));
  } catch (error) {
    document.getElementById('authoredStatus').textContent = error.message;
  } finally { setAuthoredBusy(false); }
}

let inlineSave = null;

async function finishTurnEditor() {
  if (inlineSave) return inlineSave;
  const record = activeTurnEditor;
  if (!record) return true;
  const prose = record.element.innerText;
  if (prose === record.original) {
    record.element.contentEditable = 'false';
    record.element.removeAttribute('role');
    record.element.classList.remove('is-editing');
    activeTurnEditor = null;
    syncTurnControls();
    return true;
  }
  if (!prose.trim()) {
    turnNotice('Kappale ei voi olla tyhjä. Muutoksia ei tallennettu.');
    return false;
  }
  editorSaving = true;
  record.element.contentEditable = 'false';
  syncTurnControls();
  inlineSave = (async () => {
    try {
      const response = await fetch(`/api/stories/${record.storyId}/turns/${record.turn.id}`, {
        method: 'PUT', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({prose, expected_revision: record.revision, sync_state: false})
      });
      if (!response.ok) throw new Error((await response.json()).detail || 'Tallennus epäonnistui.');
      const result = await response.json();
      record.turn.director_prose = prose;
      currentStoryData.revision = result.revision;
      record.element.classList.remove('is-editing');
      record.element.removeAttribute('role');
      activeTurnEditor = null;
      turnNotice('Tekstikorjaus tallennettu.');
      return true;
    } catch (error) {
      record.element.contentEditable = 'true';
      turnNotice(`${error.message} Teksti säilyy muokkaustilassa.`);
      return false;
    } finally {
      editorSaving = false;
      inlineSave = null;
      syncTurnControls();
    }
  })();
  return inlineSave;
}

async function openTurnEditor(turn, turnElement, event) {
  if (isGenerating || authoredTurn) return;
  const element = turnElement.querySelector('.turn-prose');
  if (activeTurnEditor?.element === element) return;
  let caret;
  if (event && document.caretPositionFromPoint) {
    const position = document.caretPositionFromPoint(event.clientX, event.clientY);
    if (position && element.contains(position.offsetNode)) caret = {node: position.offsetNode, offset: position.offset};
  } else if (event && document.caretRangeFromPoint) {
    const range = document.caretRangeFromPoint(event.clientX, event.clientY);
    if (range && element.contains(range.startContainer)) caret = {node: range.startContainer, offset: range.startOffset};
  }
  if (!await finishTurnEditor()) return;
  document.getElementById('autoContinue').checked = false;
  element.contentEditable = 'plaintext-only';
  element.classList.add('is-editing');
  element.setAttribute('role', 'textbox');
  element.setAttribute('aria-label', 'Vuoron teksti');
  element.setAttribute('aria-multiline', 'true');
  activeTurnEditor = {element, turn, storyId: currentStoryId, revision: currentStoryData.revision, original: element.innerText};
  element.onblur = () => { finishTurnEditor(); };
  element.onpaste = event => {
    event.preventDefault();
    document.execCommand('insertText', false, event.clipboardData.getData('text/plain'));
  };
  element.focus({preventScroll: true});
  if (caret?.node.isConnected) {
    const range = document.createRange();
    range.setStart(caret.node, caret.offset);
    range.collapse(true);
    const selection = getSelection();
    selection.removeAllRanges();
    selection.addRange(range);
  }
  syncTurnControls();
}

addEventListener('beforeunload', event => {
  if (activeTurnEditor || authoredTurn || editorSaving) {
    event.preventDefault();
    event.returnValue = '';
  }
});

async function undoLastTurn() {
  if (!currentStoryId || isGenerating || activeTurnEditor || editorSaving || !currentStoryData?.can_undo) return;
  document.getElementById('autoContinue').checked = false;
  if (!confirm('Kumotaanko viimeisin vuoro ja palautetaanko sitä edeltävä tarinan tila? Mallikutsujen kustannuksia ei palauteta.')) return;
  const storyId = currentStoryId;
  editorSaving = true;
  syncTurnControls();
  try {
    const response = await fetch(`/api/stories/${storyId}/turns/undo`, {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({expected_revision: currentStoryData.revision})
    });
    if (!response.ok) throw new Error((await response.json()).detail || 'Kumoaminen epäonnistui.');
    editorSaving = false;
    await loadStory(storyId);
    turnNotice('Viimeisin vuoro kumottu.');
  } catch (error) {
    turnNotice(error.message);
  } finally {
    editorSaving = false;
    syncTurnControls();
  }
}

function savePendingTurns() {
  sessionStorage.setItem('storytime.pendingTurns', JSON.stringify(pendingTurns));
}

function turnNotice(message, retry = false) {
  document.getElementById('turnNotice').textContent = message;
  document.getElementById('retryTurnBtn').classList.toggle('hidden', !retry);
}

function syncTurnControls() {
  isGenerating = Boolean(pendingTurns[currentStoryId]);
  const blocked = isGenerating || Boolean(activeTurnEditor) || editorSaving || Boolean(authoredTurn);
  document.querySelectorAll('.segment-btn').forEach(button => button.disabled = blocked);
  document.getElementById('readingView').disabled = blocked || currentMode === 'roleplay';
  document.getElementById('showRecaps').disabled = blocked;
  for (const id of ['advanceBtn', 'playerActBtn']) document.getElementById(id).disabled = blocked;
  for (const id of ['readerInput', 'playerInput', 'privateIntention', 'worldIntervention']) {
    document.getElementById(id).disabled = blocked;
  }
  document.querySelectorAll('.choice-btn, .edit-turn-btn').forEach(button => button.disabled = blocked);
  document.getElementById('undoTurnBtn').disabled = blocked || !currentStoryData?.can_undo;
  const cancel = document.getElementById('cancelTurnBtn');
  document.getElementById(currentMode === 'roleplay' ? 'playerControls' : 'readerControls').appendChild(cancel);
  cancel.classList.toggle('hidden', !isGenerating);
  document.getElementById('advanceBtn').classList.toggle('hidden', isGenerating && currentMode !== 'roleplay');
  document.getElementById('playerActBtn').classList.toggle('hidden', isGenerating && currentMode === 'roleplay');
  if (!isGenerating) showLiveAgentBar(false);
  document.querySelector('.story-writing-area')?.classList.toggle('hidden', isGenerating);
}

async function advanceStory() {
  const storyId = currentStoryId;
  if (!storyId || pendingTurns[storyId] || activeTurnEditor || editorSaving || authoredTurn) return;
  const inputId = currentMode === 'roleplay' ? 'playerInput' : 'readerInput';
  const record = {storyId, payload: {
    request_id: crypto.randomUUID(), mode: currentMode,
    user_input: document.getElementById(inputId).value.trim() || null,
    private_intention: currentMode === 'roleplay' ? document.getElementById('privateIntention').value.trim() || null : null,
    custom_guidance: document.getElementById('worldIntervention').value.trim() || null
  }};
  pendingTurns[storyId] = record;
  record.startedAt = Date.now();
  renderChoices([]);
  showTurnProgress(record);
  savePendingTurns();
  syncTurnControls();
  await submitPendingTurn(record);
}

async function submitPendingTurn(record) {
  try {
    if (currentStoryId === record.storyId) turnNotice('');
    const response = await fetch(`/api/stories/${record.storyId}/turn-jobs`, {
      method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(record.payload)
    });
    if (!response.ok) {
      const error = await response.json();
      if (response.status >= 400 && response.status < 500) {
        delete pendingTurns[record.storyId];
        savePendingTurns();
      }
      throw new Error(error.detail || 'Generointi ei käynnistynyt.');
    }
    monitorTurn(record);
  } catch (error) {
    if (currentStoryId === record.storyId) {
      syncTurnControls();
      showLiveAgentBar(false);
      turnNotice(error.message, Boolean(pendingTurns[record.storyId]));
    }
  }
}

async function monitorTurn(record) {
  const requestId = record.payload.request_id;
  if (pendingTurns[record.storyId]?.payload.request_id !== requestId) return;
  if (pollingTurns.has(requestId)) return;
  pollingTurns.add(requestId);
  let clock;
  try {
    const result = await new Promise((resolve, reject) => {
      if (currentStoryId === record.storyId) showTurnProgress(record);
      const source = new EventSource(`/api/stories/${record.storyId}/turn-jobs/${requestId}/events`);
      clock = setInterval(() => {
        if (currentStoryId === record.storyId) document.getElementById('turnElapsed').textContent = `${Math.max(0, Math.floor((Date.now() - (record.startedAt || Date.now())) / 1000))} s`;
      }, 1000);
      source.addEventListener('progress', event => {
        const progress = JSON.parse(event.data);
        if (currentStoryId === record.storyId) {
          showLiveAgentBar(true, progress.message);
        }
      });
      source.addEventListener('result', event => { source.close(); resolve(JSON.parse(event.data)); });
      source.onerror = () => {
        source.close();
        reject(new Error('Seurantayhteys katkesi. Palauta yhteys jatkaaksesi saman työn seurantaa.'));
      };
    });
    if (pendingTurns[record.storyId]?.payload.request_id !== requestId) return;
    delete pendingTurns[record.storyId];
    savePendingTurns();
    if (currentStoryId !== record.storyId) return;
    syncTurnControls();
    if (result.status === 'completed') {
      const inputId = record.payload.mode === 'roleplay' ? 'playerInput' : 'readerInput';
      if (document.getElementById(inputId).value.trim() === (record.payload.user_input || '')) document.getElementById(inputId).value = '';
      if (document.getElementById('worldIntervention').value.trim() === (record.payload.custom_guidance || '')) document.getElementById('worldIntervention').value = '';
      if (document.getElementById('privateIntention').value.trim() === (record.payload.private_intention || '')) document.getElementById('privateIntention').value = '';
      await loadStory(record.storyId);
      turnNotice((result.data.warnings || []).join(' '));
      const auto = document.getElementById('autoContinue');
      const budget = document.getElementById('autoBudget');
      const remaining = Math.min(10, Math.max(1, Number(budget.value) || 1)) - 1;
      if (auto.checked && currentMode !== 'roleplay' && !result.data.requires_player_input && remaining > 0) {
        budget.value = remaining;
        setTimeout(() => { if (currentStoryId === record.storyId && auto.checked) advanceStory(); }, 500);
      } else auto.checked = false;
    } else {
      document.getElementById('autoContinue').checked = false;
      turnNotice(result.message || 'Generointi ei valmistunut.');
    }
  } catch (error) {
    if (currentStoryId === record.storyId) {
      showLiveAgentBar(true, 'Seurantayhteys katkesi.');
      document.getElementById('autoContinue').checked = false;
      turnNotice(error.message, true);
    }
  } finally {
    clearInterval(clock);
    pollingTurns.delete(requestId);
  }
}

function showTurnProgress(record) {
  renderChoices([]);
  showLiveAgentBar(true, 'Valmistellaan vuoroa...');
  const submittedAction = [record.payload.user_input,
    record.payload.custom_guidance && `Maailmanmuutos: ${record.payload.custom_guidance}`].filter(Boolean).join('\n');
  const submittedActionElement = document.getElementById('submittedAction');
  submittedActionElement.textContent = submittedAction;
  submittedActionElement.classList.toggle('hidden', !submittedAction);
  document.getElementById('turnElapsed').textContent = '';
  document.querySelector('.story-writing-area')?.classList.add('hidden');
}

function resumePendingTurn(storyId) {
  syncTurnControls();
  turnNotice('');
  const record = pendingTurns[storyId];
  if (record) monitorTurn(record);
}

function retryPendingTurn() {
  const record = pendingTurns[currentStoryId];
  if (record) submitPendingTurn(record);
}

async function cancelPendingTurn() {
  document.getElementById('autoContinue').checked = false;
  const record = pendingTurns[currentStoryId];
  if (!record) return;
  try {
    const response = await fetch(`/api/stories/${record.storyId}/turn-jobs/${record.payload.request_id}`, {method: 'DELETE'});
    if (!response.ok) throw new Error('Keskeytyspyyntö epäonnistui.');
    turnNotice('Keskeytetään...');
    monitorTurn(record);
  } catch (error) {
    turnNotice(error.message, true);
  }
}