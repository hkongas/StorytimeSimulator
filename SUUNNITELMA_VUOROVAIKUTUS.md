# Suunnitelma: adaptiivinen vuorovaikutus ja kevyt tilanneohjaaja

Päiväys 8.10.2026. Jatkosuunnitelma, ei toteutettu tässä muutoksessa. Perustuu kutsujen 32–42 analyysiin ja käyttäjän tavoitteeseen elävästä, orgaanisesta vuorovaikutuksesta. Tavanomaiset mallikutsut säilyvät käytössä; Realtime ei ole tämän muutoksen edellytys.

## 1. Nykyinen toimintatapa ja sen rajat

Nykyinen suunnittelija palauttaa koko päätösryhmälistan ennen hahmokutsuja. Ryhmä määrää hahmot, niiden järjestyksen tai rinnakkaisuuden ja requires_resolved_outcome-lipun. collect_groups käy tämän listan läpi eikä lisää uusia päätöksentekijöitä väliratkaisun perusteella. Väliratkaisu voi keskeyttää ketjun, ja muuttunut läsnäolo tai toimintakyky voi estää kutsun.

Hahmo palauttaa public_start-kentässä ehdotuksen havaittavasta aloituksesta sekä observer_ids- ja modality-kentät. Ohjelma rajaa listaa sijainnin, toimintakyvyn ja piilossaolon perusteella. Hahmo ei palauta ratkaisuvaatimuslippua. Ohjelma ei tulkitse toimintatekstin merkitystä päättääkseen väliratkaisusta: suunnittelijan aiemmin antama ryhmälippu ratkaisee sen. Pelkkä speech-kenttä ei automaattisesti välity seuraavalle hahmolle, jos public_start puuttuu.

Kukin hahmo saa päättää vain kerran yhdessä rajatussa kierroksessa. Tämä estää luontevan A → B → A -vastauksen saman jatkopyynnön sisällä. Simulaation oletusryhmä voi kutsua kaikki läsnäolijat rinnakkain, mutta eksplisiittinen suunnitelma rajoittaa ryhmät ennalta. Riippuvuuslista kuvaa järjestystä, ei tapahtumista aktivoituvaa reaktiovalintaa.

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

Lupa sisältää vastaanottajat, sallitun julkisen sisällön lajin, voimassaolon ja ehdot. Paikan, osallistujien, äänenvoimakkuuden, keskeytystilanteen tai havaintokanavan muutos mitätöi luvan. Epäselvä tai puuttuva lupa johtaa tilanneohjaajaan; ohjelma ei arvaa turvallisuutta tekstin pituudesta tai toimintaverbistä.

Välitys voi herättää luvassa määritellyn vastaajan. Se ei valitse tämän vastausta. Tavallista A → B → A -keskustelua voidaan näin jatkaa rajatun luvan sisällä ilman ohjaajakutsua jokaisen repliikin jälkeen.

### Tilanneohjaajan rajattu tulkinta

Tarvitaan, kun havaitsijat, onnistuminen, ajoitus, keskeytys, seuraava päätöksentekijä tai maailmanmuutos ovat avoimia. Ohjaaja palauttaa yhdessä pienessä vastauksessa:

- toteutuneet tapahtumat ja vastaanottajakohtaiset havainnot;
- edelleen avoimet yritykset ja niiden ajallinen vaihe;
- tarpeelliset tilamuutokset, yritystulokset, sitoumukset ja kulunut aika;
- seuraavan ryhmän tai rajatun välitysluvan;
- pysähtymisen: pelaajavalinta, tilanne päättynyt, odotus tai aikasiirtymä;
- lyhyen päätösperusteen auditointiin, ei pitkää sisäistä päättelytekstiä.

Ei proosaa, kuvitusprompttia, koko historian palauttamista tai juonisuunnitelman uudelleenkirjoittamista. Lisätietohaku on rajattu käsillä olevaan tilanteeseen. Raskas suunnittelija kutsutaan uudelleen vain, jos tilanne vaihtuu olennaisesti tai kevyt ohjaaja ilmoittaa, ettei nykyinen kehys riitä.

## 5. Dynaamiset reaktioryhmät

Ensimmäisen ryhmän jälkeen seuraava valitaan todellisten havaintojen ja avoimien päätösten perusteella. Mahdollisia vastaajia ovat puhuttelun kohde, havaittu toimintaan liittyvä osapuoli tai itsenäistä merkityksellistä aloitetta tekevä paikalla oleva hahmo.

- Sama hahmo voi saada uuden vuoron, kun uusi havainto tai muuttunut tilanne perustelee uuden valinnan.
- Hahmo ei saa uutta yritystä pelkästään siksi, että aiempi epäonnistui tai jäi odottamaan.
- Reaktiokutsulla on lähdetapahtuma tai avoimen yrityksen vaihe; jo käytetty heräte ei käynnistä samaa reaktiota uudelleen.
- Rinnakkaisen ryhmän kaikki omat näkymät lukitaan ennen ensimmäistä kutsua. Mallikutsun valmistumisjärjestys ei anna etua.
- Ulkopuolinen keskustelija ei saa yksityistä puhetta vain koska voisi haluta reagoida. Ohjaajalle voidaan antaa kaikkitietävä konteksti, hahmolle ei.
- Kaikkien ei tarvitse puhua. Hiljaisuus ja odottaminen ovat oikeita valintoja.
- Pelaajan uusi merkityksellinen päätös katkaisee automaation ja tallentaa ehjän rajakohdan; pelaajan oletusreaktiota ei luoda.

Staattinen ryhmämalli säilytetään yhteensopivuuspolkuna ja rinnakkaisuustestien vertailuna, mutta dynaaminen ketju korvaa vanhan kerran-per-hahmo-rajoituksen ja päällekkäisen lisäreaktiosilmukan.

## 6. Budjetit ja luonteva pysähtyminen

Erotetaan hahmopäätösten, ohjaajakutsujen, todellisten väliratkaisujen ja kokonaiskutsujen rajat. Lisäksi käytetään per-hahmo-reaktiokattoa, aikarajaa ja tokenbudjettia. Oletukset valitaan mitattujen kokeiden pohjalta; lukuja ei pidetä osoitettuna laatutakuuna.

Budjetin täyttyessä tallennetaan viimeinen johdonmukainen tapahtumaraja ja säilytetään avoimet yritykset sekä jatkosuunnitelma. Kustannuksia ei peitetä automaattisilla jatkokutsuilla. Jos kaikki odottavat eikä pelaajasyötettä tarvita, ohjaaja voi siirtää ajan seuraavaan perusteltuun tapahtumaan tai päättää tilanteen ilman keinotekoista lisäuhkaa.

SSE näyttää valmistuneet julkiset työvaiheet ajoissa. Yksityisajatukset eivät vuoda roolipeliprogressiin. Ehdokasvaihe erotetaan hyväksytystä historiasta, ja keskeytys ei muutu historian takautuvaksi peruutukseksi.

## 7. Kevyt malli ja reasoning-asetukset

Lisätään oma tilanneohjaajan malli, provider/deployment-tuki olemassa olevan profiilirakenteen ehdoilla, päättelyasetus ja vastausbudjetti. Roolin nimi lokissa on erillinen, mutta hahmomallin hyödyntäminen ei tarkoita hahmon roolikehotteen hyödyntämistä.

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
- Jos kirjoittaja ehdottaa uutta asiaa, se on erillinen ehdotus eikä suoraan hyväksytty tapahtuma.
- Rajattu pelaajanäkymä syntyy samojen tapahtumien omista havainnoista.
- Proosa, tapahtumat ja tila hyväksytään atomisesti. Korjauskutsu ei toista hahmopäätöksiä. Sisältökorjaus, joka muuttaisi jo käytettyjä havaintoja, mitätöi riippuvat ehdokasreaktiot eikä jää muotopaikkaukseksi.
- Säilytetään koko ehdokasketju, revisio, budjetinkulutus ja jatkoraja palautumista varten. Uudelleenlähetys tai palvelimen käynnistys ei monista jo hyväksyttyjä tapahtumia.

## 9. Toteutusjärjestys

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

Mittaa p50/p95-viive, syöte-/tuotos-/reasoning-/cachetokenit, kutsumäärä, korjausaste, alkuperäisen tapahtumaketjun kattavuus, tietovuodot, toisto ja käyttäjän arvioima luonnollisuus. Valemallit todistavat teknisiä rajoja, eivät orgaanisen tarinan laatua.

## 11. Suhde muihin suunnitelmiin

Tämä tarkentaa [simulaatiosuunnitelman](SUUNNITELMA_SIMULAATIO.md) ryhmäajoa, säilyttäen sen null/läsnäolo-, historia-, korjaus- ja haarasopimukset. [Realtime-suunnitelman](SUUNNITELMA_REALTIME.md) toteutus voidaan myöhemmin sovittaa samaan tapahtumaketjuun, mutta ei kuulu ensimmäiseen muutokseen. Yleinen historiallisten proosamuutosten tilasynkronointi pysyy erillisenä [editorisuunnitelmassa](SUUNNITELMA_EDITORI.md).
