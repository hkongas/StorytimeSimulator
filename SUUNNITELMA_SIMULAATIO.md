# Tarinamoottori: vapaa maailma ja rajattu toimijuus

Suunnitelma 7.10.2026. Koostettu keskustelun suunnitteluratkaisuista ja toteutettu tavanomaisilla mallikutsuilla. Kenttäkohtaiset muutokset, päätösryhmät, vastauskorjaus, juoniohjaus, migraatioesikatselu ja jatkovalinnat on lisätty. Valemallitestit varmentavat tekniset rajat; kirjallinen laatu ja pitkäkestoinen muistaminen tarvitsevat oikeiden mallien kokeet. Realtime jää erilliseksi tutkimus- ja jatkosuunnitelmaksi; sitä ei oteta tämän muutoksen yhteydessä käyttöön.

## 1. Tavoite ja vastuunjako

Kielimallit luovat vapaan, kontekstiin sopivan tarinan. Ohjelma varmistaa tallennuksen, tietorajat ja toimivallan, ei määrää tarinan sisältöä rajatusta tapahtumavalikoimasta.

- Kertoja luo maailman, valitsee tilanteen rytmin ja ratkaisee seuraukset.
- Hahmot tekevät omat valintansa omien tietojensa ja motiiviensa pohjalta.
- Käyttäjä ohjaa omaa hahmoaan tai antaa erillisiä maailmanmuutosohjeita.
- Ohjelma pitää yritykset, toteutuneet tapahtumat, havainnot, faktat ja suunnitelmat erillään.
- Epäonnistuminen, kieltäytyminen, luopuminen ja tilanteen päättyminen ovat kelvollisia seurauksia. Kaikkiin tilanteisiin ei lisätä uhkaa tai salaisuutta etenemisen pakottamiseksi.

## 2. Sijainti, läsnäolo ja havainnot

Sovittu merkitys: hahmon `location_id: null` tarkoittaa tuntematonta sijaintia ja poissaoloa nykyisestä kohtauksesta.

- Läsnä olevan hahmon sijainti on tunnettu ja vastaa kohtauksen sijaintia.
- Aktiivihahmolista ei yksin tee tuntemattomassa sijainnissa olevasta hahmosta läsnä olevaa.
- Piilossa oleva hahmo voi olla samassa paikassa. Piilossaolo ei tarkoita tuntematonta sijaintia eikä automaattista havaittavuutta.
- Samassa paikassa oleminen ei yksin takaa havaintoa: etäisyys, esteet, huomio ja aistit vaikuttavat.
- Hahmon läsnäolo ei oikeuta välittämään hänen nimeään kaikille muille nykyisen NÄET NYT -listan kautta. Lista muodostetaan havaittavista tai jo tiedossa olevista läsnäolijoista.
- Poissa oleva hahmo ei saa paikallisia havaintoja. Paluu tapahtuu uudella saapumistapahtumalla, ilman poissaolon aikaisten havaintojen jälkikäteistä myöntämistä.
- Etähavainto on erillinen poikkeus, jolla on nimetty tiedonkulun lähde ja vastaanottaja. Lähde voi olla esimerkiksi yhteys tai tallenne; se ei merkitse paikallista läsnäoloa.
- Uusi etähavaintokanava voidaan luoda maailmanmuutoksella. Historiallinen tallenne voi tuoda tietoa nyt, mutta se ei muuta aiempia päätöksiä tai anna hahmolle tietoa takautuvasti.
- Etähavaintojen täysi toteutus on myöhempi vaihe. Ensimmäisessä vaiheessa ei sallita yleistä etähavainto-oikotietä.

Vanha data tarkistetaan esikatselulla: nykyisessä koodissa null on voinut tarkoittaa kohtauksen oletussijaintia. Vanhoja hahmoja ei siirretä automaattisesti pois uuden tulkinnan vuoksi. Yksiselitteiset tapaukset voidaan migroida tunnettuun kohtauspaikkaan; epäselvät vaativat hyväksynnän.

## 3. Vapaa maailman luominen ja tallennussopimus

Uusi paikka, esine, suhde tai sivuhenkilö voi syntyä tarinan mukana. Viittaus saa kohdistua aiemmin tallennettuun asiaan tai saman vastauskokonaisuuden uuteen määrittelyyn.

- Luo uusi asia ja sen tapahtumaperuste yhdessä; ratkaise paikalliset viitteet ennen tietokantaan kirjoittamista.
- Ohjelma tuottaa tai normalisoi pysyvät tunnisteet. Kielimallin ei tarvitse tehdä monimutkaista tunnistelaskentaa.
- Erottele olemassa olevan asian päivitys ja uuden asian luominen. Älä yhdistä samannimisiä asioita automaattisesti.
- Tarkista kenttäkohtaiset tyypit ja ristiriidat, ei mielikuvituksellisen sisällön kuulumista valmiiseen luetteloon.
- Laajat vapaat kuvaukset täydentävät pientä rakenteellista ydintä. Kaikille narratiivisille ominaisuuksille ei tarvita tietokantakenttää.
- Käyttäjä voi muokata vapaata kuvausta. Jos muutos koskee sijaintia, tietoja tai muuta rakenteellista tilaa, näytä erillinen tilamuutosesikatselu.
- Epävarma uskomus ei muutu maailman faktaksi eikä toisen hahmon tiedoksi tekstin kopioimisen vuoksi.

Ensimmäinen välttämätön korjaus on kenttäkohtainen StateChange-sopimus sekä null-sijainnin yhdenmukainen käsittely kehotteissa, skeemassa, validoinnissa, läsnäolosuodatuksessa ja tallennuksessa.

## 4. Historia, proosa ja kronikka

Alkuperäinen hyväksytty kertojaproosa on pysyvä kirjallinen historiatallenne. Kronikka on siitä ja toteutuneista tapahtumista johdettu tiivistelmä, ei alkuperäisen korvaaja.

- Tapahtumat ja tilapäivitykset ovat saman vuoron rakenteellinen esitys. Proosa, tapahtumat ja tila eivät saa muodostaa kolmea ristiriitaista totuutta.
- Ratkaise tapahtumat ja seuraukset, kirjoita proosa niiden pohjalta ja tarkista olennaiset ristiriidat ennen hyväksyntää.
- Hahmon rajattu näkymä muodostetaan havainnoista, ei kaikkitietävän proosan suodattamattomasta tulkinnasta.
- Kertojan tulkinnat ja kielikuvat eivät automaattisesti ole uusia maailman faktoja.
- Proosan, tapahtumien ja tilan ristiriita pysäyttää hyväksynnän korjattavaksi; sitä ei ratkaista hiljaisella historian muutoksella.
- Kronikkaan säilytetään lähdeviitteet ja tiivistelmäversio. Vanha alkuperäinen aineisto voidaan hakea tarvittaessa.
- Tekstieditointi ja maailmanmuutos erotetaan. Merkitystä muuttava editointi vaatii vaikutusten esikatselun tai uuden haaran.
- Kumoaminen ja uudelleenyritys palauttavat tai haarauttavat tilan; ne eivät väitä, ettei alkuperäistä suoritusta tapahtunut sen omassa haarassa.

## 5. Vastauskorjaus ilman kierroksen uusimista

- Säilytä alkuperäiset aikeet, lähtötilan revisio, vastausehdokas ja validointivirheet.
- Tarkista koko vastauskokonaisuus ennen pysyvän tilan muuttamista.
- Normalisoi vain yksiselitteiset muotovirheet. Älä keksi puuttuvaa seurausta tai muuta nullia tekstiksi.
- Tee enintään yksi automaattinen rajattu korjauskutsu. Anna virheen polku, odotettu muoto ja säilytettävät tapahtumat sekä aikeet.
- Tarkista myös korjatun vastauksen kaikki ristiinviitteet ja tietorajat.
- Jos korjaus muuttaa tapahtumaketjua, aiemmat siihen perustuneet ehdokashavainnot ja reaktiot on mitätöitävä tai ratkaistava uudelleen. Tämä ei ole pelkkä JSON-paikkaus.
- Epäonnistuneen korjauksen jälkeen jätä nykyinen tila ehjäksi ja säilytä ehdokas jatkokorjausta varten.
- Lokita erikseen mallikutsu, rakenteellinen validointi, merkityksellinen validointi, korjaus ja tallennus. success ei yksin tarkoita hyväksyttyä vuoroa.
- Keskeytys ja uudelleenyritys eivät toista jo tallennettua toimintaa; pyyntötunniste ja revisiotarkistus säilyvät.

## 6. Päätösryhmät ja vuorovaikutus

Suunnittelija valitsee tilanteen perusteella peräkkäiset, rinnakkaiset tai yhdistetyt päätösryhmät. Ohjelma tarkistaa toimijat, riippuvuudet, tietorajat ja vaihebudjetin.

### Peräkkäinen, tiivistetty vuorovaikutus

Hahmon vastaus sisältää yksityisen ajattelun ja julkisen toiminnan tai puheen ehdotuksen. Seuraava hahmo saa havaitsemansa käynnissä olevan toiminnan, ei yksityisajattelua eikä varmistamatonta lopputulosta.

- Erota tapahtunut osa, havaittava aloitus ja vielä avoin lopputulos.
- Seuraava hahmo voi reagoida ja yrittää keskeyttää. Kertoja ratkaisee ajoituksen, onnistumisen ja seuraukset kerättyään tarpeelliset vastaukset.
- Vain havaittavissa oleva aloitus välitetään; ei koko toimijan salaista suunnitelmaa.
- Lopullinen ratkaisu ei saa perua jo havaittua aloitusta. Jos aloituksen kelpoisuutta ei pystytä ratkaisemaan kevyesti, tarvitaan väliin kertojan tarkistus.
- Jos myöhempi valinta edellyttää jo ratkaistua lopputulosta, lisää väliratkaisu ennen sitä. Muuten seuraava hahmo voisi reagoida tapahtumaan, jota ei koskaan tapahtunut.
- Tavallisessa keskustelussa kokonainen repliikki voi olla pienin tarkoituksenmukainen yksikkö. Jokaista sanaa tai elettä ei pilkota omaksi kutsukseen.

### Rinnakkainen itsenäinen päätös

- Ryhmän kaikki hahmot saavat oman rajatun näkymän samaan lukittuun lähtöhetkeen.
- Ne eivät saa saman ryhmän muiden vastauksia ennen omaa päätöstään.
- Kertoja ratkaisee yhteensovittamisen ominaisuuksien, tilanteen ja sovittujen sääntöjen perusteella.
- Rajapinnan valmistumisnopeus ei ole hahmon reaktionopeus. Tulosten tekninen järjestys ei saa antaa toimintaetua.

### Budjetti, pelaaja ja tallennus

- Ehdotus: rajattu päätösryhmien ja väliratkaisujen määrä yhtä käyttäjän jatkopyyntöä kohti. Tarkka oletus valitaan vertailukokeissa.
- Pysähdy pelaajan uuteen merkitykselliseen päätökseen. Älä tee pelaajan reaktiota hänen puolestaan.
- Välivaiheet ovat ehdokastilaa. Hyväksy kokonaisuus atomisesti tai tallenna erillinen ehjä vuoro selkeässä päätöskohdassa.
- Nykyinen yhden lisäreaktion asetus korvataan tai sovitetaan ryhmämalliin; se ei saa synnyttää toista päällekkäistä orkestrointisilmukkaa.
- SSE näyttää työvaiheet, mutta ehdokastekstiä ei esitetä tallennettuna historiana.

## 7. Juoniohjauksen voimakkuus

Käyttöliittymään aluksi kolme nimettyä tasoa, ei näennäisen tarkkaa prosenttilukua.

- Mukautuva: painota hahmojen tavoitteista syntyviä kehityskulkuja.
- Tasapainoinen: ylläpidä suunniteltuja ristiriitoja ja etenemismahdollisuuksia, hyväksy vaihtoehtoiset suunnat.
- Vahvasti ohjattu: ulkoiset toimijat, määräajat ja valmistellut tapahtumat etenevät aktiivisesti, vaikka pelaaja valitsisi muun tekemisen.

Voimakkuus ei oikeuta määräämään hahmon vapaaehtoista valintaa tai muuttamaan historiaa. Sitovat maailmansäännöt ja salaiset totuudet määritellään erikseen; tulevaisuuden suunnitelmat voivat joustaa kaikilla tasoilla.

Suunnitelma kertoo tavoitteen, perusteen, riippuvuudet hahmovalinnoista ja ehdot sen hylkäämiselle tai taustalle siirtämiselle. Päivitykseen kirjataan lyhyt perustelu. Tiukkuus ei ole todennäköisyys eikä onnistumisprosentti.

## 8. Tavoitteet, aika ja eteneminen

- Tavoitteet ovat vapaamuotoisia, mutta yrityksellä on tunniste ja tulos: toteutui, epäonnistui, keskeytyi tai odottaa.
- Sitoumuksiin voidaan liittää osapuolet, edellytykset ja määräaika. Kaikki tavoitteet eivät ole tehtäviä tai määräaikaisia.
- Kertoja arvioi kuluneen ajan ja seuraavan merkityksellisen hetken. Tavallinen kierros ei aina vastaa yhtä aikayksikköä.
- Kellot etenevät sovitulla ajalla; keskustelun lisäreaktio ei automaattisesti kuluta uutta täyttä aikajaksoa.
- Maailma ja sivutoimijat voivat jatkaa omia kehityskulkujaan hahmon huomion ulkopuolella. Hahmo ei saa näitä tietoja automaattisesti.
- Etenemisarvio käyttää tilamuutoksia ja tapahtumien merkitystä. Pelkkä change_kind tai erilainen sanamuoto ei todista etenemistä.
- Toiston arvio kertoo, mikä tavoite ei edistynyt ja miksi. Ratkaisu voi olla odottaminen, luopuminen, uusi lähestymistapa tai kohtauksen päättyminen.
- Koodilla voidaan havaita toistuva rakenne; semanttinen arvio ja luonteva jatko kuuluvat kertojalle. Ne eivät ole täydellisesti todistettavissa automaattisesti.

## 9. Epäonnistuminen ja pelin jatkaminen

Nykyinen tilamalli tukee dead-tilaa, hahmoagentti jättää kuolleen hahmon toimimatta ja ratkaisija ei saa kumota tilaa automaattisesti. Pelaajanäkökulman kehote kieltää uudet havainnot kuolleelta tai tajuttomalta. Tarkastetussa pääkerrontakehotteessa ei ole yhtä selkeää yleistä epäonnistumis- tai pelinlopetussopimusta; erillistä kattavaa pelinlopetusvirtaa ei ole tässä analyysissä varmennettu.

- Tarinakohtainen epäonnistumiskäytäntö sekä kontekstiin ja tyyliin sopiva seurausten realismi.
- Pelaajahamon menettäminen ei välttämättä päätä maailman tarinaa.
- Käyttöliittymä tarjoaa hyväksytyn lopetuksen, siirtymisen kelvolliseen toiseen hahmoon tai uudelleenyrityksen aiemmasta tilannekuvasta uudessa haarassa.
- Uuden hahmon näkökulma käyttää vain hänen omia tietojaan. Vanha pelaajatieto ei siirry automaattisesti hahmolle.
- Uudelleenyritys ei palauta hahmoa eloon alkuperäisessä historiassa.
- Yhtenäistä toimintakykyisten, poissa olevien ja päättyneiden hahmojen valinta kaikissa käyttöliittymissä.

## 10. Konteksti ja kehotteet

- Poista päällekkäiset profiilit, muistot ja kieliohjeet; säilytä roolikohtaiset ydinsäännöt yhdessä paikassa.
- Säilytä ydinsäännöt, nykytilanne, tavoitteet, sitoumukset ja relevantit vanhat tiedot. Älä rajaa kontekstia vain viimeisimpiin tapahtumiin.
- Kertojalle annetaan tilanteeseen liittyvä maailmanosa ja tarvittaessa lisähaku. Hahmon haku koskee vain hänen sallittuja tietojaan.
- Kirjaa oikeasti käytetyt lähteet kontekstimanifestiin, ei vain laajaa kaikkien mahdollisten tapahtumien luetteloa.
- Mittaa syötetokenit, tuotostokenit, cache, viive ja tunnettu tai tuntematon kustannus erikseen.
- Suunnittelukutsun arvo on ryhmittely, rytmi, ulkoiset tapahtumat, aikahorisontti ja pysähtymisehto, ei saman maailmantilan uudelleen kertominen.

Kertojan itse luoma vapaa järjestelmäkehote ei ole ensimmäinen toteutus. Käytä olemassa olevassa suunnittelukutsussa tilanteeseen sidottua työohjetta: mitä ratkaistaan, ryhmät, tietorajat, avoimet seuraukset ja pysähtymiskohta. Ohjelma yhdistää sen kiinteään roolisopimukseen. Suunnitelma ei voi poistaa toimijuus-, tietoraja- tai tallennussääntöjä. Erillistä metakehotekutsua kokeillaan vain, jos vertailu osoittaa hyötyä.

## 11. Realtime: myöhempi tutkimushaara

Realtime-rajapinnat tukevat pysyviä istuntoja, uutta syötettä ja keskeytyksiä. Pelkkä tavallisen vastauksen tokenstream ei muuta jo käynnissä olevan generoinnin lähtökontekstia. Realtime ei itsessään takaa yhteistä simulaatioaikaa, tietorajoja tai kahden mallin keskinäistä välitöntä reagointia; sovellus orkestroi edelleen tapahtumat.

Nykyiseen JSON-pohjaiseen arkkitehtuuriin päätösryhmät ovat ensimmäinen toteutus. Realtime arvioidaan myöhemmin erikseen laadun, mallituen, kustannuksen ja toistettavuuden perusteella. Erillinen [Realtime-suunnitelma](SUUNNITELMA_REALTIME.md) kirjaa päätepisteet, mallirajoitukset, hahmokohtaiset istunnot, tiedonkulun ja laskutuksen.

Lähde: [OpenAI: Realtime conversations](https://developers.openai.com/api/docs/guides/realtime-conversations).

## 12. Toteutusjärjestys ja hyväksymiskriteerit

### Vaihe 1 — luotettava vapaa tila

Kenttäkohtaiset muutokset, null-sijainnin tulkinta, läsnäolo ja näkyvyys, uusien paikkojen rekisteröinti, vanhan datan esikatselu ja rajattu vastauskorjaus.

Hyväksyntä: alkuperäinen sijaintivirhe ei kaada vuoroa; tuntematon hahmo ei saa paikallisia havaintoja; piilossa oleva hahmo ei paljastu nimilistasta; uusi paikka ja siirtymä tallentuvat yhdessä; epäonnistunut korjaus ei muuta tilaa.

### Vaihe 2 — luonteva vuorovaikutus

Suunnittelijan päätösryhmät, tiivistetyt julkiset aloitukset, tarpeelliset väliratkaisut, pelaajan päätösrajat ja vaihebudjetti.

Hyväksyntä: keskusteluvastaus huomioi edellisen havaitun repliikin; rinnakkaisen ryhmän päätökset pysyvät toisiltaan piilossa; avoin lopputulos ei esiinny faktana; keskeytys ja uudelleenyritys eivät monista tapahtumia.

### Vaihe 3 — aika, tavoitteet ja juoniohjaus

Yritysten tulokset, sitoumukset, aikasiirtymät, toiston arvio, maailman itsenäinen eteneminen ja kolme juoniohjauksen tasoa.

Hyväksyntä: sama ratkaistu yritys ei palaudu uutena; maailman kulku ei riipu vain pelaajan yhteistyöstä; ohjaustaso ei määrää pelaajan päätöstä; rauhallinen tarina voi edetä ilman lisättyä uhkaa.

### Vaihe 4 — muisti, pelin jatko ja mittaus

Lähteistetty kronikka, relevantti kontekstihaku, rajattujen näkymien eheys, epäonnistumisvirta ja hallitut haarat.

Hyväksyntä: vanha sitoumus löytyy tiivistämisen jälkeen; näkökulman vaihto ei tuo toisen hahmon tietoja; uudelleenyritys ei muuta alkuperäistä haaraa; tallennetun tekstin, tapahtumien ja tilan ristiriita havaitaan.

### Vertailukokeet

Vertaa samoilla lähtötilanteilla nykyistä rinnakkaista mallia, tiivistettyä peräkkäistä mallia ja yhdistelmää. Käytä rauhallista neuvottelua, piilossa olevaa havaitsijaa, samanaikaisia itsenäisiä valintoja, poissaoloa ja paluuta, maailman luomista sekä tavoitteesta poikkeavaa pelaajaa.

Mittaa autonomia, tietorajat, toisto, tavoitteiden seuraukset, historiakonsistenssi, korjausaste, kutsumäärä, viive ja tokenit. Automaattitestit todistavat teknisiä rajoja; oikeiden mallien usean kohtauksen kokeet arvioivat kirjallista ja semanttista laatua.

## 13. Toteutuksen varmennus

Varmennuksessa 50 simulaatio-, tilasopimus- ja reaktiotestiä ajettiin kokonaisuutena: 49 läpäisi ensimmäisellä ajolla. Yksi vanha testi oletti, ettei virheellistä vastausta korjata; sen valemalli muutettiin palauttamaan virheellinen tapahtumaviite myös korjauskutsussa. Kyseisen testin uusinta läpäisi ja varmisti, ettei virheellistä korjausta tallenneta. Kaikki 16 käyttöliittymätestiä sekä Pythonin syntaksi- ja whitespace-tarkistukset läpäisivät. API-integraation migraatio, jatkaminen, haaran eristys ja juoniohjauksen tallennus on tarkistettu oikealla backendillä ja valemallilla. Katselmoinnin kaksi löydöstä korjattiin ja niiden kohdennetut testit läpäisivät: poistuneen hahmon uusi päätös ja haaralähteen säilyminen.

Koko projektin regressioajo jäi kesken ympäristön istuntovaihdoksessa; täyttä koko projektin puhdasta läpäisyä ei väitetä. Automaattitestit eivät osoita proosan semanttista laatua tai käytössä olevien pilvimallien skeemayhteensopivuutta.

Toteutus tarkistetaan ensin alkuperäisen null-sijaintivirheen, saman vastauksen uusien asioiden, vastauskorjauksen ja päätösryhmien kohdennetuilla testeillä. API:n ja käyttöliittymän kontrollit tarkistetaan sekä eristetyillä testeillä että todellisen backendin ja valemallin integraatiolla. Kaikki testitarinat ovat väliaikaisia; käyttäjän tarinoita tai oikeita mallipalveluja ei käytetä automaattiseen validointiin.

Oikeiden mallien pitkät laadun vertailukokeet, Realtime-toteutus, yleinen historiallisten tekstimuutosten tilasynkronointi ja yleiskäyttöinen haarojen yhdistäminen eivät ole automaattitestien osoittamia ominaisuuksia.

## 14. Muutosten kohteet

- [Skeemat](core/schemas.py), [tilasopimus](engine/turn_contract.py) ja [vuoromoottori](engine/story_engine.py).
- [Kertoja](engine/director_agent.py), [hahmoagentti](engine/character_agent.py) ja [kehotteet](prompts/).
- [Tallennus](database/turn_store.py), [tietokanta](database/db.py), migraatiot ja pyyntökuittien palautus.
- [API](web/api.py), [käyttöliittymä](web/static/) ja [testit](tests/).
- Päivitä [kehityslista](todo.txt) toteutuksen yhteydessä ja sovita historia- sekä haaramuutokset [editorisuunnitelmaan](SUUNNITELMA_EDITORI.md).
