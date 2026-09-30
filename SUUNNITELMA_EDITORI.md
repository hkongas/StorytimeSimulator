# Suunnitelma: Tarinan Editori ja Älykäs Tilasynkronointi

Toteutustilanne 30.9.2026: tekstieditori, revision tarkistus, proosahistoria tietokannassa ja uusien vuorojen kumoaminen palautuspisteistä on toteutettu. Aloituksella ja vanhoilla vuoroilla ei ole palautuspisteitä. Myöhemmät erilliset tilamuutokset estävät kumoamisen. Tasot 2 ja 3 ovat edelleen suunnitelma, eivät käytettävissä olevia toimintoja. Tilasynkronoinnin pitää käyttää ennen vuoroa vallinnutta tilaa, näyttää muutosehdotus ja vaatia hyväksyntä. Vanhojen lukujen muutokset tarvitsevat myöhemmän tilan uudelleenarvioinnin tai haaran, eivät pelkkää nykytilan paikkausta.

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

## 5. Näkökulmat, Luvut Ja Uudet Seikkailut

Suunnittelusuositus 30.9.2026. Monirivinen syöttökenttä ja uuden oman jatkokappaleen analyysi, esikatselu ja atominen hyväksyntä on toteutettu. Vanhojen kappaleiden sovitus, pelaajan näkökulmatekstit ja muut tämän osion kokonaisuudet ovat edelleen suunnitelma.

### Yksi tapahtumatila, kaksi lukunäkymää

- Säilytä yksi kanoninen tapahtuma- ja maailmantila. Pelaajan teksti ja kertojan teksti ovat saman hyväksytyn vuoron esityksiä, eivät erillisiä simulaatioita.
- Roolipelissä pelaajan proosa tuotetaan vain hänen tiedoistaan ja havaitsemistaan tapahtumista. Myös valinnat, otsikot ja kertaukset rajataan tähän tietoon.
- Tiukin toteutus erottaa tapahtumien ratkaisun ja pelaajaproosan kirjoittamisen: jälkimmäinen kutsu ei saa kaikkitietävää proosaa tai muiden salaisuuksia. Kertojan täysi proosa voidaan tuottaa erikseen tai tilauksesta.
- Tallenna vuorolle mode, viewpoint_character_id ja näkökulmahahmon nimi vuoron hetkellä. Näytä erotin näkökulman tai tilan vaihtuessa. Vanhojen vuorojen näkökulmaa ei vaihdeta jälkikäteen pelaajahahmon mukana.
- Lukunäkymään Pelaajan näkökulma ja Kertojan kokonaiskertomus. Jälkimmäinen on tietoinen spoilerivalinta, ei osa pelaajan normaalia tietovirtaa.
- Älä kirjoita kaikille hahmoille omaa täyttä proosaa jokaisella vuorolla. Havainnot, muistit ja nykytila riittävät agenttien syötteeksi; hahmon päiväkirjan voi tuottaa pyynnöstä.
- Taustahahmot aktivoidaan merkityksellisen tavoitteen, aikarajan tai maailmantapahtuman perusteella. Ei kaikkien hahmojen kutsua joka vuorolla. Offscreen-tapahtumat tallennetaan ja tulevat pelaajalle näkyviin vasta havaittavien seurausten kautta.

### Luvut ja sisällysluettelo

- Hyödynnä olemassa olevaa chapter_end-rajaa, älä muodosta lukua kiinteästä vuoromäärästä.
- Tallenna otsikko, vuoroväli ja luvun tiivistelmä. Sisällysluettelo siirtyy tallennettuun vuorotunnisteeseen.
- Roolipelissä näkyvät otsikot ja kertaukset eivät saa paljastaa salaisia tapahtumia. Kertojan kronikka voi sisältää laajemman version.
- Tiivistelmän pitää avautua myös napsauttamalla ja näppäimistöllä, ei vain hoverilla. Kumulatiivinen runtime.summary ei korvaa historiallisia lukutiivistelmiä.

### Maailman kopiointi uudeksi seikkailuksi

- Luo ensin paikallinen luonnos ilman LLM-kutsua tai aloituskappaletta. Käyttäjä valitsee hahmot, teeman, juonen ja alkutilanteen ennen aloituksen generointia.
- Erottele Maailmapohja (lore ja hahmojen perustiedot) ja Jatka nykyisestä tilanteesta (myös valitut faktat, tilat ja muistit).
- Älä kopioi vanhaa juonisuunnitelmaa, pyyntökuitteja, API-lokeja tai undo-historiaa uuteen tarinaan.
- Valitsemattomiin hahmoihin viittaavia suhteita tai muistoja ei poisteta hiljaisesti: valitse jäävätkö he maailman taustahahmoiksi vai tarvitseeko sisältö hyväksytyn sovituksen.
- Tallenna lähdetarinan tunniste ja revision kopiointirajaksi. Uusi luonnos on itsenäinen, ei linkki muuttuvaan lähdetilaan.

### Käyttäjän kirjoittama jatko

- Luonnos kertojalle: monirivinen syöte, jonka kertoja muotoilee ja ratkaisee hahmojen aikeiden kanssa. Tämä syöttökenttä on toteutettu; Enter lisää rivin ja Ctrl/Cmd+Enter lähettää.
- Oma valmis kappale: toteutettu erillinen toiminto säilyttää proosan sellaisenaan. Tapahtumat, havaitsijat ja tilamuutokset poimitaan esikatseluun ja hyväksytään atomisesti palautuspisteen kanssa. Esikatselu ei muuta tilaa, vanhenee 30 minuutissa ja hylätään revision vaihtuessa. Ensimmäinen versio käyttää olemassa olevia hahmoja, enintään 20 000 merkin tekstiä eikä sovita vanhoja kappaleita.
- Tuleva toive pidetään erillään jo tapahtuneesta proosasta. Tyhjä toive sallii itsenäisen jatkon.
- Synkronoimaton oma teksti on luonnos, ei hahmojen tietolähde. Agenttien jatko estetään, kunnes muutokset on hyväksytty tai hylätty.

Suositeltu toteutusjärjestys: oma jatko ja tilasynkronointi; pelaajan näkökulma ja vuorojen näkökulmatiedot; luvut ja sisällysluettelo; maailman kopiointi; valikoiva taustasimulaatio ja pyynnöstä tuotettavat hahmopäiväkirjat.
