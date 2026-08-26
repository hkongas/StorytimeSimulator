// StorytimeSimulator / Tarinamoottori – Frontend sovelluslogiikka

let currentStoryId = null;
let currentStoryData = null;
let currentMode = "reader"; // 'reader', 'player', 'director'
let selectedCharacterId = null;
let isGenerating = false;
let importedJsonCache = null;

// Alustus kun sivu latautuu
document.addEventListener("DOMContentLoaded", () => {
  applyTranslations();
  loadStoryList();
  loadSettings();

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

// --- Tarinalistan ja Tarinan lataus ---

async function loadStoryList() {
  try {
    const res = await fetch("/api/stories");
    const data = await res.json();
    const select = document.getElementById("storySelect");
    select.innerHTML = `<option value="" disabled selected>${t('selectStoryPrompt')}</option>`;

    if (data.stories && data.stories.length > 0) {
      data.stories.forEach(s => {
        const opt = document.createElement("option");
        opt.value = s.id;
        opt.textContent = `${s.title} (${s.genre})`;
        select.appendChild(opt);
      });

      // Jos mikään tarina ei ole vielä valittuna, valitaan uusin
      if (!currentStoryId && data.stories.length > 0) {
        select.value = data.stories[0].id;
        loadStory(data.stories[0].id);
      }
    }
  } catch (err) {
    console.error("Virhe ladattaessa tarinalistaa:", err);
  }
}

async function loadStory(storyId) {
  if (!storyId) return;
  currentStoryId = storyId;

  try {
    const res = await fetch(`/api/stories/${storyId}`);
    if (!res.ok) throw new Error("Tarinaa ei voitu ladata");
    const data = await res.json();
    currentStoryData = data;

    renderStoryView(data);
    renderInspector(data);
  } catch (err) {
    console.error("Virhe ladattaessa tarinaa:", err);
    alert(err.message);
  }
}

function renderStoryView(data) {
  const meta = data.meta;
  document.getElementById("storyTitle").textContent = meta.title;
  document.getElementById("storyGenre").textContent = `Genre: ${meta.genre}`;
  document.getElementById("emptyStoryNotice").classList.add("hidden");

  const stream = document.getElementById("proseStream");
  stream.classList.remove("hidden");
  stream.innerHTML = "";

  if (data.turns && data.turns.length > 0) {
    data.turns.forEach(turn => {
      appendTurnToView(turn, false);
    });
  }

  scrollStoryToBottom();
}

function appendTurnToView(turn, animate = true) {
  const stream = document.getElementById("proseStream");
  const turnEl = document.createElement("div");
  turnEl.className = "prose-turn";

  // Muotoillaan kappaleet
  const paragraphs = turn.director_prose.split("\n\n").filter(p => p.trim().length > 0);
  paragraphs.forEach(p => {
    const pEl = document.createElement("p");
    pEl.className = "prose-paragraph";
    pEl.textContent = p.trim();
    turnEl.appendChild(pEl);
  });

  // Metapalkki kappaleen alle
  const metaBar = document.createElement("div");
  metaBar.className = "turn-meta-bar";

  if (turn.acting_character_id) {
    const charPill = document.createElement("span");
    charPill.className = "meta-pill";
    charPill.textContent = `${t('actingCharacterLabel')} ${turn.acting_character_id}`;
    metaBar.appendChild(charPill);
  }

  if (turn.image_prompt) {
    const imgBadge = document.createElement("span");
    imgBadge.className = "meta-pill image-prompt-badge";
    imgBadge.title = turn.image_prompt;
    imgBadge.textContent = t('imagePromptBadge');
    imgBadge.onclick = () => {
      navigator.clipboard.writeText(turn.image_prompt);
      alert(t('imagePromptCopied') + turn.image_prompt);
    };
    metaBar.appendChild(imgBadge);
  }

  turnEl.appendChild(metaBar);
  stream.appendChild(turnEl);

  if (animate) {
    scrollStoryToBottom();
  }
}

function scrollStoryToBottom() {
  const container = document.getElementById("storyScrollArea");
  setTimeout(() => {
    container.scrollTop = container.scrollHeight;
  }, 50);
}

// --- Inspector ja Hahmot ---

function renderInspector(data) {
  // Lore & Juoni
  document.getElementById("worldLoreContent").textContent = data.meta.world_lore || t('noWorldLore');
  document.getElementById("directorPlotContent").textContent = data.meta.director_plot_arc || t('noDirectorPlot');
  document.getElementById("directorNotesContent").textContent = data.meta.director_notes || t('noDirectorNotes');

  // Kronikka
  const chronicleList = document.getElementById("chronicleList");
  chronicleList.innerHTML = "";
  if (data.chronicle && data.chronicle.length > 0) {
    data.chronicle.forEach(c => {
      const item = document.createElement("div");
      item.className = "chronicle-item";
      item.innerHTML = `<strong>${t('chapterPrefix')} ${c.chapter_index}:</strong> ${c.summary}`;
      chronicleList.appendChild(item);
    });
  } else {
    chronicleList.innerHTML = `<p class="text-muted">${t('noChronicleYet')}</p>`;
  }

  // Hahmot
  renderCharacters(data.characters);
}

function renderCharacters(characters) {
  const charList = document.getElementById("charList");
  charList.innerHTML = "";

  if (!characters || characters.length === 0) {
    charList.innerHTML = `<p class="text-muted">${t('noCharactersYet')}</p>`;
    document.getElementById("charDetailView").classList.add("hidden");
    return;
  }

  characters.forEach((char, idx) => {
    const chip = document.createElement("button");
    chip.className = `char-chip ${selectedCharacterId === char.id || (!selectedCharacterId && idx === 0) ? 'active' : ''}`;
    chip.textContent = `${char.name} ${char.is_player_controlled ? '⚔️' : ''}`;
    chip.onclick = () => selectCharacter(char.id);
    charList.appendChild(chip);
  });

  const firstCharId = selectedCharacterId || characters[0].id;
  selectCharacter(firstCharId);
}

async function selectCharacter(charId) {
  selectedCharacterId = charId;
  
  // Päivitetään aktiivinen chip
  document.querySelectorAll(".char-chip").forEach(chip => {
    chip.classList.toggle("active", chip.textContent.includes(charId));
  });

  const char = currentStoryData?.characters?.find(c => c.id === charId);
  if (!char) return;

  const detailView = document.getElementById("charDetailView");
  detailView.classList.remove("hidden");

  document.getElementById("charDetailName").textContent = char.name;
  document.getElementById("charAgeBadge").textContent = `${t('ageLabel')} ${char.age}`;
  
  const roleBadge = document.getElementById("charRoleBadge");
  roleBadge.textContent = char.is_player_controlled ? t('rolePlayer') : t('roleNpc');
  roleBadge.className = `badge ${char.is_player_controlled ? 'badge-accent' : ''}`;

  document.getElementById("charPhysicalState").textContent = char.physical_state || "Terve";
  document.getElementById("charMentalState").textContent = char.mental_state || "Rauhallinen";
  document.getElementById("charSecretMotive").textContent = char.secret_motive || t('noSecretMotive');

  // Haetaan hahmon tuoreet muistit
  try {
    const res = await fetch(`/api/stories/${currentStoryId}/characters`);
    const data = await res.json();
    const target = data.characters?.find(c => c.character.id === charId);
    
    const memList = document.getElementById("charMemoryList");
    memList.innerHTML = "";
    if (target && target.memories && target.memories.length > 0) {
      target.memories.forEach(m => {
        const li = document.createElement("li");
        li.textContent = m.content;
        memList.appendChild(li);
      });
    } else {
      memList.innerHTML = `<li>${t('noMemoriesYet')}</li>`;
    }
  } catch (err) {
    console.error("Virhe muistien haussa:", err);
  }
}

function switchInspectorTab(tabName) {
  document.querySelectorAll(".tab-btn").forEach(btn => btn.classList.remove("active"));
  document.querySelectorAll(".tab-content").forEach(c => c.classList.remove("active"));

  if (tabName === "characters") {
    document.querySelector("button[onclick=\"switchInspectorTab('characters')\"]").classList.add("active");
    document.getElementById("tabCharacters").classList.add("active");
  } else if (tabName === "lore") {
    document.querySelector("button[onclick=\"switchInspectorTab('lore')\"]").classList.add("active");
    document.getElementById("tabLore").classList.add("active");
  } else if (tabName === "director") {
    document.querySelector("button[onclick=\"switchInspectorTab('director')\"]").classList.add("active");
    document.getElementById("tabDirector").classList.add("active");
  }
}

// --- Käyttäjätilat ja Tarinan Edistäminen ---

function setMode(mode) {
  currentMode = mode;
  document.querySelectorAll(".mode-btn").forEach(b => b.classList.remove("active"));

  document.getElementById("readerControls").classList.add("hidden");
  document.getElementById("playerControls").classList.add("hidden");
  document.getElementById("directorControls").classList.add("hidden");

  if (mode === "reader") {
    document.getElementById("modeReaderBtn").classList.add("active");
    document.getElementById("readerControls").classList.remove("hidden");
  } else if (mode === "player") {
    document.getElementById("modePlayerBtn").classList.add("active");
    document.getElementById("playerControls").classList.remove("hidden");
    
    // Tarkistetaan onko pelaajahahmoa
    const playerChar = currentStoryData?.characters?.find(c => c.is_player_controlled);
    if (playerChar) {
      document.getElementById("playerTag").textContent = `⚔️ ${playerChar.name}`;
    }
  } else if (mode === "director") {
    document.getElementById("modeDirectorBtn").classList.add("active");
    document.getElementById("directorControls").classList.remove("hidden");
  }
}

async function advanceStory() {
  if (!currentStoryId || isGenerating) return;

  let userInput = "";
  if (currentMode === "reader") {
    userInput = document.getElementById("readerInput").value.trim();
  } else if (currentMode === "player") {
    userInput = document.getElementById("playerInput").value.trim();
  } else if (currentMode === "director") {
    userInput = document.getElementById("directorInput").value.trim();
  }

  isGenerating = true;
  showLoading(true, t('loadingStatusDefault'));

  try {
    const res = await fetch(`/api/stories/${currentStoryId}/advance`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        mode: currentMode,
        user_input: userInput || null
      })
    });

    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || "Virhe tarinan edistämisessä");
    }

    const data = await res.json();
    const turnData = data.data;

    // Tyhjennetään syötekenttä
    if (currentMode === "reader") document.getElementById("readerInput").value = "";
    if (currentMode === "player") document.getElementById("playerInput").value = "";
    if (currentMode === "director") document.getElementById("directorInput").value = "";

    // Lisätään uusi vuoro kirjaan
    appendTurnToView({
      acting_character_id: turnData.acting_character?.name || null,
      director_prose: turnData.director_prose,
      image_prompt: turnData.image_prompt
    }, true);

    // Päivitetään hahmot ja tila
    if (turnData.updated_characters) {
      currentStoryData.characters = turnData.updated_characters;
      renderCharacters(turnData.updated_characters);
    }
  } catch (err) {
    console.error("Virhe tarinan edistämisessä:", err);
    alert("Virhe: " + err.message);
  } finally {
    isGenerating = false;
    showLoading(false);
  }
}

function showLoading(show, messageKey) {
  const bar = document.getElementById("loadingIndicator");
  const statusEl = document.getElementById("loadingStatusText");
  if (show) {
    if (messageKey) statusEl.textContent = messageKey;
    bar.classList.remove("hidden");
  } else {
    bar.classList.add("hidden");
  }
}

// --- Uuden tarinan luonti ---

function openNewStoryModal() {
  document.getElementById("newStoryModal").classList.remove("hidden");
}

function closeNewStoryModal() {
  document.getElementById("newStoryModal").classList.add("hidden");
}

function togglePlayerFields(role) {
  const fields = document.getElementById("playerCharFields");
  if (role === "player") {
    fields.classList.remove("hidden");
  } else {
    fields.classList.add("hidden");
  }
}

async function submitNewStory() {
  const title = document.getElementById("newTitle").value.trim();
  const genre = document.getElementById("newGenre").value.trim() || "Seikkailu";
  const userIdea = document.getElementById("newIdea").value.trim();
  const plotIdea = document.getElementById("newPlotIdea").value.trim();
  const role = document.getElementById("newUserRole").value;
  const playerName = document.getElementById("newPlayerCharName")?.value.trim() || null;
  const playerDetails = document.getElementById("newPlayerCharDetails")?.value.trim() || null;

  if (!title) {
    alert(t('titleRequiredAlert'));
    return;
  }

  closeNewStoryModal();
  showLoading(true, t('loadingStatusCreating'));

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
        custom_plot_idea: plotIdea
      })
    });

    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || "Virhe uuden tarinan luonnissa");
    }

    const data = await res.json();
    const storyId = data.data.story_id;

    // Päivitetään lista ja ladataan tarina
    await loadStoryList();
    document.getElementById("storySelect").value = storyId;
    await loadStory(storyId);

    if (role === "player") {
      setMode("player");
    }
  } catch (err) {
    console.error("Virhe:", err);
    alert(err.message);
  } finally {
    showLoading(false);
  }
}

// --- Hahmojen Vienti ja Tuonti ---

function openExportCharModal() {
  if (!currentStoryId || !selectedCharacterId) {
    alert(t('selectStoryFirstAlert'));
    return;
  }
  document.getElementById("exportCharModal").classList.remove("hidden");
}

function closeExportCharModal() {
  document.getElementById("exportCharModal").classList.add("hidden");
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

    // Luodaan latauslinkki
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
    alert(t('selectStoryFirstAlert'));
    return;
  }
  document.getElementById("importJsonText").value = "";
  document.getElementById("importFileInput").value = "";
  importedJsonCache = null;
  document.getElementById("importCharModal").classList.remove("hidden");
}

function closeImportCharModal() {
  document.getElementById("importCharModal").classList.add("hidden");
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
      alert(t('importInvalidJsonAlert'));
    }
  };
  reader.readAsText(file);
}

async function executeImportCharacter() {
  if (!currentStoryId) {
    alert(t('selectStoryFirstAlert'));
    return;
  }

  let payload = importedJsonCache;
  const textVal = document.getElementById("importJsonText").value.trim();
  if (textVal) {
    try {
      payload = JSON.parse(textVal);
    } catch (err) {
      alert(t('importInvalidJsonAlert'));
      return;
    }
  }

  if (!payload) {
    alert(t('importInvalidJsonAlert'));
    return;
  }

  const includeState = document.getElementById("importCheckState").checked;
  const includeMemories = document.getElementById("importCheckMemories").checked;
  const asPlayer = document.getElementById("importCheckAsPlayer").checked;

  closeImportCharModal();
  showLoading(true, t('loadingStatusImporting'));

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

    const data = await res.json();
    alert(t('importSuccessAlert'));

    // Päivitetään tarinan hahmotiedot
    await loadStory(currentStoryId);
    selectCharacter(data.character.id);
  } catch (err) {
    alert(err.message);
  } finally {
    showLoading(false);
  }
}

// --- Vienti ja Lataus ---

function toggleExportMenu() {
  const menu = document.getElementById("exportMenu");
  menu.classList.toggle("hidden");
}

document.addEventListener("click", (e) => {
  if (!e.target.closest(".export-dropdown")) {
    document.getElementById("exportMenu")?.classList.add("hidden");
  }
});

function downloadStory(format) {
  if (!currentStoryId) {
    alert(t('selectStoryFirstAlert'));
    return;
  }
  window.open(`/api/stories/${currentStoryId}/export/${format}`, "_blank");
}

// --- Asetukset ---

function openSettingsModal() {
  loadSettings();
  document.getElementById("settingsModal").classList.remove("hidden");
}

function closeSettingsModal() {
  document.getElementById("settingsModal").classList.add("hidden");
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
    director_max_tokens: 3500,
    director_temperature: 0.85,
    director_reasoning_effort: "medium",
    character_model: provider === "azure" ? "gpt-4o" : "grok-4.3",
    character_max_tokens: 600,
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
  localStorage.setItem(SETTINGS_PROFILES_KEY, JSON.stringify(profiles));
}

function getActiveSettingsProfileId() {
  return localStorage.getItem(ACTIVE_SETTINGS_PROFILE_KEY);
}

function setActiveSettingsProfileId(profileId) {
  localStorage.setItem(ACTIVE_SETTINGS_PROFILE_KEY, profileId);
}

function renderSettingsProfileSelect() {
  const select = document.getElementById("settingsProfileSelect");
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

function currentSettingsProfile() {
  return getSettingsProfiles().find((profile) => profile.id === document.getElementById("settingsProfileSelect").value);
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
  const provider = document.getElementById("settingProvider").value;
  const endpoint = document.getElementById("settingAzureEndpoint").value;
  const model = document.getElementById(modelId).value;
  const isFixed = isAzureFoundryGpt5Profile(provider, endpoint, model);
  const temperatureInput = document.getElementById(temperatureId);
  const note = document.getElementById(noteId);

  temperatureInput.disabled = isFixed;
  temperatureInput.title = isFixed ? "Azure AI Foundry GPT-5 tukee vain lämpötilaa 1." : "";
  note.classList.toggle("hidden", !isFixed);
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
  setInputValue("settingDirectorReasoning", profile.director_reasoning_effort || "none");
  setInputValue("settingCharModel", profile.character_model);
  setInputValue("settingCharMaxTokens", profile.character_max_tokens);
  setInputValue("settingCharTemp", profile.character_temperature);
  setInputValue("settingCharReasoning", profile.character_reasoning_effort || "none");
  toggleProviderSettings(profile.provider);
  updateTemperatureControls();
}

function profileFromForm(profileId) {
  return {
    id: profileId,
    name: document.getElementById("settingProfileName").value.trim() || "Nimetön profiili",
    provider: document.getElementById("settingProvider").value,
    xai_api_key: document.getElementById("settingXaiKey").value.trim(),
    azure_openai_endpoint: document.getElementById("settingAzureEndpoint").value.trim(),
    azure_openai_api_key: document.getElementById("settingAzureKey").value.trim(),
    azure_openai_api_version: document.getElementById("settingAzureVersion").value.trim(),
    azure_deployment_name: document.getElementById("settingAzureDeployment").value.trim(),
    director_model: document.getElementById("settingDirectorModel").value.trim(),
    director_max_tokens: Number(document.getElementById("settingDirectorMaxTokens").value),
    director_temperature: Number(document.getElementById("settingDirectorTemp").value),
    director_reasoning_effort: document.getElementById("settingDirectorReasoning").value,
    character_model: document.getElementById("settingCharModel").value.trim(),
    character_max_tokens: Number(document.getElementById("settingCharMaxTokens").value),
    character_temperature: Number(document.getElementById("settingCharTemp").value),
    character_reasoning_effort: document.getElementById("settingCharReasoning").value,
  };
}

function persistCurrentSettingsProfile() {
  const selectedId = document.getElementById("settingsProfileSelect").value;
  if (!selectedId) return null;
  const profile = profileFromForm(selectedId);
  const profiles = getSettingsProfiles().map((item) => item.id === selectedId ? profile : item);
  saveSettingsProfiles(profiles);
  renderSettingsProfileSelect();
  document.getElementById("settingsProfileSelect").value = selectedId;
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
  const selectedId = document.getElementById("settingsProfileSelect").value;
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

async function loadSettings() {
  try {
    const res = await fetch("/api/settings");
    const data = await res.json();
    let profiles = getSettingsProfiles();
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
    document.getElementById("settingsProfileSelect").value = activeId;
    populateSettingsProfile(profiles.find((profile) => profile.id === activeId));

  } catch (err) {
    console.error("Virhe haettaessa asetuksia:", err);
  }
}

async function saveSettings() {
  const profile = persistCurrentSettingsProfile();
  if (!profile) return;

  try {
    const payload = {
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

    if (!res.ok) throw new Error("Asetusten tallennus epäonnistui");
  setActiveSettingsProfileId(profile.id);
    closeSettingsModal();
    alert(t('settingsSavedAlert'));
  } catch (err) {
    alert("Virhe: " + err.message);
  }
}
