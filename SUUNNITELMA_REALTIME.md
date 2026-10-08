# Tarinamoottori: Realtime-arkkitehtuurin tutkimussuunnitelma

Tila: **tutkimus- ja arkkitehtuurisuunnitelma, ei toteutusta.** Tätä dokumenttia ei oteta käyttöön nykyisessä tavanomaisten mallikutsujen toteutuksessa (ks. `SUUNNITELMA_SIMULAATIO.md`). Dokumentti kerää virallisista lähteistä varmennetut faktat ja merkitsee erikseen omat ehdotukset. Yksityistä lähdekoodia ei ole lähetetty ulkopuolisille tutkimushakujen yhteydessä — kaikki tiedonhaku kohdistui vain julkisiin, yleisiin API-dokumentaatiosivuihin.

Päivitetty: 2026-10-07. Kaikki alla olevat numerot, mallinimet ja rajat on poimittu valmistajien virallisilta dokumentaatiosivuilta mainittuna päivänä; API:t ja hinnat muuttuvat, joten ennen toteutusta jokainen luku on tarkistettava uudelleen alkuperäisestä lähteestä.

Merkintätapa koko dokumentissa:
- **[FAKTA]** = varmennettu virallisesta dokumentaatiosta, lähde mainittu.
- **[EHDOTUS]** = tämän suunnitelman oma arkkitehtuuriehdotus Tarinamoottorille, ei valmistajan vaatimus.

**HUOMIO:** Vaikka nämä rajapinnat tukevat voice to voice tuotosta, käytetään rajapintoja vain text to text moodilla.

---

## 1. Yhteenveto ja suositus

**[EHDOTUS]** Realtime-puheliittymä (OpenAI Realtime API / Azure GPT Realtime / Google Gemini Live API) on erillinen, valinnainen lisäkerros tulevaisuudessa — ei nykyisen tekstipohjaisen simulaation korvaaja. Suositus:

1. Jatka nykyistä tavanomaista (ei-reaaliaikaista) mallikutsutoteutusta kertojalle ja hahmoille (ks. `SUUNNITELMA_SIMULAATIO.md`), koska se on provider-riippumaton, halvempi ja yksinkertaisempi debugata.
2. Rakenna mallikutsut niin, että kertoja- ja hahmopromptit, työkalurajapinnat (tool calls) ja tilakoneen tapahtumat (StateChange, havainnot, kronikka) pysyvät erillään varsinaisesta kuljetuskerroksesta (HTTP vs. WebSocket vs. WebRTC).
3. Kun/jos ääni- tai erittäin matalan viiveen vaatimus ilmaantuu, lisää **Realtime-adapteri**, joka toteuttaa saman sisäisen rajapinnan (promptit, työkalut, tapahtumaloki) mutta puhuu valitun providerin realtime-protokollaa. Tämä pitää ydinlogiikan (tila, havainnot, pysyvyys) muuttumattomana.
4. Älä oleta, että käyttäjän valitsemat chat-mallit (`gpt-6.1-sol`, `gpt-6-luna`) toimivat Realtime-päätepisteissä — ks. luku 2.

---

## 2. Dedikoidut realtime-mallit vs. mielivaltainen chat-malli

**[FAKTA]** OpenAIn Realtime API vaatii nimenomaisesti realtime-tuotelinjan malleja, ei mitä tahansa chat-mallia. Virallinen malliluettelo (developers.openai.com/api/docs/guides/realtime, haettu 2026-10-07) käyttää esimerkkinä `gpt-realtime-2.1`. Azure OpenAI (Microsoft Foundry) -dokumentaatio listaa tuetut realtime-mallit erikseen omana tuoteryhmänään:

> `gpt-4o-realtime-preview` (2024-12-17), `gpt-4o-mini-realtime-preview` (2024-12-17), `gpt-realtime` (2025-08-28), `gpt-realtime-mini` (2025-10-06 ja 2025-12-15), `gpt-realtime-1.5` (2026-02-23), `gpt-realtime-2` (2026-05-07), `gpt-realtime-2.1` (2026-07-07), `gpt-realtime-2.1-mini` (2026-07-07), `gpt-realtime-translate` (2026-05-06), `gpt-realtime-whisper` (2026-05-06), `gpt-live-transcribe` (2026-07-29).
> Lähde: learn.microsoft.com/azure/ai-foundry/openai/how-to/realtime-audio, haettu 2026-10-07.

OpenAIn yleinen hinnoittelusivu (developers.openai.com/api/docs/pricing, haettu 2026-10-07) listaa "Realtime and audio generation models" omana ryhmänään erillään tavallisista chat-malleista (gpt-6-astra, gpt-6.1-sol, gpt-6-luna jne., jotka ovat "Flagship models" -ryhmässä). Näitä ryhmiä ei sekoiteta hinnoittelussa eikä mallinimissä.

**[FAKTA]** Google Gemini -puolella Live API on dokumentoitu omana mallilinjanaan erillään tavanomaisista Gemini-teksti/chat-malleista. Virallinen malli­vertailu (ai.google.dev/gemini-api/docs/live-api/capabilities, haettu 2026-10-07) listaa nimenomaan `gemini-3.8-live`, `gemini-3.8-live-extended-thinking` ja (legacy) `gemini-3.1-flash-live-preview` Live-yhteensopivina malleina. Teknisissä spekseissä (ai.google.dev/gemini-api/docs/live, haettu 2026-10-07) todetaan protokollaksi "Stateful WebSocket connection (WSS)" ja syötteiksi raaka 16-bit PCM -ääni (16 kHz), kuvat (≤1 FPS) ja teksti; ulostulo on 24 kHz PCM-ääni.

**Johtopäätös [FAKTA → EHDOTUS]:** Realtime-yhteensopivuus ei ole ominaisuus, jonka mikä tahansa tekstimalli automaattisesti saa. Käyttäjän nykyiset valinnat `gpt-6.1-sol` ja `gpt-6-luna` esiintyvät vain OpenAIn tavallisessa "Flagship models" -hinnastossa, **ei** "Realtime and audio generation models" -ryhmässä (tarkistettu developers.openai.com/api/docs/pricing, 2026-10-07). Niitä **ei pidä olettaa Realtime-päätepisteen kanssa yhteensopiviksi**, eikä tätä oletusta pidä koodata sisään ilman erillistä, ajantasaista tarkistusta OpenAIn/Azuren mallidokumentaatiosta toteutushetkellä. Mahdollinen myöhempi Realtime-adapteri tarvitsee oman, erikseen konfiguroitavan mallinimen (esim. `REALTIME_NARRATOR_MODEL`, `REALTIME_CHARACTER_MODEL`), joka ei oletusarvoisesti periydy chat-mallin asetuksesta.

---

## 3. Päätepisteet: WebSocket vs. WebRTC (ja SIP)

**[FAKTA] OpenAI Realtime:**
- Selainkäyttöön suositellaan **WebRTC**-yhteyttä; palvelin-palvelin-integraatioihin **WebSocket**. Lähde: developers.openai.com/api/docs/guides/realtime, developers.openai.com/api/docs/guides/voice-webrtc, developers.openai.com/api/docs/guides/voice-websockets (haettu 2026-10-07).
- GA-rajapinnassa selaimen ephemeraalit tunnistetiedot (client secrets) luodaan `POST /v1/realtime/client_secrets` -kutsulla, ja WebRTC-puhelut muodostetaan `/v1/realtime/calls`-reitin kautta. Beta-otsake `OpenAI-Beta: realtime=v1` ei enää kuulu GA-rajapintaan. Lähde: developers.openai.com/api/docs/guides/realtime, haettu 2026-10-07.
- Istunnon enimmäiskesto on **60 minuuttia**. Lähde: developers.openai.com/api/docs/guides/realtime-conversations, haettu 2026-10-07.

**[FAKTA] Azure OpenAI (Microsoft Foundry):**
Virallinen vertailutaulukko (learn.microsoft.com/azure/ai-foundry/openai/how-to/realtime-audio, haettu 2026-10-07):

| Yhteystapa | Käyttötapaus | Viive | Sopii parhaiten |
|---|---|---|---|
| WebRTC | Asiakassovellukset | ~100 ms | Selain-/mobiilisovellukset |
| WebSocket | Palvelin-palvelin | ~200 ms | Taustapalvelut, erä­käsittely, väliohjelmistot |
| SIP | Puhelinliittymä | vaihtelee | Call centerit, IVR, puhelinsovellukset |

Azure noudattaa muuten OpenAIn Realtime-tapahtumaspesifikaatiota; dokumentoitu poikkeus koskee `input_audio_transcription`-kentän `model`-arvoa, joka Azuressa on deployment-nimi, ei OpenAIn mallinimi. Lähde: learn.microsoft.com/azure/ai-foundry/openai/realtime-audio-reference, haettu 2026-10-07.

**[FAKTA] Google Gemini Live API:**
- Protokolla on **stateful WebSocket (WSS)**; WebRTC ei ole Googlen oma ensisijainen vaihtoehto, mutta kolmansien osapuolten integraatiot voivat tarjota WebRTC-kerroksen Live APIn päälle. Lähde: ai.google.dev/gemini-api/docs/live, haettu 2026-10-07.
- Kaksi toteutustapaa: **server-to-server** (oma backend yhdistää Live APIin WebSocketilla) ja **client-to-server** (frontend yhdistää suoraan WebSocketilla, ephemeraalein tokenein). Sama lähde.

**[EHDOTUS]** Tarinamoottorin palvelinarkkitehtuuri (oma backend hallitsee kaikki pelaajat ja sessiot) sopii luontevasti palvelin-palvelin-malliin kaikilla kolmella providerilla: oma palvelin pitää omat WebSocket/WebRTC-yhteydet providerin realtime-päätepisteeseen, eikä selain koskaan puhu suoraan OpenAI/Google-palvelimille. Tämä säilyttää nykyisen keskitetyn auktoriteetin (kertoja validoi, tallentaa, suodattaa havainnot) myös realtime-tilassa.

---

## 4. Yksi kertoja + jokainen hahmo omana palvelimen hallinnoimana sessiona

**[FAKTA]** Sekä OpenAI että Gemini Live API ovat luonteeltaan **yksi malli-istunto per WebSocket/WebRTC-yhteys**: istunto pitää sisällään yhden mallin, sen konfiguraation (`session.update` / `LiveConnectConfig`) ja yhden keskusteluhistorian (OpenAIn "Conversation"-objekti). Ei ole olemassa yhtä virallista moni-agentti-istuntoa, jossa yksi yhteys jakaisi useita "persoonia" saman mallitilan sisällä. Lähteet: developers.openai.com/api/docs/guides/realtime-conversations ("A Realtime Session is a stateful interaction between the model and a connected client... Session, Conversation, Responses"), ai.google.dev/gemini-api/docs/live-api/session-management, haettu 2026-10-07.

**[EHDOTUS]** Tästä seuraa suoraan Tarinamoottorin arkkitehtuuriperiaate: **kertoja ja jokainen hahmo tarvitsevat oman, erillisen realtime-session/yhteyden**, aivan kuten nykyinen tavanomainen toteutus tekee erilliset mallikutsut kertojalle ja kullekin hahmolle. Palvelin (ei selain, ei pelaaja) omistaa ja hallinnoi näitä yhteyksiä:

- **Kertojaistunto**: pitää koko maailman tilan, kaikkien hahmojen piilotetut ajatukset (ks. luku 5), StateChange-päätökset ja proosan tuottamisen.
- **Hahmoistunto per aktiivinen hahmo**: saa vain kyseisen hahmon oman näkymän (tiedot, havainnot, muisti) — ei koko maailman tilaa eikä muiden hahmojen piilotettuja ajatuksia.
- Palvelin reitittää tapahtumat istuntojen välillä (kertoja → hahmo: tilanne ja kehote; hahmo → kertoja: aie/puhe/hidden thought), eivätkä hahmoistunnot koskaan yhdisty suoraan toisiinsa.
- Koska jokainen WebSocket/WebRTC-yhteys ja sen taustalla oleva mallikonteksti laskutetaan erikseen (ks. luku 10), hahmomäärän kasvu kasvattaa yhteyksien ja siten kustannuksen lineaarisesti — tämä on tietoinen arkkitehtuurivalinta, ei sivuvaikutus.

---

## 5. Piilotetut ajatukset vain kertojalle; havaittava toiminta reititetään

**[FAKTA — tekninen mekanismi, ei Tarinamoottori-spesifinen]** Molemmat API:t tukevat eriytettyä tekstiä/ääntä ja "järkeilyä" (reasoning/thinking), jota ei automaattisesti lähetetä kaikille osapuolille:
- OpenAI Realtime: `response.create`-tapahtumalla voi pyytää vain tekstiä tai vain ääntä (`output_modalities`), ja järjestelmäkehote (`instructions`) sekä konversaatioitemit ohjataan eksplisiittisesti tiettyyn istuntoon `conversation.item.create`-tapahtumalla. Lähde: developers.openai.com/api/docs/guides/realtime-conversations, haettu 2026-10-07.
- Gemini Live: Gemini 3.8 Live / Extended Thinking -malleissa on sisäänrakennettu "Thinking"-tuki (interleaved reasoning / `thinkingLevel`), joka on eri asia kuin mallin ulos lähettämä puhe/teksti. Lähde: ai.google.dev/gemini-api/docs/live-api/capabilities, haettu 2026-10-07.

**[EHDOTUS]** Koska yksikään näistä API:sta ei tarjoa valmista "moni-osapuolinen keskustelu, jossa osa sisällöstä on piilossa osalta kuulijoista" -mallia, Tarinamoottorin on itse toteutettava piilotettujen ajatusten ja julkisen havaittavan toiminnan erottelu **sovellustasolla, oman istuntoarkkitehtuurinsa kautta** (ei providerin ominaisuutena):

- Hahmoistunto tuottaa jäsennellyn vastauksen, joka sisältää sekä "sisäisen ajatuksen/aikeen" että "havaittavan toiminnan/puheen" kenttinä (samaan tapaan kuin nykyinen tavanomainen toteutus erottelee StateChange/proosa/havainnot, ks. `SUUNNITELMA_SIMULAATIO.md` luku 4).
- Palvelin lähettää hahmon koko jäsennellyn vastauksen (ajatus mukaan lukien) **vain kertojaistunnolle**. Muille hahmoistunnoille ja pelaajalle lähetetään vain kertojan sallima, suodatettu havaittava osa.
- Tämä vastaa nykyistä periaatetta: "Hahmon rajattu näkymä muodostetaan havainnoista, ei kaikkitietävän proosan suodattamattomasta tulkinnasta" (`SUUNNITELMA_SIMULAATIO.md` luku 4) ja "Hahmon läsnäolo ei oikeuta välittämään hänen nimeään kaikille muille... Lista muodostetaan havaittavista tai jo tiedossa olevista läsnäolijoista" (sama, luku 2).
- Realtime-muodossa tämä tarkoittaa, ettei hahmon raakaa audio/text-deltaa koskaan yhdistetä suoraan toisen hahmon istunnon sisääntuloon ilman kertojan reititystä välissä.

---

## 6. Julkinen puhe vain todellisille kuulijoille; kuiskaus ja kertojan adjudikaatio

**[EHDOTUS — rakentuu luvun 5 mekanismin päälle]** Kuten nykyisessä tavanomaisessa toteutuksessa, myös realtime-arkkitehtuurissa julkinen puhe ei saa mennä sokeasti kaikille istunnoille:

- Kertojaistunto (tai sen sisäinen logiikka) ratkaisee kunkin puhetapahtuman kuulijajoukon samoilla säännöillä kuin nykyinen havaintosuodatus (etäisyys, esteet, huomio, piilossaolo — `SUUNNITELMA_SIMULAATIO.md` luku 2). Vasta tämän ratkaisun jälkeen palvelin työntää (forward/relay) puheen vain niiden hahmoistuntojen sisääntuloon, jotka kertoja on hyväksynyt kuulijoiksi.
- **Kuiskaus (whisper)** on oma, eksplisiittisesti valikoiva reititys: palvelin merkitsee tapahtuman kohdennetuksi yhdelle tai nimetylle pienelle joukolle hahmoistuntoja, eikä se koskaan päädy muiden hahmojen tai kertojan julkiseen historiaan ilman kertojan omaa adjudikaatiota (esim. jos kertoja päättää, että kuiskaus paljastuu kolmannelle osapuolelle tarinallisesti).
- Kertoja toimii samalla tavalla kuin nykyisessä toteutuksessa: se ei ole vain reititin, vaan auktoriteetti, joka hyväksyy/hylkää tapahtumat ja ratkaisee ristiriidat ennen kuin ne tulevat pysyviksi (vrt. `SUUNNITELMA_SIMULAATIO.md` luku 4: "Proosan, tapahtumien ja tilan ristiriita pysäyttää hyväksynnän korjattavaksi").
- Kumpikaan provider ei tarjoa valmista "kuiskaa vain näille N osallistujalle" -primitiiviä moni-istunto-skenaarioon; tämä on puhtaasti sovellustason reititys palvelimessa, joka päättää mitkä `conversation.item.create`/`send_client_content`-kutsut lähetetään mihinkin istuntoon.

---

## 7. Rajattu autonominen vastaaminen ja odottaminen

**[FAKTA]** Molemmat API:t tukevat mallin oma-aloitteisen vastaamisen rajoittamista:
- OpenAI: istunnon voi konfiguroida niin, ettei malli vastaa automaattisesti puheen loputtua (VAD pois päältä → sovellus päättää milloin `response.create` lähetetään), tai `turn_detection`-asetuksella (esim. `semantic_vad`) hallita milloin mallin vuoro alkaa. Lähde: developers.openai.com/api/docs/guides/realtime-conversations, haettu 2026-10-07.
- Gemini: "Proactive audio" -ominaisuus antaa sovelluksen "control when the model responds and in what contexts" ja asynkroninen funktiokutsujärjestelmä (`behavior: NON_BLOCKING`, ajoitusvaihtoehdot `SILENT`, `WHEN_IDLE`, `INTERRUPTED`) sallii mallin jatkaa taustalla ilman, että se heti puhuu päälle. Lähde: ai.google.dev/gemini-api/docs/live, ai.google.dev/gemini-api/docs/live-api/capabilities, haettu 2026-10-07.

**[EHDOTUS]** Tarinamoottorin hahmoistunnoille asetetaan sovellustasolla **yläraja autonomisille, oma-aloitteisille vastauksille** (esim. hahmo ei saa generoida uutta julkista toimintaa ilman kertojan sallimaa vuoroa tai aikaikkunaa), vastaavasti kuin nykyinen toteutus rajaa hahmon toimijuutta: hahmo tekee valintoja omien tietojensa pohjalta, mutta ohjelma (= kertojaistunto) pitää toimivallan. Käytännössä tämä tarkoittaa, että palvelin lähettää `response.create`/`send_client_content`-pyynnön hahmoistunnolle vasta kertojan päätöksellä, ei suoraan VAD:n laukaisemana.

---

## 8. Kertojan työkalukomento: pysäytä/keskeytä/pelaaja

**[FAKTA — mekanismi]** Molemmat API:t tukevat funktiokutsuja (tool/function calling) osana istuntoa, joten kertojaistunto voi altistaa työkalurajapinnan, jolla se ohjaa muita istuntoja:
- OpenAI Realtime: funktiot määritellään istunnon konfiguraatiossa, malli pyytää kutsua, sovellus suorittaa ja palauttaa tuloksen istunnon kautta (sama mekanismi kuin Chat Completions / Responses APIssa, dokumentoitu samassa Realtime-oppaassa, developers.openai.com/api/docs/guides/realtime-conversations).
- Gemini Live: funktiokutsut määritellään `tools`-kentässä, malli lähettää `tool_call`-viestin, sovellus vastaa `session.send_tool_response`-kutsulla. Tuki synkroniselle ja (joissain malleissa) asynkroniselle (`NON_BLOCKING`) kutsulle vaihtelee mallin mukaan (vertailutaulukko: Gemini 3.8 Live = molemmat, Gemini 2.5 Flash Live = vain async, legacy 3.1 Flash Live = vain synkroninen). Lähde: ai.google.dev/gemini-api/docs/live-api/tools ja .../capabilities, haettu 2026-10-07.

**[EHDOTUS]** Kertojaistunnolle määritellään omat sisäiset "ohjaustyökalut" (ei pelimaailman toimintoja, vaan session-tason komentoja), esim. `pause_character_session(character_id)`, `resume_character_session(character_id)`, `stop_character_session(character_id)`, `request_player_input()`. Nämä eivät ole providerin valmiita ominaisuuksia vaan Tarinamoottorin oma funktiolista, jonka kertoja saa kutsuttavaksi — toteutus (mitä palvelin tekee kutsun saadessaan: sulkee/avaa toisen WebSocket-yhteyden, puskuroi syötteen jne.) on sovelluskoodia providerin API:n päällä.

---

## 9. Joutokäynti ajastimella, ei verkkonopeudella; sulkemis- vs. uudelleenkäyttörajat

**[FAKTA] Istunnon/yhteyden kestorajat:**
- OpenAI Realtime -istunnon enimmäiskesto on **60 minuuttia**. Lähde: developers.openai.com/api/docs/guides/realtime-conversations, haettu 2026-10-07.
- Gemini Live: "Without compression, audio-only sessions are limited to **15 minutes**, and audio-video sessions are limited to **2 minutes**." Itse **yhteyden** (connection) kesto on rajattu noin **10 minuuttiin**, minkä jälkeen yhteys katkeaa vaikka istunto jatkuisi käsitteellisesti (ks. luku alla session resumption). Palvelin lähettää `GoAway`-viestin ennen katkaisua, viesti sisältää `timeLeft`-kentän. `ContextWindowCompressionConfig` (liukuva ikkuna) mahdollistaa istunnon jatkamisen rajatta. Lähde: ai.google.dev/gemini-api/docs/live-api/session-management, haettu 2026-10-07.

**[EHDOTUS]** Koska providerin yhteys/istunto katkeaa aikarajan (ei verkkonopeuden) perusteella, Tarinamoottorin simulaation **joutokäyntilogiikka (idle timer)** on pidettävä tarinan sisäisenä, providerista riippumattomana mekanismina: pelaajan tai hahmon passiivisuus mitataan simulaation omalla kellolla/vuorologiikalla (sama periaate kuin nykyisessä ei-reaaliaikaisessa toteutuksessa), ei realtime-yhteyden verkkolatenssilla tai -nopeudella. Realtime-adapterin tehtävä on piilottaa providerin yhteysrajat sovelluslogiikalta:

- **Sulje istunto**, kun kohtaus päättyy tai hahmo poistuu pitkäksi aikaa (vrt. `SUUNNITELMA_SIMULAATIO.md`: poissa oleva hahmo ei saa paikallisia havaintoja; paluu on uusi saapumistapahtuma). Uuden istunnon avaaminen on tällöin halvempaa ja yksinkertaisempaa kuin tilan säilyttäminen auki käyttämättömänä.
- **Käytä uudelleen / resumoi istunto**, kun tauko on lyhyt ja tarinan konteksti pitää säilyttää välittömästi jatkuvana (esim. kertojaistunto koko kohtauksen ajan). Tällöin käytetään providerin omaa resumointimekanismia (luku 11), ei avata uutta istuntoa tyhjästä.
- Konkreettinen raja-arvo (montako sekuntia/minuuttia joutokäyntiä ennen sulkemista) on sovelluksen oma parametri, jota ei pidä sitoa suoraan OpenAIn 60 minuutin tai Geminin 10–15 minuutin teknisiin kattoihin — nämä ovat *maksimeja*, eivät suositeltuja joutokäyntirajoja.

---

## 10. Tyypitetty tapahtumaloki vs. proosa tavanomaisella kutsulla

**[FAKTA]** Realtime-protokollat ovat luonteeltaan **tyypitettyjä tapahtumavirtoja** (client events / server events), eivät yhtä proosavastausta: OpenAI dokumentoi kymmeniä tapahtumatyyppejä (`session.created`, `session.updated`, `conversation.item.create`, `conversation.item.added`, `conversation.item.done`, `response.create`, `response.created`, `response.output_item.added`, `response.content_part.added`, `response.output_text.delta`/`.done`, `response.output_audio.delta`/`.done`, `response.output_audio_transcript.delta`/`.done`, `response.done`, `input_audio_buffer.speech_started`/`.speech_stopped`/`.committed`, `rate_limits.updated` jne.) järjestyksellisenä elinkaarena. Lähde: developers.openai.com/api/docs/guides/realtime-conversations, haettu 2026-10-07. Gemini Live vastaavasti käyttää tyypitettyjä viestejä (`BidiGenerateContentSetup`, `serverContent`, `toolCall`, `sessionResumptionUpdate`, `goAway`, `generationComplete` jne.). Lähde: ai.google.dev/gemini-api/docs/live-api/session-management, haettu 2026-10-07.

**[EHDOTUS]** Nykyinen tavanomainen toteutus tuottaa yhden jäsennellyn vastauksen per kutsu (StateChange + proosa + havainnot samassa mallikutsussa, ks. `SUUNNITELMA_SIMULAATIO.md` luku 4). Realtime-maailmassa tämä yksi "vuoro" hajoaa kymmeniksi erillisiksi, ajallisesti limittyviksi delta-tapahtumiksi. Siksi Realtime-adapterin on sisällettävä **kokoaja (aggregator)**, joka:
- kerää saman vastauksen `delta`-tapahtumat yhteen ennen kuin niistä muodostetaan sovelluksen StateChange/proosa/havainto-tietomalli,
- käyttää `response.done`/`generationComplete`-tapahtumaa luotettavana "vuoro on valmis" -signaalina ennen tallennusta tietokantaan,
- säilyttää saman proosa/tapahtuma/tila-ristiriidattomuusperiaatteen kuin tavanomaisessa kutsussa, vaikka data saapuu paloina.
Tämä on merkittävä toteutustyön lisä verrattuna tavanomaiseen yhden-vastauksen-per-kutsu-malliin, ja se on yksi keskeinen peruste pitää realtime myöhempänä, valinnaisena kerroksena (luku 1).

---

## 11. Kirjoittamisen keskeytys/perumiskilpa-ajot, barriääri, luonnos ei pelaajan toiminto

**[FAKTA] Keskeytys (barge-in) ja puskurin katkaisu:**
- OpenAI: Kun käyttäjä alkaa puhua mallin tuottaessa ääntä, palvelin lähettää `input_audio_buffer.speech_started`-tapahtuman. Sovellus voi/tulee tällöin katkaista (truncate) mallin meneillään olevan äänivastauksen (dokumentoitu samassa WebSocket-tapahtumataulukossa; `input_audio_buffer.clear` löytyy palvelimen lähettämien tapahtumien joukosta ääniulostulon yhteydessä). Semanttinen VAD (`turn_detection: {type: "semantic_vad"}`) on konfiguroitavissa istunnon perustaksi. Lähde: developers.openai.com/api/docs/guides/realtime-conversations, haettu 2026-10-07.
- Gemini: `send_client_content`-kutsu with `turn_complete=true` **"unconditionally interrupts generation"** — eli asiakas voi aina pakottaa keskeytyksen lähettämällä uuden vuoron, riippumatta mallista. Automaattinen "barge-in" (malli huomaa käyttäjän puheen kesken oman vastauksensa) perustuu palvelinpuolen äänenaktiviteetin tunnistukseen (automatic/server-side VAD); kun uutta puhetta havaitaan kesken mallin vastauksen, istunto keskeyttää ja ilmoittaa asiasta. Lähde: ai.google.dev/gemini-api/docs/live-api/capabilities, haettu 2026-10-07, sekä yleiskatsaus ai.google.dev/gemini-api/docs/live ("Barge-in: Users can interrupt the model at any time").

**[EHDOTUS — kirjoittamisen/perumisen kilpa-ajot ja luonnos]** Kumpikaan provider ei tunne käsitteitä "pelaaja kirjoittaa, mutta ei ole vielä lähettänyt" tai "luonnos ei ole vielä toiminto" — nämä ovat Tarinamoottorin omia UX/sovelluskäsitteitä, jotka on pidettävä selvästi erillään providerin keskeytysmekanismista:
- Pelaajan **kirjoittaessa (typing) mutta ei vielä lähettäessä**, sovellus ei saa lähettää mitään `conversation.item.create`/`send_client_content`-kutsua providerille. Luonnos elää vain paikallisessa UI-tilassa.
- Kun pelaaja **peruu** kesken kirjoituksen, ei pidä syntyä kilpa-ajoa, jossa jo ehditty lähettämään osittainen syöte providerille ennen peruutusta: sovelluksen on käytettävä eksplisiittistä **barrieeria** (esim. "debounce" tai eksplisiittinen lähetyspainike/pidempi hiljaisuusraja ennen `input_audio_buffer.commit`/`response.create`-kutsua) sen sijaan, että luotettaisiin pelkkään VAD:iin tekstikirjoituksen yhteydessä.
- Jos käyttäjän ääni/teksti ehtii providerille asti ja pelaaja perkääntyy vasta sen jälkeen, on pelattava sama periaate kuin nykyisessä tavanomaisessa toteutuksessa: peruminen/uudelleenyritys palauttaa tai haarauttaa tilan, mutta ei väitä ettei alkuperäistä tapahtumaa koskaan tapahtunut omassa haarassaan (vrt. `SUUNNITELMA_SIMULAATIO.md` luku 4, "Kumoaminen ja uudelleenyritys palauttavat tai haarauttavat tilan").
- Keskeisin periaate: **luonnos ei koskaan ole pelaajan toiminto** tilakoneen/kronikan mielessä. Vain eksplisiittisesti commitoitu/lähetetty syöte muuttuu StateChange-kelpoiseksi tapahtumaksi, aivan kuten nykyisessä muutoshyväksyntämallissa.

**HUOMIO:** Luonnollisestikaan tässä ei ole tarkoitus lähettää palvelimille mitään keskeytyskäskyjä pelaajan kirjoittaessa, vaan pysäytetään ohjelmassa uusien kutsujen tai tapahtumien lähettäminen RTC rajapintaan, kunnes pelaaja lähettää toimintansa tai peruu kirjoittamisen (timeout?), jolloin hahmojen ja kertojan toiminta jatkuu. Ei tarvita rajapinnan päässä barge-in toimintoja, ellei rajapinta itse alkaisi huhuilemaan käyttäjän perään yhteyden ollessa idle.

---

## 12. Yhteyden jatkaminen (resume): replay ja dedupe

**[FAKTA] Gemini Live — Session resumption:**
- `sessionResumption`-asetus (`SessionResumptionConfig`) saadaan istunnon `setup`-konfiguraatioon. Palvelin lähettää tällöin `SessionResumptionUpdate`-viestejä, joissa on `handle`-kahva. Uusi yhteys voidaan avata antamalla viimeisin `handle` `SessionResumptionConfig.handle`-kenttään, jolloin istunto jatkuu loogisesti samana. **Resumointikahvat ovat voimassa 2 tuntia** viimeisen istunnon päättymisestä. Lähde: ai.google.dev/gemini-api/docs/live-api/session-management, haettu 2026-10-07.
- Ennen yhteyden katkeamista palvelin lähettää `GoAway`-viestin (`timeLeft`-kentällä), jotta sovellus ehtii reagoida (esim. pyytää uuden kahvan tai valmistautua uudelleenyhdistämiseen) ennen pakotettua katkaisua. Sama lähde.
- `generationComplete`-viesti kertoo, milloin mallin vastaus on valmis — hyödyllinen signaali myös uudelleenyhdistämisen jälkeiselle tilan synkronoinnille.

**[FAKTA] OpenAI Realtime:** Virallisessa Realtime-oppaassa ei (2026-10-07 haetussa versiossa) kuvattu vastaavaa nimettyä "istunnon jatkamiskahva" -mekanismia session resumption -käsitteellä; istunto on sidottu 60 minuutin enimmäiskestoon, minkä jälkeen uusi istunto on avattava. Tätä ei pidä olettaa tueksi ilman erillistä varmistusta ajantasaisesta OpenAI-dokumentaatiosta toteutushetkellä.

**[EHDOTUS]** Realtime-adapterin on itse vastattava **replay/dedupe**-logiikasta providerin resumointimekanismin ollessa rajallinen tai puuttuessa:
- Tarinamoottorin oma tapahtumaloki (luku 10 kokoaja) on totuuden lähde; yhteyden katketessa palvelin tietää viimeisen onnistuneesti tallennetun/kuitatun tapahtuman tunnisteen.
- Uudelleenyhdistämisen jälkeen (Gemini: `handle`; OpenAI: kokonaan uusi istunto) palvelin **toistaa (replay)** puuttuvan kontekstin omasta tapahtumalokista mallin promptiin/konversaatioon sen sijaan, että luottaisi pelkästään providerin sisäiseen muistiin, ja **poistaa duplikaatit (dedupe)** tapahtumatunnisteiden avulla, jos sekä provider että oma loki yrittävät toimittaa saman sisällön kahdesti.
- Tämä periaate on sama riippumatta siitä, onko kyseessä providerin natiivi resumointi (Gemini) vai täysin uusi istunto (OpenAI 60 min raja): Tarinamoottorin oma tila on aina se, mikä määrittää "totuuden", providerin istunto on vain väliaikainen suoritusympäristö.

---

## 13. Providerikohtaiset kyvyt ja tuen puuttuessa varajärjestely (fallback)

**[FAKTA] Toiminnallisuuserot on dokumentoitu eksplisiittisesti providerien sisälläkin eri mallien välillä, ei vain providerien välillä:**
- Gemini-mallien välinen funktiokutsuvertailu (ai.google.dev/gemini-api/docs/live-tools, haettu 2026-10-07): Gemini 3.1 Flash Live Preview tukee funktiokutsuja vain synkronisesti; Gemini 2.5 Flash Live Preview tukee sekä synkronista että asynkronista; Google Maps -työkalua, koodin suoritusta ja URL-kontekstia ei tue kumpikaan Live-malli ("Not supported" molemmille).
- Asynkronisen funktiokutsun ajoitustuki (`SILENT`, `WHEN_IDLE`, `INTERRUPTED`) vaihtelee mallin mukaan: Gemini 3.8 Live tukee kaikkia, Gemini 2.5 Flash Live tukee vain `NON_BLOCKING`-perusmuotoa, Gemini 3.1 Flash Live Preview ei tue asynkronista kutsua lainkaan ("Function calling is sequential only"). Lähde: ai.google.dev/gemini-api/docs/live-api/capabilities, haettu 2026-10-07.
- OpenAIn puolella Azure-dokumentaatio toteaa eksplisiittisesti ainakin yhden kenttätason poikkeaman OpenAI-spesifikaatioon verrattuna (`input_audio_transcription.model`-kentän arvo on Azuressa deployment-nimi). Lähde: learn.microsoft.com/azure/ai-foundry/openai/realtime-audio-reference, haettu 2026-10-07.

**[EHDOTUS]** Realtime-adapterin on sisällettävä **kyvykkyystarkistus (capability check)** per valittu malli/provider ennen ominaisuuden käyttöä, ei oletus "kaikki realtime-mallit tukevat samaa": esim. jos valittu malli ei tue asynkronista funktiokutsua, adapterin on käytettävä synkronista varapolkua (sovellus odottaa työkaluvastausta ennen kuin antaa mallin jatkaa), eikä kaadu tai hiljaa jätä komentoa suorittamatta. Vastaavasti, jos valittu Realtime-malli/provider ei tue jotain Tarinamoottorin vaatimaa toimintoa (esim. kuva­syöte, tietty äänimuoto, tietty työkalu), sovelluksen on osattava **pudota takaisin tavanomaiseen ei-realtime-kutsuun** kyseiselle osalle vuorovaikutusta sen sijaan, että koko istunto epäonnistuisi.

---

## 14. Kustannukset: teksti/ääni/kuva, input/output/cached, kasvava historia, joutokäynti, per-hahmo-kertyminen

Tämä luku erottelee tarkasti **varmennetut, päivätyt hinnat** ja **arkkitehtuuriperiaatteet**, joita ei pidä sekoittaa keskenään. Kaikki hinnat ovat julkisen (ei-neuvotellun) listahinnan mukaisia USD/1M tokenia, haettu ilmoitettuna päivänä. **Älä käytä näitä lukuja ilman uudelleentarkistusta ennen budjetointia** — tekoälypalveluiden hinnat muuttuvat usein.

### 14.1 OpenAI Realtime — varmennettu hinnasto

**[FAKTA]** Lähde: developers.openai.com/api/docs/pricing, osio "Realtime and audio generation models", haettu 2026-10-07. Hinnat ovat USD per 1M tokenia (paitsi `tts-1`/`tts-1-hd`, jotka ovat per 1M merkkiä):

| Malli | Modaliteetti | Input | Cached input | Output |
|---|---|---|---|---|
| gpt-realtime-2.1 | Audio | $32.00 | $0.40 | $64.00 |
| gpt-realtime-2.1 | Text | $4.00 | $0.40 | $24.00 |
| gpt-realtime-2.1 | Image | $5.00 | $0.50 | – |
| gpt-realtime-2.1-mini | Audio | $10.00 | $0.30 | $20.00 |
| gpt-realtime-2.1-mini | Text | $0.60 | $0.06 | $2.40 |
| gpt-realtime-2.1-mini | Image | $0.80 | $0.08 | – |
| gpt-realtime-2 | Audio | $32.00 | $0.40 | $64.00 |
| gpt-realtime-2 | Text | $4.00 | $0.40 | $24.00 |
| gpt-realtime-1.5 | Audio | $32.00 | $0.40 | $64.00 |
| gpt-realtime-1.5 | Text | $4.00 | $0.40 | $16.00 |
| gpt-realtime-mini | Audio | $10.00 | $0.30 | $20.00 |
| gpt-realtime-mini | Text | $0.60 | $0.06 | $2.40 |
| gpt-realtime | Audio | $32.00 | $0.40 | $64.00 |
| gpt-realtime | Text | $4.00 | $0.40 | $16.00 |
| gpt-audio-1.5 / gpt-audio / gpt-audio-mini | (ei-realtime audio-mallit) | ks. sivu | – | ks. sivu |

Lisäksi sivu dokumentoi erillisen tuotteen **"GPT-Live sessions"**: `gpt-live-1` -mallin puheistunnot laskutetaan **sekuntiperusteisesti (ei pyöristystä minuuttiin), $0.05/min**, ja taustamallin sekä työkalujen käyttö laskutetaan erikseen. Tämä on eri tuote kuin yllä oleva per-token Realtime-hinnasto, eikä sitä pidä sekoittaa siihen.

Huom: käyttäjän valitsemat `gpt-6.1-sol`/`gpt-6-luna` eivät esiinny tässä taulukossa lainkaan — ne ovat omassa "Flagship models" -taulukossaan tavallisella teksti-token-hinnalla, mikä vahvistaa luvun 2 johtopäätöksen.

### 14.2 Google Gemini Live — varmennettu hinnasto

**[FAKTA]** Lähde: ai.google.dev/gemini-api/docs/pricing, osio "Gemini 3.8 Live" ("Our low-latency, audio-to-audio models optimized for real-time voice agents and live dialogue"), Standard-taso, haettu 2026-10-07:

| Suunta | Hinta |
|---|---|
| Input (teksti) | $0.75 / 1M tokenia |
| Input (ääni) | $3.00 / 1M tokenia, tai noin **$0.005/min** |
| Input (kuva/video) | $1.00 / 1M tokenia, tai noin **$0.002/min** |
| Output (teksti, sis. thinking-tokenit) | $4.50 / 1M tokenia |
| Output (ääni, sis. thinking-tokenit) | $12.00 / 1M tokenia, tai noin **$0.018/min** |

Samalta sivulta, muut Live-sukuiset mallit (varmennettu samalla haulla, 2026-10-07):
- **Reaaliaikainen puhe-puhe-käännösmalli** (70+ kieltä): input-ääni $3.50/1M tai ~$0.0053/min, output-ääni $21.00/1M tai ~$0.0315/min, blended-hinta noin **$0.0368/min**, laskettuna 25 audio-tokenia/sekunti -muunnoksella.
- **Reaaliaikainen bidirektionaalinen puhe-tekstiksi-transkriptio** ("Live Transcribe"): input-ääni $3.50/1M tai ~$0.005/min, output-teksti $21.00/1M tai ~$0.004/min, blended ~$0.009/min (laskettu 25 audio-tokenia/s sisään, 175 teksti-tokenia/min ulos).
- **Transkriptiomalli** (ei-reaaliaikainen, diarisaatio ym.): input-ääni $2.00/1M tai ~$0.003/min, output-teksti $12.00/1M tai ~$0.002/min, blended ~$0.005/min.

Sivu mainitsee myös context caching -hinnoittelun tavallisille (ei-Live) Gemini-malleille (esim. Gemini 3 Flash: caching $0.075–0.15/1M + $0.50–1.00/1M-tokenia-per-tunti varastointimaksu), mutta **sivulla ei ilmoitettu erillistä cache-rivin hintaa nimenomaan Live-audio-malleille** haetussa näkymässä — tätä ei siis pidä olettaa, vaan tarkistettava erikseen ennen budjetointia, jos sovellus aikoo hyödyntää kontekstin välimuistitusta Live-istunnoissa.

### 14.3 Azure OpenAI Realtime — ei varmennettu

**[EI VARMENNETTU]** Azuren julkinen hinnoittelusivu (azure.microsoft.com/pricing/details/...) latautuu JavaScript-pohjaisena eikä palauttanut konkreettisia lukuja tällä haulla (2026-10-07). Kolmannen osapuolen yhteenvedot viittaavat siihen, että Azuren `gpt-realtime`-hinnoittelu vastaisi suuruusluokaltaan OpenAIn omaa listaa, mutta **tätä ei ole vahvistettu Microsoftin virallisesta hinnoittelulähteestä** tässä tutkimuksessa, joten numeroita ei kirjata tähän dokumenttiin. Ennen toteutusta: tarkista suoraan Azure-portaalin hinnoittelulaskurista tai azure.microsoft.com/pricing/details/ai-foundry (tai ajantasaisesta vastaavasta Azure-hinnoittelusivusta) kyseisen Azure-tilauksen ja alueen todellinen hinta.

### 14.4 Kustannusperiaatteet — [EHDOTUS / arkkitehtuurinen huomio]

Nämä eivät ole tiettyjä dollarilukuja, vaan laskentalogiikan periaatteita, jotka Tarinamoottorin budjetti- ja seurantatoteutuksen on huomioitava, kun/jos realtime otetaan käyttöön:

1. **Kasvava historia laskutetaan toistuvasti, ei kertaalleen.** Molemmissa API:ssa konteksti (mukaan lukien koko aiempi keskusteluhistoria kyseisessä istunnossa) syötetään uudelleen mallille jokaisella uudella vastauskutsulla, ellei erillistä context-caching-mekanismia käytetä ja sovellettu alennus koske koko kontekstia. Tämä tarkoittaa, että pitkän kohtauksen kertojaistunto, jonka konteksti kasvaa vuoro vuorolta, maksaa **inkrementaalisesti enemmän jokaisesta uudesta vuorosta**, koska koko aiempi historia on osa jokaisen uuden vastauksen input-tokeneita — tätä ei pidä mallintaa budjetissa "yhtenä kertamaksuna koko kohtaukselle", vaan kumulatiivisena, karkeasti kohtauksen pituuden toisessa potenssissa kasvavana kuluna ilman kompressiota/cachingia.
2. **Cached input alentaa mutta ei poista toistuvaa maksua.** Sekä OpenAI (ks. 14.1 taulukon "Cached input" -sarake, esim. `gpt-realtime` audio-cached $0.40 vs. normaali $32.00/1M) että Gemini (context caching -mekanismi tavallisille malleille) tarjoavat halvemman hinnan toistuvalle/muuttumattomalle kontekstin osalle, mutta cache-osuuskin on edelleen maksullinen token, ei ilmainen — eikä (14.2 mukaan) ole varmistettu, että Live-audio-malleilla on edes cache-hinta ollenkaan.
3. **Joutokäyvät (idle) yhteydet eivät välttämättä laskuta tokeneita, mutta tämä on malli-/providerikohtainen eikä yleistettävä sääntö.** Kumpikaan virallinen dokumentaatio (haettu 2026-10-07) ei antanut yksiselitteistä, yleispätevää lausuntoa "avoinna oleva mutta hiljainen yhteys ei koskaan maksa mitään" kaikille malleille/tuotteille. Sen sijaan on dokumentoitu erillisiä aikaperusteisia maksukomponentteja: OpenAIn `gpt-live-1`-istunnot laskutetaan **minuuttiperusteisesti, ei pelkästään token-perusteisesti** (ks. 14.1), ja Geminin context-cache-varastointi laskutetaan **tokenia per tunti** riippumatta siitä, lähetetäänkö uutta sisältöä (ks. 14.2:n viittaus "storage price"). Siksi avoin yhteys **voi** aiheuttaa kuluja ajan, ei vain tokenien, perusteella — tarkista jokaisen käytettävän tuotteen oma hinnoittelumalli erikseen, älä oleta kumpaakaan suuntaan.
4. **Per-hahmo-kertyminen.** Koska (luku 4) jokainen hahmo tarvitsee oman istunnon/yhteyden, ja koska kustannus lasketaan per istunto (oma konteksti, oma mallinkutsuhistoria), N samanaikaisen hahmon kohtaus maksaa karkeasti N kertaa yhden hahmon kuluerän — tämä on suoraan verrannollinen nykyisen ei-realtime-toteutuksen per-hahmo-mallikutsukuluun, mutta realtime-audiossa yksikköhinta (per token tai per minuutti) on merkittävästi korkeampi kuin tekstikutsussa (esim. OpenAIn audio-input $32.00/1M vs. tavallisen tekstimallin $0.10–$10.00/1M-luokan hinnat samalla sivulla), joten moninkertaistuva kustannus kasvaa nopeammin kuin tekstipohjaisessa mallissa.
5. **Teksti/ääni/kuva-modaliteetit hinnoitellaan erikseen eri yksikköhinnoin**, kuten 14.1–14.2 taulukot osoittavat (ääni on OpenAIlla noin 3–8x kalliimpi kuin teksti samalla mallilla; Geminillä samankaltainen suhde input-puolella). Budjettilaskennassa näitä ei pidä niputtaa yhteen "token"-lukuun ilman modaliteettikohtaista erittelyä.

---

## 15. Lähdeluettelo (haettu 2026-10-07, ellei toisin mainittu)

**OpenAI / Azure OpenAI:**
- https://developers.openai.com/api/docs/guides/realtime — Realtime-aloitusopas, mallit, GA-migraatio, WebRTC/WebSocket-viittaukset, safety identifiers.
- https://developers.openai.com/api/docs/guides/realtime-conversations — Session/Conversation/Response-malli, 60 min enimmäiskesto, tapahtumataulukot, ääni-I/O, VAD, keskeytys.
- https://developers.openai.com/api/docs/guides/voice-webrtc — WebRTC-yhteysopas.
- https://developers.openai.com/api/docs/guides/voice-websockets — WebSocket-yhteysopas.
- https://developers.openai.com/api/docs/pricing — Virallinen hinnoittelusivu, Realtime and audio generation models -osio, GPT-Live sessions -osio, Flagship models -osio (gpt-6.1-sol, gpt-6-luna).
- https://learn.microsoft.com/en-us/azure/ai-foundry/openai/how-to/realtime-audio — Azure Realtime: yhteystavat (WebRTC/WebSocket/SIP), tuettujen mallien luettelo.
- https://learn.microsoft.com/en-us/azure/ai-foundry/openai/realtime-audio-reference — Azure-spesifiset poikkeamat OpenAI-spesifikaatioon.

**Google Gemini:**
- https://ai.google.dev/gemini-api/docs/live — Live API yleiskatsaus, tekniset spesifikaatiot, WebSocket-protokolla, barge-in.
- https://ai.google.dev/gemini-api/docs/live-api/capabilities — Mallivertailu (Gemini 3.8 Live / Extended Thinking / 3.1 Flash Live), thinking, funktiokutsujen ajoitus, interaktiomodaliteetit.
- https://ai.google.dev/gemini-api/docs/live-tools — Funktiokutsu, työkaluvertailutaulukko malleittain.
- https://ai.google.dev/gemini-api/docs/live-api/session-management — Istunnon/yhteyden kestorajat, context window compression, session resumption, GoAway, generationComplete.
- https://ai.google.dev/gemini-api/docs/pricing — Gemini 3.8 Live, Live-käännösmalli, Live Transcribe ja Transcribe -hinnastot.

**Ei virallisesti varmennettu (mainittu läpinäkyvyyden vuoksi):**
- Azure OpenAI Realtime -yksikköhintoja ei saatu suoraan Microsoftin viralliselta hinnoittelusivulta tämän tutkimuksen aikana (sivu on JS-renderöity); kolmannen osapuolen hintavertailusivustoja ei käytetty lähteenä tähän dokumenttiin.

---

## 16. Avoimet kysymykset ennen mahdollista toteutusta

**[EHDOTUS]** Nämä on selvitettävä uudelleen ajantasaisesta dokumentaatiosta juuri ennen toteutuspäätöstä, koska API:t ja hinnat muuttuvat:

1. Onko valittu provider/malli sillä hetkellä yleisesti saatavilla (GA) vai preview/beta, ja millä SLA:lla?
2. Mikä on sillä hetkellä kyseisen mallin tarkka tuki asynkroniselle funktiokutsulle (luku 13) — vaaditaanko synkroninen varapolku?
3. Onko Azure-hinnoittelu vahvistettu organisaation omasta Azure-sopimuksesta (luku 14.3)?
4. Onko Live/Realtime-audiomalleille olemassa context-caching-hinta sillä hetkellä (luku 14.2 huomio), ja kannattaako sitä käyttää pitkissä kohtauksissa?
5. Tukeeko valittu malli tarvittavaa kuvasyötettä (esim. kohtauskuvat/kartat) samassa istunnossa ilman erillistä pudotusta tekstiin?
6. Onko OpenAI-puolella sillä hetkellä olemassa Geminin `session resumption`-kaltainen natiivi jatkomekanismi, vai pitääkö luvun 12 replay/dedupe-logiikka kantaa koko vastuun 60 minuutin rajan ylityksestä?

**TÄRKEÄÄ**

7. ! Tukeeko realtime rajapinta stukturoitua vastausta, eli ymmärtääkö sovellus keille hahmoille sen pitää lähettää mitäkin, vai onko vastaus optimoitu tekstintuottoa varten ja siten pelkkää tekstiä? Pystyykö hahmo ilmoittamaan ajatuksensa, puheensa, yms. sruckturoituna, jotta ne voidaan erotella? Toteutettavissa työkalukutsuilla?
8. ! Tekeekö realtime malli metakommentointia ("Jatketaanpa tarinaa..." tai muuta sisäistä puheeseen sopivaa komenntointia)vai pystyykö pysymään roolissaan? Saattaa toimia pelkissä puhtaissa vuorosanoissa. Toteutettavissa työkalukutsuilla?
9. Realtime rajapinta on huomattavasti kalliimpi. Tulisiko halvemmaksi lähettää tavallisia kutsuja esim. Luna mallille tiheästi keskustelussa? Tiheä "Kertoja --> hahmo(t) --> kertoja --> hahmo(t) --> kertoja --> hahmo(t) --> kertoja --> ..." sykli voi olla toimiva, joskin hitaampi ja vaatii koko kontekstin lähettämisen jokaisessa kutsussa. Kutsut pitäisi muotoilla siten, että ne tuottaisivat runsaasti cached-input osumia.
