// Kertojan salaiset tapahtumat, esineet, suhteet sekä juonilangat.

let bibleDraft = null;
let bibleDraftStoryId = null;

function bibleEscape(value) {
  return escapeHtml(value);
}

function bibleCharacterName(id) {
  return currentStoryData?.characters?.find(character => character.id === id)?.name || id;
}

function renderBible(data) {
  const runtime = data.runtime || {};
  const list = items => items?.length
    ? items.map(item => `• ${item}`).join("\n")
    : t("bibleNone");
  document.getElementById("plotThreadsDisplay").textContent = list(runtime.plot_threads);
  document.getElementById("worldFactsDisplay").textContent = list(runtime.world_facts);
  renderBibleWorld(data.bible);
  if (bibleDraft && bibleDraftStoryId !== currentStoryId) stopBibleEdit();
  if (bibleDraft) return;
  renderBibleView(data.bible);
}

function renderBibleView(bible) {
  const container = document.getElementById("bibleDisplay");
  const truths = bible?.secret_truths || [];
  const clocks = bible?.clocks || [];
  const agents = bible?.offscreen_agents || [];
  if (!truths.length && !clocks.length && !agents.length) {
    container.innerHTML = `<p class="text-muted">${bibleEscape(t("bibleEmpty"))}</p>`;
    return;
  }
  const stateLabel = state => t(`bibleState_${state}`);
  container.innerHTML = `
    <h4 class="bible-subheading">${bibleEscape(t("bibleTruths"))}</h4>
    ${truths.map(truth => `
      <div class="bible-card bible-state-${bibleEscape(truth.reveal_state)}">
        <div class="bible-card-head"><span class="bible-badge">${bibleEscape(stateLabel(truth.reveal_state))}</span>
          <code>${bibleEscape(truth.id)}</code></div>
        <p>${bibleEscape(truth.fact)}</p>
        ${truth.discoverable_via ? `<p class="bible-meta">${bibleEscape(t("bibleDiscoverVia"))}: ${bibleEscape(truth.discoverable_via)}</p>` : ""}
        ${truth.related_location_id ? `<p class="bible-meta">${bibleEscape(t("bibleLocation"))}: ${bibleEscape(truth.related_location_id)}</p>` : ""}
        ${truth.revealed_at_turn != null && truth.reveal_state === "revealed" ? `<p class="bible-meta">${bibleEscape(t("bibleRevealedAt"))}: ${bibleEscape(truth.revealed_at_turn)}</p>` : ""}
      </div>`).join("")}
    <h4 class="bible-subheading">${bibleEscape(t("bibleClocks"))}</h4>
    ${clocks.map(clock => `
      <div class="bible-card">
        <div class="bible-card-head"><span class="bible-badge">${bibleEscape(clock.remaining_beats)} ${bibleEscape(t("bibleBeatsLeft"))}</span>
          <code>${bibleEscape(clock.id)}</code>${clock.visible ? ` <span class="bible-meta">${bibleEscape(t("bibleVisible"))}</span>` : ""}</div>
        <p>${bibleEscape(clock.description)}</p>
        ${clock.on_expire_effect ? `<p class="bible-meta">${bibleEscape(t("bibleOnExpire"))}: ${bibleEscape(clock.on_expire_effect)}</p>` : ""}
      </div>`).join("")}
    <h4 class="bible-subheading">${bibleEscape(t("bibleAgents"))}</h4>
    ${agents.map(agent => `
      <div class="bible-card">
        <div class="bible-card-head"><strong>${bibleEscape(agent.name)}</strong> <code>${bibleEscape(agent.id)}</code></div>
        <p>${bibleEscape(agent.goal)}</p>
        ${agent.progress ? `<p class="bible-meta">${bibleEscape(t("bibleProgress"))}: ${bibleEscape(agent.progress)}</p>` : ""}
        ${agent.next_move ? `<p class="bible-meta">${bibleEscape(t("bibleNextMove"))}: ${bibleEscape(agent.next_move)}</p>` : ""}
        ${agent.location ? `<p class="bible-meta">${bibleEscape(t("bibleLocation"))}: ${bibleEscape(agent.location)}</p>` : ""}
        ${agent.visible_to?.length ? `<p class="bible-meta">${bibleEscape(t("bibleVisibleTo"))}: ${bibleEscape(agent.visible_to.map(bibleCharacterName).join(", "))}</p>` : ""}
      </div>`).join("")}`;
}

function renderBibleWorld(bible) {
  const container = document.getElementById("bibleWorldDisplay");
  container.setAttribute("aria-label", t("bibleWorldHeading"));
  const items = bible?.items || [];
  const relationships = bible?.relationships || [];
  const locationName = id => bible?.locations?.find(location => location.id === id)?.name || id;
  const empty = `<p class="text-muted">${bibleEscape(t("bibleNone"))}</p>`;
  container.innerHTML = `
    <p class="bible-warning">${bibleEscape(t("bibleWorldReadOnly"))}</p>
    <h4 class="bible-subheading">${bibleEscape(t("bibleItems"))}</h4>
    ${items.length ? items.map(item => `
      <div class="bible-card">
        <div class="bible-card-head"><strong>${bibleEscape(item.name)}</strong> <code>${bibleEscape(item.id)}</code></div>
        ${item.state ? `<p>${bibleEscape(t("bibleState"))}: ${bibleEscape(item.state)}</p>` : ""}
        ${item.holder_character_id ? `<p class="bible-meta">${bibleEscape(t("bibleHolder"))}: ${bibleEscape(bibleCharacterName(item.holder_character_id))}</p>` : ""}
        ${item.location_id ? `<p class="bible-meta">${bibleEscape(t("bibleLocation"))}: ${bibleEscape(locationName(item.location_id))}</p>` : ""}
        ${!item.holder_character_id && !item.location_id ? `<p class="bible-meta">${bibleEscape(t("bibleUnknownPlacement"))}</p>` : ""}
      </div>`).join("") : empty}
    <h4 class="bible-subheading">${bibleEscape(t("bibleRelationships"))}</h4>
    ${relationships.length ? relationships.map(relation => `
      <div class="bible-card">
        <p><strong>${bibleEscape(bibleCharacterName(relation.character_a))} → ${bibleEscape(bibleCharacterName(relation.character_b))}</strong></p>
        ${relation.attitude ? `<p>${bibleEscape(t("bibleAttitude"))}: ${bibleEscape(relation.attitude)}</p>` : ""}
        ${relation.trust != null ? `<p class="bible-meta">${bibleEscape(t("bibleTrust"))}: ${bibleEscape(relation.trust)} (−1 … 1)</p>` : ""}
        ${relation.summary ? `<p>${bibleEscape(relation.summary)}</p>` : ""}
      </div>`).join("") : empty}`;
}

function startBibleEdit() {
  if (!currentStoryData) return;
  bibleDraft = JSON.parse(JSON.stringify(currentStoryData.bible || {secret_truths: [], clocks: [], offscreen_agents: []}));
  bibleDraftStoryId = currentStoryId;
  document.getElementById("bibleDisplay").classList.add("hidden");
  document.getElementById("editBibleBtn").classList.add("hidden");
  const editor = document.getElementById("bibleEditor");
  editor.classList.remove("hidden");
  renderBibleEditor();
}

function stopBibleEdit() {
  bibleDraft = null;
  document.getElementById("bibleEditor").classList.add("hidden");
  document.getElementById("bibleDisplay").classList.remove("hidden");
  document.getElementById("editBibleBtn").classList.remove("hidden");
  renderBibleView(currentStoryData?.bible);
  renderBibleWorld(currentStoryData?.bible);
}

function bibleField(group, index, field, label, value, {multiline = false, type = "text"} = {}) {
  const attributes = `data-bible-group="${group}" data-bible-index="${index}" data-bible-field="${field}"`;
  const control = multiline
    ? `<textarea class="styled-textarea" rows="3" ${attributes}>${bibleEscape(value)}</textarea>`
    : `<input class="styled-input" type="${type}" ${type === "number" ? 'min="0"' : ""} value="${bibleEscape(value)}" ${attributes}>`;
  return `<label class="bible-field"><span>${bibleEscape(label)}</span>${control}</label>`;
}

function renderBibleEditor() {
  const editor = document.getElementById("bibleEditor");
  const characters = currentStoryData?.characters || [];
  const truths = bibleDraft.secret_truths.map((truth, index) => `
    <div class="bible-card">
      <div class="bible-card-head"><code>${bibleEscape(truth.id)}</code>
        <button type="button" class="btn btn-secondary btn-xs" onclick="removeBibleItem('secret_truths', ${index})">✕</button></div>
      ${bibleField("secret_truths", index, "fact", t("bibleFact"), truth.fact, {multiline: true})}
      ${bibleField("secret_truths", index, "discoverable_via", t("bibleDiscoverVia"), truth.discoverable_via || "", {multiline: true})}
      <label class="bible-field"><span>${bibleEscape(t("bibleState"))}</span>
        <select class="styled-select" data-bible-group="secret_truths" data-bible-index="${index}" data-bible-field="reveal_state">
          ${["hidden", "hinted", "revealed"].map(state => `<option value="${state}" ${truth.reveal_state === state ? "selected" : ""}>${bibleEscape(t(`bibleState_${state}`))}</option>`).join("")}
        </select></label>
      ${bibleField("secret_truths", index, "related_location_id", t("bibleLocation"), truth.related_location_id || "")}
    </div>`).join("");
  const clocks = bibleDraft.clocks.map((clock, index) => `
    <div class="bible-card">
      <div class="bible-card-head"><code>${bibleEscape(clock.id)}</code>
        <button type="button" class="btn btn-secondary btn-xs" onclick="removeBibleItem('clocks', ${index})">✕</button></div>
      ${bibleField("clocks", index, "description", t("bibleDescription"), clock.description, {multiline: true})}
      ${bibleField("clocks", index, "remaining_beats", t("bibleBeatsLeft"), clock.remaining_beats, {type: "number"})}
      ${bibleField("clocks", index, "on_expire_effect", t("bibleOnExpire"), clock.on_expire_effect || "", {multiline: true})}
      <label class="bible-check"><input type="checkbox" data-bible-group="clocks" data-bible-index="${index}" data-bible-field="visible" ${clock.visible ? "checked" : ""}> ${bibleEscape(t("bibleVisible"))}</label>
    </div>`).join("");
  const agents = bibleDraft.offscreen_agents.map((agent, index) => `
    <div class="bible-card">
      <div class="bible-card-head"><code>${bibleEscape(agent.id)}</code>
        <button type="button" class="btn btn-secondary btn-xs" onclick="removeBibleItem('offscreen_agents', ${index})">✕</button></div>
      ${bibleField("offscreen_agents", index, "name", t("bibleName"), agent.name)}
      ${bibleField("offscreen_agents", index, "goal", t("bibleGoal"), agent.goal, {multiline: true})}
      ${bibleField("offscreen_agents", index, "progress", t("bibleProgress"), agent.progress || "", {multiline: true})}
      ${bibleField("offscreen_agents", index, "next_move", t("bibleNextMove"), agent.next_move || "", {multiline: true})}
      ${bibleField("offscreen_agents", index, "location", t("bibleLocation"), agent.location || "")}
      <fieldset class="bible-visible-to"><legend>${bibleEscape(t("bibleVisibleTo"))}</legend>
        ${characters.map(character => `<label class="bible-check"><input type="checkbox" data-bible-group="offscreen_agents" data-bible-index="${index}" data-bible-visible="${bibleEscape(character.id)}" ${(agent.visible_to || []).includes(character.id) ? "checked" : ""}> ${bibleEscape(character.name)}</label>`).join("")}
      </fieldset>
    </div>`).join("");
  editor.innerHTML = `
    <p class="bible-warning">${bibleEscape(t("bibleEditWarning"))}</p>
    <h4 class="bible-subheading">${bibleEscape(t("bibleTruths"))}</h4>${truths}
    <button type="button" class="btn btn-secondary btn-xs" onclick="addBibleItem('secret_truths')">+ ${bibleEscape(t("bibleAdd"))}</button>
    <h4 class="bible-subheading">${bibleEscape(t("bibleClocks"))}</h4>${clocks}
    <button type="button" class="btn btn-secondary btn-xs" onclick="addBibleItem('clocks')">+ ${bibleEscape(t("bibleAdd"))}</button>
    <h4 class="bible-subheading">${bibleEscape(t("bibleAgents"))}</h4>${agents}
    <button type="button" class="btn btn-secondary btn-xs" onclick="addBibleItem('offscreen_agents')">+ ${bibleEscape(t("bibleAdd"))}</button>
    <div class="edit-actions">
      <button type="button" class="btn btn-secondary btn-xs" onclick="stopBibleEdit()">${bibleEscape(t("bibleCancel"))}</button>
      <button type="button" class="btn btn-primary btn-xs" onclick="saveBible()">${bibleEscape(t("bibleSave"))}</button>
    </div>`;
}

function nextBibleId(group, prefix) {
  const used = new Set(bibleDraft[group].map(item => item.id));
  let number = bibleDraft[group].length + 1;
  while (used.has(`${prefix}_${number}`)) number += 1;
  return `${prefix}_${number}`;
}

function addBibleItem(group) {
  if (group === "secret_truths") {
    bibleDraft.secret_truths.push({id: nextBibleId(group, "truth"), fact: "", discoverable_via: "", reveal_state: "hidden", related_location_id: null});
  } else if (group === "clocks") {
    bibleDraft.clocks.push({id: nextBibleId(group, "clock"), description: "", remaining_beats: 5, on_expire_effect: "", visible: false});
  } else {
    bibleDraft.offscreen_agents.push({id: nextBibleId(group, "agent"), name: "", goal: "", progress: "", location: "", next_move: "", visible_to: []});
  }
  renderBibleEditor();
}

function removeBibleItem(group, index) {
  bibleDraft[group].splice(index, 1);
  renderBibleEditor();
}

function updateBibleDraft(event) {
  const target = event.target;
  const group = target.dataset.bibleGroup;
  if (!bibleDraft || !group) return;
  const item = bibleDraft[group][Number(target.dataset.bibleIndex)];
  if (!item) return;
  if (target.dataset.bibleVisible) {
    const visible = new Set(item.visible_to || []);
    target.checked ? visible.add(target.dataset.bibleVisible) : visible.delete(target.dataset.bibleVisible);
    item.visible_to = [...visible];
    return;
  }
  const field = target.dataset.bibleField;
  if (target.type === "checkbox") item[field] = target.checked;
  else if (target.type === "number") item[field] = Math.max(0, parseInt(target.value, 10) || 0);
  else item[field] = target.value;
}

document.addEventListener("input", updateBibleDraft);
document.addEventListener("change", updateBibleDraft);

async function saveBible() {
  if (!currentStoryId || !bibleDraft) return;
  const payload = {
    secret_truths: bibleDraft.secret_truths.map(truth => ({
      id: truth.id, fact: truth.fact.trim(), discoverable_via: (truth.discoverable_via || "").trim(),
      reveal_state: truth.reveal_state, related_location_id: (truth.related_location_id || "").trim() || null
    })),
    clocks: bibleDraft.clocks.map(clock => ({
      id: clock.id, description: clock.description.trim(), remaining_beats: clock.remaining_beats,
      on_expire_effect: (clock.on_expire_effect || "").trim(), visible: Boolean(clock.visible)
    })),
    offscreen_agents: bibleDraft.offscreen_agents.map(agent => ({
      id: agent.id, name: agent.name.trim(), goal: agent.goal.trim(), progress: (agent.progress || "").trim(),
      location: (agent.location || "").trim(), next_move: (agent.next_move || "").trim(), visible_to: agent.visible_to || []
    }))
  };
  try {
    const res = await fetch(`/api/stories/${currentStoryId}/bible`, {
      method: "PUT",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(payload)
    });
    const result = await res.json().catch(() => ({}));
    if (!res.ok) {
      const detail = Array.isArray(result.detail) ? t("bibleInvalid") : result.detail;
      throw new Error(detail || t("bibleSaveFailed"));
    }
    // The PUT endpoint edits secrets only; older responses omit read-only world state.
    currentStoryData.bible = {...currentStoryData.bible, ...result.bible};
    currentStoryData.revision = result.revision;
    stopBibleEdit();
  } catch (err) {
    alert(err.message);
  }
}
