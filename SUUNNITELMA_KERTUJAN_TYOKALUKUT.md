# Arvio: kertojan orkestroimat hahmotyökalukutsut

Päiväys 10.10.2026. Tämä on arkkitehtuurivertailu, ei ehdotus nykyisen toimintatavan välittömäksi korvaamiseksi. Tarkastelu perustuu tämänhetkiseen staattiseen ja adaptiiviseen vuoroputkeen.

## Tiivistelmä ja suositus

Kertojalle voisi tarjota hahmon aktivoinnin työkaluna: kertoja pyytäisi moottoria kutsumaan nimettyä hahmoa, moottori muodostaisi hahmolle rajatun havaintokontekstin ja palauttaisi sen tuoreen aikeen kertojalle työkalutuloksena. Kertoja voisi valita seuraavan hahmon uuden tapahtuman perusteella ja päättää, milloin ketju pysähtyy sekä milloin hyväksytty tapahtumajono annetaan proosavaiheeseen.

Tämä voisi tehdä reaktioketjuista joustavampia, mutta ei itsessään parantaisi hahmojen ajattelua tai vuorovaikutusta. Nykyinen adaptiivinen toteutus jo valitsee reaktioryhmän havaintojen ja avoimien yritysten perusteella, sallii A → B → A -vuoron ja käyttää erillistä kevyttä tilanneohjaajaa. Kertojatyökalut olisivat siis ensisijaisesti vaihtoehtoinen orkestrointirajapinta, eivät uusi kyvykkyys.

**Suositus:** älä siirrä hahmojen päätöksiä kertojalle äläkä korvaa toimivaa adaptiivista ketjua kerralla. Kokeile ensin rajattua hybridiä, jossa kertoja saa pyytää hahmon tuoreen päätöksen työkalun kautta mutta hahmoagentti pysyy päätöksen omistajana, tilanneohjaaja tai moottori validoi reaktiot ja tapahtumat, ja erillinen proosavaihe kirjoittaa hyväksytyn ketjun. Natiivien mallikohtaisten työkalukutsujen sijaan sisäinen, palveluntarjoajasta riippumaton työkalusopimus olisi turvallisin ensimmäinen prototyyppi. Vertailutestien tulee osoittaa laadun tai ohjattavuuden parantuminen ennen kuin lisäviive ja monimutkaisuus hyväksytään.

## Nykyinen toimintatapa ja vaihtoehto

### Nykyinen vuoroputki

- Suunnittelija tuottaa vuorokehyksen ja aloitusryhmän; se ei päätä läsnä olevien hahmojen vapaaehtoisia tekoja.
- Jokainen hahmoagentti saa omat havaintonsa, profiilinsa, suhteensa, muistonsa ja oman aiemman aikeensa. Se palauttaa rakenteisen päätöksen: aikeen, puheen, mahdollisen havaittavan aloituksen ja yksityisen ajatuksen.
- Adaptiivisessa tilassa tilanneohjaaja ratkaisee tuoreet yritykset ja valitsee havaittuun uuteen tapahtumaan perustuvan seuraavan reaktioryhmän. Moottori tarkistaa osallistujat, tapahtumaviitteet, budjetit, pelaajarajat sekä tilamuutokset.
- Erillinen kirjoitusvaihe kuvaa hyväksytyn tapahtumaketjun proosaksi. Tila ja vuorot tallennetaan validoituina ja atomisesti. Staattisella yhteensopivuuspolulla ratkaisija tuottaa tuloksia ja proosan yhdessä laajemmassa vastauksessa.

Nykyinen rakenne erottaa toisistaan hahmon päätöksen, seurauksen ratkaisemisen, orkestroinnin, kerronnan ja tallennuksen. Tämä erottelu auttaa säilyttämään hahmon toimijuuden ja rajatun tiedon, mutta monivaiheinen putki voi olla työläs ymmärtää ja siinä on useita vastauksia validoitavana.

### Kertojan orkestroima työkalumalli

1. Kertoja tuottaa vuorokehyksen ja saa käyttöönsä rajatun `activate_character`-tyyppisen toiminnon.
2. Kertoja pyytää toimintoa nimetylle, kelpoiselle hahmolle. Pyyntö voi viitata uuteen havaintotapahtumaan, mutta ei antaa hahmon päätöstä valmiina.
3. Moottori tarkistaa kelpoisuuden ja kontekstin, kutsuu kyseisen hahmon päätösagenttia ja palauttaa tuloksen kertojalle. Hahmon yksityinen ajatus pysyy rajattuna, eikä työkalutulos ole vielä hyväksytty tapahtuma.
4. Kertoja voi pyytää uuden hahmon päätöstä tai pyytää moottoria ratkaisemaan tuoreet yritykset ja tapahtumat. Moottori validoi tulokset, pysäytysehdot ja pelaajalle kuuluvat valinnat.
5. Lopullinen kerronta käyttää vain moottorin hyväksymää tapahtuma- ja havaintojonoa. Se ei saa tehdä uusia hahmopäätöksiä tai lisätä hyväksymättömiä maailmanmuutoksia.

Tässä mallissa “työkalukutsu” on mallille näkyvä ohjauspyyntö, ei suora tietokantaoperaatio. Työkalun toteutus pysyy sovelluskoodissa ja kutsuu hahmoagenttia. Kertoja voi ehdottaa, ketä aktivoida, mutta sovellus ratkaisee, saako kyseisen hahmon kutsua.

## Vertailu

| Ominaisuus | Nykyinen adaptiivinen putki | Kertojan orkestroimat työkalukutsut |
|---|---|---|
| Reaktioryhmän valinta | Erillinen kevyt tilanneohjaaja valitsee uuden havainnon ja avoimien yritysten perusteella. | Kertoja valitsee hahmot työkalukutsuilla; valinta ja mahdollinen perustelu keskittyvät samaan orkestroivaan malliin. |
| Hahmon päätös | Erillinen hahmoagentti tekee aina tuoreen päätöksen omalla kontekstillaan. | Voi säilyä täysin samana, jos työkalu vain käynnistää hahmoagentin. Päätöstä ei pidä generoida kertojamallin puolesta. |
| Seurausten validointi | Moottori ja tilanneohjaaja erottavat yrityksen toteutuneesta tapahtumasta. | Työkalurajapinnan on edelleen erotettava päätöspyyntö, ehdotus, hyväksytty tulos ja lopullinen tallennus. |
| Hahmojen välinen reagointi | Tuore havainto voi aktivoida uuden hahmon tai saman hahmon uudelleen. | Kertoja voi pyytää seuraavan reaktion joustavasti, mutta työkalutuloksen tulee tulla reagoivalle hahmolle vain sen omista havainnoista. |
| Kutsujen määrä ja viive | Suunnittelu, hahmopäätökset, tilannekutsut ja proosa ovat erillisiä vaiheita; fast path voi ohittaa osan tilannekutsuista. | Ei automaattisesti vähennä mallikutsuja. Kertojan päätös + hahmopäätös voi lisätä kierroksia etenkin sarjallisessa käytössä; yhdistäminen voi myös vähentää välivaiheita, jos mittaus osoittaa sen. |
| Palveluntarjoajariippuvuus | Nykyinen JSON/JSON Schema -rajapinta on yhteisen adapterin takana. | Natiivit työkalukutsut vaativat provider- ja mallikohtaista tukea, työkalutulosten parsintaa, kutsujonon jatkamista ja fallback-käytäntöjä. |
| Virheiden ja replayn hallinta | Ehdokasketjun tarkistuspisteet, pyyntö kuitteineen, revision tarkistus ja atominen commit muodostavat nykyiset rajat. | Jokainen työkalupyyntö ja -tulos tarvitsee saman ketjutetun auditoinnin, idempotenssin sekä keskeytyksen ja uudelleentoiston säännöt. |
| Muutoksen koko | Nykyinen malli toimii ja adaptiivinen polku tukee dynaamista vuorovaikutusta. | Muuttaa malliprotokollaa ja orkestrointivastuun sijaintia; hyöty pitää todistaa ennen laajaa migraatiota. |

## Mihin muutos vaikuttaisi?

### Mallien vastausrakenteet ja kehotteet

- Hahmon nykyinen `CharacterDecisionResponse` kuvaa yhden rajatun päätöksen. Sen kenttiä ei pidä korvata kertojan työkalupyyntömallilla: hahmon sisäinen vastaus ja kertojan orkestrointivastaus ovat eri sopimuksia.
- Kertojan nykyinen suunnittelija-, tilanne-, ratkaisija- ja proosavastaus täytyisi joko yhdistää työkalukutsuja sisältäväksi orkestrointivastaukseksi tai jättää osin rinnalle. Uuden sopimuksen on erotettava vähintään työkalupyyntö, sen argumentit, tulos, ketjun jatkaminen ja lopullinen valmistuminen.
- Hahmon aktivointityökalulle tarvitaan suppea syöte: hahmotunniste, täsmällinen herätetapahtuma tarvittaessa sekä rajattu vuoron tarkoitus. Kertoja ei saa syöttää fiktiivistä havaintoa hahmolle eikä valita vastauksen sisältöä.
- Yhden vastauksen sisäinen työkalukutsusilmukka muuttaa `finish`- ja pysäytyssemantiikkaa. Työkalukutsujen määrän, syvyyden, käyttöajan ja rinnakkaisuuden katot on määriteltävä.
- Uusi rakenne vaikuttaa JSON-skeemoihin, Pydantic-validointiin, korjauspolkuihin, auditointeihin, mallivasteiden lokitukseen ja mahdollisesti tietokantaan tallennettavaan vuorokuittiin. Tallennusmalli kannattaa ensin pitää ennallaan, jos tulokset voidaan muuntaa nykyiseksi hyväksytyksi tapahtumaketjuksi.

### LLM-asiakas ja palveluntarjoajat

Nykyinen asiakas pyytää JSON-objektin tai JSON Schemalla rajatun vastauksen ja parsii viestisisällön. Työkalukutsut palautuvat useissa rajapinnoissa erillisenä `tool_calls`-rakenteena eivätkä tavallisena JSON-tekstinä. Asiakas ja kaikki tuetut provider-adapterit tarvitsevat tällöin yhteisen työkalukutsuabstraktion tai eksplisiittisen JSON-pohjaisen vaihtoehdon. Adapterien tulee normalisoida kutsut, validoida argumentit ja palauttaa myös tekstivastaukset samalla sopimuksella.

Natiivien työkalukutsujen ominaisuudet, skeemarajoitukset ja yhdistäminen JSON Schema -tilaan vaihtelevat malleittain ja palveluntarjoajittain. On testattava mallikohtaisesti, voiko kertoja kutsua työkalua ja saada samalla halutun rakenteisen valmistumisvastauksen. Käyttökelpoinen fallback on sisäinen JSON-discriminated union -sopimus, mutta sitä ei pidä sekoittaa natiivin työkalukutsun suorituskyky- tai laatutakuuseen.

### Vuoromoottori, käyttöliittymä ja tallennus

- Moottorin olisi ajettava ohjattua tilakonetta eikä annettava mallille vapaata työkalusuoritusta. Jokainen tulos validioidaan ennen kuin se palautetaan seuraavaan mallikutsuun.
- Pelaajahahmoa ei saa kutsua automaattisesti uudelleen ilman pelaajan valintaa. Samoin pysäytys, keskeytys, budjettiraja, tuntematon sijainti, piilossaolo ja toimintakyky tarkistetaan ennen hahmoagentin käynnistystä.
- SSE-/job-vaiheiden pitäisi näyttää ymmärrettävästi kertojan orkestrointi, hahmon päätöksen valmistuminen ja hyväksytty ratkaisu. Yksityisajatusta, raakoja argumentteja tai yksityistä työkalutulosta ei saa näyttää muille hahmoille tai pelaajalle ilman nimenomaista näkymärajauksen perustetta.
- Työkalukutsu voi päättyä timeoutiin tai keskeytykseen siinä kohdassa, kun hahmon vastaus on jo saatu mutta tapahtumaa ei ole vielä ratkaistu. Checkpointin täytyy tallentaa ketjun vaihe, työkalukutsun tunniste, käytetty heräte ja hyväksyntätila niin, ettei uusinta suorita hahmon päätöstä tai maailmavaikutusta kahdesti.
- Vuorokuitti, replay, rollback, revision ja atominen tallennus pysyvät välttämättöminä. Mallille annettu valtuutus ei saa ohittaa tietokannan revision tai tapahtumaviitteen tarkistusta.
- API- ja käyttöliittymävastaukset voivat muuttua, jos nykyiset vaihetapahtumat tai lopputulos muuttavat muotoaan. Muutos koskee myös palveluntarjoajien adapteritestejä, tilanneohjausta, ryhmäajoa, SSE-seurantaa, palautumista, roolipelin pelaajarajoja ja skeeman hylkäystestejä.

### Vastuunjako ja tietoturvarajat

Kertoja tuntee maailman kokonaisuuden ja voi valita seuraavan aktivoitavan hahmon, mutta hahmoprompti ei saa saada kertojan kaikkitietävää tilaa, muiden yksityisiä ajatuksia tai proosaa yhteisenä tietolähteenä. Moottorin on muodostettava kullekin hahmolle erillinen havaintojoukko, profiili, muisti, suhteet ja oma aikomushistoria kuten nytkin. Kertoja voi nähdä laajemman kokonaisuuden reititystä varten, mutta työkalun argumentit eivät ole lupa lisätä tietoja hahmon kontekstiin.

Työkalukutsut ovat epäluotettavaa mallin ulostuloa. Tunnisteiden, osallistujien, työkalujen sallittujen argumenttien ja seurausten validointi kuuluu sovellukselle. Malli ei saa työkalulla suoraan kirjoittaa tietokantaan, hyväksyä tapahtumia, muuttaa havaitsijoita, ohittaa pelaajapysäytystä eikä suorittaa rajoittamattomia lisäkutsuja.

## Vaikutus hahmojen vuorovaikutuskykyyn

### Mahdollinen parannus

Kertojan työkalureititys voi antaa mallille mahdollisuuden reagoida heti tuoreeseen tapahtumaan, aktivoida alussa suunnittelemattoman hahmon tai palata samaan hahmoon uuden ärsykkeen jälkeen. Se voi vähentää ennalta määriteltyjen ryhmien jäykkyyttä sekä tehdä puheenvuorojen järjestyksen tilanteeseen sopivaksi. Sama dynaamisuus on kuitenkin jo adaptiivisen tilanneohjaajan tarkoitus. Työkalukutsujen hyöty näkyisi lähinnä siinä, valitseeko kertoja paremmin seuraavan reagoijan kuin erillinen tilanneohjaaja ja pystyykö tämä tekemään sen vähemmillä kokonaiskutsuilla tai pienemmällä kontekstilla.

### Mahdollinen heikennys

Keskitetty kertoja voi suosia näkyvää dialogia ja dramaattista juonenkuljetusta realistisen hiljaisuuden, väärinymmärryksen, keskeytyksen tai itsenäisten tavoitteiden sijaan. Jos kertoja saa valita hahmon ja syöttää hänelle tavoitteet tai toiminnan, se voi käytännössä päättää hahmon puolesta. Jos jokainen hahmo aktivoidaan vain kertojan kutsusta, itsenäiset aloitteet voivat jäädä pois. Jos kertoja saa lukea koko ketjun yksityiset ajatukset, ne voivat vuotaa seuraavien hahmojen vastauksiin tai proosaan.

Erillinen hahmoagentti, sille rajattu konteksti ja erillinen seurausten ratkaisija säilyttävät selkeämmin sen, kuka halusi mitä, mitä hän oikeasti havaitsi ja mikä lopulta tapahtui. Työkalumalli ei poista tarvetta näille rajoille.

### Voivatko hahmot kutsua toisiaan työkaluina?

Suositus on **olla antamatta hahmolle suoraa työkalua, joka käynnistää toisen hahmoagentin**. Se sekoittaisi maailman sisäisen toiminnan ja sovelluksen orkestroinnin: fiktiivinen hahmo ei voi taata, että toinen kuulee viestin, suostuu vastaamaan tai on edes läsnä. Suora kutsu voisi myös ohittaa reaktiobudjetin, pelaajan vuoron tai toisen hahmon rajatun tiedon.

Hahmo voi sen sijaan tuottaa puheen tai muun yrityksen, jonka tarkoitettu vastaanottaja on vain ehdotus. Moottori tai tilanneohjaaja päättää, tapahtuiko havaittava viestintä ja ketkä sen havaitsivat; kertoja tai tilanneohjaaja voi tämän uuden tapahtuman jälkeen pyytää vastaanottajalle oman päätöksen. Näin kerronnallinen “hahmo puhuu toiselle hahmolle” säilyy, mutta protokollassa päätöskutsu on kertojan/moottorin hallittu aktivointi eikä hahmon oma ohjelmallinen komento.

Rajattu poikkeus olisi hahmolle tarjottu “osoita puhe X:lle” -toiminto, joka merkitsee tavoitellun vastaanottajan tai puhetyypin mutta ei käynnistä häntä suoraan. Senkin tulee tuottaa tarkistettava yritys; todelliset kuulijat ratkaistaan erikseen.

## Mihin muuhun työkalukutsuista voisi olla hyötyä?

Hyötyä voi olla, kun mallin täytyy pyytää sovellukselta rajattu, varmennettava tai ympäristöstä riippuva toiminto:

- **Hahmon rajattu aktivointi:** moottori kerää juuri yhden kelpoisen hahmon tuoreen päätöksen.
- **Havaintojen tai muistojen haku:** hahmo voi pyytää lisähakua omista sallituista muistoistaan tai tapahtumahavainnoistaan; tulos rajataan käyttäjän identiteettiin eikä kertoja saa antaa hahmolle muiden muistia.
- **Tapahtumien validointi ja ratkaisu:** mallin ehdotus voi pyytää moottoria tarkistamaan sijainnin, tapahtumaviitteet, avoimen yrityksen tai sallitun tilapäivityksen. Lopullinen hyväksyntä pysyy deterministisellä validoinnilla ja kertojan rajatulla ratkaisulla.
- **Pelaajan välitön valinta:** orkestroija voi pyytää käyttöliittymää pysähtymään ja odottamaan syötettä täsmällisessä päätöskohdassa sen sijaan, että kirjoittaisi valinnan pelaajan puolesta.
- **Tekstin jälkikäsittelyn rajatut toiminnot:** kuvituspyynnön valmistelu, lukijanäkymän generointi, yhteenveto tai vienti voi olla erillinen jälkivaihe. Näiden tulisi pysyä ei-kanonisina, ellei niille ole erillistä vahvistusta.
- **Tarinan työkalut:** editorin analyysi ja ehdotetut muutokset voivat toimia ehdotuksina, jotka käyttäjä hyväksyy ennen tilapäivitystä.

Työkalukutsuja ei kannata lisätä vain siksi, että toiminto on teknisesti mallille näkyvä. Yksinkertaiset, usein käytetyt tiedonhaut voidaan pitää sovelluksen tavallisena kontekstinmuodostuksena. Mallille näkyvät työkalut lisäävät uuden epäluotettavan syöte-/tulosrajan, joten niiden on oltava tarpeen mukaan tarjolla ja vähimmillä oikeuksilla.

## Suositeltu eteneminen ja vertailu

1. **Määrittele protokolla ennen toteutusta.** Kirjaa työkalun argumentit, tulos, kelpoisuusehdot, pysäytys- ja budjettikatot, rinnakkaisuuden säännöt, pelaajarajat, yksityisyysrajat sekä replay- ja keskeytyskäytös.
2. **Tee sisäinen orkestrointiprototyyppi.** Pidä nykyinen hahmoagentti, tilanteen validointi, tapahtumasopimus, commit ja erillinen proosakirjoitus. Muuta ensin vain sitä, kuka valitsee seuraavan hahmon. Vertailua varten nykyinen adaptiivinen polku säilyy käytettävissä.
3. **Vertaa samoilla tilanteilla nykyistä adaptiivista ja työkaluprototyyppiä.** Käytä eri tilanteita: kahden henkilön keskustelu, A → B → A, suunnittelematon C, yksityinen tai kuulumaton puhe, keskeytys, ristiriitaiset tavoitteet, hiljaisuus, odotus, epäonnistunut yritys ja pelaajalle kuuluva päätös. Toista useilla siemenillä ja samoilla malleilla/asetuksilla.
4. **Arvioi sokkona laadulliset tulokset.** Mittaa vuorovaikutuksen luonnollisuutta, hahmojen oman äänen ja tavoitteiden säilymistä, reaktioiden syy-yhteyttä, kerronnan koherenssia, toistuvuutta, hiljaisuuden uskottavuutta sekä väärin aktivoituja tai ohitettuja hahmoja. Testiautomaatio voi todentaa rajat, ei yksin kirjallista laatua.
5. **Mittaa operatiiviset vaikutukset.** Kirjaa mallikutsut vaiheittain, kokonaisviive, input/output-tokenit ja toteutuneet kustannukset, epäonnistuneet/korjatut työkalukutsut, katkenneet ketjut, budjetin ylitykset sekä käyttäjän pelaajavalintojen oikea pysäytys. Älä päättele säästöä pelkästä pienemmästä vastausskeemasta.
6. **Laajenna vain näytön perusteella.** Jos keskitetty reititys parantaa reaktioiden laatua eikä heikennä hahmojen itsenäisyyttä tai luotettavuutta, harkitse natiivien provider-työkalukutsujen adapteria. Muussa tapauksessa pidä nykyinen adaptiivinen ohjaaja tai käytä työkalumallia vain rajattuihin toimintoihin.

### Hyväksymiskriteerit prototyypille

- Hahmopäätökset syntyvät vain hahmoagentin omalla, havaintojen perusteella rajatulla kontekstilla.
- Työkalupyyntö ei yksin todista puheen kuulemista, yrityksen onnistumista tai toisen hahmon suostumusta.
- Sama hahmo voi reagoida uudelleen vain uuteen, kyseisen hahmon havaitsemaan tapahtumaan; vanha heräte ei aiheuta kutsusilmukkaa.
- Rinnakkaiset päätökset näkevät yhteisen lukitun lähtötilan, eivät toistensa keskeneräisiä vastauksia.
- Pelaajahahmon automaattinen valinta pysähtyy, kun pelaajalle kuuluu merkityksellinen päätös.
- Työkalukutsujen, tokenien ja ajan katot pysäyttävät ketjun säilyttäen ehjän tapahtumarajan; replay ei toista jo hyväksyttyä päätöstä tai muutosta.
- Yksikään työkalupolku ei ohita skeemavalidointia, tapahtumaviitteitä, tilarevisiota tai atomista tallennusta.
- Laadullinen arvio osoittaa nykyiseen adaptiiviseen polkuun nähden merkityksellisen hyödyn; kustannus- ja viiveväitteet perustuvat mitattuihin tuloksiin.

## Tämänhetkinen arvio

Kertojatyökalut voivat toimia hyvin, jos niitä käsitellään **orkestrointikielenä** ja hahmoagenttien, havaintorajojen sekä moottorin auktoriteetin päälle rakennettuna ohjauskerroksena. Ne eivät ole hyvä syy yhdistää hahmon aikomusta, kertojan ratkaisua ja maailman tosiasioita yhdeksi mallivastaukseksi.

Nykyisen adaptiivisen tilanneohjaajan ja kertojan työkalureitityksen olennaisin ero on ohjauslogiikan keskittäminen. Koska ensimmäinen jo mahdollistaa tuoreet, dynaamiset hahmoreaktiot, täysi siirtymä on perusteltu vain, jos mitattu vuorovaikutuslaatu, hallittavuus tai kokonaiskustannus paranee. Tällä hetkellä varmin vaihtoehto on hybridi: kertoja ehdottaa kenet aktivoida, hahmo päättää itse, moottori validoi ja ratkaisee, ja proosavaihe kertoo vain hyväksytyn ketjun.

## Nykyisen toteutuksen luettavaa

- `engine/character_agent.py` ja `core/schemas.py`: hahmon päätös ja sen JSON-sopimus.
- `engine/story_engine.py`, `engine/adaptive_interaction.py` ja `engine/situation_agent.py`: vuoron orkestrointi, adaptiivinen ryhmäajo ja tilanteen ratkaisu.
- `engine/director_agent.py`, `core/llm_client.py` ja `core/providers/`: kertojan vaiheet, JSON-vastausten käsittely ja provider-adapterit.
- `SUUNNITELMA_VUOROVAIKUTUS.md` ja `README.md`: nykyisen adaptiivisen arkkitehtuurin rajat, tietovirta ja hyväksymiskokeet.
