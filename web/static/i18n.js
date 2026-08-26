// Tarinamoottori / StorytimeSimulator – i18n Kielipaketti

const translations = {
  fi: {
    // Brändi ja Yläpalkki
    brandName: "Tarinamoottori",
    selectStoryPrompt: "Valitse tarina...",
    newStoryBtn: "+ Uusi tarina",
    modeReader: "📖 Lukija",
    modePlayer: "⚔️ Pelaaja",
    modeDirector: "🎭 Ohjaaja",
    exportBtn: "📥 Vie",
    exportTxt: "Lataa Tekstitiedostona (.txt)",
    exportMd: "Lataa Markdownina (.md)",
    settingsTooltip: "Asetukset",

    // Kirjanäkymä & Pääalue
    defaultStoryTitle: "Valitse tai luo tarina",
    defaultStoryGenre: "Genre: -",
    emptyStoryTitle: "Ei avointa tarinaa",
    emptyStoryDesc: "Aloita luomalla uusi seikkailu tai valitse aiempi tarina yläpalkista.",
    createFirstStoryBtn: "Luo uusi tarina",
    imagePromptBadge: "🎨 Kuvausprompti valmiina",
    imagePromptCopied: "Kuvitusprompti kopioitu leikepöydälle:\n\n",
    actingCharacterLabel: "Hahmo:",

    // Alapalkki & Toiminnot
    loadingStatusDefault: "Agentit simuloivat tapahtumia ja kirjoittavat proosaa...",
    loadingStatusCreating: "Pääagentti luo maailmaa, hahmoja ja aloituskappaletta...",
    loadingStatusImporting: "Tuodaan hahmoa tarinaan...",
    readerPlaceholder: "Valinnainen toive tai käänne (esim. 'Yllättävä koputus ovelle')...",
    readerAdvanceBtn: "📖 Jatka tarinaa",
    playerTagDefault: "⚔️ Pelaajahahmo",
    playerPlaceholder: "Mitä teet tai sanot? (esim. 'Nostan katseeni ja kysyn: Kuka olet?')",
    playerActBtn: "⚔️ Toimi",
    directorPlaceholder: "Ohjaajan salainen komento (esim. 'Hahmojen välille syntyy riita kadonneesta avaimesta')...",
    directorActBtn: "🎭 Ohjaa & Jatka",

    // Sivupaneeli (Inspector)
    tabCharacters: "🧠 Hahmojen mieli",
    tabLore: "🗺️ Maailma",
    tabDirector: "🎬 Juoni & Ohjaaja",
    noCharactersYet: "Ei hahmoja luotu vielä.",
    ageLabel: "Ikä:",
    roleNpc: "NPC",
    rolePlayer: "⚔️ PELAAJA",
    physicalStateLabel: "❤️ Fyysinen vointi:",
    mentalStateLabel: "🧠 Henkinen tila & Tunteet:",
    secretMotiveLabel: "🎯 Salainen motiivi:",
    noSecretMotive: "Ei salaista motiivia.",
    memoryStreamTitle: "💭 Yksityinen muistivirta",
    noMemoriesYet: "Ei vielä tallennettuja muistoja.",
    exportCharBtn: "📤 Vie hahmo",
    importCharBtn: "📥 Tuo hahmo",

    // Maailma & Juoni välilehdet
    worldLoreHeading: "🌍 Maailman yleistieto & Säännöt",
    noWorldLore: "Ei maailmankuvausta saatavilla.",
    chronicleHeading: "📜 Tapahtumakronikka (Chronicle)",
    noChronicleYet: "Ei kronikkakirjauksia vielä.",
    chapterPrefix: "Luku",
    directorPlotHeading: "🎭 Salainen juonisuunnitelma",
    noDirectorPlot: "Ei juonisuunnitelmaa.",
    directorNotesHeading: "📝 Ohjaajan muistiinpanot",
    noDirectorNotes: "Ei muistiinpanoja.",

    // Uusi Tarina Modali
    newStoryHeader: "✨ Luo uusi tarina / roolipeli",
    newStoryTitleLabel: "Tarinan Otsikko *",
    newStoryTitlePlaceholder: "esim. Varjojen Laakso, Tähtiristelijä Orion, Murha Kartanossa",
    newStoryGenreLabel: "Genre / Tyylilaji",
    newStoryGenrePlaceholder: "esim. Tumma Fantasia, Kyberpunk, Psykologinen Trilleri, Sci-Fi",
    newStoryIdeaLabel: "Tarinan pohja-ajatus / Lähtötilanne",
    newStoryIdeaPlaceholder: "Kuvaile lyhyesti mistä tarina alkaa ja minkälainen maailma on...",
    newStoryPlotIdeaLabel: "Salainen Juoni-idea (Valinnainen)",
    newStoryPlotIdeaPlaceholder: "Jos sinulla on mielessä tietty juonenkäänne tai salaisuus, jonka Pääagentti tietää hahmoilta salassa...",
    newStoryRoleLabel: "Roolisi tarinassa",
    newStoryRoleReaderOpt: "📖 Lukija (Tekoäly luo ja ohjaa hahmoja, voit seurata ja ohjata tarinaa)",
    newStoryRolePlayerOpt: "⚔️ Pelaaja (Otat yhden hahmon ohjaukseesi)",
    playerCharNameLabel: "Pelaajahahmosi Nimi",
    playerCharNamePlaceholder: "esim. Eerik",
    playerCharDetailsLabel: "Pelaajahahmon taustat ja toiveet",
    playerCharDetailsPlaceholder: "esim. Entinen ritari, kantaa salattua sormusta, hiljainen luonne",
    cancelBtn: "Peruuta",
    createStorySubmitBtn: "🚀 Luo maailma & Aloita",
    titleRequiredAlert: "Anna tarinalle vähintään otsikko!",

    // Asetukset Modali
    settingsHeader: "⚙️ Asetukset & Rajapinnat",
    settingProviderLabel: "LLM Palveluntarjoaja",
    settingProviderXai: "xAI Grok (Suositus: luovuus ja vapaus)",
    settingProviderOpenai: "OpenAI (GPT-4o)",
    settingProviderOpenrouter: "OpenRouter (Monimallit)",
    settingXaiKeyLabel: "xAI API-avain (Grok)",
    settingOpenaiKeyLabel: "OpenAI API-avain",
    settingOpenrouterKeyLabel: "OpenRouter API-avain",
    settingDirectorModelLabel: "Pääagentin malli (Director / Kirjailija)",
    settingCharModelLabel: "Hahmoagenttien malli (Character Agent)",
    closeBtn: "Sulje",
    saveSettingsBtn: "Tallenna asetukset",
    settingsSavedAlert: "Asetukset tallennettu onnistuneesti!",

    // Hahmon Vienti Modali
    exportCharHeader: "📤 Vie hahmo (Storytime Character Card)",
    exportCharDesc: "Valitse mitä tietoja haluat sisällyttää vietävään hahmokorttiin:",
    exportIncludeProfile: "Perustiedot & Persoona (Nimi, ikä, ulkonäkö, luonne, kuvaus)",
    exportIncludeState: "Nykyinen tila & Salainen motiivi (Fyysinen & henkinen vointi, salainen tavoite)",
    exportIncludeMemories: "Hahmon muistivirta (Tarinan aikana kertyneet muistijäljet)",
    downloadCharJsonBtn: "💾 Lataa JSON-kortti",

    // Hahmon Tuonti Modali
    importCharHeader: "📥 Tuo hahmo tarinaan",
    importCharDesc: "Tuo aiemmin viety hahmokortti tähän tarinaan:",
    importFileLabel: "Valitse JSON-tiedosto (.json):",
    importPasteLabel: "Tai liitä JSON suoraan tähän:",
    importIncludeState: "Tuo hahmon nykyinen tila & salainen motiivi",
    importIncludeMemories: "Tuo hahmon aiemmat muistit",
    importAsPlayerCheckbox: "Aseta tämä hahmo pelaajan ohjaamaksi (⚔️ Pelaaja)",
    executeImportBtn: "📥 Tuo hahmo tarinaan",
    importSuccessAlert: "Hahmo tuotu onnistuneesti tarinaan!",
    importInvalidJsonAlert: "Virheellinen JSON-tiedosto tai sisältö.",
    selectStoryFirstAlert: "Valitse ensin tarina!"
  },

  en: {
    // Brand & Header
    brandName: "StorytimeSimulator",
    selectStoryPrompt: "Select a story...",
    newStoryBtn: "+ New Story",
    modeReader: "📖 Reader",
    modePlayer: "⚔️ Player",
    modeDirector: "🎭 Director",
    exportBtn: "📥 Export",
    exportTxt: "Download Text File (.txt)",
    exportMd: "Download Markdown (.md)",
    settingsTooltip: "Settings",

    // Book View & Main Area
    defaultStoryTitle: "Select or create a story",
    defaultStoryGenre: "Genre: -",
    emptyStoryTitle: "No Active Story",
    emptyStoryDesc: "Start by creating a new adventure or select an existing story from the header.",
    createFirstStoryBtn: "Create New Story",
    imagePromptBadge: "🎨 Image Prompt Ready",
    imagePromptCopied: "Illustration prompt copied to clipboard:\n\n",
    actingCharacterLabel: "Character:",

    // Action Bar & Controls
    loadingStatusDefault: "Agents are simulating actions and crafting prose...",
    loadingStatusCreating: "Director Agent is generating world, characters, and opening chapter...",
    loadingStatusImporting: "Importing character into story...",
    readerPlaceholder: "Optional director nudge or twist (e.g. 'A sudden knock on the door')...",
    readerAdvanceBtn: "📖 Continue Story",
    playerTagDefault: "⚔️ Player Character",
    playerPlaceholder: "What do you do or say? (e.g. 'I step forward and ask: Who goes there?')",
    playerActBtn: "⚔️ Act",
    directorPlaceholder: "Director's secret command (e.g. 'A fierce argument erupts over the missing key')...",
    directorActBtn: "🎭 Direct & Advance",

    // Sidebar (Inspector)
    tabCharacters: "🧠 Character Minds",
    tabLore: "🗺️ World",
    tabDirector: "🎬 Plot & Director",
    noCharactersYet: "No characters created yet.",
    ageLabel: "Age:",
    roleNpc: "NPC",
    rolePlayer: "⚔️ PLAYER",
    physicalStateLabel: "❤️ Physical Condition:",
    mentalStateLabel: "🧠 Mental & Emotional State:",
    secretMotiveLabel: "🎯 Secret Motive:",
    noSecretMotive: "No secret motive.",
    memoryStreamTitle: "💭 Private Memory Stream",
    noMemoriesYet: "No memories recorded yet.",
    exportCharBtn: "📤 Export Character",
    importCharBtn: "📥 Import Character",

    // World & Plot Tabs
    worldLoreHeading: "🌍 Shared World Lore & Rules",
    noWorldLore: "No world description available.",
    chronicleHeading: "📜 Event Chronicle",
    noChronicleYet: "No chronicle entries yet.",
    chapterPrefix: "Chapter",
    directorPlotHeading: "🎭 Secret Master Plot",
    noDirectorPlot: "No plot plan available.",
    directorNotesHeading: "📝 Director's Notes",
    noDirectorNotes: "No notes.",

    // New Story Modal
    newStoryHeader: "✨ Create New Story / RPG",
    newStoryTitleLabel: "Story Title *",
    newStoryTitlePlaceholder: "e.g. Valley of Shadows, Star Cruiser Orion, Murder at Blackwood Manor",
    newStoryGenreLabel: "Genre / Tone",
    newStoryGenrePlaceholder: "e.g. Dark Fantasy, Cyberpunk, Psychological Thriller, Hard Sci-Fi",
    newStoryIdeaLabel: "Starting Premise / Setting Idea",
    newStoryIdeaPlaceholder: "Describe briefly where the story begins and what kind of world it is...",
    newStoryPlotIdeaLabel: "Secret Plot Idea (Optional)",
    newStoryPlotIdeaPlaceholder: "Any hidden twist or objective known only to the Director Agent...",
    newStoryRoleLabel: "Your Role in Story",
    newStoryRoleReaderOpt: "📖 Reader (AI generates and directs characters, you can watch & guide)",
    newStoryRolePlayerOpt: "⚔️ Player (You control one character directly)",
    playerCharNameLabel: "Your Character Name",
    playerCharNamePlaceholder: "e.g. Eric",
    playerCharDetailsLabel: "Character Background & Notes",
    playerCharDetailsPlaceholder: "e.g. Former knight carrying a secret sigil, stoic temperament",
    cancelBtn: "Cancel",
    createStorySubmitBtn: "🚀 Build World & Begin",
    titleRequiredAlert: "Please provide at least a title for the story!",

    // Settings Modal
    settingsHeader: "⚙️ Settings & API Config",
    settingProviderLabel: "LLM Provider",
    settingProviderXai: "xAI Grok (Recommended: creative freedom & nuance)",
    settingProviderOpenai: "OpenAI (GPT-4o)",
    settingProviderOpenrouter: "OpenRouter (Multi-model)",
    settingXaiKeyLabel: "xAI API Key (Grok)",
    settingOpenaiKeyLabel: "OpenAI API Key",
    settingOpenrouterKeyLabel: "OpenRouter API Key",
    settingDirectorModelLabel: "Director / Novelist Model",
    settingCharModelLabel: "Character Agent Model",
    closeBtn: "Close",
    saveSettingsBtn: "Save Settings",
    settingsSavedAlert: "Settings saved successfully!",

    // Character Export Modal
    exportCharHeader: "📤 Export Character (Storytime Character Card)",
    exportCharDesc: "Select which data components to include in the exported character card:",
    exportIncludeProfile: "Profile & Persona (Name, age, appearance, personality, public bio)",
    exportIncludeState: "Current State & Secret Motive (Physical & emotional condition, hidden goal)",
    exportIncludeMemories: "Character Memory Stream (Episodic memories formed during the story)",
    downloadCharJsonBtn: "💾 Download JSON Card",

    // Character Import Modal
    importCharHeader: "📥 Import Character into Story",
    importCharDesc: "Import a previously exported character card into the active story:",
    importFileLabel: "Select JSON file (.json):",
    importPasteLabel: "Or paste character JSON here:",
    importIncludeState: "Import character's current state & secret motive",
    importIncludeMemories: "Import character's previous memory stream",
    importAsPlayerCheckbox: "Set this character as Player-controlled (⚔️ Player)",
    executeImportBtn: "📥 Import into Story",
    importSuccessAlert: "Character imported into story successfully!",
    importInvalidJsonAlert: "Invalid JSON format or file content.",
    selectStoryFirstAlert: "Please select a story first!"
  }
};

let currentLanguage = localStorage.getItem("storytime_lang") || "fi";

function t(key) {
  const langTable = translations[currentLanguage] || translations.fi;
  return langTable[key] || translations.fi[key] || key;
}

function setLanguage(lang) {
  if (translations[lang]) {
    currentLanguage = lang;
    localStorage.setItem("storytime_lang", lang);
    applyTranslations();
  }
}

function toggleLanguage() {
  const nextLang = currentLanguage === "fi" ? "en" : "fi";
  setLanguage(nextLang);
}

function applyTranslations() {
  document.documentElement.lang = currentLanguage;

  // Kielikytkimen aktiivisuus
  const langToggleBtn = document.getElementById("langToggleBtn");
  if (langToggleBtn) {
    langToggleBtn.textContent = currentLanguage === "fi" ? "🌐 FI" : "🌐 EN";
  }

  // Päivitetään kaikki elementit joilla on data-i18n
  document.querySelectorAll("[data-i18n]").forEach(el => {
    const key = el.getAttribute("data-i18n");
    if (key) {
      el.textContent = t(key);
    }
  });

  // Päivitetään placeholderit
  document.querySelectorAll("[data-i18n-placeholder]").forEach(el => {
    const key = el.getAttribute("data-i18n-placeholder");
    if (key) {
      el.placeholder = t(key);
    }
  });

  // Päivitetään title/tooltipit
  document.querySelectorAll("[data-i18n-title]").forEach(el => {
    const key = el.getAttribute("data-i18n-title");
    if (key) {
      el.title = t(key);
    }
  });
}
