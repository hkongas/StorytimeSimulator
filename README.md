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
| Simulaatio | Läsnä olevat toimintakykyiset hahmot tekevät itsenäisiä ratkaisuja kertojan valitsemissa peräkkäisissä tai rinnakkaisissa päätösryhmissä. | Ratkaisee aikeiden ristiriidat ja tapahtumien seuraukset. Kaikkien ei tarvitse saada puheenvuoroa samassa hetkessä. |
| Roolipeli | Pelaajan toiminta menee suoraan kertojalle. Muut läsnä olevat hahmot tekevät omat ratkaisunsa. | Säilyttää pelaajan yrityksen, ratkaisee seuraukset ja pysähtyy ennen pelaajan seuraavaa merkittävää valintaa. |

Tilaa voi vaihtaa kesken tarinan. Hahmokortin **Pelaa hahmona** siirtää roolipeliin. Hahmon on oltava aktiivisessa kohtauksessa ja toimintakykyinen.

- **Yksityinen aikomus** antaa pelaajan suunnitelman kertojalle, ei muiden hahmojen syötteeseen.
- **Muuta maailmaa** antaa seuraavan vuoron maailmanmuutoksen kertojalle. Hahmot saavat muutoksen havaittavat seuraukset seuraaviin päätöksiinsä, eivät alkuperäistä ohjetta.
- Romaanissa ja simulaatiossa voi valita rajatun automaattijatkon, enintään kymmenen jatkoa. Jokainen jatko voi tehdä maksullisia mallikutsuja.
- **Keskeytä** lopettaa keskeneräisen työn. Jo hyväksyttyä vuoroa se ei peruuta.
- **Näytä salaisuudet** avaa ohjaajan ja hahmojen yksityisiä tietoja. Se on lukukokemuksen valinta, ei käyttäjien välinen käyttöoikeusraja.

## Lukunäkymät Ja Kehittyvä Juoni

Lukutilan näkökulmavalinta erottaa kertojan kaikkitietävän proosan ja valitun pelaajahahmon rajatun proosan. Roolipelissä näytetään rajattu näkökulma; romaani- tai simulaatiotilaan siirtyminen avaa kertojanäkymän. Kertojan proosaan voidaan sisällyttää hahmojen palauttamia ajatuksia. Pelaajaversio muodostetaan erillisellä mallikutsulla vain hahmon omista tiedoista ja todistetuista havainnoista, ei kaikkitietävää proosaa suodattamalla. Kanoninen vuoro tallennetaan ensin; rajattu näkökulma tuotetaan tämän jälkeen erikseen. Näkökulmakutsun virhe ei peruuta vuoroa: lukutilassa näytetään `view_failed`-tila ja näkökulman voi yrittää muodostaa uudelleen vuoron toiminnosta. Tietoraja riippuu edelleen mallin havaintomerkintöjen oikeellisuudesta, eikä ole eri käyttäjien käyttöoikeusraja.

Näkökulmavalinta ja sisällysluettelo pysyvät näkyvissä lukunäkymän yläreunassa myös tekstiä vieritettäessä. Sisällysluettelo siirtyy lukuotsikoihin. Proosan jäljessä on vakionkorkuinen 320 pikselin alue jatkamisen tyhjätilalle, työvaiheille ja valinnoille; pitkät sisällöt vierivät sen sisällä. Oman jatkon editori avautuu tarvittaessa tätä korkeammaksi. Hahmokortin muistijäljet vierivät omassa, enintään 240 pikselin listassaan, johon voi kohdistaa myös näppäimistöllä. Vuorojen ja API-lokin aikaleimat näytetään tietokoneen eli selaimen paikallisella aikavyöhykkeellä, kesäaika huomioiden; tietokannan aikaleimat säilyvät UTC-ajassa. Kertaukset avautuvat valitun näkökulman tietojen mukaan; pelaajan otsikotkaan eivät saa paljastaa salaisuuksia. Vanhoille vuoroille tai myöhemmin valitulle eri pelaajahahmolle ei arvata rajattua versiota, vaan puuttuva näkökulma merkitään. Jos viimeisin näkökulma puuttuu, pelaajan lukunäkymässä voi valita **Muodosta hahmon tilannekertaus**. Maksullisen mallikutsun vahvistus tehdään erikseen. Yksi looginen mallikutsu muodostaa lyhyen nykyhetken kertauksen vain hahmon omista muistoista, havainnoista ja viimeisestä aikeesta, ei kaikkitietävästä proosasta. Kertaus tallennetaan erillisenä lukunäkymän lisänä; vanhoja vuoroja, tapahtumia tai muisteja ei muuteta. Sama kertaus käytetään uudelleen niin kauan kuin tarinan revisio säilyy ennallaan; muuttunut tila piilottaa vanhan kertauksen. Kesken olevan tai epäonnistuneen varsinaisen näkökulmakutsun yhteydessä käytetään sen uusintatoimintoa. Pelaajaversion proosaa ei voi muokata kertojan tekstieditorilla. Tekstikorjaus ei automaattisesti kirjoita rajattua versiota uudelleen. TXT/Markdown-vienti on edelleen kertojan proosa.

Kertojan maailmanäkymä näyttää myös esineet (haltija tai sijainti ja tila) sekä suunnatut hahmosuhteet (asenne, luottamus ja yhteenveto). Ne ovat tässä vaiheessa vain luettavissa; salaisuuksien editorin tallennus säilyttää ne ennallaan. Näkymä edellyttää **Näytä salaisuudet** -valintaa eikä ole käytettävissä roolipelissä, koska kaikkien esineiden sijainnit ja muiden hahmojen asenteet voivat paljastaa pelaajalle tuntematonta tietoa.

Salaiset totuudet, kellot ja sivussa toimivat agentit ovat valinnaisia (0–n). Tarinan alustus voi luoda niitä asetelman tai käyttäjän toiveen perusteella; tyhjää tarinaraamattua ei täytetä automaattisesti. Kertoja voi lisätä perusteltuja uusia rakenteita vuoron `bible_additions`-kentässä, ja käyttäjä voi muokata niitä tarinaraamatun editorissa. Uusi salaisuus alkaa piilossa eikä korvaa olemassa olevaa totuutta. Paljastukset etenevät `hidden` → `hinted` → `revealed`; hahmo saa vain oman havaintonsa, ei salaisen faktan koko tekstiä. Löytöreitin muutos viittaa sitä aiheuttaneeseen tapahtumaan. Olemassa olevat kellot etenevät kerran vuorossa, ja niiden päättymisen seuraus laukeaa kerran. Rauhallisen tarinan ei tarvitse sisältää salaisuuksia, uhkia tai aikapainetta.

Mallivastaukset ovat vaihekohtaisia. Hahmo palauttaa yhden toimintayrityksen, puheen ja yksityisen ajatuksen ilman rinnakkaisia yhteensopivuuskenttiä. Suunnittelija ei palauta kohtauksen siirtoa tai hahmopäivityksiä. Ratkaisija palauttaa vuoron `recap_delta`-tekstin ja jatkuvuuden faktojen sekä juonilankojen lisäykset/poistot, ei koko historiaa uudelleen. Ohjelma yhdistää muutokset aiempaan tilaan ja tiivistää pitkän tapahtumahistorian erillisellä mallikutsulla. Tilamuutosten `event_id`-viitteet tarkistetaan ennen tallennusta; vapaaehtoinen teko tai valtuutettu rutiini viittaa tämän vuoron täsmälliseen `intent_id`-aikeeseen. Paikan tunniste ja nimi kulkevat erikseen `location: {event_id, id, name}` -rakenteessa.

## Simulaation tilasopimus ja orkestrointi

Uudistuksen määrittely ja hyväksymiskriteerit ovat [simulaatiosuunnitelmassa](SUUNNITELMA_SIMULAATIO.md). Hahmon tuntematon sijainti (`location_id: null`) tarkoittaa poissaoloa paikallisesta kohtauksesta. Piilossaolo on erillinen ominaisuus: paikalla oleva piiloutunut hahmo ei saa paljastua muiden hahmojen nimilistasta. Etähavainnot edellyttävät erikseen määriteltyä tiedonkulun lähdettä; ne eivät seuraa automaattisesti tuntemattomasta sijainnista.

Kertojan luomisvapautta ei rajata valmiiseen paikkaluetteloon. Uusi maailmanasia ja siihen viittaava seuraus validoidaan yhtenä vastauskokonaisuutena. Kenttäkohtainen tilasopimus erottaa vapaamuotoisen kuvauksen tietokantaan tallennettavista tunnisteista, arvoista ja tapahtumaviitteistä. Virheellisen ratkaisuvastauksen korjaus säilyttää alkuperäiset hahmoaikeet eikä aloita koko kierrosta alusta; korjauskin validoidaan ennen tallennusta.

Suunnittelija voi pyytää `interaction_mode: adaptive` -tilaa ja antaa vain yhden aloitusryhmän (tai ei ryhmää). Kevyt tilanneohjaaja ratkaisee tuoreet aikeet ja valitsee seuraavat ryhmät todellisten tapahtumahavaintojen ja avoimien yritysten perusteella. Uusi havainto mahdollistaa A → B → A -vastauksen ja alussa suunnittelemattoman C:n reaktion; sama hahmo–tapahtuma-heräte käytetään vain kerran. Puuttuva tilakenttä tarkoittaa `static`: vanhat skeemat ja valemallit säilyttävät staattisen yhteensopivuuspolun, jossa ryhmät voivat olla peräkkäisiä tai rinnakkaisia. Rinnakkaiset päätökset saavat lukitun lähtötilan eivätkä näe toistensa uusia vastauksia. Adaptiivinen tila ja eksplisiittiset staattiset ryhmät estävät vanhan lisäreaktiosilmukan.

Tilanneohjaajan rajattu `RelayPermit` voi välittää kokonaisia pelkän puheen repliikkejä ilman uutta ohjaajakutsua. Lupa määrää näkyvät samassa paikassa olevat kuulijat, lähdekuulohavainnon, äänenvoimakkuuden, kanavan ja repliikkikaton. **Fast path luottaa ohjaajan oikeaan semanttiseen puhe-, yksityisyys- ja keskeytysarvioon; hahmon `resolution_hint` ja kenttätarkistukset eivät todista pelkkää puhetta.** Luvaton tai muuttunut tilanne palauttaa ohjaajalle. Yksityisajatuksia tai avoimen yrityksen varmaa lopputulosta ei välitetä muille hahmoille.

Adaptiivisen ehdokasvaiheen rajat koskevat hahmopäätöksiä, ohjaajakutsuja, hahmokohtaisia päätöksiä, aikaa ja tokenvarauksia. Alustava tokenbudjetti on 48000 varattua tokenia: UTF-8-tavumäärä/3 arvioi viestisyötteen ja skeeman, ja lisäksi varataan tuotoksen yläraja. Estimaatti ei ole todellisten tokenien ehdoton yläraja, laskutettu käyttö tai koko pyynnön raja. Suunnittelu, loppuproosa ja erillinen pelaajanäkymä jäävät rajojen ulkopuolelle. `frame_exhausted` pysäyttää ilman automaattista uudelleensuunnittelua. Keskeytyksen recovery säilyttää ehdokasketjun, rajakohdan odottavat herätteet ja seuraavan ryhmän sekä estää saman pyynnön aikeiden uusinnan, mutta ei jatka autonomisesti palvelimen uudelleenkäynnistyksen jälkeen.

Välitapahtumat, jatkuvuus, yritystulokset, sitoumukset ja aika yhdistetään järjestyksessä. Erillinen `InteractionProse`-skeema ei salli tapahtuma- tai tilakenttiä: kirjoittaja kuvaa muuttamattoman ketjun, ja proosa sekä ehdokastila tallentuvat atomisesti. Kertoja sovittaa uuden proosan vahvistettuihin tapahtumiin; vältetty taustaristiriita tallentuu auditointiin eikä kaada vuoroa. Uuden proosan jäljellä oleva ristiriita saa rajatun korjauksen täsmällisellä palautteella. Virheellinen vastaus tai kirjoituspalvelun epäonnistuminen johtaa hyväksyttyjen tapahtumakuvausten varatekstiin, ei uusiin hahmopäätöksiin. Täsmällinen yhteenvetorivi tai valittu reflection-muisti voidaan korjata tapahtumatunnisteilla; muistille käytetään vain hahmon omia havaintoja. Korjaukset tallentuvat atomisesti muutosjälkeen ja palautuvat rollbackissa. Vanha proosa ja belief-muistit säilyvät. Tämä koskee adaptiivista kirjoituspolkua, ei staattista yhteensopivuusratkaisijaa; koko historian tai semanttisen oikeellisuuden takuuta ei ole. Uusia maailmanasioita ja hahmoja voidaan luoda ohjaajavaiheessa, ei proosavaiheessa; hahmoluonnin omat testit puuttuvat vielä. Provider-reitityksen perustestit läpäisivät 10/10 ja uusi situation-kohtainen testi erikseen 1/1. Automaattitestit eivät osoita kirjallista laatua tai kustannussäästöä. Tarkempi toteutus ja rajoitukset: [vuorovaikutussuunnitelma](SUUNNITELMA_VUOROVAIKUTUS.md).

Juoniohjaus valitaan tarinalle kolmesta tasosta: **Mukautuva**, **Tasapainoinen** tai **Vahvasti ohjattu**. Se ohjaa maailman painetta ja suunnitelman sitkeyttä, ei pelaajan vapaaehtoisia valintoja. Yritysten tulokset, sitoumukset ja kulunut aika säilyvät jatkuvuudessa. Pelaajan menetettyä toimintamahdollisuutensa jatkovalinnat voivat päättää tarinan, vaihtaa kelvolliseen hahmoon tai luoda uudelleenyrityksen palautuspisteestä erilliseen tarinaan. Alkuperäisen tarinan historiaa ei kirjoiteta uudelleen.

Vanhojen tuntemattomien sijaintien muunnos edellyttää esikatselua, eksplisiittistä valintaa ja ajantasaista revisiota. Älä hyväksy automaattisesti kaikkia ehdotuksia: vanhan tyhjän sijainnin merkitys voi olla epäselvä.

Tavanomaiset mallikutsut säilyvät käytössä. Realtime-yhteyksiä ei avata. [Realtime-jatkosuunnitelma](SUUNNITELMA_REALTIME.md) kuvaa erilliset mallirajoitukset ja päätepisteet, hahmokohtaisten istuntojen orkestroinnin, pelaajan keskeytykset sekä token- ja välimuistilaskutuksen. Avoin yhteys ei tarkoita, että koko kasvava keskustelukonteksti laskutettaisiin vain kerran.

## Tekstimuokkaus

Vuoron kynäpainike tai tekstin tuplaklikkaus avaa muokkauksen suoraan lukutekstiin. Fontti säilyy samana ja sivumerkki ilmaisee muokkaustilan. Toiseen kohtaan siirtyminen tallentaa tekstikorjauksen ja vientitiedostot ilman mallikutsuja. Virheessä teksti jää muokkaustilaan eikä katoa. Korjattu tuore proosa menee kertojan seuraavan vuoron kontekstiin. Revision tarkistus estää vanhentuneen tallennuksen. Vanha ja uusi proosa säilyvät `prose_edits`-historiassa; historian palautusnäkymää ei vielä ole.

**Tekstimuokkaus ei muuta tapahtumia, havaintoja, muisteja tai jatkuvuustiivistelmää.** Käytä sitä oikolukuun ja tyyliin. Juonimuutosten automaattista tilasynkronointia ei vielä ole; `sync_state: true` hylätään tallentamatta tekstiä. Myös vanhoja kappaleita voi korjata tekstinä, mutta muutokset eivät kirjoita myöhempien vuorojen tilaa uudelleen.

**Oma jatkokappale** lisää uuden, sellaisenaan säilytettävän tekstin tarinan loppuun. **Analysoi muutokset** käyttää kertojamallia ehdottamaan tapahtumat, niiden havaitsijat, hahmotilat ja jatkuvuuden. Tarkista ehdotus ja valitse **Hyväksy ja tallenna**; hyväksyntä ei tee uutta mallikutsua. Ennen hyväksyntää tarinan tila ei muutu. Peruuttaminen säilyttää tekstin lomakkeessa mutta hylkää esikatselun. Esikatselu vanhenee 30 minuutissa tai palvelimen uudelleenkäynnistyksessä; välissä muuttunut tarina vaatii uuden analyysin. Hyväksytty kappale voidaan kumota kuten uusi generoitu vuoro. Kappaleen enimmäispituus on 20 000 merkkiä. Tämä ensimmäinen versio ei luo uusia hahmoja: lisää tarvittavat hahmot ennen analyysiä.

Tapahtumien ja havaitsijoiden semanttinen oikeellisuus on edelleen mallin ehdotus, jonka käyttäjä tarkistaa. Tuntemattomat hahmotunnisteet hylätään. Vanhojen kappaleiden sisällöllinen sovitus ei kuulu tähän toimintoon. Tavallinen monirivinen jatkosyöte on eri asia: se antaa kertojalle muotoiltavan luonnoksen tai toiveen. Generoinnin aikana vuoron syöttökentät lukitaan; epäonnistuminen tai keskeytys ei tyhjennä tekstiä.

Kumoamispainike palauttaa viimeisintä vuoroa edeltäneet hahmot, muistit, havainnot, kohtaukset ja jatkuvuustilan. Se toimii vain uusille vuoroille, joille tämä versio tallensi palautuspisteen. Aloitusta ja vanhoja vuoroja ei voi kumota. Myöhemmät erilliset tilamuutokset estävät kumoamisen; tekstikorjaukset eivät. Mallikuluja ei hyvitetä. Uusi jatko käyttää uutta pyyntötunnistetta. Editorin avaaminen tai kumoaminen pysäyttää automaattijatkon.

## Valinnainen yksi lisäreaktio

**Yksi lisäreaktio tarvittaessa** on vanhan staattisen ryhmättömän yhteensopivuuspolun valinnainen toiminto, oletuksena pois, myös roolipelissä. Pyyntöasetus on `extra_reaction_cycle: true`. Adaptiivinen ketju valitsee reaktiot ilman tätä asetusta; adaptive ja eksplisiittiset päätösryhmät estävät päällekkäisen lisäsyklin. Ratkaisijan uuden, konkreettisen tapahtuman täytyy synnyttää läsnä olevan toimintakykyisen AI-hahmon ratkaisematon merkittävä päätös. Koodi tarkistaa tapahtumaviitteen, uutuuden, etenemisen, havaitsijan ja päätöksentekijän kelpoisuuden; pelkkä mahdollinen reaktio ei riitä. Pelaajan päätös, kohtauksen tai luvun pysäytys, paikanvaihto, puutteellinen kelpoisuus, etenemättömyys, keskeytys ja yhden syklin katto estävät lisäjatkon.

Jatko ohittaa maailmansuunnittelun ja kellojen tikityksen, kutsuu vain kelvolliset AI-hahmot ja ratkaisee niiden tuoreet aikeet. Uutta pelaajan tekoa ei keksitä eikä alkuperäistä tekoa tai maailmanmuutosta toisteta. Molemmat syklit kuuluvat samaan lukittuun, SSE-seurattuun ja keskeytettävään työhön. Lisäkutsut voivat kasvattaa viivettä ja hintaa; tapahtumien ja päätösten semanttinen laatu vaatii oikeiden mallien kokeita.

Syklit tallentuvat erillisinä atomisina vuoroina omine kuitteineen, palautuslokeineen, palautuspisteineen ja pelaajanäkökulmineen. Ensimmäinen kuitti linkitetään jatkokuittiin ennen lisäsyklin alkua. Saman pyynnön uusinta palauttaa tallennetun jatkon tai ensimmäisen vuoron; kesken jäänyttä lisäsykliä ei jatketa automaattisesti. Keskeytys säilyttää tallennetut vuorot. Konkreettisesti etenemätöntä lisävuoroa ei tallenneta. Kumoaminen poistaa viimeisimmän syklin (molemmat poistetaan kahdella kumoamisella), ja kumotun pyynnön uusinta hylätään. Oletuksena pois -pyynnöt säilyttävät vanhan kuittiyhteensopivuuden.

## Vuoron Tietovirta

Staattisella yhteensopivuuspolulla vuoro käyttää rajattua sykliä: ulkoisten maailmanmuutosten suunnitelma, valittujen hahmojen aikeet ja kertojan loppuratkaisu. Suunnittelijan pyytämässä adaptiivisessa tilassa aikeet ja kevyet tilanneratkaisut vuorottelevat havaintopohjaisesti ennen erillistä loppuproosaa. Suunnittelija ei ratkaise hahmojen vapaaehtoisia toimia eikä vanhoja aikomuksia uudelleen. Staattinen ratkaisukutsu tuottaa auktoritatiiviset tapahtumat, toteutuneet tilamuutokset ja proosan samassa vastauksessa. Adaptiivinen tilanneohjaaja ei kirjoita proosaa; loppukirjoittaja kuvaa hyväksytyn tapahtumaketjun erillisellä tapahtumia muuttamattomalla skeemalla. Esineiden hallussapito, suhteet ja hahmojen sijainnit tallennetaan rakenteisina seurauksina atomisesti. Hahmokohtaisia havaintoja käytetään samalla tavalla päätöksissä ja muistien tallennuksessa. Rajattu lukuteksti käyttää vuoron jälkeistä hahmotilaa ja erottaa uskomukset havainnoista. Kehotteet suosivat tekemistä ja seurauksia toistuvan negaatio-kerronnan sijaan, mutta sallivat tilanteeseen vaikuttavat kielteiset havainnot. Suunnitelma soveltaa maailmanmuutokset ennen hahmojen päätöksiä ja välittää vain havaittavat seuraukset. Tilakohtaiset ohjeet painottavat romaanissa kirjailijan suuntaa, simulaatiossa itsenäisiä aikeita ja roolipelissä pelaajan yritystä. Toiveen toteutumista ei selitetä erillisellä ilmoituksella. Suunnittelukutsu lisää yhden mallikutsun vuoroon. Kertojan pysäytyssignaali katkaisee automaattijatkon. Vanhan staattisen polun valinnainen yksi lisäreaktio kuvataan edellä. Oma jatko kirjoitetaan myös tarinan lopussa samassa näkymässä, ei erillisessä pop-upissa.

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

- Tarinalla on oma SQLite-tietokanta `stories/<tunniste>/story.db`; nykyinen kehitysskeema 9 sisältää `story_branches`-perustan ja oletushaaran `main`.
- Rakenteinen maailma tallentaa paikat, esineet, suhteet, salaiset totuudet, kellot, offscreen-agentit ja tapahtumien havaitsijat omiin tauluihinsa; hahmon `location_id` ei ole fyysiseen tilaan upotettua vapaatekstiä.
- Hahmojen muutokset, havainnot, muistot, kohtaus, proosa, jatkuvuustila ja pyyntökuitti hyväksytään yhdessä transaktiossa.
- Tilaversio estää vanhaan tilanteeseen perustuvaa generointia ylikirjoittamasta välissä tehtyä muokkausta.
- Saman pyyntötunnisteen uudelleenlähetys palauttaa hyväksytyn vastauksen. Samaa tunnistetta ei saa käyttää eri sisällölle.
- Selain seuraa palvelimen taustatyötä SSE-yhteydellä, ei sekunnin välein toistuvilla GET-kyselyillä. Työvaiheet näyttää suunnittelun, hahmojen aikeiden valmistumisen ja tallennuksen. SSE-yhteyden katkeaminen ei keskeytä taustatyötä; Palauta yhteys jatkaa saman tunnisteen seurantaa. Sivun lataus ei käynnistä uutta vuoroa. Keskeneräisen työn tunniste säilyy välilehden `sessionStorage`-tilassa. Väli-ilmoitukset ovat palvelimen muistissa; valmis kuitti säilyy tietokannassa.
- Palvelimen uudelleenkäynnistys keskeyttää keskeneräiset työt. Valmiit kuitit säilyvät tietokannassa. **Palauta yhteys** käyttää samaa pyyntöä.
- Katkennut tai virheellinen mallivastaus hylätään. Se ei muutu keksityksi varatarinaksi.
- `story.txt` ja `story.md` ovat tietokannasta muodostettavia vientitiedostoja. Niihin käsin tehdyt muutokset eivät päivitä tarinan tilaa ja korvautuvat seuraavassa viennissä.

Projekti on julkaisematon kehitysversio. Vanhoja tietokantoja ei migroida eikä korjata automaattisesti: luo vanhan skeeman tarinat uudelleen. Tiedostoja ei poisteta automaattisesti. Kumoamispisteet pakataan gzip-muotoon. Älä käytä samaa tarinakansiota samanaikaisesti usealta koneelta pilvisynkronoinnin kautta.

## Yksityisyys Ja Asetukset

### Vuorojen Palautusloki

Ennen vuoron tallennusta koko hyväksyttävä vastaus, tapahtumat, hahmotilat ja lähtötila kirjoitetaan Google Drive -projektikansion ulkopuolelle Windowsin `%LOCALAPPDATA%/Tarinamoottori/recovery`-hakemistoon. Commitin jälkeen vuoro, kuitti ja palautuspiste tarkistetaan uudella tietokantayhteydellä. Valmiiden taustatöiden tilakysely tarkistaa myös levyltä, että vuoro on edelleen olemassa. Puuttuva tallennus ilmoitetaan virheenä, ei onnistumisena.

Palautusloki sisältää salaamatonta tarinatekstiä, hahmojen salaisuuksia ja tilatietoja. Se ei ole API-avainvarasto. Suojaa käyttäjätili ja poista tarpeettomat palautustiedostot erikseen; tarinan poistaminen ei poista tätä paikallista lokia automaattisesti. Aktiivisen SQLite-tietokannan pilvisynkronointi on edelleen riski: suosi paikallista työkansiota ja synkronoi vain suljettuja SQLite-varmuuskopioita. Käytä yhtä palvelinprosessia ja yhtä kirjoittavaa konetta.

Tallennus on paikallinen, mutta pilvimallia käytettäessä sen saamat promptit, hahmotiedot ja tarinakatkelmat lähetetään valitulle palveluntarjoajalle. Sovellus ei siis ole automaattisesti kokonaan paikallinen tai offline.

API-avaimet säilytetään palvelimen `.env`- ja `.provider-profiles.json`-tiedostoissa. Niitä ei palauteta asetusten GET-rajapinnasta eikä tallenneta uusiin selainprofiileihin. Vanhojen selainprofiilien avaimet siirretään palvelimelle ennen niiden poistamista selaintallennuksesta. Tiedostot ovat **salaamattomia** ja Gitin ulkopuolella; suojaa käyttäjätili, kansio ja varmuuskopiot asianmukaisesti.

Sovellus on yhden omistajan paikallinen työkalu: ei kirjautumista, monikäyttäjyyttä tai internet-julkaisua varten. Palvelu hyväksyy localhost-isännät ja torjuu vieraasta selainalkuperästä tulevat pyynnöt. Tarina- ja prompttipolut on rajattu omiin hakemistoihinsa. Mallin ja tuontikorttien tekstiä ei suoriteta HTML:nä.

Asetuksissa on yhteinen tarjoaja ja erilliset kertoja- ja hahmomallit. Suunnittelulle, proosalle, aloitukselle, hahmoille ja pelaajanäkymälle on erilliset lämpötila-, token- ja päättelyasetukset (`DIRECTOR_PLAN_*`, `PROSE_*`, `STORY_INIT_*`, `CHARACTER_*`, `PLAYER_VIEW_*`). Koodi tukee xAI-, Azure-, Gemini-, OpenAI-, OpenRouter- ja OpenAI-yhteensopivia rajapintoja; selainprofiilien näkymä kattaa xAI:n, Azuren ja Google AI Studion. Gemini käyttää Googlen OpenAI-yhteensopivaa tekstirajapintaa. Aseta `GEMINI_API_KEY` ja `LLM_PROVIDER=gemini` tai luo Google-profiili selaimessa. Mallinimet ovat muokattavia. Gemini 2.5 Flash-Liten mallitunniste on `gemini-2.5-flash-lite`; Googlen nykyisen dokumentaation mukaan 2.5-mallit ovat rajattuja aiemmille käyttäjille. Uuden profiilin oletukset ovat dokumentoidut uudemmat Flash ja Flash-Lite. Katso [malliarvio](ARVIO_GEMINI.md). Muut tarjoajat voi määrittää ympäristöasetuksilla.

API-loki sisältää syöte-, vastaus-, päättely- ja välimuistitokenit silloin, kun palvelu ilmoittaa ne. Välimuistitokenit ovat syötetokenien osajoukko. Hinta näytetään vain palvelun raportoimana, ja kooste ilmoittaa kuinka monesta kutsusta hintatieto on saatavilla. Täydet promptit ja vastaukset voi tallentaa gzip-pakattuina paikalliseen `api_calls`-tauluun asettamalla `LLM_CALL_CONTENT_LOGGING=true`; ominaisuus on oletuksena pois, koska sisältö sisältää yksityisiä tietoja. Lokien **Sisältö**-toiminto avaa yksittäisen kutsun pyynnön ja vastauksen. `LLM_CALL_RETENTION_DAYS` (oletus 30) määrittää lokien säilytysajan.

`MAX_INPUT_TOKENS` rajoittaa syötteen arvioitua kokoa (oletus 64000). Arvio on merkkimääräpohjainen, ei mallin tarkka tokenisaattori. Ylitys keskeyttää pyynnön ennen verkkokutsua eikä leikkaa sisältöä hiljaisesti.

## Projektin Rakenne

### Azure-rajapinnan valinta

Valitse asetuksista Azure-portaalin koodiesimerkin URL-muoto. **OpenAI v1** käyttää osoitetta `https://<resurssi>.services.ai.azure.com/openai/v1/` tai `https://<resurssi>.openai.azure.com/openai/v1/`. Poista viimeinen `responses`: sovellus käyttää Chat Completions -rajapintaa, ei Responses API:a. Selain poistaa kopioidun `responses`- tai `chat/completions`-päätteen tallennuksessa. API-version ja saman deploymentin kentät piilotetaan v1-tilassa. Malli-kenttiin tulee Azure-portaalin deployment-nimi.

**Deployment-rajapinta** käyttää resurssin juuriosoitetta `https://<resurssi>.openai.azure.com/` ja päivämäärämuotoista `api-version`-arvoa. **Sama deployment kertojalle ja hahmoille** on valinnainen: tyhjänä käytetään roolien omia Malli-kenttiä. Sovellus muodostaa kutsupolun itse. 404 voi tarkoittaa väärää resurssia, URL-muotoa tai deployment-nimeä.

Tokenkentät rajaavat yhden vastauksen budjettia, eivät proosan tavoitepituutta tai syötteen kontekstia. Oletusbudjetti on kertojalle ja proosalle 128 000 tokenia sekä hahmoille 64 000. Rakenteisten suunnitelma- ja pelaajanäkymävastausten oletus on 64 000. Tallennetut selainprofiilit ja `.env`-arvot ohittavat oletukset, eikä niitä muuteta automaattisesti. Mallin oma vastausraja pätee aina. Azure v1 käyttää `max_completion_tokens`-parametria, joka sisältää mallista riippuen myös päättelyn. Muiden tarjoajien parametrit pysyvät tarjoajakohtaisina. Katkeamisen automaattinen uusintayritys voi kasvattaa pyydettyä budjettia: asetus ei ole ehdoton kustannuskatto.

- `engine/story_engine.py`: tilakohtainen vuoroprosessi ja hyväksyminen.
- `engine/director_agent.py`, `engine/character_agent.py`: agenttien syötteet ja validoidut vastaukset.
- `database/turn_store.py`: vuorotransaktio, havainnot, jatkuvuus ja pyyntökuitit.
- `database/db.py`: muut tietokantatoiminnot, muistihaku ja nykyisen skeeman alustus.
- `core/schemas.py`: mallivastausten tietosopimukset.
- `core/llm_client.py`, `core/providers/`: mallirajapinnat, vastaukset ja lokitus.
- `core/profile_store.py`: palvelinpuolen avainprofiilit.
- `web/api.py`: paikallinen API ja taustavuorotyöt.
- `web/static/app.js`: tarina-, hahmo-, promptti- ja asetusnäkymät.
- `web/static/turns.js`: vuoropyyntöjen seuranta, palautuminen ja keskeyttäminen.
- `prompts/`: oletuspromptit; `prompts/custom/`: omat ohitukset.

Vanhoja kronikoitsija-, aistisuodatin- ja valvojatoimintoja on edelleen lähdekoodissa yhteensopivuutta varten. Aktiivinen vuoropolku käyttää tapahtumia ja kertojan jatkuvuustilaa, ei erillistä kronikoitsija- tai valvojakutsua joka neljännellä tai kuudennella vuorolla. Vanhat API-tilanimet muunnetaan: `reader -> novel`, `player -> roleplay`, `director -> simulation`.

## Testit

Kehitystyössä ajetaan vain muutokseen liittyvät testimetodit, luokat tai moduulit, samassa komennossa. Esimerkiksi tietokannan skeematarkistuksen muutokselle:

```powershell
python -m unittest -v tests.test_engine.StorageTests.test_current_schema_initialization_is_repeatable tests.test_engine.StorageTests.test_legacy_database_is_rejected_without_migration tests.test_engine.StorageTests.test_incomplete_database_is_rejected_without_repair
```

Pääagentin raportoima lopullinen kohdennettu varmennus:

| Ajo / valitsin | Tulos | Runner / seinäkello |
| --- | --- | --- |
| `tests.test_adaptive_interaction` (valmis moduuli) | 18/18 läpäisi | 5.331 s / 5.764 s |
| Adaptiivinen vuorovaikutus, simulaatio ja tilasopimus (ennen moduulin kolmea uusinta testiä; valitsimet alla) | 26/26 läpäisi | 8.682 s / 9.101 s |
| Provider-/Azure-/API-reitityksen perustestit (valitsimet alla) | 10/10 läpäisi | 0.714 s / 2.909 s |
| `node --test tests\test_simulation_frontend.cjs tests\test_frontend.cjs` | 10/10 läpäisi | 0.440 s / 0.525 s |

Yhdistelmäajon valitsimet: `tests.test_adaptive_interaction`, `tests.test_simulation_plan.SimulationUnitTests`, `tests.test_simulation_plan.SimulationStorageTests.test_integrated_intermediate_resolution_is_atomic`, `tests.test_simulation_plan.SimulationStorageTests.test_same_response_creation_elapsed_attempt_and_commitment`, `tests.test_turn_contract.TurnContractTests.test_history_compression_is_separate_from_resolver` ja `tests.test_turn_contract.TurnContractTests.test_expired_clock_fires_once_without_omniscient_observers`.

Reitityksen perustestit: `tests.test_engine.ProviderTests`, `tests.test_engine.AzureTransportTests`, `tests.test_api.ApiTests.test_profile_secrets_are_not_returned` ja `tests.test_api.ApiTests.test_gemini_profile_key_stays_server_side`. Situation-roolin oma malli ja oletukset sisältyvät valmiin adaptiivisen moduulin testinäyttöön.

Aiemmat regressiot korjattiin; yllä olevat ajot läpäisivät, mutta koko projektin regressioajoa ei väitetä eikä päällekkäisiä testejä lasketa yhteen. Tallennustestien budjetti on eristetty 48000:een käyttäjän `.env`-asetuksista. Moduuli kattaa keruunaikaiset julkiset SSE-vaiheet, tapahtumaketjun säilymisen proosan uusinnassa, keskeytyksen siivouksen ja pelaajan aie → NPC → uusi pelaajavalinta -rajan ilman generoituja pelaajavastauksia sekä odottavan reaktion tallennuksen. Adaptiivinen peräkkäinen ryhmä sisältää vain yhden toimijan; useat toimijat sallitaan vain rinnakkaisessa lukitun lähtöhetken ryhmässä. Loppuproosa ei palauta tapahtuma-/tilakenttiä ja säilyttää vain sävyohjauksen, ei koko ratkaisijan ohjeistoa. Uusien hahmojen omat testit ja oikeiden mallien laatu-/säästövertailut puuttuvat edelleen. Dokumentointimuutoksessa testejä ei ajeta.

Kokonainen testiluokka: `python -m unittest -v tests.test_engine.StorageTests`. Moduuli: `python -m unittest -v tests.test_turn_contract`. Windowsissa virtuaaliympäristön tulkkia voi käyttää suoraan: `& .\venv\Scripts\python.exe -m unittest -v <testit>`.

Pääagentti koordinoi testauksen: aliagentit ilmoittavat tarvittavat testit eivätkä aja samoja tarkistuksia uudestaan ilman erillistä toimeksiantoa. Testitulos raportoidaan valitsimineen ja kestoineen. Testiä muutetaan vain, jos sen odotus on todistetusti väärä tai vaatimus muuttuu, ei virheen peittämiseksi. Koko testipaketti ajetaan erillisessä sovitussa regressiotarkistuksessa tai kun kohdennetut tulokset osoittavat laajemman tarpeen:

```powershell
python -m unittest discover -s tests -v
```

Skeeman vertailurakenne välimuistitetaan SQL-sisällön perusteella. Jo tarkistettu tietokanta tarvitsee vain kevyen skeema- ja versiokyselyn: tavalliset tietomuutokset eivät aiheuta täyttä uusintatarkistusta. Skeeman, version, skeematiedoston tai tietokantatiedoston identiteetin muutos käynnistää täyden tarkistuksen. Vanhojen ja puutteellisten tietokantojen hylkäystestit ovat edelleen tarpeellisia; ne eivät edellytä vanhojen skeemojen tukemista.

Ympäristö: käytä projektin virtuaaliympäristöä ja paikallista SSD-levyä. Pilvisynkronoitu projektikansio voi hidastaa lähdekoodin ja pakettien lukua; paikallinen klooni ja paikallinen virtuaaliympäristö välttävät tämän. `tempfile`-testit käyttävät järjestelmän väliaikaiskansiota: pidä `TEMP`/`TMP` paikallisella levyllä. Älä kytke tietoturvaohjelmistoa pois päältä. Mahdollinen tarkistuskuorma pitää mitata ennen organisaation hyväksymiä rajattuja muutoksia. Testiluokat muuttavat yhteistä `settings.STORIES_DIR`-asetusta, joten niitä ei pidä rinnakkaistaa samassa prosessissa; mahdollinen rinnakkaisajo vaatii erilliset prosessit ja tallennuskansiot.

Käyttöliittymän aikaleima- ja rakenne-regressiot voi ajaa erikseen Node.js:llä (vain testaukseen, ei sovelluksen käyttöön):

```powershell
node --test tests\test_frontend.cjs tests\test_bible_frontend.cjs tests\test_simulation_frontend.cjs
```

Testit käyttävät väliaikaisia kansioita ja valemalleja, eivät käyttäjän tarinoita tai oikeita mallikutsuja. Ne kattavat muun muassa tietorajauksen, tilojen erot, pelaajan toiminnan, tallennuksen eheyden, uudelleenlähetyksen, muokkausristiriidat, muistinhaun, skeeman validoinnin, taustatyöt ja polkurajaukset. Testit ovat rajallisia eivätkä kata kaikkia käyttötilanteita.

Käyttöliittymää on kokeiltu kehitystyön yhteydessä työpöytä- ja puhelinleveydellä, mutta kattavaa selain- tai käyttäjätestausta ei ole tehty. Kirjallisen laadun ja pitkien tarinoiden muistamisen arviointi edellyttää erillisiä oikeiden mallien kokeiluja.

## Nykyiset Rajat

Havaitsijoiden rajaus estää suoran yhteisen proosakontekstin vuodon. Kertoja on silti kielimalli: se voi kirjoittaa virheellisen havaintokuvauksen tai ristiriitaisen seurauksen. Skeematarkistus ei todista tapahtumien semanttista oikeellisuutta. Päätöskohtien ja kappaleiden rytmitys riippuu mallista ja prompteista.

Proosamuutosten automaattinen tilasynkronointi, kuvien generointi, Realtime-istunnot ja usean palvelinprosessin työjono eivät kuulu tähän toteutukseen. Uudelleenyrityshaara ei ole yleiskäyttöinen haarojen yhdistämis- tai historian uudelleenkirjoitustoiminto. Kuvituspromptteja voidaan edelleen tuottaa. Näitä ominaisuuksia kannattaa lisätä hyväksytyn tapahtuma- ja tilamallin päälle, ei ohittamalla sitä.