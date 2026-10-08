# Suunnitelma: adaptiivinen vuorovaikutus ja kevyt tilanneohjaaja

Päiväys 8.10.2026. Adaptiivinen vuorovaikutus on toteutettu suunnittelijan pyytämänä tilana; puuttuva `interaction_mode` säilyttää staattisen yhteensopivuuspolun vanhoille skeemoille ja valemalleille. Perustuu kutsujen 32–42 analyysiin ja tavoitteeseen elävästä vuorovaikutuksesta. Tavanomaiset mallikutsut säilyvät käytössä; Realtimea ei toteuteta. Lopullinen kohdennettu yhdistelmäajo läpäisi 26/26 testiä; provider-reitityksen perustestit läpäisivät 10/10 ja uusi situation-kohtainen testi erikseen 1/1. Kirjallista laatua tai kustannussäästöä ei väitetä.

## 1. Toteutettu toimintatapa ja staattinen yhteensopivuus

`PlannerResponse.interaction_mode` on `static` tai `adaptive`, oletuksena `static`. Adaptiivisessa tilassa suunnittelija antaa vain yhden aloitusryhmän (tai ei ryhmää); useampi hylätään. `collect_adaptive` ratkaisee tuoreet aikeet pienellä `SituationResponse`-skeemalla. Tilanneohjaaja valitsee seuraavan ryhmän vastaanottajakohtaisten tapahtumahavaintojen ja avoimien yritysten perusteella. Uusi havainto mahdollistaa A → B → A -ketjun ja alussa suunnittelemattoman C:n reaktion. Sama `(character_id, event_id)`-heräte käytetään vain kerran, eikä ryhmässä ole samaa hahmoa kahdesti.

Adaptiivisen ketjun välitapahtumat, jatkuvuus, yritystulokset, sitoumukset ja aika kootaan järjestyksessä. Lopullinen `InteractionProse` ei salli tapahtuma- tai tilakenttiä. Se sisältää kerronnan lisäksi ei-estävät lähderistiriitahavainnot ja rajatut johdetun tiedon korjausehdotukset. Vahvistetut tapahtumat ovat vanhaa proosaa, yhteenvetoja ja hahmon tulkintoja vahvempia lähteitä. Kertoja korjaa uuden kuvauksen jo samassa vastauksessa; vanhaa proosaa ei kirjoiteta uudelleen.

`consistency_issues` koskee vain uuden proosan jäljellä olevia virheitä; `source_issues` tallentuu auditointiin eikä kaada vuoroa. Enintään kaksi proosayritystä saa saman hyväksytyn ketjun ja täsmällisen palautteen. Virheellinen JSON, tyhjä proosa, toistuva ristiriita tai kirjoituspalvelun virhe johtaa hyväksyttyjen tapahtumakuvausten varatekstiin, ei hahmopäätösten tai tilanteen uudelleenarpomiseen. Keskeytys sekä tallennus-/tietorajavirheet säilyvät virheinä.

Kertoja voi ehdottaa täsmälleen yhden olemassa olevan yhteenvetorivin tai syötteeseen valitun reflection-muistin korjausta tapahtumatunnisteilla. Ohjelma muodostaa korvaustekstin itse tapahtumista; muistille kelpaavat vain kyseisen hahmon omat havainnot. Belief- ja observation-muisteja ei muokata. Korjaukset, hylkäykset sekä vanha/uusi teksti tallentuvat vuoroauditointiin samassa transaktiossa; rollback palauttaa alkuperäiset muistit ja yhteenvedon. Saman virhemuistin täsmällistä kopiota ei tallenneta uutena muistikuvana. Enintään 100 tuoretta historiallista tapahtumaa ja päätöksissä käytetyt reflection-muistit annetaan korjauksen lähteiksi: koko historian korjausta tai semanttista virheettömyyttä ei taata. Malli päättää korjaustarpeen; ohjelma varmentaa lähteet ja tietorajat, ei luonnollisen kielen merkitystä. Staattinen yhteensopivuuspolku ei käytä tätä erillistä kirjoitusmenettelyä.

Lähteet: [adaptiivinen ajuri](engine/adaptive_interaction.py), [tilanneohjaaja](engine/situation_agent.py), [historian yhdistäminen](engine/interaction_history.py), [tokenvaraukset](engine/interaction_llm.py), [skeemat](core/schemas.py) ja [vuoromoottori](engine/story_engine.py).

### Automaattikorjauksen kohdennettu validointi 8.10.2026

Loppuajon valitsimet: `tests.test_adaptive_interaction`, `tests.test_engine.StorageTests.test_editor_and_rollback_restore_state`, `tests.test_engine.StorageTests.test_incomplete_schema_is_rejected_before_database_creation`, `tests.test_turn_contract.TurnContractTests.test_resolved_possession_persists_atomically`. **26/26 läpäisi**, unittest 19.285 s / seinäkello 19.794 s. Adaptiivinen moduuli sisältää 23 testiä. Uusi näyttö kattaa lähdehuomautuksen ilman uusintaa, täsmällisen palautteen, varatekstin ja saman pyynnön replayn, virheellisen/tyhjän vastauksen, palveluvirheen, keskeytyksen, lähdekorjauksen auditoinnin ja rollbackin, vanhan proosan säilymisen sekä havaitsemattomien tapahtumien ja belief-muistikorjauksen hylkäyksen. Vain valemalleja ja väliaikaista tallennusta käytettiin; kirjallista laatua ja semanttista korjaustarvetta ei todisteta.

### Lähtötilanteen analyysi ennen adaptiivista toteutusta

Seuraavat rajoitukset kuvaavat aiempaa staattista ryhmäajoa ja analysoituja kutsuja, eivät adaptiivisen tilan nykyisiä ominaisuuksia.

Nykyinen suunnittelija palauttaa koko päätösryhmälistan ennen hahmokutsuja. Ryhmä määrää hahmot, niiden järjestyksen tai rinnakkaisuuden ja requires_resolved_outcome-lipun. collect_groups käy tämän listan läpi eikä lisää uusia päätöksentekijöitä väliratkaisun perusteella. Väliratkaisu voi keskeyttää ketjun, ja muuttunut läsnäolo tai toimintakyky voi estää kutsun.

Hahmo palauttaa public_start-kentässä ehdotuksen havaittavasta aloituksesta sekä observer_ids- ja modality-kentät. Ohjelma rajaa listaa sijainnin, toimintakyvyn ja piilossaolon perusteella. Hahmo ei palauta ratkaisuvaatimuslippua. Ohjelma ei tulkitse toimintatekstin merkitystä päättääkseen väliratkaisusta: suunnittelijan aiemmin antama ryhmälippu ratkaisee sen. Pelkkä speech-kenttä ei automaattisesti välity seuraavalle hahmolle, jos public_start puuttuu.

Staattisessa `collect_groups`-polussa kukin hahmo saa päättää vain kerran yhdessä rajatussa kierroksessa. Tämä estää luontevan A → B → A -vastauksen saman jatkopyynnön sisällä. Simulaation oletusryhmä voi kutsua kaikki läsnäolijat rinnakkain, mutta eksplisiittinen suunnitelma rajoittaa ryhmät ennalta. Riippuvuuslista kuvaa järjestystä, ei tapahtumista aktivoituvaa reaktiovalintaa.

Väliratkaisu käyttää nykyisin samaa mallia ja täyttä proosaskeemaa kuin lopullinen kerronta. Kutsussa 40 tämä vei noin 26 sekuntia ja 13 284 tokenia. Lopullinen kerronta sai välituloksen laajana pakettina uudelleen. Välituloksen tapahtumat, sitoumukset, yritystulokset ja aika yhdistetään; sen proosaa ja jatkuvuusdeltaa ei yhdistetä erikseen. Tämä voi jättää hyväksytyn välitapahtuman pois kirjallisesta historiasta tai yhteenvedosta.

Lähdekohteet: [skeemat](core/schemas.py), [ryhmäajuri](engine/simulation_contract.py), [vuoromoottori](engine/story_engine.py), [kertoja](engine/director_agent.py). Liitteen read-only snapshot ei korvaa työtilan nykyistä lähdekoodia: snapshotissa scene-parametria ei käytetä poistuneen hahmon kelpoisuustarkistuksessa, työtilan nykyisessä versiossa käytetään.

## 2. Tavoite ja vastuunjako

- Suunnittelija valitsee tilanteen painotuksen, aloitusryhmän, mahdolliset samanaikaiset valinnat ja pysähtymisehdot; ei kirjoita koko keskustelua ennakkoon.
- Hahmo tekee oman valintansa ja voi ilmaista puheen, havaittavan toiminnan aloituksen, hiljaisuuden tai odottamisen. Hahmo ei vahvista omaa onnistumistaan tai muiden tietoja.
- Kevyt tilanneohjaaja tulkitsee käynnissä olevan tilanteen, ratkaisee tarpeelliset seuraukset ja valitsee seuraavan reaktioryhmän.
- Ohjelma tarkistaa kelpoisuuden, tiedon lähteen, tapahtumaviitteet, yhteisen lähtöhetken, budjetit ja tallennuksen. Se ei ratkaise vapaamuotoisen sisällön semantiikkaa avainsanoilla.
- Proosakirjoittaja kuvaa koko hyväksytyn ketjun kerran. Se ei saa ratkaista jo ratkaistuja tapahtumia uudelleen.

## 3. Hahmovastaus: ehdotus, ei kaikkitietävä päätös

Säilytetään yksityisajatus erillään julkisesta aineistosta. Julkinen ehdotus kuvaa tarvittaessa:

- täsmällinen puhe, vastaanottajan tarkoitettu tunniste ja äänenvoimakkuus;
- havaittava aloitus erillään tavoitellusta lopputuloksesta;
- odotetaanko vastausta tai tapahtuuko toiminta samalla kun muut reagoivat;
- mikä osa edellyttää onnistumista, siirtymää, toisen suostumusta tai ulkoista tapahtumaa;
- hahmon oma arvio keskeytysmahdollisuudesta ja odottamisesta.

Ratkaisun tarpeen arvio on hahmon vihje, ei valtuutus. Hahmo voi olla väärässä ympäristöstä, kuultavuudesta tai muiden mahdollisuuksista. observer_ids muutetaan ehdotetuiksi vastaanottajiksi tai johdetaan ohjaajan havainnoista; hahmolle ei anneta yksinomaista valtaa päättää todellisista havaitsijoista.

Puhe ja toiminnan seuraus ovat eri asioita. Lausuttu ehdotus voi olla toteutunut puhe, vaikka sen tavoite tai yhteinen sopimus jää avoimeksi. Keskeneräisen puheen myöhemmin keskeytyvää loppuosaa ei saa välittää jo kuultuna.

## 4. Kaksi polkua: varmennettu välitys ja tilannetulkinta

### Varmennettu välitys ilman uutta mallikutsua

Ohjelma voi välittää jo hyväksytyn havainnon tai käyttää tilanneohjaajan etukäteen antamaa rajattua välityslupaa. Lupa kattaa esimerkiksi yhden vastaanottajaryhmän tavallisen keskustelun, jossa kuultavuus, osallistujat ja toiminnan keskeytysrajat on jo ratkaistu.

Lupa sisältää osallistujat, lähdetapahtuman, äänenvoimakkuuden, kuulokanavan ja repliikkikaton. Ohjelma tarkistaa kohtauksen sijainnin ja aktiivihahmot sekä rosterin sijainnin, toimintakyvyn ja näkyvyyden muutokset; se ei tunnista kaikkia semanttisia keskeytysriskejä itsenäisesti. Puuttuva lupa tai rikkoutunut rakenteellinen ehto johtaa tilanneohjaajaan; ohjelma ei arvaa turvallisuutta tekstin pituudesta tai toimintaverbistä.

Toteutettu `RelayPermit` rajaa lähdekuulotapahtuman, näkyvät samassa paikassa olevat osallistujat, kiinteän `heard`-kanavan ja äänenvoimakkuuden sekä 1–6 kokonaista repliikkiä. Ohjelma tarkistaa osallistujien läsnäolon, toimintakyvyn ja lähdehavainnot. Fast path hyväksyy yhden puhujan `interaction_kind: speech`-vastauksen vain, kun `resolution_hint` on epätosi, `public_start` puuttuu ja muut lupaehdot täyttyvät. Todelliset kuulijat tulevat luvasta, eivät hahmon ehdotuksesta; muut osallistujat voivat vastata uuteen repliikkiin. Ympäristösignatuurin muutos tai ehtojen rikkoutuminen palauttaa tilanneohjaajalle.

**Rajoitus:** lupa edellyttää ohjaajan oikeaa semanttista arviota pelkästä puheesta, yksityisyydestä ja keskeytysriskistä. Hahmon vihje tai kenttien tarkistus ei todista, ettei vapaamuotoinen toiminta sisällä samanaikaista tekoa. Fast path ei ole itsenäinen semanttinen turvallisuustodistus.

### Tilanneohjaajan rajattu tulkinta

Tarvitaan, kun havaitsijat, onnistuminen, ajoitus, keskeytys, seuraava päätöksentekijä tai maailmanmuutos ovat avoimia. Ohjaaja palauttaa yhdessä pienessä vastauksessa:

- toteutuneet tapahtumat ja vastaanottajakohtaiset havainnot;
- edelleen avoimet yritykset ja niiden ajallinen vaihe;
- tarpeelliset tilamuutokset, yritystulokset, sitoumukset ja kulunut aika;
- seuraavan ryhmän tai rajatun välitysluvan;
- pysähtymisen: pelaajavalinta, tilanne päättynyt, odotus tai aikasiirtymä;
- lyhyen päätösperusteen auditointiin, ei pitkää sisäistä päättelytekstiä.

Ei proosaa, kuvitusprompttia, koko historian palauttamista tai juonisuunnitelman uudelleenkirjoittamista. Nykyinen tilannekonteksti sisältää kehyksen, kohtauksen, tiiviin hahmotilan, tuoreet aikeet, kahden viimeisen välituloksen tapahtumat, avoimet yritykset, sitoumukset, maailman ja budjettiauditin. `frame_exhausted` pysäyttää ketjun; automaattista raskaan suunnittelijan uudelleenkutsua tai lisätietohaun silmukkaa ei ole toteutettu.

## 5. Dynaamiset reaktioryhmät

Ensimmäisen ryhmän jälkeen seuraava valitaan todellisten havaintojen ja avoimien päätösten perusteella. Mahdollisia vastaajia ovat puhuttelun kohde, havaittu toimintaan liittyvä osapuoli tai itsenäistä merkityksellistä aloitetta tekevä paikalla oleva hahmo.

- Sama hahmo voi saada uuden vuoron, kun uusi hänelle kirjattu tapahtumahavainto perustelee uuden valinnan; pelkkä muuttuneen tilanteen kuvaus ei korvaa tapahtumaviitettä.
- Hahmo ei saa uutta yritystä pelkästään siksi, että aiempi epäonnistui tai jäi odottamaan.
- Jokaisella reaktiokutsulla on täsmällinen lähdetapahtuma, jonka hahmo havaitsi. Avoin yritys voi ohjata ohjaajan valintaa, mutta ei korvaa tätä viitettä; jo käytetty hahmo–tapahtuma-pari ei käynnistä samaa reaktiota uudelleen.
- Rinnakkaisen ryhmän kaikki omat näkymät lukitaan ennen ensimmäistä kutsua. Mallikutsun valmistumisjärjestys ei anna etua.
- Ulkopuolinen keskustelija ei saa yksityistä puhetta vain koska voisi haluta reagoida. Ohjaajalle voidaan antaa kaikkitietävä konteksti, hahmolle ei.
- Kaikkien ei tarvitse puhua. Hiljaisuus ja odottaminen ovat oikeita valintoja.
- Pelaajan uusi merkityksellinen päätös katkaisee automaation ja tallentaa ehjän rajakohdan; pelaajan oletusreaktiota ei luoda.

Staattinen ryhmämalli säilyy oletuksena puuttuvalla tilakentällä. Adaptiivisessa tilassa dynaaminen ketju korvaa kerran-per-hahmo-rajoituksen. Adaptiivinen tila ja eksplisiittiset staattiset päätösryhmät estävät päällekkäisen vanhan `extra_reaction_cycle`-silmukan; asetus jää staattiselle ryhmättömälle yhteensopivuuspolulle.

## 6. Budjetit ja luonteva pysähtyminen

Toteutetun ehdokasvaiheen budjetti rajaa hahmopäätökset, ohjaajakutsut, hahmokohtaiset päätökset, kuluneen ajan ja tokenvaraukset. Ne eivät ole koko jatkopyynnön rajoja: suunnittelu, lopullinen proosa ja erillinen pelaajanäkymä jäävät niiden ulkopuolelle. Fast path ei kuluta ohjaajakutsua, mutta hahmopäätös kuuluu budjettiin.

**Tokenrajan merkitys:** alustava budjetti on 48000 varattua tokenia. `InteractionLLM` varaa ennen kutsua UTF-8-tavumäärä/3-estimaatilla arvioidun viestisyötteen ja JSON-skeeman sekä sallitun tuotoksen ylärajan. Estimaatti pyrkii konservatiivisuuteen, mutta ei ole todellisten tokenien ehdoton yläraja. Kertyvä luku ei ole palveluntarjoajan laskuttama tai mitattu toteutunut tokenkäyttö eikä koko pyynnön kustannuskatto. Käyttämätöntä tuotosvarausta ei palauteta. Budjetit eivät osoita kirjallista laatua, nopeutta tai säästöä.

Budjetin täyttyessä tallennetaan viimeinen johdonmukainen tapahtumaraja ja säilytetään avoimet yritykset sekä jatkosuunnitelma. Kustannuksia ei peitetä automaattisilla jatkokutsuilla. Jos kaikki odottavat eikä pelaajasyötettä tarvita, ohjaaja voi siirtää ajan seuraavaan perusteltuun tapahtumaan tai päättää tilanteen ilman keinotekoista lisäuhkaa.

SSE välittää julkiset ohjaaja- ja hahmovaiheet jo adaptiivisen ketjun keruun aikana, ei vasta keruun jälkeen. Yksityisajatuksia ei välitetä roolipeliprogressiin eikä ehdokastekstiä esitetä hyväksyttynä historiana. Kohdennetut testit varmentavat keruunaikaisen välityksen, samat tapahtumat proosan uusinnassa ja keskeytyksen siivouksen. Keskeytys ei peruuta jo tallennettua historiaa takautuvasti. Automaattinen loppuproosa ei palauta tapahtuma- tai tilakenttiä. Sen kehote säilyttää sävyohjauksen, ei koko ratkaisijan ohjeistoa.

## 7. Kevyt malli ja reasoning-asetukset

Tilanneohjaajan `situation`-rooli käyttää omaa `SITUATION_MODEL`-asetusta (tyhjänä hahmomalli), lämpötilaa, päättelyasetusta ja tuotoskattoa. Oletuspäättely on `low`; provider/deployment kulkee olemassa olevan asiakasrakenteen kautta, ei erillisenä Realtime-istuntona. Hahmomallin hyödyntäminen ei tarkoita hahmon roolikehotteen hyödyntämistä. Provider-/Azure-/API-perustestit läpäisivät 10/10 (valitsimet ja ajat alla). Situation-roolin oma malli ja oletukset läpäisivät erillisen 1/1 testin (valitsin ja ajat alla).

Ehdotus ensimmäiseen vertailuun:

- suunnittelija: nykyinen kertojamalli;
- tilanneohjaaja: nykyinen malli low-asetuksella vastaan nopeampi hahmomalli low-asetuksella;
- proosakirjoittaja: nykyinen kertojamalli, yksi kutsu hyväksyttyä ketjua kohti.

Azure-adapteri välittää nyt vain low/medium/high. none jätetään pois eikä se siis tarkoita päättelyn poistamista. none-tuki tarvitsee palveluntarjoaja- ja mallikohtaisen capability-tarkistuksen. Asetuksen puuttuminen, palvelun oletus ja eksplisiittinen none pidetään erillään. Jos palvelu hylkää asetuksen, käyttäjälle ja lokiin kerrotaan toteutunut fallback.

Kutsujen 40 ja 42 päättelytokenit olivat 202 ja 210. Pelkkä reasoningin vähentäminen ei takaa suurta nopeutusta: myös noin 11 000–18 000 syötetokenin kontekstia ja laajaa vastausskeemaa pitää pienentää. Ei luvata nopeutta tai kustannussäästöä ennen mittausta.

## 8. Yksi hyväksytty historia ja lopullinen proosa

Kaikki hyväksytyt aloitukset, ratkaisut ja havainnot muodostavat järjestetyn tapahtumaketjun. Avoin yritys erotetaan faktasta. Jokaisella tapahtumalla on pysyvä tunniste, aikajärjestys ja lähdeaie.

- Väliratkaisun jatkuvuusdelta yhdistetään täsmälleen kerran ennen seuraavan vaiheen kontekstin muodostamista.
- Sitoumusten, yritystulosten ja tilan päivittäminen tehdään tapahtumajärjestyksessä; vanha välitulos ei ylikirjoita uudempaa.
- Lopullinen proosa saa hyväksytyn ketjun tiiviisti ja relevantit tyyli-/historiatiedot, ei koko väliratkaisuvastausten pakettia.
- Proosa kattaa välitapahtumat luontevasti ilman niiden uudelleenratkaisua. Kaiken ei tarvitse näkyä yhtä pitkänä kuvauksena, mutta olennaista seurausta ei saa kadottaa.
- Proosakirjoittaja ei myönnä uusia havaintoja, luo uusia toteutuneita tekoja tai muuta hyväksyttyä onnistumista.
- Uusia maailmanasioita ja hahmoja voidaan luoda tilanneohjaajan vaiheessa saman vastauskokonaisuuden määrittelyillä ja tapahtumaviitteillä. Proosavaihe ei saa lisätä niitä. Uusien hahmojen tuki ei vielä sisällä omia kohdennettuja testejä.
- Proosavastauksen rajattu uusinta saa alkuperäisen hyväksytyn tapahtumaketjun ja edellisen validointivirheen; se ei uusi hahmopäätöksiä tai ratkaise tapahtumia uudelleen.
- Rajattu pelaajanäkymä syntyy samojen tapahtumien omista havainnoista.
- Proosa, tapahtumat ja tila hyväksytään atomisesti. Korjauskutsu ei toista hahmopäätöksiä. Sisältökorjaus, joka muuttaisi jo käytettyjä havaintoja, mitätöi riippuvat ehdokasreaktiot eikä jää muotopaikkaukseksi.
- Ehdokasketjun checkpoint säilyttää aikeet, välitulokset, revision, hahmo-/kohtaus-/jatkuvuustilan, suunnitelman ja budjettiauditin sekä rajakohdan odottavat herätteet ja seuraavan ryhmän. Keskeytys säilyttää ehdokkaan ja estää saman pyynnön aikeiden uusinnan. Tämä on palautumisen aineisto ja replay-esto, ei autonominen jatkaminen palvelimen käynnistyksen jälkeen; automaattista ehdokasketjun jatko-/korjausvirtaa ei ole toteutettu.

## 9. Toteutuksen tila

Pieni tilanneratkaisuskeema, adaptiivinen ryhmäajo, rajattu puhevälitys, ehdokasvaiheen budjetit, historian yhdistäminen ja erillinen tapahtumia muuttamaton proosaskeema on lisätty. Checkpoint tallentaa ehdokkaan ja estää replayn, mutta ei jatka sitä autonomisesti. Seuraava alkuperäinen toteutusjärjestys toimii jatkovarmennuksen listana; julkisten SSE-vaiheiden välitys keruun aikana on nyt kohdennetusti varmennettu, mutta oikeiden mallien vertailua tai täydellistä käyttöliittymän päästä päähän -seurantaa ei väitetä.

1. Korjaa nykyisen välituloksen jatkuvuus- ja proosakattavuus. Testaa hyväksyntä, joka tapahtuu vain välivaiheessa.
2. Erota pieni tilanneratkaisuskeema ja omat malli-/reasoning-asetukset; poista väliproosa ja raskaan kontekstin toisto.
3. Lisää adaptiivinen seuraava ryhmä sekä uuden havainnon perusteella toistuvat hahmovuorot rajatussa ketjussa.
4. Lisää varmennetut välitysluvat ja turvallinen fast path; epäselvät tilanteet palaavat ohjaajalle.
5. Integroi vaiheittainen SSE, pelaajarajat, ehdokasketjun palautuminen ja budgetin näkyminen.
6. Mittaa nykyinen, kevyt staattinen ja adaptiivinen toteutus samoilla lähtötilanteilla.

## 10. Hyväksymiskokeet

- A → B → A -keskustelu jatkuu uuden havaitun repliikin perusteella samassa jatkopyynnössä.
- B:n odottamaton toiminta voi tuoda C:n seuraavaan ryhmään ilman alkusuunnitelman C-vuoroa.
- Pelkkä vanhan kysymyksen toisto ei herätä rajatonta reaktioketjua.
- public_start puuttuu mutta speech on olemassa: puhe ei katoa; ohjaaja ratkaisee sen havaittavuuden.
- Tarkoitettu vastaanottaja ei automaattisesti vastaa kaikkia todellisia kuulijoita. Yksityinen puhe ei vuoda ehdotetun observer_ids-listan kautta.
- Rinnakkaiset valinnat eivät näe toistensa saman ryhmän vastauksia.
- Poistunut tai toimintakyvytön hahmo ei saa paikallista reaktiokutsua. Piilossaolo ei paljastu nimilistasta.
- Olennaisesti muuttunut havaintotilanne mitätöi aiemman välitysluvan.
- Välivaiheessa hyväksytty sitoumus säilyy tilassa, yhteenvedossa ja koko ketjun loppuproosassa.
- Sama väliajan osuus tai jatkuvuusdelta ei kirjaudu kahdesti.
- Pelaajapäätös, keskeytys, budjettiraja ja uusintapyyntö pysähtyvät eheään rajaan.
- Kevyt malli ei lisää keksittyä yhteistä suostumusta, väärää havaitsijaa tai luvattomia toimintoja.

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

Mittaa oikeilla malleilla p50/p95-viive, toteutuneet syöte-/tuotos-/reasoning-/cachetokenit, kutsumäärä, korjausaste, tapahtumaketjun kattavuus, tietovuodot, toisto ja käyttäjän arvioima luonnollisuus. Valemallit varmentavat teknisiä rajoja, eivät orgaanisen tarinan laatua tai kustannussäästöä.

## 11. Suhde muihin suunnitelmiin

Tämä tarkentaa [simulaatiosuunnitelman](SUUNNITELMA_SIMULAATIO.md) ryhmäajoa, säilyttäen sen null/läsnäolo-, historia-, korjaus- ja haarasopimukset. [Realtime-suunnitelman](SUUNNITELMA_REALTIME.md) toteutus voidaan myöhemmin sovittaa samaan tapahtumaketjuun, mutta ei kuulu ensimmäiseen muutokseen. Yleinen historiallisten proosamuutosten tilasynkronointi pysyy erillisenä [editorisuunnitelmassa](SUUNNITELMA_EDITORI.md).
