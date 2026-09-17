// StorytimeSimulator / Tarinamoottori – Frontend Sovelluslogiikka (v3.0 Modern UI)

let currentStoryId = null;
let currentStoryData = null;
let currentMode = "novel";
let selectedCharacterId = null;
let isGenerating = false;
let isCreatingStory = false;
let importedJsonCache = null;
let activeCharFilter = "active"; // 'active', 'all', 'archived'

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, character => ({"&":"&amp;", "<":"&lt;", ">":"&gt;", '"':"&quot;", "'":"&#39;"}[character]));
}

// --- Alustus kun sivu latautuu ---
document.addEventListener("DOMContentLoaded", () => {
  if (typeof applyTranslations === "function") applyTranslations();
  loadThemeFromStorage();
  initSidebarState();
  document.querySelectorAll('.form-group').forEach(group => {
    const label = group.querySelector('label');
    const input = group.querySelector('input[id], textarea[id], select[id]');
    if (label && input && !label.htmlFor) label.htmlFor = input.id;
  });
  document.querySelectorAll('.modal-backdrop').forEach(modal => {
    modal.setAttribute('role', 'dialog');
    modal.setAttribute('aria-modal', 'true');
    const heading = modal.querySelector('h2');
    if (heading) {
      heading.id = heading.id || `${modal.id}Heading`;
      modal.setAttribute('aria-labelledby', heading.id);
    }
    modal.querySelector('.modal-close')?.setAttribute('aria-label', 'Sulje ikkuna');
    let previousFocus;
    new MutationObserver(() => {
      if (!modal.classList.contains('hidden')) {
        previousFocus = document.activeElement;
        const input = [...modal.querySelectorAll('input:not([type="hidden"]), textarea, select, button')].find(element => element.offsetParent && !element.disabled);
        input?.focus();
      } else previousFocus?.focus();
    }).observe(modal, {attributes: true, attributeFilter: ['class']});
    modal.addEventListener('keydown', event => {
      if (event.key === 'Escape') {
        if (modal.id === 'settingsModal') closeSettingsModal();
        else modal.classList.add('hidden');
      }
      if (event.key === 'Tab') {
        const controls = [...modal.querySelectorAll('button, input, select, textarea, [tabindex="0"]')].filter(element => element.offsetParent && !element.disabled);
        const first = controls[0], last = controls[controls.length - 1];
        if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
        else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
      }
    });
  });
  if (matchMedia("(max-width: 1100px)").matches) {
    document.getElementById("appSidebar").classList.add("collapsed");
    document.getElementById("inspectorPanel").classList.add("collapsed");
  }
  loadStoryList();
  loadSettings();
  loadToneProfilesForNewStory();

  // Enter-painikkeen tuki syötekentissä
  document.getElementById("readerInput")?.addEventListener("keydown", (e) => {
    if (e.key === "Enter") advanceStory();
  });
  document.getElementById("playerInput")?.addEventListener("keydown", (e) => {
    if (e.key === "Enter") advanceStory();
  });
  document.getElementById("directorInput")?.addEventListener("keydown", (e) => {
    if (e.key === "Enter") advanceStory();
  });

  ["settingAzureEndpoint", "settingDirectorModel", "settingCharModel"].forEach((elementId) => {
    document.getElementById(elementId)?.addEventListener("input", updateTemperatureControls);
  });
});

// --- Sivupalkin tila ja kutistus ---
function initSidebarState() {
  const isCollapsed = localStorage.getItem("storytime.sidebarCollapsed") === "true";
  if (isCollapsed) {
    document.getElementById("appSidebar")?.classList.add("collapsed");
  }
}

function toggleSidebar() {
  const sidebar = document.getElementById("appSidebar");
  if (!sidebar) return;
  sidebar.classList.toggle("collapsed");
  localStorage.setItem("storytime.sidebarCollapsed", sidebar.classList.contains("collapsed"));
}

function toggleInspector() {
  const panel = document.getElementById("inspectorPanel");
  if (!panel) return;
  panel.classList.toggle("collapsed");
}

// --- Väriteemojen hallinta ---
function loadThemeFromStorage() {
  const saved = localStorage.getItem("storytime.theme") || "amber";
  setAccentTheme(saved, false);
}

function setAccentTheme(themeName, saveToStory = true) {
  document.body.className = `theme-${themeName}`;
  localStorage.setItem("storytime.theme", themeName);

  // Jos tarina on auki, tallennetaan teema myös tarinan tietoihin
  if (saveToStory && currentStoryId) {
    fetch(`/api/stories/${currentStoryId}/meta`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ theme_color: themeName })
    }).catch(err => console.warn("Teeman tallennus tarinaan epäonnistui:", err));
  }
}

function applyStoryTheme(genre, explicitTheme) {
  if (explicitTheme) {
    setAccentTheme(explicitTheme, false);
    return;
  }
  if (!genre) return;
  const g = genre.toLowerCase();
  if (g.includes("kyber") || g.includes("cyber") || g.includes("futur")) {
    setAccentTheme("cyan", false);
  } else if (g.includes("kauhu") || g.includes("trilleri") || g.includes("veri") || g.includes("murha")) {
    setAccentTheme("crimson", false);
  } else if (g.includes("sci-fi") || g.includes("scifi") || g.includes("avaruus")) {
    setAccentTheme("blue", false);
  } else if (g.includes("metsä") || g.includes("erämaa") || g.includes("luonto")) {
    setAccentTheme("emerald", false);
  } else if (g.includes("fantasia") || g.includes("taika") || g.includes("mystiikka")) {
    setAccentTheme("purple", false);
  } else if (g.includes("noir") || g.includes("salapoliisi") || g.includes("historia") || g.includes("christie")) {
    setAccentTheme("amber", false);
  }
}

// --- Tarinalistan ja Tarinan lataus ---

async function loadStoryList() {
  try {
    const res = await fetch("/api/stories");
    const data = await res.json();
    const listContainer = document.getElementById("sidebarStoryList");
    if (!listContainer) return;
    listContainer.innerHTML = "";

    if (data.stories && data.stories.length > 0) {
      data.stories.forEach(s => {
        const item = document.createElement("div");
        item.className = `sidebar-story-item ${s.id === currentStoryId ? 'active' : ''}`;
        item.onclick = (e) => {
          if (e.target.closest('.btn-delete-story')) return;
          loadStory(s.id);
        };

        item.innerHTML = `
          <div class="story-item-text" title="${escapeHtml(s.title)} (${escapeHtml(s.genre)})">${escapeHtml(s.title)}</div>
          <button class="btn-delete-story" title="Poista tarina">✕</button>
        `;
        item.querySelector("button").onclick = event => deleteStory(s.id, event);
        item.tabIndex = 0;
        item.setAttribute("role", "button");
        item.onkeydown = event => { if (event.target === item && event.key === "Enter") loadStory(s.id); };
        listContainer.appendChild(item);
      });

      // Jos mikään tarina ei ole vielä valittuna, valitaan uusin
      if (!currentStoryId && data.stories.length > 0) {
        loadStory(data.stories[0].id);
      }
    } else {
      listContainer.innerHTML = `<p class="text-muted" style="padding: 10px; font-size: 0.8rem;">Ei tarinoita vielä.</p>`;
    }
  } catch (err) {
    console.error("Virhe ladattaessa tarinalistaa:", err);
  }
}

async function loadStory(storyId) {
  if (!storyId) return;
  if (storyId !== currentStoryId) document.getElementById('autoContinue').checked = false;
  currentStoryId = storyId;

  // Päivitetään aktiivinen luokka sivupalkkiin
  document.querySelectorAll(".sidebar-story-item").forEach(el => {
    el.classList.toggle("active", el.querySelector(".story-item-text")?.textContent === storyId);
  });

  try {
    const res = await fetch(`/api/stories/${storyId}`);
    if (!res.ok) throw new Error("Tarinaa ei voitu ladata");
    const data = await res.json();
    if (currentStoryId !== storyId) return;
    currentStoryData = data;

    setMode(localStorage.getItem(`storytime.mode.${storyId}`) || data.runtime?.mode || "novel");
    renderStoryView(data);
    renderInspector(data);
    resumePendingTurn(storyId);
    loadStoryList(); // Päivitetään aktiivinen merkintä listaan
    updateTokenStats(storyId);
  } catch (err) {
    console.error("Virhe ladattaessa tarinaa:", err);
    alert(err.message);
  }
}

function renderStoryView(data) {
  const meta = data.meta;
  document.getElementById("storyTitle").textContent = meta.title;
  
  const genreTextEl = document.getElementById("storyGenreText");
  if (genreTextEl) genreTextEl.textContent = meta.genre || "-";
  
  const toneBadge = document.getElementById("storyToneBadge");
  if (meta.tone_profile) {
    toneBadge.textContent = meta.tone_profile.replace("_", " ");
    toneBadge.classList.remove("hidden");
  } else {
    toneBadge.classList.add("hidden");
  }

  document.getElementById("deleteCurrentStoryBtn")?.classList.remove("hidden");
  document.getElementById("emptyStoryNotice")?.classList.add("hidden");

  // Teeman automaattinen sovitus tarinalle
  applyStoryTheme(meta.genre, meta.theme_color);

  // Päivitetään aktiivinen pelaajahahmo
  updateActivePlayerBadge(data.characters);

  const stream = document.getElementById("proseStream");
  stream.classList.remove("hidden");
  stream.innerHTML = "";
  renderChoices([]);

  if (data.turns && data.turns.length > 0) {
    data.turns.forEach(turn => {
      appendTurnToView(turn, false);
    });
    const lastTurn = data.turns[data.turns.length - 1];
    if (lastTurn && lastTurn.choices && lastTurn.choices.length > 0) {
      renderChoices(lastTurn.choices);
    }
  }

  scrollStoryToBottom();
}

function appendTurnToView(turn, animate = true) {
  const stream = document.getElementById("proseStream");
  const turnEl = document.createElement("div");
  turnEl.className = "prose-block turn-block";

  // Lisätään tyylikäs vuoro- ja aikaleimaotsake
  const headerEl = document.createElement("div");
  headerEl.className = "turn-header";
  
  const leftGroup = document.createElement("div");
  leftGroup.className = "turn-header-left";
  
  const turnTag = document.createElement("span");
  turnTag.className = "turn-number-tag";
  turnTag.textContent = `Vuoro ${turn.turn_index || 1}`;
  leftGroup.appendChild(turnTag);

  if (turn.acting_character_id) {
    const actorTag = document.createElement("span");
    actorTag.className = "turn-actor-tag";
    actorTag.textContent = `• ${turn.acting_character_id}`;
    leftGroup.appendChild(actorTag);
  }
  headerEl.appendChild(leftGroup);

  const timeTag = document.createElement("span");
  timeTag.className = "turn-timestamp";
  if (turn.created_at) {
    const d = new Date(turn.created_at);
    timeTag.textContent = !isNaN(d.getTime())
      ? d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
      : turn.created_at;
  } else {
    timeTag.textContent = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  }
  headerEl.appendChild(timeTag);

  turnEl.appendChild(headerEl);

  const paragraphs = (turn.director_prose || "").split("\n\n").filter(p => p.trim().length > 0);
  paragraphs.forEach(p => {
    const pEl = document.createElement("p");
    pEl.textContent = p.trim();
    turnEl.appendChild(pEl);
  });

  stream.appendChild(turnEl);
}

function renderChoices(choices) {
  const container = document.getElementById("choicesContainer");
  const buttonsEl = document.getElementById("choicesButtons");
  buttonsEl.innerHTML = "";

  if (!choices || choices.length === 0) {
    container.classList.add("hidden");
    return;
  }

  choices.forEach(choiceText => {
    const btn = document.createElement("button");
    btn.className = "choice-btn";
    btn.textContent = choiceText;
    btn.onclick = () => selectChoice(choiceText);
    buttonsEl.appendChild(btn);
  });

  container.classList.remove("hidden");
  scrollStoryToBottom();
}

function selectChoice(text) {
  document.getElementById(currentMode === "roleplay" ? "playerInput" : "readerInput").value = text;
  advanceStory();
}

function scrollStoryToBottom() {
  const container = document.getElementById("storyScrollArea");
  setTimeout(() => {
    container.scrollTop = container.scrollHeight;
  }, 60);
}

// --- Tarinan poisto ---

async function deleteStory(storyId, event) {
  if (event) event.stopPropagation();
  if (!confirm("Haluatko varmasti poistaa tämän tarinan? Toimintoa ei voi perua.")) return;

  try {
    const res = await fetch(`/api/stories/${storyId}`, { method: "DELETE" });
    if (!res.ok) throw new Error("Tarinan poisto epäonnistui");

    if (currentStoryId === storyId) {
      currentStoryId = null;
      currentStoryData = null;
      document.getElementById("storyTitle").textContent = "Valitse tai luo tarina";
      document.getElementById("storyToneBadge").classList.add("hidden");
      document.getElementById("storyGenreText").textContent = "-";
      document.getElementById("proseStream").innerHTML = "";
      document.getElementById("proseStream").classList.add("hidden");
      document.getElementById("choicesContainer").classList.add("hidden");
      document.getElementById("emptyStoryNotice").classList.remove("hidden");
      document.getElementById("deleteCurrentStoryBtn").classList.add("hidden");
    }

    await loadStoryList();
  } catch (err) {
    alert("Virhe: " + err.message);
  }
}

function deleteCurrentActiveStory() {
  if (currentStoryId) {
    deleteStory(currentStoryId);
  }
}

// --- Inspector, Lennosta muokkaus & Hahmolista ---

function renderInspector(data) {
  const meta = data.meta;
  document.getElementById("worldLoreDisplay").textContent = meta.world_lore || "Ei maailmankuvausta saatavilla.";
  document.getElementById("worldLoreInput").value = meta.world_lore || "";
  document.getElementById("storyGenreText").textContent = meta.genre || "-";

  document.getElementById("directorPlotDisplay").textContent = meta.director_plot_arc || "Ei juonisuunnitelmaa.";
  document.getElementById("directorPlotInput").value = meta.director_plot_arc || "";

  document.getElementById("directorNotesDisplay").textContent = meta.director_notes || "Ei muistiinpanoja.";
  document.getElementById("directorNotesInput").value = meta.director_notes || "";

  const chronicleList = document.getElementById("chronicleList");
  chronicleList.innerHTML = "";
  if (data.chronicle && data.chronicle.length > 0) {
    data.chronicle.forEach(c => {
      const item = document.createElement("div");
      item.className = "chronicle-item";
      item.style.padding = "6px 0";
      item.style.borderBottom = "1px solid var(--border-color)";
      item.textContent = `Luku ${c.chapter_index}: ${c.summary}`;
      chronicleList.appendChild(item);
    });
  } else {
    chronicleList.innerHTML = `<p class="text-muted">Ei kronikkakirjauksia vielä.</p>`;
  }

  filterAndRenderCharacters();
}

function switchInspectorTab(tabName) {
  document.querySelectorAll(".inspector-tabs .tab-btn").forEach(btn => btn.classList.remove("active"));
  document.querySelectorAll(".tab-content").forEach(c => c.classList.remove("active"));

  if (tabName === "characters") {
    document.querySelector("button[onclick=\"switchInspectorTab('characters')\"]")?.classList.add("active");
    document.getElementById("tabCharacters")?.classList.add("active");
  } else if (tabName === "lore") {
    document.querySelector("button[onclick=\"switchInspectorTab('lore')\"]")?.classList.add("active");
    document.getElementById("tabLore")?.classList.add("active");
  } else if (tabName === "director") {
    document.querySelector("button[onclick=\"switchInspectorTab('director')\"]")?.classList.add("active");
    document.getElementById("tabDirector")?.classList.add("active");
  }
}

// Maailman muokkaus
function toggleLoreEdit(show = null) {
  const group = document.getElementById("worldLoreEditGroup");
  const display = document.getElementById("worldLoreDisplay");
  const isEditing = show !== null ? show : group.classList.contains("hidden");

  group.classList.toggle("hidden", !isEditing);
  display.classList.toggle("hidden", isEditing);
  if (isEditing) {
    document.getElementById("worldLoreInput").focus();
  }
}

async function saveLoreChanges() {
  if (!currentStoryId) return;
  const newLore = document.getElementById("worldLoreInput").value.trim();
  try {
    const res = await fetch(`/api/stories/${currentStoryId}/meta`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ world_lore: newLore })
    });
    if (!res.ok) throw new Error("Tallennus epäonnistui");
    const data = await res.json();
    currentStoryData.meta = data.meta;
    document.getElementById("worldLoreDisplay").textContent = newLore;
    toggleLoreEdit(false);
  } catch (err) {
    alert("Virhe: " + err.message);
  }
}

async function editStoryGenre() {
  if (!currentStoryId) return;
  const currentGenre = currentStoryData?.meta?.genre || "";
  const newGenre = prompt("Muokkaa tarinan genreä / tyylilajia:", currentGenre);
  if (newGenre === null || newGenre.trim() === currentGenre) return;

  try {
    const res = await fetch(`/api/stories/${currentStoryId}/meta`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ genre: newGenre.trim() })
    });
    if (!res.ok) throw new Error("Tallennus epäonnistui");
    const data = await res.json();
    currentStoryData.meta = data.meta;
    document.getElementById("storyGenreText").textContent = newGenre.trim();
    loadStoryList();
  } catch (err) {
    alert("Virhe: " + err.message);
  }
}

// Juonen muokkaus
function togglePlotEdit(show = null) {
  const group = document.getElementById("directorPlotEditGroup");
  const display = document.getElementById("directorPlotDisplay");
  const isEditing = show !== null ? show : group.classList.contains("hidden");

  group.classList.toggle("hidden", !isEditing);
  display.classList.toggle("hidden", isEditing);
  if (isEditing) {
    document.getElementById("directorPlotInput").focus();
  }
}

async function savePlotChanges() {
  if (!currentStoryId) return;
  const newPlot = document.getElementById("directorPlotInput").value.trim();
  try {
    const res = await fetch(`/api/stories/${currentStoryId}/meta`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ director_plot_arc: newPlot })
    });
    if (!res.ok) throw new Error("Tallennus epäonnistui");
    const data = await res.json();
    currentStoryData.meta = data.meta;
    document.getElementById("directorPlotDisplay").textContent = newPlot;
    togglePlotEdit(false);
  } catch (err) {
    alert("Virhe: " + err.message);
  }
}

// Muistiinpanojen muokkaus
function toggleNotesEdit(show = null) {
  const group = document.getElementById("directorNotesEditGroup");
  const display = document.getElementById("directorNotesDisplay");
  const isEditing = show !== null ? show : group.classList.contains("hidden");

  group.classList.toggle("hidden", !isEditing);
  display.classList.toggle("hidden", isEditing);
  if (isEditing) {
    document.getElementById("directorNotesInput").focus();
  }
}

async function saveNotesChanges() {
  if (!currentStoryId) return;
  const newNotes = document.getElementById("directorNotesInput").value.trim();
  try {
    const res = await fetch(`/api/stories/${currentStoryId}/meta`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ director_notes: newNotes })
    });
    if (!res.ok) throw new Error("Tallennus epäonnistui");
    const data = await res.json();
    currentStoryData.meta = data.meta;
    document.getElementById("directorNotesDisplay").textContent = newNotes;
    toggleNotesEdit(false);
  } catch (err) {
    alert("Virhe: " + err.message);
  }
}

// Hahmojen suodatus ja renderöinti
function setCharFilter(filter) {
  activeCharFilter = filter;
  document.querySelectorAll(".filter-pill").forEach(btn => {
    btn.classList.toggle("active", btn.getAttribute("data-filter") === filter);
  });
  filterAndRenderCharacters();
}

function filterAndRenderCharacters() {
  if (!currentStoryData || !currentStoryData.characters) return;
  const characters = currentStoryData.characters;
  const searchTerm = (document.getElementById("charSearchInput")?.value || "").toLowerCase().trim();
  const sortBy = document.getElementById("charSortSelect")?.value || "activity";

  let filtered = characters.filter(c => {
    if (activeCharFilter === "active" && c.status === "archived") return false;
    if (activeCharFilter === "archived" && c.status !== "archived") return false;
    if (searchTerm && !c.name.toLowerCase().includes(searchTerm)) return false;
    return true;
  });

  if (sortBy === "name") {
    filtered.sort((a, b) => a.name.localeCompare(b.name));
  } else if (sortBy === "tier") {
    filtered.sort((a, b) => (a.tier === "major" ? -1 : 1));
  }

  renderCharacterAccordion(filtered);
}

function renderCharacterAccordion(characters) {
  const container = document.getElementById("characterAccordion");
  container.innerHTML = "";

  if (!characters || characters.length === 0) {
    container.innerHTML = `<p class="text-muted" style="padding: 10px; font-size: 0.84rem;">Ei hahmoja valitulla suodatuksella.</p>`;
    return;
  }

  characters.forEach(char => {
    const item = document.createElement("div");
    item.className = "character-card";
    item.id = `char-card-${char.id}`;

    const isPlayer = char.is_player_controlled;
    item.dataset.player = String(isPlayer);

    item.innerHTML = `
      <div class="char-card-header" role="button" tabindex="0">
        <div class="char-card-title">
          <span class="char-name">${escapeHtml(char.name)}</span>
          ${isPlayer ? '<span class="badge" style="background-color: var(--color-primary-subtle); color: var(--color-primary); font-weight: 600; font-size: 0.72rem; padding: 2px 6px; border-radius: 4px;">Pelaaja</span>' : ''}
          <span class="badge" style="color: var(--text-muted); font-size: 0.75rem;">${char.age}v</span>
        </div>
        <span class="accordion-arrow" style="font-size: 0.75rem; color: var(--text-muted);">▼</span>
      </div>
      <div class="char-card-body hidden" id="char-body-${escapeHtml(char.id)}">
        <div class="state-item">
          <strong>Fyysinen vointi:</strong>
          <p>${escapeHtml(char.physical_state || 'Terve')}</p>
        </div>
        <div class="state-item private-detail">
          <strong>Mielentila:</strong>
          <p>${escapeHtml(char.mental_state || 'Rauhallinen')}</p>
        </div>
        ${char.secret_motive && (document.getElementById('revealSecrets')?.checked || (currentMode === 'roleplay' && isPlayer)) ? `
        <div class="state-item">
          <strong>Salainen motiivi:</strong>
          <p style="color: var(--color-primary);">${escapeHtml(char.secret_motive)}</p>
        </div>` : ''}

        <div class="char-actions-row">
          <button class="btn btn-secondary btn-xs edit-character">Muokkaa</button>
          ${!isPlayer ? `<button class="btn btn-primary btn-xs play-character">Pelaa hahmona</button>` : ''}
        </div>

        <div class="memory-stream-container private-detail mt-4">
          <h4 style="font-size: 0.8rem; text-transform: uppercase; color: var(--text-muted); margin-bottom: 6px;">Muistijäljet</h4>
          <ul class="memory-list" id="memlist-${escapeHtml(char.id)}" style="list-style: none; font-size: 0.82rem; color: var(--text-secondary); display: flex; flex-direction: column; gap: 4px;">
            <li>Ladataan muistoja...</li>
          </ul>
        </div>
      </div>
    `;

    item.querySelector('.char-card-header').onclick = () => toggleCharacterAccordion(char.id);
    item.querySelector('.char-card-header').onkeydown = event => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); toggleCharacterAccordion(char.id); } };
    item.querySelector('.edit-character').onclick = () => openEditCharModal(char.id);
    item.querySelector('.play-character')?.addEventListener('click', () => makeCharacterPlayer(char.id));
    container.appendChild(item);
  });
}

function toggleCharacterAccordion(charId) {
  const body = document.getElementById(`char-body-${charId}`);
  if (!body) return;
  const isHidden = body.classList.contains("hidden");

  // Suljetaan muut
  document.querySelectorAll(".char-card-body").forEach(b => b.classList.add("hidden"));
  if (isHidden) {
    body.classList.remove("hidden");
    selectedCharacterId = charId;
    loadCharacterMemoriesIntoCard(charId);
  }
}

async function loadCharacterMemoriesIntoCard(charId) {
  const listEl = document.getElementById(`memlist-${charId}`);
  if (!listEl) return;

  try {
    const res = await fetch(`/api/stories/${currentStoryId}/characters`);
    const data = await res.json();
    const target = data.characters?.find(c => c.character.id === charId);

    listEl.innerHTML = "";
    if (target && target.memories && target.memories.length > 0) {
      target.memories.forEach(m => {
        const li = document.createElement("li");
        li.style.borderLeft = "2px solid var(--color-primary)";
        li.style.paddingLeft = "6px";
        li.textContent = m.content;
        listEl.appendChild(li);
      });
    } else {
      listEl.innerHTML = `<li class="text-muted">Ei tallennettuja muistoja.</li>`;
    }
  } catch (err) {
    listEl.innerHTML = `<li class="text-muted">Muistien nouto epäonnistui.</li>`;
  }
}

// Hahmon muokkaus lennosta (Modal)
function openEditCharModal(charId) {
  const char = currentStoryData?.characters?.find(c => c.id === charId);
  if (!char) return;

  document.getElementById("editCharId").value = char.id;
  document.getElementById("editCharModalTitle").textContent = `Muokkaa hahmoa: ${char.name}`;
  document.getElementById("editCharName").value = char.name || "";
  document.getElementById("editCharAge").value = char.age || 25;
  document.getElementById("editCharGender").value = char.gender || "";
  document.getElementById("editCharTier").value = char.tier || "major";
  document.getElementById("editCharPhysicalState").value = char.physical_state || "";
  document.getElementById("editCharMentalState").value = char.mental_state || "";
  document.getElementById("editCharAppearance").value = char.appearance || "";
  document.getElementById("editCharPersonality").value = char.personality || "";
  document.getElementById("editCharSecretMotive").value = char.secret_motive || "";
  document.getElementById("editCharPublicBio").value = char.public_bio || "";
  document.getElementById("editCharStatus").value = char.status || "active";

  document.getElementById("editCharModal").classList.remove("hidden");
}

function closeEditCharModal() {
  document.getElementById("editCharModal").classList.add("hidden");
}

async function saveCharacterEdits() {
  const charId = document.getElementById("editCharId").value;
  if (!charId || !currentStoryId) return;

  const payload = {
    name: document.getElementById("editCharName").value.trim(),
    age: Number(document.getElementById("editCharAge").value),
    gender: document.getElementById("editCharGender").value.trim(),
    tier: document.getElementById("editCharTier").value,
    physical_state: document.getElementById("editCharPhysicalState").value.trim(),
    mental_state: document.getElementById("editCharMentalState").value.trim(),
    appearance: document.getElementById("editCharAppearance").value.trim(),
    personality: document.getElementById("editCharPersonality").value.trim(),
    secret_motive: document.getElementById("editCharSecretMotive").value.trim(),
    public_bio: document.getElementById("editCharPublicBio").value.trim(),
    status: document.getElementById("editCharStatus").value
  };

  try {
    const res = await fetch(`/api/stories/${currentStoryId}/characters/${charId}/update`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    if (!res.ok) throw new Error("Hahmon tallennus epäonnistui");
    const data = await res.json();
    
    // Päivitetään paikallinen data
    const idx = currentStoryData.characters.findIndex(c => c.id === charId);
    if (idx !== -1) {
      currentStoryData.characters[idx] = data.character;
    }
    filterAndRenderCharacters();
    updateActivePlayerBadge();
    closeEditCharModal();
  } catch (err) {
    alert("Virhe: " + err.message);
  }
}

// Pelattavan hahmon vaihto
async function makeCharacterPlayer(charId) {
  if (!currentStoryId) return;

  try {
    const res = await fetch(`/api/stories/${currentStoryId}/characters/${charId}/set_player`, {
      method: "POST"
    });
    if (!res.ok) throw new Error("Pelaajahahmon asetus epäonnistui");
    const data = await res.json();
    currentStoryData.characters = data.all_characters;
    
    setMode("player");
    filterAndRenderCharacters();
  } catch (err) {
    alert("Virhe: " + err.message);
  }
}

function updateActivePlayerBadge(characters) {
  const chars = characters || currentStoryData?.characters || [];
  const playerChar = chars.find(c => c.is_player_controlled);
  const badgeName = document.getElementById("activePlayerCharName");
  if (badgeName) {
    badgeName.textContent = playerChar ? playerChar.name : "Ei valittu";
  }
}

// --- Roolitilat ja Tarinan Edistäminen ---

function setMode(mode) {
  mode = ({reader: 'novel', player: 'roleplay', director: 'simulation'})[mode] || mode;
  if (!['novel', 'simulation', 'roleplay'].includes(mode)) mode = 'novel';
  currentMode = mode;
  document.body.dataset.mode = mode;
  if (currentStoryId) localStorage.setItem(`storytime.mode.${currentStoryId}`, mode);
  document.querySelectorAll(".segment-btn").forEach(b => b.classList.remove("active"));
  document.getElementById("readerControls")?.classList.toggle("hidden", mode === "roleplay");
  document.getElementById("playerControls")?.classList.toggle("hidden", mode !== "roleplay");
  document.getElementById("privateIntentionGroup")?.classList.toggle("hidden", mode !== "roleplay");
  document.getElementById("autoControls")?.classList.toggle("hidden", mode === "roleplay");
  if (mode === 'roleplay') document.getElementById('autoContinue').checked = false;
  const playerBadge = document.getElementById("playerContextBadge");
  if (playerBadge) playerBadge.classList.toggle("hidden", mode !== "roleplay");
  const button = {novel: 'modeReaderBtn', roleplay: 'modePlayerBtn', simulation: 'modeDirectorBtn'}[mode];
  document.getElementById(button)?.classList.add('active');
  document.querySelectorAll('.segment-btn').forEach(element => element.setAttribute('aria-pressed', element.classList.contains('active')));
  updateActivePlayerBadge();
  if (currentStoryData) filterAndRenderCharacters();
}

function showLiveAgentBar(show, initialText) {
  const bar = document.getElementById("liveAgentBar");
  const loading = document.getElementById("loadingIndicator");
  if (show) {
    bar?.classList.remove("hidden");
    loading?.classList.remove("hidden");
    if (initialText && document.getElementById("livePhaseText")) {
      document.getElementById("livePhaseText").textContent = initialText;
    }
  } else {
    bar?.classList.add("hidden");
    loading?.classList.add("hidden");
    highlightActiveCharacter(null, false);
  }
}

function highlightActiveCharacter(charId, highlight) {
  document.querySelectorAll(".character-card").forEach(item => {
    item.style.borderColor = "var(--border-color)";
  });
  if (charId && highlight) {
    const target = document.getElementById(`char-card-${charId}`);
    if (target) target.style.borderColor = "var(--color-primary)";
  }
}

// --- Uuden tarinan luonti ---

async function loadToneProfilesForNewStory() {
  try {
    const res = await fetch("/api/tone-profiles");
    const data = await res.json();
    const select = document.getElementById("newToneProfile");
    if (!select) return;
    select.innerHTML = "";

    data.profiles.forEach(p => {
      const opt = document.createElement("option");
      opt.value = p.id;
      opt.textContent = p.title;
      select.appendChild(opt);
    });

    updateNewStoryTonePreview();
  } catch (err) {
    console.error("Virhe ladattaessa sävyprofiileja:", err);
  }
}

async function updateNewStoryTonePreview() {
  const select = document.getElementById("newToneProfile");
  const descEl = document.getElementById("newToneProfileDesc");
  if (!select || !descEl) return;
  descEl.textContent = `Valittu sävyprofiili: ${select.value}`;
}

function openNewStoryModal() {
  loadToneProfilesForNewStory();
  document.getElementById("newStoryModal")?.classList.remove("hidden");
}

function closeNewStoryModal() {
  document.getElementById("newStoryModal")?.classList.add("hidden");
}

function togglePlayerFields(role) {
  const fields = document.getElementById("playerCharFields");
  if (role === "roleplay") {
    fields?.classList.remove("hidden");
  } else {
    fields?.classList.add("hidden");
  }
}

async function startNewStory() {
  if (isCreatingStory) return;
  const title = document.getElementById("newTitle").value.trim();
  const genre = document.getElementById("newGenre").value.trim() || "Seikkailu";
  const userIdea = document.getElementById("newIdea").value.trim();
  const plotIdea = document.getElementById("newPlotIdea").value.trim();
  const toneProfile = document.getElementById("newToneProfile").value || "default";
  const role = document.getElementById("newUserRole").value;
  const playerName = document.getElementById("newPlayerCharName")?.value.trim() || null;
  const playerDetails = document.getElementById("newPlayerCharDetails")?.value.trim() || null;

  if (!title) {
    alert("Anna tarinalle otsikko!");
    return;
  }

  closeNewStoryModal();
  isCreatingStory = true;

  // Nollataan vanha näkymä ja näytetään tyylikäs overlay
  document.getElementById("emptyStoryNotice")?.classList.add("hidden");
  const stream = document.getElementById("proseStream");
  if (stream) {
    stream.innerHTML = "";
    stream.classList.add("hidden");
  }
  document.getElementById("choicesContainer")?.classList.add("hidden");

  const overlay = document.getElementById("storyCreationOverlay");
  overlay?.classList.remove("hidden");
  document.getElementById("creationTitle").textContent = `Luodaan: "${title}"...`;
  document.getElementById("creationSubtext").textContent = `Kertoja rakentaa maailmaa (${genre}), hahmoja ja alkutilannetta.`;
  document.getElementById("creationDetails").textContent = `Sävy: ${toneProfile}`;

  showLiveAgentBar(true, "Kertoja rakentaa uutta maailmaa ja hahmoja...");

  try {
    const res = await fetch("/api/stories", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        title: title,
        genre: genre,
        user_idea: userIdea,
        user_role: role,
        player_character_name: playerName,
        player_character_details: playerDetails,
        custom_plot_idea: plotIdea,
        tone_profile: toneProfile
      })
    });

    if (!res.ok) {
      let detailMsg = "Virhe uuden tarinan luonnissa";
      try {
        const errJson = await res.json();
        if (errJson.detail) detailMsg += ": " + errJson.detail;
      } catch (e) {
        detailMsg += ` (${res.status} ${res.statusText})`;
      }
      throw new Error(detailMsg);
    }

    const data = await res.json();
    const storyId = data.data.story_id;

    overlay?.classList.add("hidden");
    await loadStoryList();
    await loadStory(storyId);

    setMode(role);
  } catch (err) {
    overlay?.classList.add("hidden");
    alert(err.message);
  } finally {
    isCreatingStory = false;
    showLiveAgentBar(false);
  }
}

// Alias aiemmalle nimelle
const submitNewStory = startNewStory;

// --- Prompt & Sävyprofiili Editori ---

function openPromptEditorModal() {
  loadPromptEditorData();
  document.getElementById("promptEditorModal")?.classList.remove("hidden");
}

function closePromptEditorModal() {
  document.getElementById("promptEditorModal")?.classList.add("hidden");
}

function switchPromptTab(tab) {
  document.getElementById("promptTabProfilesBtn")?.classList.toggle("active", tab === "profiles");
  document.getElementById("promptTabPromptsBtn")?.classList.toggle("active", tab === "prompts");
  document.getElementById("promptTabProfiles")?.classList.toggle("active", tab === "profiles");
  document.getElementById("promptTabProfiles")?.classList.toggle("hidden", tab !== "profiles");
  document.getElementById("promptTabPrompts")?.classList.toggle("active", tab === "prompts");
  document.getElementById("promptTabPrompts")?.classList.toggle("hidden", tab !== "prompts");
}

async function loadPromptEditorData() {
  try {
    const toneRes = await fetch("/api/tone-profiles");
    const toneData = await toneRes.json();
    const toneSelect = document.getElementById("toneProfileSelect");
    if (toneSelect) {
      toneSelect.innerHTML = "";
      toneData.profiles.forEach(p => {
        const opt = document.createElement("option");
        opt.value = p.id;
        opt.textContent = `${p.title} ${p.is_custom ? '(Muokattu)' : ''}`;
        toneSelect.appendChild(opt);
      });
      if (toneData.profiles.length > 0) {
        loadToneProfileContent(toneData.profiles[0].id);
      }
    }

    const promptRes = await fetch("/api/prompts");
    const promptData = await promptRes.json();
    const promptSelect = document.getElementById("promptSelect");
    if (promptSelect) {
      promptSelect.innerHTML = "";
      promptData.prompts.forEach(p => {
        const opt = document.createElement("option");
        opt.value = p.path;
        opt.textContent = p.title;
        promptSelect.appendChild(opt);
      });
      if (promptData.prompts.length > 0) {
        loadSelectedPromptContent(promptData.prompts[0].path);
      }
    }
  } catch (err) {
    console.error("Virhe ladattaessa prompt-tietoja:", err);
  }
}

async function loadToneProfileContent(profileId) {
  try {
    const res = await fetch(`/api/prompts/content?path=tone_profiles/${profileId}.txt`);
    const data = await res.json();
    document.getElementById("toneProfileEditor").value = data.content;
  } catch (err) {
    alert("Virhe profiilin latauksessa.");
  }
}

async function saveActiveToneProfile() {
  const profileId = document.getElementById("toneProfileSelect").value;
  const content = document.getElementById("toneProfileEditor").value;

  try {
    const res = await fetch("/api/tone-profiles", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id: profileId, title: profileId, content: content })
    });
    if (!res.ok) throw new Error("Tallennus epäonnistui");
    alert("Sävyprofiili tallennettu onnistuneesti!");
  } catch (err) {
    alert("Virhe: " + err.message);
  }
}

async function createNewToneProfilePrompt() {
  const name = prompt("Anna uudelle sävyprofiilille tunniste (esim. dark_fantasy):");
  if (!name) return;
  const cleanId = name.trim().toLowerCase().replace(/[^a-z0-9_]/g, "_");
  
  const template = `[TONE & NARRATIVE PROFILE: ${name.toUpperCase()}]\n- Atmosphere: ...\n- Realism: ...\n- Action style: ...`;
  document.getElementById("toneProfileEditor").value = template;
  
  const select = document.getElementById("toneProfileSelect");
  const opt = document.createElement("option");
  opt.value = cleanId;
  opt.textContent = cleanId;
  select.appendChild(opt);
  select.value = cleanId;
}

async function loadSelectedPromptContent(path) {
  try {
    const res = await fetch(`/api/prompts/content?path=${encodeURIComponent(path)}`);
    const data = await res.json();
    document.getElementById("promptEditor").value = data.content;
  } catch (err) {
    alert("Virhe promptin latauksessa.");
  }
}

async function saveSelectedPrompt() {
  const path = document.getElementById("promptSelect").value;
  const content = document.getElementById("promptEditor").value;

  try {
    const res = await fetch("/api/prompts/save", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ path: path, content: content })
    });
    if (!res.ok) throw new Error("Tallennus epäonnistui");
    alert("Prompti tallennettu!");
  } catch (err) {
    alert("Virhe: " + err.message);
  }
}

async function resetSelectedPrompt() {
  const path = document.getElementById("promptSelect").value;
  if (!confirm("Haluatko palauttaa tämän promptin järjestelmän oletusversioon?")) return;

  try {
    const res = await fetch("/api/prompts/reset", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ path: path })
    });
    if (!res.ok) throw new Error("Palautus epäonnistui");
    alert("Prompti palautettu oletukseen.");
    loadSelectedPromptContent(path);
  } catch (err) {
    alert("Virhe: " + err.message);
  }
}

// --- Hahmon Vienti & Tuonti ---

function openExportCharModal() {
  if (!currentStoryId || !selectedCharacterId) {
    alert("Valitse ensin hahmo tarkasteltavaksi.");
    return;
  }
  document.getElementById("exportCharModal")?.classList.remove("hidden");
}

function closeExportCharModal() {
  document.getElementById("exportCharModal")?.classList.add("hidden");
}

async function executeExportCharacter() {
  if (!currentStoryId || !selectedCharacterId) return;

  const includeState = document.getElementById("exportCheckState").checked;
  const includeMemories = document.getElementById("exportCheckMemories").checked;

  try {
    const url = `/api/stories/${currentStoryId}/characters/${selectedCharacterId}/export?include_state=${includeState}&include_memories=${includeMemories}`;
    const res = await fetch(url);
    if (!res.ok) throw new Error("Hahmon vienti epäonnistui");
    const blob = await res.blob();

    const downloadUrl = window.URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = downloadUrl;
    a.download = `character_${selectedCharacterId}.json`;
    document.body.appendChild(a);
    a.click();
    window.URL.revokeObjectURL(downloadUrl);
    a.remove();

    closeExportCharModal();
  } catch (err) {
    alert(err.message);
  }
}

function openImportCharModal() {
  if (!currentStoryId) {
    alert("Valitse tai luo tarina ensin.");
    return;
  }
  document.getElementById("importJsonText").value = "";
  document.getElementById("importFileInput").value = "";
  importedJsonCache = null;
  document.getElementById("importCharModal")?.classList.remove("hidden");
}

function closeImportCharModal() {
  document.getElementById("importCharModal")?.classList.add("hidden");
}

function handleImportFileSelect(event) {
  const file = event.target.files[0];
  if (!file) return;

  const reader = new FileReader();
  reader.onload = (e) => {
    try {
      const parsed = JSON.parse(e.target.result);
      importedJsonCache = parsed;
      document.getElementById("importJsonText").value = JSON.stringify(parsed, null, 2);
    } catch (err) {
      alert("Virheellinen JSON-tiedosto.");
    }
  };
  reader.readAsText(file);
}

async function executeImportCharacter() {
  if (!currentStoryId) return;

  let payload = importedJsonCache;
  const textVal = document.getElementById("importJsonText").value.trim();
  if (textVal) {
    try {
      payload = JSON.parse(textVal);
    } catch (err) {
      alert("Virheellinen JSON.");
      return;
    }
  }

  if (!payload) {
    alert("Valitse tiedosto tai liitä JSON.");
    return;
  }

  const includeState = document.getElementById("importCheckState").checked;
  const includeMemories = document.getElementById("importCheckMemories").checked;
  const asPlayer = document.getElementById("importCheckAsPlayer").checked;

  closeImportCharModal();

  try {
    const res = await fetch(`/api/stories/${currentStoryId}/characters/import`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        payload: payload,
        include_state: includeState,
        include_memories: includeMemories,
        as_player: asPlayer
      })
    });

    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || "Tuonti epäonnistui");
    }

    alert("Hahmo tuotu onnistuneesti!");
    await loadStory(currentStoryId);
  } catch (err) {
    alert(err.message);
  }
}

// --- Vienti ja Lataus ---

function toggleExportMenu() {
  document.getElementById("exportMenu")?.classList.toggle("hidden");
}

document.addEventListener("click", (e) => {
  if (!e.target.closest(".export-dropdown")) {
    document.getElementById("exportMenu")?.classList.add("hidden");
  }
});

function downloadStory(format) {
  if (!currentStoryId) {
    alert("Valitse tai luo tarina ensin.");
    return;
  }
  window.open(`/api/stories/${currentStoryId}/export/${format}`, "_blank");
}

// --- Asetukset ja Palveluntarjoajat ---

function openSettingsModal() {
  loadSettings();
  document.getElementById("settingsModal")?.classList.remove("hidden");
}

function closeSettingsModal() {
  document.getElementById("settingsModal")?.classList.add("hidden");
  setInputValue('settingXaiKey', '');
  setInputValue('settingAzureKey', '');
}

const SETTINGS_PROFILES_KEY = "storytime.providerProfiles";
const ACTIVE_SETTINGS_PROFILE_KEY = "storytime.activeProviderProfile";

function createProfile(provider, name) {
  return {
    id: crypto.randomUUID(),
    name: name || (provider === "azure" ? "Azure AI" : "Grok"),
    provider,
    xai_api_key: "",
    azure_openai_endpoint: "",
    azure_openai_api_key: "",
    azure_openai_api_version: "2024-10-21",
    azure_deployment_name: "",
    director_model: provider === "azure" ? "gpt-4o" : "grok-4.6",
    director_max_tokens: 8000,
    director_temperature: 0.85,
    director_reasoning_effort: "medium",
    character_model: provider === "azure" ? "gpt-4o" : "grok-4.3",
    character_max_tokens: 1200,
    character_temperature: 0.75,
    character_reasoning_effort: "low",
  };
}

function getSettingsProfiles() {
  try {
    const profiles = JSON.parse(localStorage.getItem(SETTINGS_PROFILES_KEY) || "[]");
    return Array.isArray(profiles) ? profiles : [];
  } catch (err) {
    console.warn("Asetusprofiilien luku epäonnistui:", err);
    return [];
  }
}

function saveSettingsProfiles(profiles) {
  const safeProfiles = profiles.map(profile => Object.fromEntries(Object.entries(profile).filter(([name]) => !name.endsWith('_api_key'))));
  localStorage.setItem(SETTINGS_PROFILES_KEY, JSON.stringify(safeProfiles));
}

function getActiveSettingsProfileId() {
  return localStorage.getItem(ACTIVE_SETTINGS_PROFILE_KEY);
}

function setActiveSettingsProfileId(profileId) {
  localStorage.setItem(ACTIVE_SETTINGS_PROFILE_KEY, profileId);
}

function renderSettingsProfileSelect() {
  const select = document.getElementById("settingsProfileSelect");
  if (!select) return;
  const profiles = getSettingsProfiles();
  const activeId = getActiveSettingsProfileId();
  select.innerHTML = "";
  profiles.forEach((profile) => {
    const option = document.createElement("option");
    option.value = profile.id;
    option.textContent = profile.name;
    select.appendChild(option);
  });
  select.value = profiles.some((profile) => profile.id === activeId) ? activeId : profiles[0]?.id;
}

function setInputValue(elementId, value) {
  const input = document.getElementById(elementId);
  if (input) input.value = value ?? "";
}

function isAzureFoundryGpt5Profile(provider, endpoint, model) {
  return provider === "azure"
    && endpoint.trim().replace(/\/$/, "").toLowerCase().endsWith("/openai/v1")
    && model.trim().toLowerCase().startsWith("gpt-5");
}

function updateTemperatureControl(modelId, temperatureId, noteId) {
  const provider = document.getElementById("settingProvider")?.value;
  const endpoint = document.getElementById("settingAzureEndpoint")?.value || "";
  const model = document.getElementById(modelId)?.value || "";
  const isFixed = isAzureFoundryGpt5Profile(provider, endpoint, model);
  const temperatureInput = document.getElementById(temperatureId);
  const note = document.getElementById(noteId);
  if (!temperatureInput) return;

  temperatureInput.disabled = isFixed;
  note?.classList.toggle("hidden", !isFixed);
  if (isFixed) temperatureInput.value = "1";
}

function updateTemperatureControls() {
  updateTemperatureControl("settingDirectorModel", "settingDirectorTemp", "settingDirectorTempNote");
  updateTemperatureControl("settingCharModel", "settingCharTemp", "settingCharTempNote");
}

function populateSettingsProfile(profile) {
  if (!profile) return;
  setInputValue("settingProfileName", profile.name);
  setInputValue("settingProvider", profile.provider);
  setInputValue("settingXaiKey", profile.xai_api_key);
  setInputValue("settingAzureEndpoint", profile.azure_openai_endpoint);
  setInputValue("settingAzureKey", profile.azure_openai_api_key);
  setInputValue("settingAzureVersion", profile.azure_openai_api_version || "2024-10-21");
  setInputValue("settingAzureDeployment", profile.azure_deployment_name);
  setInputValue("settingDirectorModel", profile.director_model);
  setInputValue("settingDirectorMaxTokens", profile.director_max_tokens);
  setInputValue("settingDirectorTemp", profile.director_temperature);
  setInputValue("settingDirectorReasoning", profile.director_reasoning_effort || "medium");
  setInputValue("settingCharModel", profile.character_model);
  setInputValue("settingCharMaxTokens", profile.character_max_tokens);
  setInputValue("settingCharTemp", profile.character_temperature);
  setInputValue("settingCharReasoning", profile.character_reasoning_effort || "low");
  toggleProviderSettings(profile.provider);
  updateTemperatureControls();
}

function profileFromForm(profileId) {
  return {
    id: profileId,
    name: document.getElementById("settingProfileName")?.value.trim() || "Nimetön profiili",
    provider: document.getElementById("settingProvider")?.value || "xai",
    xai_api_key: document.getElementById("settingXaiKey")?.value.trim() || "",
    azure_openai_endpoint: document.getElementById("settingAzureEndpoint")?.value.trim() || "",
    azure_openai_api_key: document.getElementById("settingAzureKey")?.value.trim() || "",
    azure_openai_api_version: document.getElementById("settingAzureVersion")?.value.trim() || "",
    azure_deployment_name: document.getElementById("settingAzureDeployment")?.value.trim() || "",
    director_model: document.getElementById("settingDirectorModel")?.value.trim() || "grok-4.6",
    director_max_tokens: Number(document.getElementById("settingDirectorMaxTokens")?.value || 8000),
    director_temperature: Number(document.getElementById("settingDirectorTemp")?.value || 0.85),
    director_reasoning_effort: document.getElementById("settingDirectorReasoning")?.value || "medium",
    character_model: document.getElementById("settingCharModel")?.value.trim() || "grok-4.3",
    character_max_tokens: Number(document.getElementById("settingCharMaxTokens")?.value || 1200),
    character_temperature: Number(document.getElementById("settingCharTemp")?.value || 0.75),
    character_reasoning_effort: document.getElementById("settingCharReasoning")?.value || "low",
  };
}

function persistCurrentSettingsProfile() {
  const selectedId = document.getElementById("settingsProfileSelect")?.value;
  if (!selectedId) return null;
  const profile = profileFromForm(selectedId);
  const profiles = getSettingsProfiles().map((item) => item.id === selectedId ? profile : item);
  saveSettingsProfiles(profiles);
  renderSettingsProfileSelect();
  if (document.getElementById("settingsProfileSelect")) {
    document.getElementById("settingsProfileSelect").value = selectedId;
  }
  return profile;
}

function selectSettingsProfile(profileId) {
  setActiveSettingsProfileId(profileId);
  populateSettingsProfile(getSettingsProfiles().find((profile) => profile.id === profileId));
}

function createSettingsProfile(provider) {
  persistCurrentSettingsProfile();
  const profiles = getSettingsProfiles();
  const profile = createProfile(provider, provider === "azure" ? "Azure AI" : "Grok");
  profiles.push(profile);
  saveSettingsProfiles(profiles);
  setActiveSettingsProfileId(profile.id);
  renderSettingsProfileSelect();
  document.getElementById("settingsProfileSelect").value = profile.id;
  populateSettingsProfile(profile);
  document.getElementById("settingProfileName").focus();
  document.getElementById("settingProfileName").select();
}

function deleteSettingsProfile() {
  const selectedId = document.getElementById("settingsProfileSelect")?.value;
  const profiles = getSettingsProfiles();
  if (profiles.length <= 1) {
    alert("Vähintään yksi palveluntarjoajaprofiili on säilytettävä.");
    return;
  }
  const remainingProfiles = profiles.filter((profile) => profile.id !== selectedId);
  saveSettingsProfiles(remainingProfiles);
  setActiveSettingsProfileId(remainingProfiles[0].id);
  renderSettingsProfileSelect();
  populateSettingsProfile(remainingProfiles[0]);
}

function toggleProviderSettings(provider) {
  const groups = {
    xai: document.getElementById("groupXai"),
    azure: document.getElementById("groupAzure"),
  };
  Object.entries(groups).forEach(([key, el]) => {
    if (!el) return;
    if (key === provider) {
      el.classList.remove("hidden");
    } else {
      el.classList.add("hidden");
    }
  });
  updateTemperatureControls();
}

// Automaattinen taustasynkronointi backendille
async function silentlySyncActiveProfileToBackend(profile) {
  if (!profile) return;
  try {
    const payload = {
      profile_id: profile.id,
      llm_provider: profile.provider,
      xai_api_key: profile.xai_api_key,
      azure_openai_endpoint: profile.azure_openai_endpoint,
      azure_openai_api_key: profile.azure_openai_api_key,
      azure_openai_api_version: profile.azure_openai_api_version,
      azure_deployment_name: profile.azure_deployment_name,
      director_model: profile.director_model,
      director_max_tokens: profile.director_max_tokens,
      director_temperature: profile.director_temperature,
      director_reasoning_effort: profile.director_reasoning_effort,
      character_model: profile.character_model,
      character_max_tokens: profile.character_max_tokens,
      character_temperature: profile.character_temperature,
      character_reasoning_effort: profile.character_reasoning_effort,
    };

    const response = await fetch("/api/settings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    if (!response.ok) throw new Error('Profiilin aktivointi epäonnistui.');
    console.log("Aktiiviset API-asetukset synkronoitu automaattisesti taustalla.");
  } catch (err) {
    console.warn("Automaattinen asetussynkronointi epäonnistui:", err);
  }
}

async function loadSettings() {
  try {
    const res = await fetch("/api/settings");
    const data = await res.json();
    let profiles = getSettingsProfiles();
    const legacyProfiles = profiles.filter(profile => Object.entries(profile).some(([name, value]) => name.endsWith('_api_key') && value));
    if (legacyProfiles.length) {
      const migrated = await fetch('/api/settings/profile-secrets', {
        method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({profiles: legacyProfiles})
      });
      if (!migrated.ok) throw new Error('Vanhojen API-avainten siirto palvelimelle epäonnistui. Avaimet säilytettiin selaimessa.');
      profiles = profiles.map(profile => ({...profile, server_credentials: true}));
      saveSettingsProfiles(profiles);
      profiles = getSettingsProfiles();
    }
    if (profiles.length === 0) {
      const profile = createProfile(data.llm_provider === "azure" ? "azure" : "xai", "Nykyiset asetukset");
      profile.azure_openai_endpoint = data.azure_openai_endpoint || "";
      profile.azure_openai_api_version = data.azure_openai_api_version || "2024-10-21";
      profile.azure_deployment_name = data.azure_deployment_name || "";
      profile.director_model = data.director_model || profile.director_model;
      profile.director_max_tokens = data.director_max_tokens || profile.director_max_tokens;
      profile.director_temperature = data.director_temperature ?? profile.director_temperature;
      profile.director_reasoning_effort = data.director_reasoning_effort || profile.director_reasoning_effort;
      profile.character_model = data.character_model || profile.character_model;
      profile.character_max_tokens = data.character_max_tokens || profile.character_max_tokens;
      profile.character_temperature = data.character_temperature ?? profile.character_temperature;
      profile.character_reasoning_effort = data.character_reasoning_effort || profile.character_reasoning_effort;
      profiles = [profile];
      saveSettingsProfiles(profiles);
      setActiveSettingsProfileId(profile.id);
    }
    const activeId = profiles.some((profile) => profile.id === getActiveSettingsProfileId())
      ? getActiveSettingsProfileId()
      : profiles[0].id;
    setActiveSettingsProfileId(activeId);
    renderSettingsProfileSelect();
    if (document.getElementById("settingsProfileSelect")) {
      document.getElementById("settingsProfileSelect").value = activeId;
    }
    const activeProfile = profiles.find((profile) => profile.id === activeId);
    populateSettingsProfile(activeProfile);

    // Synkronoidaan asetukset heti taustalla palvelimelle, jos avain on tallessa
    if (legacyProfiles.length && activeProfile) {
      await silentlySyncActiveProfileToBackend(activeProfile);
    }

  } catch (err) {
    console.error("Virhe haettaessa asetuksia:", err);
    turnNotice(err.message);
  }
}

async function saveSettings() {
  const profile = persistCurrentSettingsProfile();
  if (!profile) return;

  try {
    const payload = {
      profile_id: profile.id,
      llm_provider: profile.provider,
      xai_api_key: profile.xai_api_key,
      azure_openai_endpoint: profile.azure_openai_endpoint,
      azure_openai_api_key: profile.azure_openai_api_key,
      azure_openai_api_version: profile.azure_openai_api_version,
      azure_deployment_name: profile.azure_deployment_name,
      director_model: profile.director_model,
      director_max_tokens: profile.director_max_tokens,
      director_temperature: profile.director_temperature,
      director_reasoning_effort: profile.director_reasoning_effort,
      character_model: profile.character_model,
      character_max_tokens: profile.character_max_tokens,
      character_temperature: profile.character_temperature,
      character_reasoning_effort: profile.character_reasoning_effort,
    };

    const res = await fetch("/api/settings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });

    if (!res.ok) {
      let detailMsg = "Asetusten tallennus epäonnistui";
      try {
        const errJson = await res.json();
        if (errJson.detail) detailMsg += ": " + errJson.detail;
      } catch (e) {}
      throw new Error(detailMsg);
    }
    setActiveSettingsProfileId(profile.id);
    saveSettingsProfiles(getSettingsProfiles().map(item => item.id === profile.id ? {...item, server_credentials: true} : item));
    closeSettingsModal();
    alert("Asetukset tallennettu ja aktivoitu!");
  } catch (err) {
    alert("Virhe: " + err.message);
  }
}

// --- Token- ja API-seuranta sekä Debug-konsoli ---

async function updateTokenStats(storyId = currentStoryId) {
  if (!storyId) return;
  const badge = document.getElementById("tokenStatsBadge");
  const textEl = document.getElementById("tokenStatsText");
  if (!badge || !textEl) return;

  try {
    const res = await fetch(`/api/stories/${storyId}/stats`);
    if (!res.ok) return;
    const data = await res.json();
    const stats = data.stats || {};

    const totalTokens = stats.total_tokens || 0;
    const lastSec = (stats.last_duration_seconds || 0).toFixed(1);
    
    // Formatoidaan esim: "14.2k tkn • 1.8s"
    const formattedTokens = totalTokens >= 1000 ? `${(totalTokens / 1000).toFixed(1)}k` : `${totalTokens}`;
    textEl.textContent = `${formattedTokens} tkn • ${lastSec}s`;
    badge.classList.remove("hidden");
    badge.title = `Yhteensä ${totalTokens.toLocaleString()} tokenia, ${stats.total_calls || 0} API-kutsua. Viimeisin kutsu: ${lastSec}s. Klikkaa avataksesi lokitiedot.`;
  } catch (err) {
    console.warn("Token-tilastojen nouto epäonnistui:", err);
  }
}

function openDebugLogsModal() {
  document.getElementById("debugLogsModal")?.classList.remove("hidden");
  loadDebugLogs();
}

function closeDebugLogsModal() {
  document.getElementById("debugLogsModal")?.classList.add("hidden");
}

async function loadDebugLogs() {
  if (!currentStoryId) return;
  const summaryEl = document.getElementById("debugStatsSummary");
  const tbody = document.getElementById("debugLogsTableBody");
  if (!summaryEl || !tbody) return;

  tbody.innerHTML = `<tr><td colspan="10" style="text-align: center; color: var(--text-muted); padding: 20px;">Ladataan lokitietoja...</td></tr>`;

  try {
    const [statsRes, logsRes] = await Promise.all([
      fetch(`/api/stories/${currentStoryId}/stats`),
      fetch(`/api/stories/${currentStoryId}/logs?limit=100`)
    ]);

    const statsData = await statsRes.json();
    const logsData = await logsRes.json();

    const stats = statsData.stats || {};
    summaryEl.innerHTML = `
      <div class="debug-stat-card">
        <span class="debug-stat-label">Kokonaiskutsut</span>
        <span class="debug-stat-val">${stats.total_calls || 0}</span>
      </div>
      <div class="debug-stat-card">
        <span class="debug-stat-label">Kokonaistokenit</span>
        <span class="debug-stat-val">${(stats.total_tokens || 0).toLocaleString()}</span>
      </div>
      <div class="debug-stat-card">
        <span class="debug-stat-label">Prompt-tokenit</span>
        <span class="debug-stat-val">${(stats.total_prompt_tokens || 0).toLocaleString()}</span>
      </div>
      <div class="debug-stat-card">
        <span class="debug-stat-label">Välimuistista</span>
        <span class="debug-stat-val">${(stats.total_cached_tokens || 0).toLocaleString()}</span>
      </div>
      <div class="debug-stat-card">
        <span class="debug-stat-label">Vastaustokenit</span>
        <span class="debug-stat-val">${(stats.total_completion_tokens || 0).toLocaleString()}</span>
      </div>
      <div class="debug-stat-card">
        <span class="debug-stat-label">Reasoning-tokenit</span>
        <span class="debug-stat-val">${(stats.total_reasoning_tokens || 0).toLocaleString()}</span>
      </div>
      <div class="debug-stat-card">
        <span class="debug-stat-label">Kokonaisaika</span>
        <span class="debug-stat-val">${(stats.total_duration_seconds || 0).toFixed(1)} s</span>
      </div>
      <div class="debug-stat-card">
        <span class="debug-stat-label">Palvelun raportoima hinta (${stats.priced_calls || 0}/${stats.total_calls || 0})</span>
        <span class="debug-stat-val">${stats.priced_calls ? '$' + (stats.total_cost_usd || 0).toFixed(4) : 'Ei saatavilla'}</span>
      </div>
    `;

    const logs = logsData.logs || [];
    if (logs.length === 0) {
      tbody.innerHTML = `<tr><td colspan="10" style="text-align: center; color: var(--text-muted); padding: 20px;">Ei API-lokitietoja vielä tälle tarinalle.</td></tr>`;
      return;
    }

    tbody.innerHTML = "";
    logs.forEach(log => {
      const tr = document.createElement("tr");
      const timeStr = log.created_at ? (log.created_at.split(" ")[1] || log.created_at) : "-";
      let statusBadge = `<span class="debug-badge-ok">OK</span>`;
      if (log.status === "error") {
        statusBadge = `<span class="debug-badge-err" title="${escapeHtml(log.error_message)}">VIRHE</span>`;
      } else if (log.status === "truncated") {
        statusBadge = `<span class="debug-badge-trunc" title="${escapeHtml(log.error_message)}">KATKESI</span>`;
      }

      tr.innerHTML = `
        <td>${escapeHtml(timeStr)}</td>
        <td><strong>${escapeHtml(log.role || '-')}</strong></td>
        <td><code>${escapeHtml(log.model || '-')}</code></td>
        <td>${(log.duration_seconds || 0).toFixed(2)} s</td>
        <td title="Välimuistista: ${Number(log.cached_tokens || 0)}">${(log.prompt_tokens || 0).toLocaleString()}</td>
        <td>${(log.completion_tokens || 0).toLocaleString()}</td>
        <td>${(log.reasoning_tokens || 0).toLocaleString()}</td>
        <td><strong>${(log.total_tokens || 0).toLocaleString()}</strong></td>
        <td>${log.cost_known ? '$' + (log.cost_usd || 0).toFixed(5) : '-'}</td>
        <td>${statusBadge}</td>
      `;
      tbody.appendChild(tr);
    });
  } catch (err) {
    console.error("Virhe ladattaessa API-lokeja:", err);
    tbody.innerHTML = `<tr><td colspan="10" style="color: var(--accent-crimson); padding: 20px;">Latausvirhe: ${escapeHtml(err.message)}</td></tr>`;
  }
}
