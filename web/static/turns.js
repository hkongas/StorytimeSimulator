let pendingTurns;
try { pendingTurns = JSON.parse(sessionStorage.getItem('storytime.pendingTurns') || '{}'); }
catch { pendingTurns = {}; }
const pollingTurns = new Set();
let activeTurnEditor = null;
let editorSaving = false;

function openTurnEditor(turn, turnElement) {
  if (isGenerating || activeTurnEditor || editorSaving) return;
  document.getElementById('autoContinue').checked = false;
  const storyId = currentStoryId;
  const revision = currentStoryData.revision;
  const editor = document.createElement('div');
  editor.className = 'turn-editor';
  const textarea = document.createElement('textarea');
  textarea.className = 'styled-input prose-editor-input';
  textarea.value = turn.director_prose;
  textarea.setAttribute('aria-label', 'Vuoron teksti');
  const actions = document.createElement('div');
  actions.className = 'turn-editor-actions';
  const save = document.createElement('button');
  save.className = 'btn btn-primary btn-sm';
  save.textContent = 'Tallenna vain teksti';
  const cancel = document.createElement('button');
  cancel.className = 'btn btn-secondary btn-sm';
  cancel.textContent = 'Peruuta';
  cancel.onclick = () => {
    if (editorSaving) return;
    editor.remove();
    turnElement.querySelectorAll(':scope > p').forEach(paragraph => paragraph.hidden = false);
    activeTurnEditor = null;
    syncTurnControls();
  };
  save.onclick = async () => {
    if (!textarea.value.trim()) return;
    editorSaving = true;
    save.disabled = cancel.disabled = true;
    try {
      const response = await fetch(`/api/stories/${storyId}/turns/${turn.id}`, {
        method: 'PUT', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({prose: textarea.value, expected_revision: revision, sync_state: false})
      });
      if (!response.ok) throw new Error((await response.json()).detail || 'Tallennus epäonnistui.');
      activeTurnEditor = null;
      editorSaving = false;
      await loadStory(storyId);
      turnNotice('Teksti tallennettu. Hahmojen muistit ja maailman tila säilyivät ennallaan.');
    } catch (error) {
      turnNotice(error.message);
    } finally {
      editorSaving = false;
      save.disabled = cancel.disabled = false;
      syncTurnControls();
    }
  };
  actions.append(save, cancel);
  editor.append(textarea, actions);
  turnElement.querySelectorAll(':scope > p').forEach(paragraph => paragraph.hidden = true);
  turnElement.append(editor);
  activeTurnEditor = editor;
  syncTurnControls();
  textarea.focus();
}

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
  const blocked = isGenerating || Boolean(activeTurnEditor) || editorSaving;
  for (const id of ['advanceBtn', 'playerActBtn']) document.getElementById(id).disabled = blocked;
  document.querySelectorAll('.choice-btn, .edit-turn-btn').forEach(button => button.disabled = blocked);
  document.getElementById('undoTurnBtn').disabled = blocked || !currentStoryData?.can_undo;
  document.getElementById('cancelTurnBtn').classList.toggle('hidden', !isGenerating);
  if (!isGenerating) showLiveAgentBar(false);
}

async function advanceStory() {
  const storyId = currentStoryId;
  if (!storyId || pendingTurns[storyId] || activeTurnEditor || editorSaving) return;
  const inputId = currentMode === 'roleplay' ? 'playerInput' : 'readerInput';
  const record = {storyId, payload: {
    request_id: crypto.randomUUID(), mode: currentMode,
    user_input: document.getElementById(inputId).value.trim() || null,
    private_intention: currentMode === 'roleplay' ? document.getElementById('privateIntention').value.trim() || null : null,
    custom_guidance: document.getElementById('worldIntervention').value.trim() || null
  }};
  pendingTurns[storyId] = record;
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
  try {
    const response = await fetch(`/api/stories/${record.storyId}/turn-jobs/${requestId}`);
    if (!response.ok) throw new Error('Työn tilaa ei saatu. Palauta yhteys tai lähetä sama pyyntö uudelleen.');
    const result = await response.json();
    if (pendingTurns[record.storyId]?.payload.request_id !== requestId) return;
    if (result.status === 'running') {
      if (currentStoryId === record.storyId) showLiveAgentBar(true, result.message);
      setTimeout(() => monitorTurn(record), 900);
      return;
    }
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
      if (auto.checked && currentMode !== 'roleplay' && remaining > 0) {
        budget.value = remaining;
        setTimeout(() => { if (currentStoryId === record.storyId && auto.checked) advanceStory(); }, 500);
      } else auto.checked = false;
    } else {
      document.getElementById('autoContinue').checked = false;
      turnNotice(result.message || 'Generointi ei valmistunut.');
    }
  } catch (error) {
    if (currentStoryId === record.storyId) {
      showLiveAgentBar(false);
      document.getElementById('autoContinue').checked = false;
      turnNotice(error.message, true);
    }
  } finally {
    pollingTurns.delete(requestId);
  }
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