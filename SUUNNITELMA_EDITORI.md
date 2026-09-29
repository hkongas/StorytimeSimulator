# Suunnitelma: Tarinan Editori ja Älykäs Tilasynkronointi

Tämä dokumentti määrittelee suunnitelman Tarinamoottorin laajentamiseksi yhdistetyksi **simulaattoriksi ja kirjailija-apuriksi**. Järjestelmä yhdistää itsenäisten hahmojen moniagenttisimulaation vapaaseen proosan muokkaukseen, automaattiseen maailmantilan hallintaan ja ristiriitojen valvontaan.

---

## 1. Visio ja Tavoite

* **Ei enää "raiteilta suistumista":** Kirjoittajalla on aina täysi valta korjata tai muuttaa tekoälyn kirjoittamaa tekstiä missä tahansa tarinan vaiheessa.
* **Kaksi muokkaustasoa:** 
  1. *Kevyt muokkaus:* Kirjoitusvirheet, tyyli ja sanamuodot korjataan välittömästi ilman LLM-kuluja.
  2. *Sisällöllinen muokkaus:* Juonimuutokset, uudet faktat ja tapahtumat synkronoidaan taustamallin avulla tietokantaan, hahmojen muisteihin ja havaintoihin.
* **Rytmityksen pelastaja:** Kirjoittaja voi kirjoittaa käsin pitkiä siirtymiä tai hypätä rutiinien yli ja antaa simulaattorin jatkaa taas tärkeissä valintakohdissa.

---

## 2. Toiminnalliset Tasot

### Taso 1: Viimeisimmän vuoron muokkaus ja kumoaminen (Undo / Reroll)
* **Viimeisimmän proosakappaleen editointi:** Käyttäjä korjaa tekstiä suoraan käyttöliittymässä.
* **Välitön vaikutus:** Kertoja saa seuraavassa vuorossa automaattisesti korjatun tekstin `recent_prose_context`-syötteeseensä.
* **Undo (Kumoaminen):** Mahdollisuus peruuttaa viimeisin vuoro kokonaan (palauttaa tila ja poistaa vuoro `scene_turns`-taulusta).

### Taso 2: Havaintojen ja muistien päivitys (Viimeisin vuoro)
* Kun käyttäjä muuttaa merkittävästi sitä, mitä viimeisimmässä vuorossa tapahtui (esim. *"Liisa ei poistunutkaan huoneesta, vaan otti avaimen pöydältä"*):
* Käyttöliittymä tarjoaa napin: **"Päivitä hahmojen havainnot"**.
* Kertoja / nopea taustamalli analysoi uuden tekstin ja päivittää hahmojen havainnot (`character_observations`) ja muistit (`character_memories`), jotta hahmot eivät toimi vanhan tapahtumakulun mukaan.

### Taso 3: Menneiden lukujen muokkaus ja tilasynkronointi (Reconciliation)
* Käyttäjä voi muokata mitä tahansa aiempaa vuoroa/lukua.
* **Diff-analyysi:** Taustamalli (nopea ja edullinen malli) vertaa vanhaa ja uutta proosaa:
  * Mitkä faktat muuttuivat? (esineet, paikat, hahmon fyysinen/henkinen tila).
  * Mitkä muistit mitätöityvät tai syntyvät uusina?
  * Onko tulevissa luvuissa ilmeisiä ristiriitoja? (esim. luvussa 2 poistettu esine ilmestyykin luvussa 4).
* Päivittää `story_runtime`-tilan (maailman faktat, avoimet langat) ja antaa käyttäjälle ilmoituksen havaituista ristiriidoista.

---

## 3. Tekninen Arkkitehtuuri

### A. Tietokanta ja Tallennus (`database/turn_store.py` & `database/db.py`)
1. **Vuoron proosan päivitys:**
   * Funktio `update_turn_prose(story_id: str, turn_id: int, new_prose: str)`
   * Päivittää `scene_turns.director_prose`.
   * Kasvattaa `story_revision`-lukua (estää rinnakkaiset ylikirjoitusristiriidat).
   * Kutsuu `rebuild_exports(story_id)` (päivittää `story.txt` ja `story.md`).
2. **Vuoron kumoaminen (Undo):**
   * Funktio `rollback_last_turn(story_id: str)`
   * Poistaa viimeisimmän `scene_turns`-rivin, siihen liittyvät `character_memories` ja palauttaa edellisen tilaversion.
3. **Muistien ja havaintojen korjaus:**
   * Funktio `update_character_observations(story_id: str, observations: dict[str, str])`
   * Funktio `apply_state_reconciliation(story_id: str, reconciliation_data: dict)`

### B. Taustaprosessi ja LLM-prompti (`engine/reconciliation_agent.py`)
Uusi agentti tai Kertojan alitoiminto, joka ajaa strukturoidun vertailun:

* **Syöte:**
  * Alkuperäinen teksti
  * Käyttäjän muokkaama teksti
  * Nykyiset hahmotilat ja maailman faktat
* **Strukturoitu JSON-vastaus:**
```json
{
  "has_state_changes": true,
  "summary_of_changes": "Liisa otti kartan mukaan sen sijaan että olisi jättänyt sen pöydälle.",
  "world_facts_added": ["Kartta on Liisan hallussa."],
  "world_facts_removed": ["Kartta jäi pöydälle."],
  "character_updates": [
    {
      "character_id": "liisa",
      "physical_state_override": null,
      "mental_state_override": null,
      "new_memories": ["Otin kartan mukaani pöydältä."],
      "invalidated_memories": ["Jätin kartan pöydälle."]
    }
  ],
  "potential_contradictions": [
    "Huomio: Luvussa 4 Pekka etsii karttaa pöydältä. Tämä voi vaatia pienen korjauksen."
  ]
}
```

### C. Backend API (`web/api.py`)
* `PUT /api/stories/{story_id}/turns/{turn_id}`
  * Runko: `{ "prose": "...", "sync_state": false }`
  * Jos `sync_state == false`: päivittää vain tekstin ja vientitiedostot (nopea, 0 tokenia).
  * Jos `sync_state == true`: ajaa taustalla `reconciliation_agentin` ja palauttaa päivitetyt tilat ja mahdolliset varoitukset.
* `POST /api/stories/{story_id}/turns/undo`
  * Kumoaa viimeisimmän vuoron ja palauttaa tarinan edellisen tilan.

### D. Käyttöliittymä (`web/static/app.js`, `index.html`, `style.css`)
* **Proosakappaleiden muokkaustila:**
  * Jokaisen vuorokappaleen viereen hienovarainen "Muokkaa"-nappi (tai tuplaklikkaus).
  * Muuttaa tekstin `textarea`-editoriksi, joka säilyttää kappalejaot.
* **Toimintonapit editorissa:**
  * `Tallenna vain teksti` (pikanappi oikolukuun ja sanamuotokorjauksiin).
  * `Tallenna ja päivitä tarinan tila` (tekee taustalla faktantarkistuksen ja muistipäivityksen).
  * `Peruuta muokkaus`.
* **Työkalupalkkiin "Kumoa viimeisin vuoro":**
  * Selkeä peruutusnappi, jos tekoälyn generoima vuoro oli epäonnistunut.
* **Konsistenssi-ilmoitukset:**
  * Pieni tiivistepaneeli tai huomiolaatikko, jos muokkauksen jälkeen havaitaan ristiriitoja.

---

## 4. Toteutuksen Vaiheistus (Roadmap)

1. **Vaihe 1: Peruseditori ja Undo (Nopea voitto)**
   * Lisää `rollback_last_turn` ja `update_turn_prose` tietokantakerrokseen.
   * Lisää API-reitit ja yksinkertainen muokkauskenttä UI:hin viimeisimmälle vuorolle.
   * Mahdollistaa välittömästi kirjoitusvirheiden korjaamisen ja epäonnistuneiden vuorojen uusimisen.

2. **Vaihe 2: Viimeisimmän vuoron havaintojen synkronointi**
   * Lisää "Päivitä hahmojen havainnot" -vaihtoehto, joka varmistaa, että hahmot eivät kärsi vanhoista harhoista, jos edellisen vuoron tapahtumia muutettiin.

3. **Vaihe 3: Täysi Reconciliation & Konsistenssivahti**
   * Toteutetaan `reconciliation_agent.py` kattavalla skeemalla.
   * Mahdollistetaan aiempien vuorojen muokkaus ja maailman faktalistan automaattinen päivitys.
