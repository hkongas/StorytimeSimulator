# Gemini ja seuraavat kehityskohteet

Arvio 30.9.2026. Sovelluksen rajapintatestit käyttävät valepalvelua, eivät oikeaa Gemini-mallia. Kirjallista laatua tai todellista viivettä ei ole mitattu.

## Gemini 2.5 Flash-Lite

Suositus: kokeile hahmojen rajattujen päätösten moottorina, älä valitse romaanin pääkirjoittajaksi pelkän hinnan perusteella. Google kuvaa mallia kevyiden, nopeiden ja suuren volyymin tehtävien malliksi. Strukturoitu tuloste ja suuri konteksti helpottavat teknistä integraatiota mutta eivät takaa uskottavaa motivaatiota, hyvää suomenkielistä proosaa tai jatkuvuutta.

- Mallitunniste: `gemini-2.5-flash-lite`. Syöteraja 1 048 576 ja vastausraja 65 536 tokenia. Sovelluksen oma budjetti on tätä pienempi.
- Dokumentoitu maksullisen vakiotason tekstihinta: syöte 0,10 USD ja vastaus 0,40 USD / miljoona tokenia. Ajattelutokenit kuuluvat vastaushintaan. 10 000 syöte- ja 2 000 vastaustokenia maksaisi näillä hinnoilla noin 0,0018 USD per kutsu, ilman muita palvelukuluja. Tämä ei ole sovelluksen mitattu vuorohinta eikä todiste markkinoiden halvimmasta mallista.
- Googlen nykyisen mallisivun mukaan 2.5-mallien saatavuus on rajattu niitä aiemmin käyttäneisiin käyttäjiin. Uuden projektin pääsy pitää varmistaa. Uusien selainprofiilien oletukset ovat dokumentoidut `gemini-3.8-flash` ja `gemini-3.5-flash-lite`, eivät laadullisesti testatut suositukset.
- Hahmoille: hyvä ehdokas lyhyeen havainto -> aikomus -> päätös -tehtävään. Testaa erityisesti salaisuuksien säilyminen, oma-aloitteisuus, vastakkaiset motiivit ja päätösten vaihtelu.
- Kertojalle: proosa, todistajien määrittely ja maailman seuraukset ovat yhteinen vaativa tehtävä. Halpa virhe vaikuttaa monen myöhemmän vuoron muisteihin. Vertaa Flash-Litea Flashiin ja nykyiseen malliin samalla lähtötilalla.
- Ilmainen taso ja maksullinen taso eroavat käyttörajoissa ja tietojen käytössä. Hintasivu ilmoittaa ilmaiselle tasolle käytön tuotteiden parantamiseen, maksulliselle ei. Tarkista myös ajantasaiset ehdot ennen yksityisen käsikirjoituksen lähettämistä.
- Tuki kattaa tekstin, JSON-skeemat ja nykyisen sovelluksen agenttikutsut. Se ei lisää kuvia, ääntä, Live API:a tai Vertex AI -tunnistautumista. OpenAI-yhteensopivuus on Googlen mukaan beta; paikallinen skeemavalidointi säilytetään.

## Vertailukoe

Käytä samaa aloitusta ja vähintään kolmea toistoa kustakin kokoonpanosta: nykyiset mallit, Flash molemmissa rooleissa, Flash kertojana ja Flash-Lite hahmoina, Flash-Lite molemmissa. Aja 20–30 vuoroa usean kohtauksen läpi. Arvioi sokkona suomen kieli, hahmojen äänten erot, rytmitys, salaisuuksien käyttö ja jatkuvuus. Mittaa kokonaiskustannus, p50/p95-viive, skeemavirheet, katkeamiset ja uusintakutsut. Älä käytä pelkkää ensimmäisen kappaleen laatua valintaperusteena.

## Seuraavat kehityskohteet

1. Viimeisen vuoron tilasynkronointi esikatselulla: vertaa alkuperäistä ja muokattua proosaa palautuspisteen lähtötilaan, validoi hahmo- ja havaitsijatunnisteet, näytä faktamuutokset ja hyväksy kaikki yhdessä revision tarkistavassa transaktiossa. Älä päättele hahmon tietoa kaikkitietävän kertojan tekstistä.
2. Vanhojen lukujen muutokset erilliseen haaraan tai merkitse myöhempi tila vanhentuneeksi. Pelkkä nykyisten faktojen paikkailu ei korjaa niiden varaan rakennettuja myöhempiä tapahtumia.
3. Roolikohtaiset palveluntarjoajat: nyt tarjoaja on yhteinen, vaikka mallit ovat erilliset. Grok-kertoja + suora Gemini-hahmomoottori tarvitsee tämän muutoksen.
4. Malliyhteyden testipainike ja saatavilla olevien mallien haku; selkeät virheet kiintiöistä ja palvelun estämästä vastauksesta. Rajatut 429/503-uusinnat sekä kustannuskatto automaattijatkolle.
5. Arvioitu hinta erilleen palvelun raportoimasta hinnasta. Gemini ei välttämättä palauta dollarimäärää; puuttuva hintatieto ei tarkoita ilmaista käyttöä.
6. Editointihistorian palautus ja redo. Kokonaiset palautuspisteet kasvattavat levytilaa pitkissä tarinoissa; myöhemmin tarvitaan rajattu säilytys tai tapahtumamuutosten tallennus.
7. Vientien epäonnistumisen palautuminen ja saman tarinan rinnakkaisten muokkausoperaatioiden sarjoitus. Tietokanta on ensisijainen lähde, vienti ei ole samaa transaktiota.
8. Romaanin rytmityksen mittarit: merkitykselliset päätöskohdat, toistuvat rutiinit, siirtymien pituus ja hahmojen aito itsenäisyys. Kehitä promptteja oikeiden mallikokeiden perusteella.

## Lähteet

- [Googlen mallikuvaus ja saatavuus](https://ai.google.dev/gemini-api/docs/models/gemini-2.5-flash-lite)
- [Hinnoittelu ja tietojen käyttö](https://ai.google.dev/gemini-api/docs/pricing)
- [OpenAI-yhteensopivuus ja päättelyasetukset](https://ai.google.dev/gemini-api/docs/openai)