"""
Management command: seed_nl_questions

Seeds Dutch (NL) translations for the Introduction to Dutch Driving topic (72 questions).
This serves as a working demonstration; additional topics can be translated in the same pattern.

Usage:
    python manage.py seed_nl_questions [--dry-run]
"""

from django.core.management.base import BaseCommand
from apps.driving_theory.models import DrivingQuestion, DrivingQuestionOption, DrivingTopic


# ---------------------------------------------------------------------------
# Dutch translations keyed by question ID
# Format: { question_id: { 'q': NL_text, 'opts': { option_id: NL_text } } }
# ---------------------------------------------------------------------------
NL_DATA = {
    # ── ID 1 ─────────────────────────────────────────────────────────────
    1: {
        "q": "Op welke kant van de weg rij je normaal gesproken in Nederland?",
        "opts": {
            26645: "De linkerkant",
            26646: "De rechterkant",
            26647: "Het midden van de weg",
            26648: "Elke kant als de weg rustig is",
        },
    },
    # ── ID 2 ─────────────────────────────────────────────────────────────
    2: {
        "q": "Wat betekent het Nederlandse woord 'rijbewijs'?",
        "opts": {
            26649: "Kentekenbewijs",
            26650: "Rijbewijs",
            26651: "Verzekeringsbewijs",
            26652: "Wegenkaart",
        },
    },
    # ── ID 3 ─────────────────────────────────────────────────────────────
    3: {
        "q": "Een leerlingbestuurder is 17 jaar en heeft het vereiste begeleide rijschema doorlopen. Wat is toegestaan?",
        "opts": {
            26653: "Alleen rijden op elk moment",
            26654: "Alleen rijden op snelwegen",
            26655: "Rijden met een goedgekeurde coach of begeleider",
            26656: "Alleen rijden na zonsondergang",
        },
    },
    # ── ID 4 ─────────────────────────────────────────────────────────────
    4: {
        "q": "Welk document of welke verplichting zorgt ervoor dat schade aan anderen gedekt kan worden als jij een ongeluk veroorzaakt?",
        "opts": {
            26657: "Een parkeerschijf",
            26658: "Een WA-verzekering",
            26659: "Een navigatieabonnement",
            26660: "Een wegenbelastingbewijs in het handschoenvak",
        },
    },
    # ── ID 5 ─────────────────────────────────────────────────────────────
    5: {
        "q": "Je rijdt een stadscentrum in met veel fietsers en smalle straten. Wat is de veiligste basishouding?",
        "opts": {
            26661: "Rij assertief zodat anderen zich aanpassen",
            26662: "Houd lage snelheid en verwacht kwetsbare weggebruikers",
            26663: "Gebruik de claxon als de ruimte krap is",
            26664: "Blijf dicht achter fietsers om vertraging te vermijden",
        },
    },
    # ── ID 6 ─────────────────────────────────────────────────────────────
    6: {
        "q": "Welke bordvorm is gereserveerd voor een volledig STOP-gebod?",
        "opts": {
            26665: "Driehoek",
            26666: "Cirkel",
            26667: "Achthoek",
            26668: "Rechthoek",
        },
    },
    # ── ID 7 ─────────────────────────────────────────────────────────────
    7: {
        "q": "Voor een ochtendrit bedekt ijs nog het grootste deel van je voorruit. Wat moet je doen?",
        "opts": {
            26669: "Langzaam rijden en de rest later wegkrabben",
            26670: "Een passagier vragen je te begeleiden",
            26671: "De ramen goed schoon maken voordat je rijdt",
            26672: "Het zijraam openen en de rit beginnen",
        },
    },
    # ── ID 8 ─────────────────────────────────────────────────────────────
    8: {
        "q": "Wat is de beste reden om theorie te studeren, ook als je al weet hoe je een auto bestuurt?",
        "opts": {
            26673: "Theorie is alleen nuttig voor beroepschauffeurs",
            26674: "Theorie koppelt regels en gevaarbewustzijn aan echte situaties",
            26675: "Theorie vervangt praktijklessen volledig",
            26676: "Theorie telt alleen op snelwegen",
        },
    },
    # ── ID 9 ─────────────────────────────────────────────────────────────
    9: {
        "q": "Vlak voor je rit verschijnt een dashboardsymbool en je weet niet wat het betekent. Wat is de veiligste aanpak?",
        "opts": {
            26677: "Negeer het als de motor nog start",
            26678: "Rij alleen als je onder de 30 km/u blijft",
            26679: "Controleer de waarschuwing en los het probleem op voor je de auto gebruikt",
            26680: "Bedek het lampje zodat het minder afleidt",
        },
    },
    # ── ID 10 ────────────────────────────────────────────────────────────
    10: {
        "q": "Je voelt je erg moe na een lange werkdag, maar de rit naar huis is kort. Wat is juist?",
        "opts": {
            26681: "Korte ritten zijn vrijgesteld van fitnessregels",
            26682: "Vermoeidheid is alleen een probleem boven 80 km/u",
            26683: "Je bent nog steeds verantwoordelijk om fit te rijden",
            26684: "Koffie verwijdert alle vermoeidheidsrisico's direct",
        },
    },
    # ── ID 11 ────────────────────────────────────────────────────────────
    11: {
        "q": "Waarnaar verwijst 'bebouwde kom' in het Nederlandse verkeersrecht?",
        "opts": {
            26685: "Een verzorgingsplaats aan de snelweg",
            26686: "Een bebouwde kom of stadszone",
            26687: "Een landelijk fietspad",
            26688: "Een voertuigkeuringscentrum",
        },
    },
    # ── ID 12 ────────────────────────────────────────────────────────────
    12: {
        "q": "Waarom is voorspelbaar rijgedrag belangrijk in Nederland?",
        "opts": {
            26689: "Daardoor kun je hogere snelheid aanhouden in de stad",
            26690: "Het is alleen nodig op wegen met drie of meer rijstroken",
            26691: "Het helpt andere weggebruikers veilig in te spelen op jouw beweging",
            26692: "Het vervangt spiegelcontroles",
        },
    },
    # ── ID 181 ───────────────────────────────────────────────────────────
    181: {
        "q": "Welke stelling over het vroeg leren van Nederlandse bordcategorieën is juist?",
        "opts": {
            27365: "Het helpt je een bord sneller te begrijpen omdat vorm en kleur al aangeven om welk type regel het gaat.",
            27366: "Kleuren zijn decoratief en hebben geen betekenis.",
            27367: "Categorieën doen er niet toe als je kunt rijden.",
            27368: "Alleen politieagenten hebben bordcategorieën nodig.",
        },
    },
    # ── ID 182 ───────────────────────────────────────────────────────────
    182: {
        "q": "Wat moet je onthouden over rijden op gewone Nederlandse wegen?",
        "opts": {
            27369: "Je kiest een kant als er weinig verkeer is.",
            27370: "Je houdt normaal gesproken links aan.",
            27371: "Je houdt normaal gesproken rechts aan.",
            27372: "Je rijdt in het midden als de weg smal aanvoelt.",
        },
    },
    # ── ID 183 ───────────────────────────────────────────────────────────
    183: {
        "q": "Wat is de juiste regel over het vroeg leren van Nederlandse bordcategorieën?",
        "opts": {
            27373: "Kleuren zijn decoratief en hebben geen betekenis.",
            27374: "Categorieën doen er niet toe als je kunt rijden.",
            27375: "Alleen politieagenten hebben bordcategorieën nodig.",
            27376: "Het helpt je een bord sneller te begrijpen omdat vorm en kleur al aangeven om welk type regel het gaat.",
        },
    },
    # ── ID 184 ───────────────────────────────────────────────────────────
    184: {
        "q": "Wat is de juiste regel over hoe de Nederlandse theorie omgaat met kwetsbare weggebruikers?",
        "opts": {
            27377: "Ze tellen alleen binnen de bebouwde kom.",
            27378: "Ze verliezen altijd voorrang omdat ze langzaam rijden.",
            27379: "Ze worden in alle situaties behandeld zoals zwaar verkeer.",
            27380: "Ze verdienen extra aandacht omdat ze minder fysieke bescherming hebben.",
        },
    },
    # ── ID 185 ───────────────────────────────────────────────────────────
    185: {
        "q": "Wat is de juiste regel over het delen van Nederlandse wegen met fietsers en voetgangers?",
        "opts": {
            27381: "Je mag aannemen dat fietsers altijd wachten op auto's.",
            27382: "Je moet rijden op de aangegeven maximum snelheid, ook als de ruimte krap aanvoelt.",
            27383: "Je hoeft alleen bij zebrapaden aan kwetsbare weggebruikers te denken.",
            27384: "Je moet kwetsbare weggebruikers verwachten en vroeg je snelheid en ruimte aanpassen.",
        },
    },
    # ── ID 186 ───────────────────────────────────────────────────────────
    186: {
        "q": "Welke stelling over het RVV 1990, de voornaamste Nederlandse verordening voor dagelijkse verkeersborden en verkeersgedrag, is juist?",
        "opts": {
            27385: "Het is een voertuigverzekeringscontract.",
            27386: "Het geldt alleen op snelwegen.",
            27387: "Het is alleen een handboek voor rijinstructeurs.",
            27388: "Het is de voornaamste dagelijkse verkeersregelgeving.",
        },
    },
    # ── ID 187 ───────────────────────────────────────────────────────────
    187: {
        "q": "Wat moet je onthouden over het vroeg leren van Nederlandse bordcategorieën?",
        "opts": {
            27389: "Het helpt je een bord sneller te begrijpen omdat vorm en kleur al aangeven om welk type regel het gaat.",
            27390: "Kleuren zijn decoratief en hebben geen betekenis.",
            27391: "Categorieën doen er niet toe als je kunt rijden.",
            27392: "Alleen politieagenten hebben bordcategorieën nodig.",
        },
    },
    # ── ID 188 ───────────────────────────────────────────────────────────
    188: {
        "q": "Wat is de juiste regel over rijden op gewone Nederlandse wegen?",
        "opts": {
            27393: "Je rijdt in het midden als de weg smal aanvoelt.",
            27394: "Je kiest een kant als er weinig verkeer is.",
            27395: "Je houdt normaal gesproken rechts aan.",
            27396: "Je houdt normaal gesproken links aan.",
        },
    },
    # ── ID 189 ───────────────────────────────────────────────────────────
    189: {
        "q": "Je krijgt een Nederlandse theorievraag over waarom theorie studeren belangrijk is vóór praktisch rijden. Welk antwoord is juist?",
        "opts": {
            27397: "Het vervangt de noodzaak om borden op de weg te observeren.",
            27398: "Het gaat alleen over het memoriseren van straatnamen.",
            27399: "Het helpt je regels, gevaren en veilige beslissingen te herkennen vóór echte verkeerssituaties.",
            27400: "Het telt alleen voor beroepschauffeurs.",
        },
    },
    # ── ID 190 ───────────────────────────────────────────────────────────
    190: {
        "q": "Je krijgt een Nederlandse theorievraag over je rijvaardigheid voor aanvang van een rit. Welk antwoord is juist?",
        "opts": {
            27401: "Je bent verantwoordelijk om niet te rijden als je te moe, afgeleid of ziek bent.",
            27402: "Koffie vervangt wettelijk de behoefte aan rust.",
            27403: "Alleen beroepschauffeurs moeten nadenken over rijvaardigheid.",
            27404: "Korte ritten maken fitnessregels irrelevant.",
        },
    },
    # ── ID 191 ───────────────────────────────────────────────────────────
    191: {
        "q": "Welke optie komt het best overeen met de regel voor het woord 'weggebruiker' in de Nederlandse verkeerstheorie?",
        "opts": {
            27405: "Het betekent alleen automobilisten.",
            27406: "Het sluit fietsers en voetgangers uit.",
            27407: "Het omvat iedereen die de weg gebruikt, zoals automobilisten, fietsers, voetgangers, ruiters en trambestuurders.",
            27408: "Het betekent alleen mensen met een Nederlands rijbewijs.",
        },
    },
    # ── ID 192 ───────────────────────────────────────────────────────────
    192: {
        "q": "Je krijgt een Nederlandse theorievraag over hoe je een moeilijke theoriевraag aanpakt. Welk antwoord is juist?",
        "opts": {
            27409: "Kies altijd het antwoord met de hoogste snelheid.",
            27410: "Lees rustig, zoek de exacte regel en kies het veiligste antwoord dat overeenkomt met de Nederlandse wet.",
            27411: "Raad zonder alle opties te lezen.",
            27412: "Negeer borden in de vraag en volg je gewoonte.",
        },
    },
    # ── ID 193 ───────────────────────────────────────────────────────────
    193: {
        "q": "Je krijgt een Nederlandse theorievraag over documenten en wettelijke gereedheid voordat je rijdt. Welk antwoord is juist?",
        "opts": {
            27413: "Als de rit kort is, doen registratie en verzekering er niet toe.",
            27414: "Wettelijke gereedheid telt alleen op snelwegen.",
            27415: "Bestuurder en voertuig moeten wettelijk gereed zijn, inclusief correct rijbewijs, registratie, verzekering en veilige staat.",
            27416: "Alleen brandstofniveau telt voor een rit.",
        },
    },
    # ── ID 194 ───────────────────────────────────────────────────────────
    194: {
        "q": "Je krijgt een Nederlandse theorievraag over het verschil tussen een regel kennen en toepassen. Welk antwoord is juist?",
        "opts": {
            27417: "Toepassen telt alleen bij slecht weer.",
            27418: "Toepassen betekent sneller rijden om de situatie snel af te handelen.",
            27419: "Een veilige bestuurder kent de regel én past snelheid, positie en observatie op tijd aan.",
            27420: "De regel kennen betekent dat je de weg nooit hoeft te scannen.",
        },
    },
    # ── ID 195 ───────────────────────────────────────────────────────────
    195: {
        "q": "Welke optie komt het best overeen met de regel voor het RVV 1990, de voornaamste Nederlandse verordening voor dagelijkse verkeersborden en verkeersgedrag?",
        "opts": {
            27421: "Het is alleen een handboek voor rijinstructeurs.",
            27422: "Het is een voertuigverzekeringscontract.",
            27423: "Het geldt alleen op snelwegen.",
            27424: "Het is de voornaamste dagelijkse verkeersregelgeving.",
        },
    },
    # ── ID 196 ───────────────────────────────────────────────────────────
    196: {
        "q": "Wat moet je onthouden over het verschil tussen een regel kennen en toepassen in het Nederlandse verkeer?",
        "opts": {
            27425: "Een veilige bestuurder kent de regel én past snelheid, positie en observatie op tijd aan.",
            27426: "Toepassen betekent sneller rijden om de situatie snel af te handelen.",
            27427: "De regel kennen betekent dat je de weg nooit hoeft te scannen.",
            27428: "Toepassen telt alleen bij slecht weer.",
        },
    },
    # ── ID 197 ───────────────────────────────────────────────────────────
    197: {
        "q": "Wat moet je onthouden over hoe je een moeilijke theoriевraag aanpakt in het Nederlandse verkeer?",
        "opts": {
            27429: "Negeer borden in de vraag en volg je gewoonte.",
            27430: "Kies altijd het antwoord met de hoogste snelheid.",
            27431: "Raad zonder alle opties te lezen.",
            27432: "Lees rustig, zoek de exacte regel en kies het veiligste antwoord dat overeenkomt met de Nederlandse wet.",
        },
    },
    # ── ID 198 ───────────────────────────────────────────────────────────
    198: {
        "q": "Welke optie komt het best overeen met de regel voor hoe de Nederlandse theorie omgaat met kwetsbare weggebruikers?",
        "opts": {
            27433: "Ze tellen alleen binnen de bebouwde kom.",
            27434: "Ze verliezen altijd voorrang omdat ze langzaam rijden.",
            27435: "Ze worden in alle situaties behandeld zoals zwaar verkeer.",
            27436: "Ze verdienen extra aandacht omdat ze minder fysieke bescherming hebben.",
        },
    },
    # ── ID 199 ───────────────────────────────────────────────────────────
    199: {
        "q": "Welke stelling over hoe de Nederlandse theorie omgaat met kwetsbare weggebruikers is juist?",
        "opts": {
            27437: "Ze verdienen extra aandacht omdat ze minder fysieke bescherming hebben.",
            27438: "Ze verliezen altijd voorrang omdat ze langzaam rijden.",
            27439: "Ze worden in alle situaties behandeld zoals zwaar verkeer.",
            27440: "Ze tellen alleen binnen de bebouwde kom.",
        },
    },
    # ── ID 200 ───────────────────────────────────────────────────────────
    200: {
        "q": "Je krijgt een Nederlandse theorievraag over rijden op gewone Nederlandse wegen. Welk antwoord is juist?",
        "opts": {
            27441: "Je houdt normaal gesproken rechts aan.",
            27442: "Je rijdt in het midden als de weg smal aanvoelt.",
            27443: "Je kiest een kant als er weinig verkeer is.",
            27444: "Je houdt normaal gesproken links aan.",
        },
    },
    # ── ID 201 ───────────────────────────────────────────────────────────
    201: {
        "q": "Wat is de juiste regel voor het woord 'weggebruiker' in de Nederlandse verkeerstheorie?",
        "opts": {
            27445: "Het betekent alleen automobilisten.",
            27446: "Het betekent alleen mensen met een Nederlands rijbewijs.",
            27447: "Het omvat iedereen die de weg gebruikt, zoals automobilisten, fietsers, voetgangers, ruiters en trambestuurders.",
            27448: "Het sluit fietsers en voetgangers uit.",
        },
    },
    # ── ID 202 ───────────────────────────────────────────────────────────
    202: {
        "q": "Welke stelling over waarom theorie studeren belangrijk is vóór praktisch rijden is juist?",
        "opts": {
            27449: "Het telt alleen voor beroepschauffeurs.",
            27450: "Het gaat alleen over het memoriseren van straatnamen.",
            27451: "Het helpt je regels, gevaren en veilige beslissingen te herkennen vóór echte verkeerssituaties.",
            27452: "Het vervangt de noodzaak om borden op de weg te observeren.",
        },
    },
    # ── ID 203 ───────────────────────────────────────────────────────────
    203: {
        "q": "Welke optie komt het best overeen met de regel voor het verschil tussen een regel kennen en toepassen?",
        "opts": {
            27453: "Toepassen telt alleen bij slecht weer.",
            27454: "Een veilige bestuurder kent de regel én past snelheid, positie en observatie op tijd aan.",
            27455: "De regel kennen betekent dat je de weg nooit hoeft te scannen.",
            27456: "Toepassen betekent sneller rijden om de situatie snel af te handelen.",
        },
    },
    # ── ID 204 ───────────────────────────────────────────────────────────
    204: {
        "q": "Wat is de juiste regel over de organisatie die de Nederlandse theorie- en praktijkexamens afneemt?",
        "opts": {
            27457: "De politie neemt het theorie-examen voor leerlingen af.",
            27458: "Het CBR is de organisatie die die examens afneemt.",
            27459: "Verzekeringsmaatschappijen nemen het praktijkexamen af.",
            27460: "De gemeente neemt alle rijexamens af.",
        },
    },
    # ── ID 205 ───────────────────────────────────────────────────────────
    205: {
        "q": "Je krijgt een Nederlandse theorievraag over het RVV 1990, de voornaamste verordening voor dagelijkse verkeersborden en verkeersgedrag. Welk antwoord is juist?",
        "opts": {
            27461: "Het is de voornaamste dagelijkse verkeersregelgeving.",
            27462: "Het geldt alleen op snelwegen.",
            27463: "Het is alleen een handboek voor rijinstructeurs.",
            27464: "Het is een voertuigverzekeringscontract.",
        },
    },
    # ── ID 206 ───────────────────────────────────────────────────────────
    206: {
        "q": "Je krijgt een Nederlandse theorievraag over de organisatie die de theorie- en praktijkexamens afneemt. Welk antwoord is juist?",
        "opts": {
            27465: "De politie neemt het theorie-examen voor leerlingen af.",
            27466: "Het CBR is de organisatie die die examens afneemt.",
            27467: "De gemeente neemt alle rijexamens af.",
            27468: "Verzekeringsmaatschappijen nemen het praktijkexamen af.",
        },
    },
    # ── ID 207 ───────────────────────────────────────────────────────────
    207: {
        "q": "Welke optie komt het best overeen met de regel voor de organisatie die de Nederlandse theorie- en praktijkexamens afneemt?",
        "opts": {
            27469: "De gemeente neemt alle rijexamens af.",
            27470: "Verzekeringsmaatschappijen nemen het praktijkexamen af.",
            27471: "De politie neemt het theorie-examen voor leerlingen af.",
            27472: "Het CBR is de organisatie die die examens afneemt.",
        },
    },
    # ── ID 208 ───────────────────────────────────────────────────────────
    208: {
        "q": "Welke optie komt het best overeen met de regel voor het vroeg leren van Nederlandse bordcategorieën?",
        "opts": {
            27473: "Alleen politieagenten hebben bordcategorieën nodig.",
            27474: "Kleuren zijn decoratief en hebben geen betekenis.",
            27475: "Categorieën doen er niet toe als je kunt rijden.",
            27476: "Het helpt je een bord sneller te begrijpen omdat vorm en kleur al aangeven om welk type regel het gaat.",
        },
    },
    # ── ID 209 ───────────────────────────────────────────────────────────
    209: {
        "q": "Wat moet je onthouden over waarom theorie studeren belangrijk is vóór praktisch rijden in het Nederlandse verkeer?",
        "opts": {
            27477: "Het telt alleen voor beroepschauffeurs.",
            27478: "Het vervangt de noodzaak om borden op de weg te observeren.",
            27479: "Het gaat alleen over het memoriseren van straatnamen.",
            27480: "Het helpt je regels, gevaren en veilige beslissingen te herkennen vóór echte verkeerssituaties.",
        },
    },
    # ── ID 210 ───────────────────────────────────────────────────────────
    210: {
        "q": "Welke stelling over de organisatie die de Nederlandse theorie- en praktijkexamens afneemt is juist?",
        "opts": {
            27481: "Verzekeringsmaatschappijen nemen het praktijkexamen af.",
            27482: "De politie neemt het theorie-examen voor leerlingen af.",
            27483: "De gemeente neemt alle rijexamens af.",
            27484: "Het CBR is de organisatie die die examens afneemt.",
        },
    },
    # ── ID 211 ───────────────────────────────────────────────────────────
    211: {
        "q": "Je krijgt een Nederlandse theorievraag over hoe de theorie omgaat met kwetsbare weggebruikers. Welk antwoord is juist?",
        "opts": {
            27485: "Ze verdienen extra aandacht omdat ze minder fysieke bescherming hebben.",
            27486: "Ze worden in alle situaties behandeld zoals zwaar verkeer.",
            27487: "Ze verliezen altijd voorrang omdat ze langzaam rijden.",
            27488: "Ze tellen alleen binnen de bebouwde kom.",
        },
    },
    # ── ID 212 ───────────────────────────────────────────────────────────
    212: {
        "q": "Welke stelling over hoe je een moeilijke theoriевraag aanpakt is juist?",
        "opts": {
            27489: "Raad zonder alle opties te lezen.",
            27490: "Negeer borden in de vraag en volg je gewoonte.",
            27491: "Kies altijd het antwoord met de hoogste snelheid.",
            27492: "Lees rustig, zoek de exacte regel en kies het veiligste antwoord dat overeenkomt met de Nederlandse wet.",
        },
    },
    # ── ID 213 ───────────────────────────────────────────────────────────
    213: {
        "q": "Welke optie komt het best overeen met de regel voor documenten en wettelijke gereedheid voordat je rijdt?",
        "opts": {
            27493: "Bestuurder en voertuig moeten wettelijk gereed zijn, inclusief correct rijbewijs, registratie, verzekering en veilige staat.",
            27494: "Alleen brandstofniveau telt voor een rit.",
            27495: "Als de rit kort is, doen registratie en verzekering er niet toe.",
            27496: "Wettelijke gereedheid telt alleen op snelwegen.",
        },
    },
    # ── ID 214 ───────────────────────────────────────────────────────────
    214: {
        "q": "Wat moet je onthouden over het delen van Nederlandse wegen met fietsers en voetgangers?",
        "opts": {
            27497: "Je moet kwetsbare weggebruikers verwachten en vroeg je snelheid en ruimte aanpassen.",
            27498: "Je moet rijden op de aangegeven maximum snelheid, ook als de ruimte krap aanvoelt.",
            27499: "Je hoeft alleen bij zebrapaden aan kwetsbare weggebruikers te denken.",
            27500: "Je mag aannemen dat fietsers altijd wachten op auto's.",
        },
    },
    # ── ID 215 ───────────────────────────────────────────────────────────
    215: {
        "q": "Wat is de juiste regel over documenten en wettelijke gereedheid voordat je rijdt?",
        "opts": {
            27501: "Bestuurder en voertuig moeten wettelijk gereed zijn, inclusief correct rijbewijs, registratie, verzekering en veilige staat.",
            27502: "Als de rit kort is, doen registratie en verzekering er niet toe.",
            27503: "Wettelijke gereedheid telt alleen op snelwegen.",
            27504: "Alleen brandstofniveau telt voor een rit.",
        },
    },
    # ── ID 216 ───────────────────────────────────────────────────────────
    216: {
        "q": "Welke optie komt het best overeen met de regel voor rijden op gewone Nederlandse wegen?",
        "opts": {
            27505: "Je kiest een kant als er weinig verkeer is.",
            27506: "Je houdt normaal gesproken links aan.",
            27507: "Je rijdt in het midden als de weg smal aanvoelt.",
            27508: "Je houdt normaal gesproken rechts aan.",
        },
    },
    # ── ID 217 ───────────────────────────────────────────────────────────
    217: {
        "q": "Wat moet je onthouden over het RVV 1990, de voornaamste verordening voor dagelijkse verkeersborden en verkeersgedrag in het Nederlandse verkeer?",
        "opts": {
            27509: "Het is een voertuigverzekeringscontract.",
            27510: "Het is alleen een handboek voor rijinstructeurs.",
            27511: "Het geldt alleen op snelwegen.",
            27512: "Het is de voornaamste dagelijkse verkeersregelgeving.",
        },
    },
    # ── ID 218 ───────────────────────────────────────────────────────────
    218: {
        "q": "Welke stelling over documenten en wettelijke gereedheid voordat je rijdt is juist?",
        "opts": {
            27513: "Wettelijke gereedheid telt alleen op snelwegen.",
            27514: "Als de rit kort is, doen registratie en verzekering er niet toe.",
            27515: "Bestuurder en voertuig moeten wettelijk gereed zijn, inclusief correct rijbewijs, registratie, verzekering en veilige staat.",
            27516: "Alleen brandstofniveau telt voor een rit.",
        },
    },
    # ── ID 219 ───────────────────────────────────────────────────────────
    219: {
        "q": "Welke stelling over rijden op gewone Nederlandse wegen is juist?",
        "opts": {
            27517: "Je rijdt in het midden als de weg smal aanvoelt.",
            27518: "Je kiest een kant als er weinig verkeer is.",
            27519: "Je houdt normaal gesproken links aan.",
            27520: "Je houdt normaal gesproken rechts aan.",
        },
    },
    # ── ID 220 ───────────────────────────────────────────────────────────
    220: {
        "q": "Wat moet je onthouden over het woord 'weggebruiker' in de Nederlandse verkeerstheorie?",
        "opts": {
            27521: "Het betekent alleen automobilisten.",
            27522: "Het omvat iedereen die de weg gebruikt, zoals automobilisten, fietsers, voetgangers, ruiters en trambestuurders.",
            27523: "Het betekent alleen mensen met een Nederlands rijbewijs.",
            27524: "Het sluit fietsers en voetgangers uit.",
        },
    },
    # ── ID 221 ───────────────────────────────────────────────────────────
    221: {
        "q": "Welke optie komt het best overeen met de regel voor hoe je een moeilijke theoriевraag aanpakt?",
        "opts": {
            27525: "Negeer borden in de vraag en volg je gewoonte.",
            27526: "Kies altijd het antwoord met de hoogste snelheid.",
            27527: "Raad zonder alle opties te lezen.",
            27528: "Lees rustig, zoek de exacte regel en kies het veiligste antwoord dat overeenkomt met de Nederlandse wet.",
        },
    },
    # ── ID 222 ───────────────────────────────────────────────────────────
    222: {
        "q": "Je krijgt een Nederlandse theorievraag over het vroeg leren van bordcategorieën. Welk antwoord is juist?",
        "opts": {
            27529: "Alleen politieagenten hebben bordcategorieën nodig.",
            27530: "Het helpt je een bord sneller te begrijpen omdat vorm en kleur al aangeven om welk type regel het gaat.",
            27531: "Kleuren zijn decoratief en hebben geen betekenis.",
            27532: "Categorieën doen er niet toe als je kunt rijden.",
        },
    },
    # ── ID 223 ───────────────────────────────────────────────────────────
    223: {
        "q": "Wat is de juiste regel over hoe je een moeilijke theoriевraag aanpakt?",
        "opts": {
            27533: "Negeer borden in de vraag en volg je gewoonte.",
            27534: "Raad zonder alle opties te lezen.",
            27535: "Lees rustig, zoek de exacte regel en kies het veiligste antwoord dat overeenkomt met de Nederlandse wet.",
            27536: "Kies altijd het antwoord met de hoogste snelheid.",
        },
    },
    # ── ID 224 ───────────────────────────────────────────────────────────
    224: {
        "q": "Wat is de juiste regel over het RVV 1990, de voornaamste verordening voor dagelijkse verkeersborden en verkeersgedrag?",
        "opts": {
            27537: "Het geldt alleen op snelwegen.",
            27538: "Het is een voertuigverzekeringscontract.",
            27539: "Het is alleen een handboek voor rijinstructeurs.",
            27540: "Het is de voornaamste dagelijkse verkeersregelgeving.",
        },
    },
    # ── ID 225 ───────────────────────────────────────────────────────────
    225: {
        "q": "Welke stelling over het woord 'weggebruiker' in de Nederlandse verkeerstheorie is juist?",
        "opts": {
            27541: "Het betekent alleen mensen met een Nederlands rijbewijs.",
            27542: "Het omvat iedereen die de weg gebruikt, zoals automobilisten, fietsers, voetgangers, ruiters en trambestuurders.",
            27543: "Het betekent alleen automobilisten.",
            27544: "Het sluit fietsers en voetgangers uit.",
        },
    },
    # ── ID 226 ───────────────────────────────────────────────────────────
    226: {
        "q": "Welke stelling over het verschil tussen een regel kennen en toepassen is juist?",
        "opts": {
            27545: "De regel kennen betekent dat je de weg nooit hoeft te scannen.",
            27546: "Toepassen telt alleen bij slecht weer.",
            27547: "Een veilige bestuurder kent de regel én past snelheid, positie en observatie op tijd aan.",
            27548: "Toepassen betekent sneller rijden om de situatie snel af te handelen.",
        },
    },
    # ── ID 227 ───────────────────────────────────────────────────────────
    227: {
        "q": "Wat is de juiste regel over je rijvaardigheid voor aanvang van een rit?",
        "opts": {
            27549: "Korte ritten maken fitnessregels irrelevant.",
            27550: "Je bent verantwoordelijk om niet te rijden als je te moe, afgeleid of ziek bent.",
            27551: "Koffie vervangt wettelijk de behoefte aan rust.",
            27552: "Alleen beroepschauffeurs moeten nadenken over rijvaardigheid.",
        },
    },
    # ── ID 228 ───────────────────────────────────────────────────────────
    228: {
        "q": "Je krijgt een Nederlandse theorievraag over het delen van Nederlandse wegen met fietsers en voetgangers. Welk antwoord is juist?",
        "opts": {
            27553: "Je mag aannemen dat fietsers altijd wachten op auto's.",
            27554: "Je hoeft alleen bij zebrapaden aan kwetsbare weggebruikers te denken.",
            27555: "Je moet rijden op de aangegeven maximum snelheid, ook als de ruimte krap aanvoelt.",
            27556: "Je moet kwetsbare weggebruikers verwachten en vroeg je snelheid en ruimte aanpassen.",
        },
    },
    # ── ID 229 ───────────────────────────────────────────────────────────
    229: {
        "q": "Welke optie komt het best overeen met de regel voor je rijvaardigheid voor aanvang van een rit?",
        "opts": {
            27557: "Alleen beroepschauffeurs moeten nadenken over rijvaardigheid.",
            27558: "Korte ritten maken fitnessregels irrelevant.",
            27559: "Koffie vervangt wettelijk de behoefte aan rust.",
            27560: "Je bent verantwoordelijk om niet te rijden als je te moe, afgeleid of ziek bent.",
        },
    },
    # ── ID 230 ───────────────────────────────────────────────────────────
    230: {
        "q": "Wat moet je onthouden over documenten en wettelijke gereedheid voordat je rijdt in het Nederlandse verkeer?",
        "opts": {
            27561: "Alleen brandstofniveau telt voor een rit.",
            27562: "Als de rit kort is, doen registratie en verzekering er niet toe.",
            27563: "Wettelijke gereedheid telt alleen op snelwegen.",
            27564: "Bestuurder en voertuig moeten wettelijk gereed zijn, inclusief correct rijbewijs, registratie, verzekering en veilige staat.",
        },
    },
    # ── ID 231 ───────────────────────────────────────────────────────────
    231: {
        "q": "Wat is de juiste regel over het verschil tussen een regel kennen en toepassen?",
        "opts": {
            27565: "De regel kennen betekent dat je de weg nooit hoeft te scannen.",
            27566: "Toepassen telt alleen bij slecht weer.",
            27567: "Een veilige bestuurder kent de regel én past snelheid, positie en observatie op tijd aan.",
            27568: "Toepassen betekent sneller rijden om de situatie snel af te handelen.",
        },
    },
    # ── ID 232 ───────────────────────────────────────────────────────────
    232: {
        "q": "Wat moet je onthouden over hoe de Nederlandse theorie omgaat met kwetsbare weggebruikers?",
        "opts": {
            27569: "Ze worden in alle situaties behandeld zoals zwaar verkeer.",
            27570: "Ze verdienen extra aandacht omdat ze minder fysieke bescherming hebben.",
            27571: "Ze verliezen altijd voorrang omdat ze langzaam rijden.",
            27572: "Ze tellen alleen binnen de bebouwde kom.",
        },
    },
    # ── ID 233 ───────────────────────────────────────────────────────────
    233: {
        "q": "Wat moet je onthouden over je rijvaardigheid voor aanvang van een rit in het Nederlandse verkeer?",
        "opts": {
            27573: "Alleen beroepschauffeurs moeten nadenken over rijvaardigheid.",
            27574: "Koffie vervangt wettelijk de behoefte aan rust.",
            27575: "Korte ritten maken fitnessregels irrelevant.",
            27576: "Je bent verantwoordelijk om niet te rijden als je te moe, afgeleid of ziek bent.",
        },
    },
    # ── ID 234 ───────────────────────────────────────────────────────────
    234: {
        "q": "Welke stelling over het delen van Nederlandse wegen met fietsers en voetgangers is juist?",
        "opts": {
            27577: "Je moet kwetsbare weggebruikers verwachten en vroeg je snelheid en ruimte aanpassen.",
            27578: "Je mag aannemen dat fietsers altijd wachten op auto's.",
            27579: "Je hoeft alleen bij zebrapaden aan kwetsbare weggebruikers te denken.",
            27580: "Je moet rijden op de aangegeven maximum snelheid, ook als de ruimte krap aanvoelt.",
        },
    },
    # ── ID 235 ───────────────────────────────────────────────────────────
    235: {
        "q": "Welke optie komt het best overeen met de regel voor waarom theorie studeren belangrijk is vóór praktisch rijden?",
        "opts": {
            27581: "Het helpt je regels, gevaren en veilige beslissingen te herkennen vóór echte verkeerssituaties.",
            27582: "Het gaat alleen over het memoriseren van straatnamen.",
            27583: "Het vervangt de noodzaak om borden op de weg te observeren.",
            27584: "Het telt alleen voor beroepschauffeurs.",
        },
    },
    # ── ID 236 ───────────────────────────────────────────────────────────
    236: {
        "q": "Welke stelling over je rijvaardigheid voor aanvang van een rit is juist?",
        "opts": {
            27585: "Koffie vervangt wettelijk de behoefte aan rust.",
            27586: "Korte ritten maken fitnessregels irrelevant.",
            27587: "Je bent verantwoordelijk om niet te rijden als je te moe, afgeleid of ziek bent.",
            27588: "Alleen beroepschauffeurs moeten nadenken over rijvaardigheid.",
        },
    },
    # ── ID 237 ───────────────────────────────────────────────────────────
    237: {
        "q": "Wat is de juiste regel over waarom theorie studeren belangrijk is vóór praktisch rijden?",
        "opts": {
            27589: "Het vervangt de noodzaak om borden op de weg te observeren.",
            27590: "Het gaat alleen over het memoriseren van straatnamen.",
            27591: "Het helpt je regels, gevaren en veilige beslissingen te herkennen vóór echte verkeerssituaties.",
            27592: "Het telt alleen voor beroepschauffeurs.",
        },
    },
    # ── ID 238 ───────────────────────────────────────────────────────────
    238: {
        "q": "Wat moet je onthouden over de organisatie die de Nederlandse theorie- en praktijkexamens afneemt?",
        "opts": {
            27593: "De politie neemt het theorie-examen voor leerlingen af.",
            27594: "Verzekeringsmaatschappijen nemen het praktijkexamen af.",
            27595: "Het CBR is de organisatie die die examens afneemt.",
            27596: "De gemeente neemt alle rijexamens af.",
        },
    },
    # ── ID 239 ───────────────────────────────────────────────────────────
    239: {
        "q": "Welke optie komt het best overeen met de regel voor het delen van Nederlandse wegen met fietsers en voetgangers?",
        "opts": {
            27597: "Je moet rijden op de aangegeven maximum snelheid, ook als de ruimte krap aanvoelt.",
            27598: "Je moet kwetsbare weggebruikers verwachten en vroeg je snelheid en ruimte aanpassen.",
            27599: "Je mag aannemen dat fietsers altijd wachten op auto's.",
            27600: "Je hoeft alleen bij zebrapaden aan kwetsbare weggebruikers te denken.",
        },
    },
    # ── ID 240 ───────────────────────────────────────────────────────────
    240: {
        "q": "Je krijgt een Nederlandse theorievraag over het woord 'weggebruiker' in de verkeerstheorie. Welk antwoord is juist?",
        "opts": {
            27601: "Het betekent alleen mensen met een Nederlands rijbewijs.",
            27602: "Het omvat iedereen die de weg gebruikt, zoals automobilisten, fietsers, voetgangers, ruiters en trambestuurders.",
            27603: "Het sluit fietsers en voetgangers uit.",
            27604: "Het betekent alleen automobilisten.",
        },
    },
}


class Command(BaseCommand):
    help = "Seeds Dutch (NL) translations for Introduction to Dutch Driving questions"

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Preview without saving")

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        q_updated = q_skipped = o_updated = o_skipped = 0

        topic = DrivingTopic.objects.get(slug="introduction-to-dutch-driving")
        all_qs = list(topic.questions.order_by("id"))

        # Base questions still live at IDs 1-12; v3 additions are all IDs > 100
        # and map positionally: old ID 181→index 0, 182→index 1, … 240→index 59
        v3_questions = [q for q in all_qs if q.id > 100]

        for old_id, data in NL_DATA.items():
            if old_id <= 12:
                try:
                    question = DrivingQuestion.objects.get(pk=old_id)
                except DrivingQuestion.DoesNotExist:
                    self.stderr.write(f"Base question {old_id} not found — skipped")
                    q_skipped += 1
                    continue
            else:
                v3_index = old_id - 181  # 181→0, 182→1, …, 240→59
                if v3_index < 0 or v3_index >= len(v3_questions):
                    self.stderr.write(f"V3 question index {v3_index} (old ID {old_id}) out of range — skipped")
                    q_skipped += 1
                    continue
                question = v3_questions[v3_index]

            if not dry_run:
                question.question_text_nl = data["q"]
                question.save(update_fields=["question_text_nl"])
            q_updated += 1

            # Old option IDs were sequential (insertion order); sort them to get
            # the same order as current options sorted by (order, id).
            nl_opts_ordered = [nl_text for _, nl_text in sorted(data["opts"].items())]
            current_opts = list(question.options.order_by("order", "id"))

            if len(nl_opts_ordered) != len(current_opts):
                self.stderr.write(
                    f"Option count mismatch for Q{old_id} "
                    f'"{question.question_text[:50]}" — '
                    f"expected {len(nl_opts_ordered)}, got {len(current_opts)}"
                )

            for nl_text, opt in zip(nl_opts_ordered, current_opts):
                if not dry_run:
                    opt.option_text_nl = nl_text
                    opt.save(update_fields=["option_text_nl"])
                o_updated += 1

        mode = "[DRY RUN] " if dry_run else ""
        self.stdout.write(
            self.style.SUCCESS(
                f"{mode}Done — {q_updated} questions, {o_updated} options updated"
                + (f" ({q_skipped + o_skipped} skipped)" if q_skipped + o_skipped else "")
            )
        )
