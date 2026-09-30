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

## Vuoron Tietovirta

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

Muistihaku yhdistää viimeaikaisia muistoja vanhempiin paikkaan tai motiiviin sanallisesti liittyviin ja tärkeiksi merkittyihin muistoihin. Kertojalle ylläpidetään kumulatiivista tiivistelmää, pysyviä faktoja, avoimia juonilankoja ja seuraavia päätöksentekijöitä. Tämä on rajattu tekstimuisti, ei rajaton tai erehtymätön muistijärjestelmä.

## Tallennus Ja Palautuminen

- Tarinalla on oma SQLite-tietokanta `stories/<tunniste>/story.db`.
- Hahmojen muutokset, havainnot, muistot, kohtaus, proosa, jatkuvuustila ja pyyntökuitti hyväksytään yhdessä transaktiossa.
- Tilaversio estää vanhaan tilanteeseen perustuvaa generointia ylikirjoittamasta välissä tehtyä muokkausta.
- Saman pyyntötunnisteen uudelleenlähetys palauttaa hyväksytyn vastauksen. Samaa tunnistetta ei saa käyttää eri sisällölle.
- Selain seuraa palvelimen taustatyötä. Sivun lataus ei käynnistä uutta vuoroa. Keskeneräisen työn tunniste säilyy välilehden `sessionStorage`-tilassa.
- Palvelimen uudelleenkäynnistys keskeyttää keskeneräiset työt. Valmiit kuitit säilyvät tietokannassa. **Palauta yhteys** käyttää samaa pyyntöä.
- Katkennut tai virheellinen mallivastaus hylätään. Se ei muutu keksityksi varatarinaksi.
- `story.txt` ja `story.md` ovat tietokannasta muodostettavia vientitiedostoja. Niihin käsin tehdyt muutokset eivät päivitä tarinan tilaa ja korvautuvat seuraavassa viennissä.

Vanha tietokanta päivitetään avattaessa. Ennen version 4 migraatiota olemassa olevasta tietokannasta tehdään SQLite-varmuuskopio `story.pre-v4.db`. Säilytä lisäksi omat varmuuskopiot tärkeistä tarinoista. Älä käytä samaa tarinakansiota samanaikaisesti usealta koneelta pilvisynkronoinnin kautta.

## Yksityisyys Ja Asetukset

Tallennus on paikallinen, mutta pilvimallia käytettäessä sen saamat promptit, hahmotiedot ja tarinakatkelmat lähetetään valitulle palveluntarjoajalle. Sovellus ei siis ole automaattisesti kokonaan paikallinen tai offline.

API-avaimet säilytetään palvelimen `.env`- ja `.provider-profiles.json`-tiedostoissa. Niitä ei palauteta asetusten GET-rajapinnasta eikä tallenneta uusiin selainprofiileihin. Vanhojen selainprofiilien avaimet siirretään palvelimelle ennen niiden poistamista selaintallennuksesta. Tiedostot ovat **salaamattomia** ja Gitin ulkopuolella; suojaa käyttäjätili, kansio ja varmuuskopiot asianmukaisesti.

Sovellus on yhden omistajan paikallinen työkalu: ei kirjautumista, monikäyttäjyyttä tai internet-julkaisua varten. Palvelu hyväksyy localhost-isännät ja torjuu vieraasta selainalkuperästä tulevat pyynnöt. Tarina- ja prompttipolut on rajattu omiin hakemistoihinsa. Mallin ja tuontikorttien tekstiä ei suoriteta HTML:nä.

Asetuksissa on yhteinen tarjoaja ja erilliset kertoja- ja hahmomallit. Koodi tukee xAI-, Azure-, OpenAI-, OpenRouter- ja OpenAI-yhteensopivia rajapintoja; nykyinen selainprofiilien näkymä kattaa xAI:n ja Azuren. Muita tarjoajia voi määrittää ympäristöasetuksilla. Mallikohtaiset rajapintaominaisuudet voivat vaihdella.

API-loki sisältää syöte-, vastaus-, päättely- ja välimuistitokenit silloin, kun palvelu ilmoittaa ne. Välimuistitokenit ovat syötetokenien osajoukko. Hinta näytetään vain palvelun raportoimana, ja kooste ilmoittaa kuinka monesta kutsusta hintatieto on saatavilla. Puuttuva hinta ei tarkoita ilmaista kutsua.

`MAX_INPUT_TOKENS` rajoittaa syötteen arvioitua kokoa (oletus 64000). Arvio on merkkimääräpohjainen, ei mallin tarkka tokenisaattori. Ylitys keskeyttää pyynnön ennen verkkokutsua eikä leikkaa sisältöä hiljaisesti.

## Projektin Rakenne

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

Vuorojen peruminen, tarinahaarat, proosan jälkieditointi, kuvien generointi ja usean palvelinprosessin työjono eivät kuulu tähän toteutukseen. Kuvituspromptteja voidaan edelleen tuottaa. Näitä ominaisuuksia kannattaa lisätä hyväksytyn tapahtuma- ja tilamallin päälle, ei ohittamalla sitä.