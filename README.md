# Tarinamoottori / StorytimeSimulator

[English version](README.en.md)

> **Keskeneräinen projekti:** tätä sovellusta kehitetään edelleen. Sitä ei ole laajasti tai riippumattomasti testattu, eikä sitä ole validoitu tuotantokäyttöön. Mukana olevat automaattitestit ja rajalliset kehitysaikaiset selainkokeilut eivät takaa virheetöntä toimintaa.

Paikallisesti tallentava, selainkäyttöinen tarinamoottori. Sama tarina voi jatkua romaanina, itsenäisten hahmojen simulaationa tai yhden hahmon roolipelinä. Maailmaan voi puuttua missä tahansa tilassa.

## Käynnistys

Python 3.10 tai uudempi ja LLM-palvelun API-avain. Testattu kehitysympäristössä Python 3.14:llä. Selain ei tarvitse Node.js:ää tai erillistä build-vaihetta.

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
python main.py
```

Avaa http://127.0.0.1:8000. API-avaimen ja mallit voi asettaa käyttöliittymässä tai projektin `.env`-tiedostossa käyttäen `.env.example`-mallia. Käytä yhtä palvelinprosessia. Automaattinen koodin uudelleenlataus on pois päältä, jotta muokkaus ei katkaise generointia.

Jos portti on varattu:

```powershell
python -m uvicorn web.api:app --host 127.0.0.1 --port 8001
```

## Kolme Toimintatapaa

| Tila | Hahmojen päätökset | Kertojan tehtävä |
| --- | --- | --- |
| Romaani | Hahmokutsu vain edellisen vuoron osoittamissa merkittävissä päätöskohdissa. | Jatkaa rutiinitoimintaa ja siirtymiä sujuvasti. Pysähtyy ennen seuraavaa tärkeää itsenäistä ratkaisua. |
| Simulaatio | Kaikki läsnä olevat toimintakykyiset hahmot tekevät oman ratkaisunsa. Korkeintaan viisi kutsua on samanaikaisesti käynnissä; muita hahmoja ei pudoteta pois. | Ratkaisee aikeiden ristiriidat ja tapahtumien seuraukset. Kaikkien ei tarvitse saada puheenvuoroa. |
| Roolipeli | Pelaajan toiminta menee suoraan kertojalle. Muut läsnä olevat hahmot tekevät omat ratkaisunsa. | Säilyttää pelaajan yrityksen, ratkaisee seuraukset ja pysähtyy ennen pelaajan seuraavaa merkittävää valintaa. |

Tilaa voi vaihtaa kesken tarinan. Hahmokortin **Pelaa hahmona** siirtää roolipeliin. Hahmon on oltava aktiivisessa kohtauksessa ja toimintakykyinen.

- **Yksityinen aikomus** antaa pelaajan suunnitelman kertojalle, ei muiden hahmojen syötteeseen.
- **Muuta maailmaa** antaa seuraavan vuoron maailmanmuutoksen kertojalle. Hahmot saavat muutoksen havaittavat seuraukset seuraaviin päätöksiinsä, eivät alkuperäistä ohjetta.
- Romaanissa ja simulaatiossa voi valita rajatun automaattijatkon, enintään kymmenen jatkoa. Jokainen jatko voi tehdä maksullisia mallikutsuja.
- **Keskeytä** lopettaa keskeneräisen työn. Jo hyväksyttyä vuoroa se ei peruuta.
- **Näytä salaisuudet** avaa ohjaajan ja hahmojen yksityisiä tietoja. Se on lukukokemuksen valinta, ei käyttäjien välinen käyttöoikeusraja.

## Lukunäkymät Ja Kehittyvä Juoni

Lukutilan näkökulmavalinta erottaa kertojan kaikkitietävän proosan ja valitun pelaajahahmon rajatun proosan. Roolipelissä näytetään rajattu näkökulma; romaani- tai simulaatiotilaan siirtyminen avaa kertojanäkymän. Kertojan proosaan voidaan sisällyttää hahmojen palauttamia ajatuksia. Pelaajaversio muodostetaan erillisellä mallikutsulla vain hahmon omista tiedoista ja todistetuista havainnoista, ei kaikkitietävää proosaa suodattamalla. Kanoninen vuoro tallennetaan ensin; rajattu näkökulma tuotetaan tämän jälkeen erikseen. Näkökulmakutsun virhe ei peruuta vuoroa: lukutilassa näytetään `view_failed`-tila ja näkökulman voi yrittää muodostaa uudelleen vuoron toiminnosta. Tietoraja riippuu edelleen mallin havaintomerkintöjen oikeellisuudesta, eikä ole eri käyttäjien käyttöoikeusraja.

Sisällysluettelo siirtyy lukuotsikoihin. Kertaukset avautuvat valitun näkökulman tietojen mukaan; pelaajan otsikotkaan eivät saa paljastaa salaisuuksia. Vanhoille vuoroille tai myöhemmin valitulle eri pelaajahahmolle ei arvata rajattua versiota, vaan puuttuva näkökulma merkitään. Pelaajaversion proosaa ei voi muokata kertojan tekstieditorilla. Tekstikorjaus ei automaattisesti kirjoita rajattua versiota uudelleen. TXT/Markdown-vienti on edelleen kertojan proosa.

Jokaisen hyväksytyn vuoron jatkuvuustilaan tallentuvat tapahtumatiivistelmä, faktat, avoimet juonilangat, juonisuunnitelma ja ohjaajan muistiinpanot. Salaiset maailmanfaktat eivät ole proosatekstin tai hahmojen havaintojen osa, vaan erillisissä `secret_truths`-riveissä. Uudelle tarinalle ohjaaja tuottaa 4–8 löydettävää totuutta, 1–3 painetta kuvaavaa kelloa ja enintään kaksi sivussa toimivaa agenttia. Vanhat tarinat saavat saman aineiston ensimmäisellä jatkolla (lazy-init). Ohjaaja voi siirtää totuutta vaiheittain `hidden` → `hinted` → `revealed`; kellot etenevät jokaisella vuorolla ja niiden vanheneminen tuottaa havaittavan tapahtuman. Kolmen peräkkäisen objektiivisesti muuttumattoman vuoron jälkeen suunnittelu vaatii totuuden paljastamista, kellon tikkausta, sivussa toimivaa siirtoa tai muuta konkreettista tilamuutosta.

## Tekstimuokkaus

Vuoron kynäpainike tai tekstin tuplaklikkaus avaa muokkauksen suoraan lukutekstiin. Fontti säilyy samana ja sivumerkki ilmaisee muokkaustilan. Toiseen kohtaan siirtyminen tallentaa tekstikorjauksen ja vientitiedostot ilman mallikutsuja. Virheessä teksti jää muokkaustilaan eikä katoa. Korjattu tuore proosa menee kertojan seuraavan vuoron kontekstiin. Revision tarkistus estää vanhentuneen tallennuksen. Vanha ja uusi proosa säilyvät `prose_edits`-historiassa; historian palautusnäkymää ei vielä ole.

**Tekstimuokkaus ei muuta tapahtumia, havaintoja, muisteja tai jatkuvuustiivistelmää.** Käytä sitä oikolukuun ja tyyliin. Juonimuutosten automaattista tilasynkronointia ei vielä ole; `sync_state: true` hylätään tallentamatta tekstiä. Myös vanhoja kappaleita voi korjata tekstinä, mutta muutokset eivät kirjoita myöhempien vuorojen tilaa uudelleen.

**Oma jatkokappale** lisää uuden, sellaisenaan säilytettävän tekstin tarinan loppuun. **Analysoi muutokset** käyttää kertojamallia ehdottamaan tapahtumat, niiden havaitsijat, hahmotilat ja jatkuvuuden. Tarkista ehdotus ja valitse **Hyväksy ja tallenna**; hyväksyntä ei tee uutta mallikutsua. Ennen hyväksyntää tarinan tila ei muutu. Peruuttaminen säilyttää tekstin lomakkeessa mutta hylkää esikatselun. Esikatselu vanhenee 30 minuutissa tai palvelimen uudelleenkäynnistyksessä; välissä muuttunut tarina vaatii uuden analyysin. Hyväksytty kappale voidaan kumota kuten uusi generoitu vuoro. Kappaleen enimmäispituus on 20 000 merkkiä. Tämä ensimmäinen versio ei luo uusia hahmoja: lisää tarvittavat hahmot ennen analyysiä.

Tapahtumien ja havaitsijoiden semanttinen oikeellisuus on edelleen mallin ehdotus, jonka käyttäjä tarkistaa. Tuntemattomat hahmotunnisteet hylätään. Vanhojen kappaleiden sisällöllinen sovitus ei kuulu tähän toimintoon. Tavallinen monirivinen jatkosyöte on eri asia: se antaa kertojalle muotoiltavan luonnoksen tai toiveen. Generoinnin aikana vuoron syöttökentät lukitaan; epäonnistuminen tai keskeytys ei tyhjennä tekstiä.

Kumoamispainike palauttaa viimeisintä vuoroa edeltäneet hahmot, muistit, havainnot, kohtaukset ja jatkuvuustilan. Se toimii vain uusille vuoroille, joille tämä versio tallensi palautuspisteen. Aloitusta ja vanhoja vuoroja ei voi kumota. Myöhemmät erilliset tilamuutokset estävät kumoamisen; tekstikorjaukset eivät. Mallikuluja ei hyvitetä. Uusi jatko käyttää uutta pyyntötunnistetta. Editorin avaaminen tai kumoaminen pysäyttää automaattijatkon.

## Vuoron Tietovirta

Vuoro käyttää yhtä rajattua sykliä: kertojan suunnitelma, valittujen hahmojen aikeet ja kertojan loppuratkaisu. Suunnitelma soveltaa maailmanmuutokset ennen hahmojen päätöksiä ja välittää vain havaittavat seuraukset. Tilakohtaiset ohjeet painottavat romaanissa kirjailijan suuntaa, simulaatiossa itsenäisiä aikeita ja roolipelissä pelaajan yritystä. Toiveen toteutumista ei selitetä erillisellä ilmoituksella. Suunnittelukutsu lisää yhden mallikutsun vuoroon. Kertojan pysäytyssignaali katkaisee automaattijatkon; useita sisäisiä syklejä ei vielä ajeta. Oma jatko kirjoitetaan myös tarinan lopussa samassa näkymässä, ei erillisessä pop-upissa.

```text
Tarinan tila ja versio
  -> tilan mukaan valitut hahmot + omat havainnot ja muistot
  -> itsenäiset aikomukset / pelaajan suora toiminta
  -> kertoja: tapahtumat, havaitsijat, seuraukset, jatkuvuus ja proosa
  -> paikallinen skeema- ja tunnistetarkistus
  -> version tarkistus ja yksi tietokantatransaktio
  -> valmis vuorokuitti ja uudelleen muodostettavat tekstiviennit
```

**Proosa ei ole hahmojen yhteinen tietolähde.** Kertoja palauttaa erilliset tapahtumat ja niiden havaitsijat. Moottori muodostaa hahmolle vain kyseisen hahmon havaitsemat tapahtumat. Ohjaajan juoni, muiden ajatukset ja kaikkitietävä kerronta eivät mene suoraan hahmopromptiin.

Tapahtumat talletetaan pysyvällä tunnisteella `events`- ja `event_witnesses`-tauluihin. Jokainen tapahtuma kertoo alkuperänsä (`intent:<hahmo>`, `consequence`, `routine` tai `world`); havaitsijat rajataan aktiiviseen kohtaukseen ja tapahtumat ovat hahmojen havaintojen lähde. Muistirivit linkittyvät lähdetapahtumaan. Muistihaku on vakaa ja yhdistää tuoreuden, tärkeyden ja kyselyn sanallisen vastaavuuden; korkean tärkeyden muistot säilytetään haussa.

Hahmo saa seuraavalla kierroksella myös oman viimeisen hyväksytyn aikomuksensa ja ajatuksensa. Ne erotetaan havainnoista: yritys ei todista onnistumista eikä päätelmä ole fakta; muiden hahmojen ajatuksia ei välitetä. Hahmojen vastauksissa on tavoite, aikahorisontti, toimintayritys, puhe, keskeytyssuunnitelma, yksityinen ajatus ja tärkeys. Resolver ei saa lisätä uusia vapaaehtoisia hahmotekoja ilman aikomusta. Kumoaminen palauttaa myös jatkuvuuden.

## Tallennus Ja Palautuminen

- Tarinalla on oma SQLite-tietokanta `stories/<tunniste>/story.db`; skeemaversio 8 sisältää `story_branches`-perustan ja oletushaaran `main`.
- Rakenteinen maailma tallentaa paikat, esineet, suhteet, salaiset totuudet, kellot, offscreen-agentit ja tapahtumien havaitsijat omiin tauluihinsa; hahmon `location_id` ei ole fyysiseen tilaan upotettua vapaatekstiä.
- Hahmojen muutokset, havainnot, muistot, kohtaus, proosa, jatkuvuustila ja pyyntökuitti hyväksytään yhdessä transaktiossa.
- Tilaversio estää vanhaan tilanteeseen perustuvaa generointia ylikirjoittamasta välissä tehtyä muokkausta.
- Saman pyyntötunnisteen uudelleenlähetys palauttaa hyväksytyn vastauksen. Samaa tunnistetta ei saa käyttää eri sisällölle.
- Selain seuraa palvelimen taustatyötä SSE-yhteydellä, ei sekunnin välein toistuvilla GET-kyselyillä. Työvaiheet näyttää suunnittelun, hahmojen aikeiden valmistumisen ja tallennuksen. SSE-yhteyden katkeaminen ei keskeytä taustatyötä; Palauta yhteys jatkaa saman tunnisteen seurantaa. Sivun lataus ei käynnistä uutta vuoroa. Keskeneräisen työn tunniste säilyy välilehden `sessionStorage`-tilassa. Väli-ilmoitukset ovat palvelimen muistissa; valmis kuitti säilyy tietokannassa.
- Palvelimen uudelleenkäynnistys keskeyttää keskeneräiset työt. Valmiit kuitit säilyvät tietokannassa. **Palauta yhteys** käyttää samaa pyyntöä.
- Katkennut tai virheellinen mallivastaus hylätään. Se ei muutu keksityksi varatarinaksi.
- `story.txt` ja `story.md` ovat tietokannasta muodostettavia vientitiedostoja. Niihin käsin tehdyt muutokset eivät päivitä tarinan tilaa ja korvautuvat seuraavassa viennissä.

Vanha tietokanta päivitetään avattaessa (skeemaversio 8). Migraatio lisää rakenteisen maailman, tapahtumat ja muistien lähdekentät; aiemmin luotuja tarinoita ei poisteta. Version 4 kannasta tehdään `story.pre-v5.db`-varmuuskopio; myöhemmistä kannoista säilytetään vastaava edeltävän version varmuuskopio. Kumoamispisteet pakataan gzip-muotoon. Säilytä lisäksi omat varmuuskopiot tärkeistä tarinoista. Älä käytä samaa tarinakansiota samanaikaisesti usealta koneelta pilvisynkronoinnin kautta.

## Yksityisyys Ja Asetukset

### Vuorojen Palautusloki

Ennen vuoron tallennusta koko hyväksyttävä vastaus, tapahtumat, hahmotilat ja lähtötila kirjoitetaan Google Drive -projektikansion ulkopuolelle Windowsin `%LOCALAPPDATA%/Tarinamoottori/recovery`-hakemistoon. Commitin jälkeen vuoro, kuitti ja palautuspiste tarkistetaan uudella tietokantayhteydellä. Valmiiden taustatöiden tilakysely tarkistaa myös levyltä, että vuoro on edelleen olemassa. Puuttuva tallennus ilmoitetaan virheenä, ei onnistumisena.

Palautusloki sisältää salaamatonta tarinatekstiä, hahmojen salaisuuksia ja tilatietoja. Se ei ole API-avainvarasto. Suojaa käyttäjätili ja poista tarpeettomat palautustiedostot erikseen; tarinan poistaminen ei poista tätä paikallista lokia automaattisesti. Aktiivisen SQLite-tietokannan pilvisynkronointi on edelleen riski: suosi paikallista työkansiota ja synkronoi vain suljettuja SQLite-varmuuskopioita. Käytä yhtä palvelinprosessia ja yhtä kirjoittavaa konetta.

Tallennus on paikallinen, mutta pilvimallia käytettäessä sen saamat promptit, hahmotiedot ja tarinakatkelmat lähetetään valitulle palveluntarjoajalle. Sovellus ei siis ole automaattisesti kokonaan paikallinen tai offline.

API-avaimet säilytetään palvelimen `.env`- ja `.provider-profiles.json`-tiedostoissa. Niitä ei palauteta asetusten GET-rajapinnasta eikä tallenneta uusiin selainprofiileihin. Vanhojen selainprofiilien avaimet siirretään palvelimelle ennen niiden poistamista selaintallennuksesta. Tiedostot ovat **salaamattomia** ja Gitin ulkopuolella; suojaa käyttäjätili, kansio ja varmuuskopiot asianmukaisesti.

Sovellus on yhden omistajan paikallinen työkalu: ei kirjautumista, monikäyttäjyyttä tai internet-julkaisua varten. Palvelu hyväksyy localhost-isännät ja torjuu vieraasta selainalkuperästä tulevat pyynnöt. Tarina- ja prompttipolut on rajattu omiin hakemistoihinsa. Mallin ja tuontikorttien tekstiä ei suoriteta HTML:nä.

Asetuksissa on yhteinen tarjoaja ja erilliset kertoja- ja hahmomallit. Suunnittelulle, proosalle, aloitukselle, hahmoille ja pelaajanäkymälle on erilliset lämpötila-, token- ja päättelyasetukset (`DIRECTOR_PLAN_*`, `PROSE_*`, `STORY_INIT_*`, `CHARACTER_*`, `PLAYER_VIEW_*`). Koodi tukee xAI-, Azure-, Gemini-, OpenAI-, OpenRouter- ja OpenAI-yhteensopivia rajapintoja; selainprofiilien näkymä kattaa xAI:n, Azuren ja Google AI Studion. Gemini käyttää Googlen OpenAI-yhteensopivaa tekstirajapintaa. Aseta `GEMINI_API_KEY` ja `LLM_PROVIDER=gemini` tai luo Google-profiili selaimessa. Mallinimet ovat muokattavia. Gemini 2.5 Flash-Liten mallitunniste on `gemini-2.5-flash-lite`; Googlen nykyisen dokumentaation mukaan 2.5-mallit ovat rajattuja aiemmille käyttäjille. Uuden profiilin oletukset ovat dokumentoidut uudemmat Flash ja Flash-Lite. Katso [malliarvio](ARVIO_GEMINI.md). Muut tarjoajat voi määrittää ympäristöasetuksilla.

API-loki sisältää syöte-, vastaus-, päättely- ja välimuistitokenit silloin, kun palvelu ilmoittaa ne. Välimuistitokenit ovat syötetokenien osajoukko. Hinta näytetään vain palvelun raportoimana, ja kooste ilmoittaa kuinka monesta kutsusta hintatieto on saatavilla. Täydet promptit ja vastaukset voi tallentaa gzip-pakattuina paikalliseen `api_calls`-tauluun asettamalla `LLM_CALL_CONTENT_LOGGING=true`; ominaisuus on oletuksena pois, koska sisältö sisältää yksityisiä tietoja. `LLM_CALL_RETENTION_DAYS` (oletus 30) määrittää lokien säilytysajan.

`MAX_INPUT_TOKENS` rajoittaa syötteen arvioitua kokoa (oletus 64000). Arvio on merkkimääräpohjainen, ei mallin tarkka tokenisaattori. Ylitys keskeyttää pyynnön ennen verkkokutsua eikä leikkaa sisältöä hiljaisesti.

## Projektin Rakenne

### Azure-rajapinnan valinta

Valitse asetuksista Azure-portaalin koodiesimerkin URL-muoto. **OpenAI v1** käyttää osoitetta `https://<resurssi>.services.ai.azure.com/openai/v1/` tai `https://<resurssi>.openai.azure.com/openai/v1/`. Poista viimeinen `responses`: sovellus käyttää Chat Completions -rajapintaa, ei Responses API:a. Selain poistaa kopioidun `responses`- tai `chat/completions`-päätteen tallennuksessa. API-version ja saman deploymentin kentät piilotetaan v1-tilassa. Malli-kenttiin tulee Azure-portaalin deployment-nimi.

**Deployment-rajapinta** käyttää resurssin juuriosoitetta `https://<resurssi>.openai.azure.com/` ja päivämäärämuotoista `api-version`-arvoa. **Sama deployment kertojalle ja hahmoille** on valinnainen: tyhjänä käytetään roolien omia Malli-kenttiä. Sovellus muodostaa kutsupolun itse. 404 voi tarkoittaa väärää resurssia, URL-muotoa tai deployment-nimeä.

Tokenkentät rajaavat yhden vastauksen budjettia, eivät proosan tavoitepituutta tai syötteen kontekstia. Uusien Azure-profiilien oletukset ovat kertojalle 32 000 ja hahmoille 16 000; muiden tarjoajien profiilioletukset säilyvät 8 000 / 1 200. Tallennettuja profiileja ja ympäristöasetuksia ei koroteta automaattisesti. Kenttien ylärajat ovat 128 000 / 64 000, mutta mallin oma vastausraja pätee. Azure v1 käyttää `max_completion_tokens`-parametria, joka sisältää mallista riippuen myös päättelyn. Muiden tarjoajien parametrit pysyvät tarjoajakohtaisina. Katkeamisen automaattinen uusintayritys voi nostaa pyydettyä budjettia: asetus ei ole ehdoton kustannuskatto.

- `engine/story_engine.py`: tilakohtainen vuoroprosessi ja hyväksyminen.
- `engine/director_agent.py`, `engine/character_agent.py`: agenttien syötteet ja validoidut vastaukset.
- `database/turn_store.py`: vuorotransaktio, havainnot, jatkuvuus ja pyyntökuitit.
- `database/db.py`: muut tietokantatoiminnot, muistihaku ja versionoidut migraatiot.
- `core/schemas.py`: mallivastausten tietosopimukset.
- `core/llm_client.py`, `core/providers/`: mallirajapinnat, vastaukset ja lokitus.
- `core/profile_store.py`: palvelinpuolen avainprofiilit.
- `web/api.py`: paikallinen API ja taustavuorotyöt.
- `web/static/app.js`: tarina-, hahmo-, promptti- ja asetusnäkymät.
- `web/static/turns.js`: vuoropyyntöjen seuranta, palautuminen ja keskeyttäminen.
- `prompts/`: oletuspromptit; `prompts/custom/`: omat ohitukset.

Vanhoja kronikoitsija-, aistisuodatin- ja valvojatoimintoja on edelleen lähdekoodissa yhteensopivuutta varten. Aktiivinen vuoropolku käyttää tapahtumia ja kertojan jatkuvuustilaa, ei erillistä kronikoitsija- tai valvojakutsua joka neljännellä tai kuudennella vuorolla. Vanhat API-tilanimet muunnetaan: `reader -> novel`, `player -> roleplay`, `director -> simulation`.

## Testit

```powershell
python -m unittest discover -s tests -v
```

Testit käyttävät väliaikaisia kansioita ja valemalleja, eivät käyttäjän tarinoita tai oikeita mallikutsuja. Ne kattavat muun muassa tietorajauksen, tilojen erot, pelaajan toiminnan, tallennuksen eheyden, uudelleenlähetyksen, muokkausristiriidat, muistinhaun, migraation, taustatyöt ja polkurajaukset. Testit ovat rajallisia eivätkä kata kaikkia käyttötilanteita.

Käyttöliittymää on kokeiltu kehitystyön yhteydessä työpöytä- ja puhelinleveydellä, mutta kattavaa selain- tai käyttäjätestausta ei ole tehty. Kirjallisen laadun ja pitkien tarinoiden muistamisen arviointi edellyttää erillisiä oikeiden mallien kokeiluja.

## Nykyiset Rajat

Havaitsijoiden rajaus estää suoran yhteisen proosakontekstin vuodon. Kertoja on silti kielimalli: se voi kirjoittaa virheellisen havaintokuvauksen tai ristiriitaisen seurauksen. Skeematarkistus ei todista tapahtumien semanttista oikeellisuutta. Päätöskohtien ja kappaleiden rytmitys riippuu mallista ja prompteista.

Tarinahaarat, proosamuutosten automaattinen tilasynkronointi, kuvien generointi ja usean palvelinprosessin työjono eivät kuulu tähän toteutukseen. Kuvituspromptteja voidaan edelleen tuottaa. Näitä ominaisuuksia kannattaa lisätä hyväksytyn tapahtuma- ja tilamallin päälle, ei ohittamalla sitä.