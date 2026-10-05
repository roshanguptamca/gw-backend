"""Offline, deterministic original-bank authoring. Never run during an exam."""

import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dutch_exam_scenarios import CIVIC, CIVIC_DISTRACTORS, INTENT, KNM_THEMES, SCENARIOS  # noqa: E402

from apps.dutch_practice.blueprints import BANK_VERSION, catalog_formats  # noqa: E402

ROOT = Path(__file__).resolve().parents[1] / "apps/dutch_practice/data"
NAMES = [
    "Noor",
    "Amir",
    "Eva",
    "Luca",
    "Sara",
    "Milan",
    "Lotte",
    "Adam",
    "Nina",
    "Omar",
    "Sanne",
    "Yara",
    "Daan",
    "Lina",
    "Joris",
    "Rosa",
    "Sam",
    "Emma",
    "Timo",
    "Aya",
]
MONTHS = [
    "januari",
    "februari",
    "maart",
    "april",
    "mei",
    "juni",
    "juli",
    "augustus",
    "september",
    "oktober",
    "november",
    "december",
]
CITIES = [
    "Amsterdam",
    "Rotterdam",
    "Utrecht",
    "Den Haag",
    "Eindhoven",
    "Groningen",
    "Tilburg",
    "Almere",
    "Breda",
    "Nijmegen",
    "Apeldoorn",
    "Haarlem",
    "Arnhem",
    "Enschede",
    "Amersfoort",
    "Zwolle",
    "Leiden",
    "Delft",
    "Maastricht",
    "Deventer",
]


def context(level, set_number, index):
    scenario = SCENARIOS[(set_number - 1 + index * 3) % len(SCENARIOS)]
    topic, venue, audience, activity, rule, reason, exception, action, tradeoff = scenario
    venue = f"{venue} in {CITIES[set_number - 1]}"
    name = NAMES[(set_number + index) % len(NAMES)]
    day = 2 + (set_number * 3 + index) % 24
    month = MONTHS[(set_number + index) % 12]
    hour = 9 + (set_number + index) % 8
    date = f"{day} {month}"
    event = f"informatiebijeenkomst op {date} om {hour}.00 uur"
    title = f"{topic.replace('_', ' ').title()} — {venue}, {date}"
    if level == "A1":
        text = (
            f"{name} gaat naar {venue}. Er is een bijeenkomst op {date}. "
            f"De bijeenkomst begint om {hour}.00 uur. Het onderwerp is: {activity}. "
            "De bijeenkomst is gratis. Neem uw vragen mee. "
            f"U kunt zich bij {venue} aanmelden. Kom tien minuten voor het begin."
        )
    else:
        text = (
            f"Informatie voor {audience}\n\n"
            f"{venue[:1].upper() + venue[1:]} organiseert een {event}. Het onderwerp is {activity}. "
            f"{name} geeft uitleg en beantwoordt vragen. De bijeenkomst is gratis. "
            "Aanmelden kan tot twee dagen voor de bijeenkomst. Neem de bevestiging mee. "
            "Deelnemers worden gevraagd tien minuten voor de begintijd aanwezig te zijn.\n\n"
            f"De belangrijkste afspraak is dat {rule}. Deze afspraak bestaat omdat {reason}. "
            f"Let op: {exception}. Wie twijfelt of deze uitzondering van toepassing is, "
            f"kan vooraf contact opnemen met {venue}. De aanbevolen volgende stap is: {action}. "
            "Een vraag stellen verplicht u niet om aan een activiteit deel te nemen."
        )
        if level in ("B1", "B2"):
            text += (
                f"\n\nIn de afgelopen maanden kreeg {venue} vragen over de bereikbaarheid van de dienstverlening. "
                f"Daarom licht {name} niet alleen de procedure toe, maar bespreekt ook de reden achter de afspraak. "
                "Een deelnemer kan een eigen situatie voorleggen. Daarbij is het belangrijk onderscheid te maken "
                "tussen de algemene regel en de genoemde uitzondering. Een uitzondering betekent namelijk niet "
                "dat de regel voor iedereen vervalt. De organisator zal de persoonlijke situatie niet in het "
                "openbare verslag opnemen.\n\n"
                f"Er is ook een praktisch nadeel om rekening mee te houden: {tradeoff}. "
                "Deelnemers hoeven het niet met ieder voorstel eens te zijn. Wel vraagt de organisator om "
                "een concreet alternatief en een toelichting op de gevolgen daarvan. Na de bijeenkomst krijgen "
                "de aangemelde deelnemers een samenvatting. Daarin staan de besproken vervolgstappen, niet "
                "de persoonlijke gegevens van de aanwezigen."
            )
        if level == "B2":
            text += (
                "\n\nDe voorgestelde aanpak wordt voorlopig niet als definitief beleid beschouwd. "
                "Volgens de organisator kan een procedure die op papier efficiënt lijkt in de praktijk "
                "voor bepaalde groepen juist een hogere drempel opleveren. Dat is geen pleidooi om alle "
                "afspraken af te schaffen: zonder een voorspelbare werkwijze is gelijke behandeling evenmin "
                "vanzelfsprekend. Het gaat erom de uitvoering te toetsen, in plaats van alleen het aantal "
                "afgehandelde aanvragen als succesmaatstaf te nemen.\n\n"
                "Om die reden wordt na drie maanden zowel de bereikbaarheid als de duidelijkheid van de "
                "informatie onderzocht. De organisatie verzamelt reacties van deelnemers én van mensen "
                "die wel belangstelling hadden maar niet kwamen. Als uitsluitend aanwezigen worden bevraagd, "
                "blijven de ervaringen van de tweede groep immers buiten beeld. Een hoge tevredenheid onder "
                "de bezoekers zou dan ten onrechte kunnen worden uitgelegd als bewijs dat iedereen toegang heeft. "
                "De uitkomsten worden gezamenlijk besproken voordat de werkwijze structureel wordt aangepast."
            )
    questions = [
        (
            "Wat is het onderwerp van de bijeenkomst?",
            [activity.capitalize(), "Een nieuwe leidinggevende kiezen", "De jaarlijkse contributie vaststellen"],
            f"De tekst noemt {activity} als onderwerp.",
            "main_idea",
        ),
        (
            "Hoe laat begint de bijeenkomst?",
            [f"Om {hour}.00 uur", f"Om {hour - 1}.00 uur", f"Om {hour + 1}.00 uur"],
            f"De genoemde begintijd is {hour}.00 uur; tien minuten eerder komen verandert de begintijd niet.",
            "detail",
        ),
        (
            "Wat moeten aangemelde deelnemers meenemen?",
            [
                "De bevestiging van hun aanmelding",
                "Een ingevuld evaluatieformulier",
                "Het verslag van een eerdere bijeenkomst",
            ],
            "De tekst vraagt om de bevestiging; het verslag volgt pas na de bijeenkomst.",
            "detail",
        ),
        (
            "Waarom is de algemene afspraak ingevoerd?",
            [
                reason.capitalize(),
                "Om de bijeenkomst uitsluitend online te houden",
                "Om alle uitzonderingen af te schaffen",
            ],
            f"De tekst geeft deze reden: {reason}.",
            "cause",
        ),
        (
            "Welke vervolgstap wordt aanbevolen?",
            [
                action.capitalize(),
                "Zonder verdere informatie wachten op een automatisch besluit",
                "Eerst een samenvatting van de toekomstige bijeenkomst opsturen",
            ],
            f"De aanbevolen stap staat expliciet in de tekst: {action}.",
            "action",
        ),
        (
            (
                "Waarom verzamelt de organisatie ook reacties van mensen die niet kwamen?"
                if level == "B2"
                else "Wat betekent de genoemde uitzondering voor de algemene regel?"
            ),
            (
                [
                    "Om te onderzoeken welke drempels bezoekerscijfers niet laten zien",
                    "Om aanmeldingen achteraf verplicht te maken",
                    "Om tevreden bezoekers niet meer te hoeven spreken",
                ]
                if level == "B2"
                else [
                    "De regel blijft gelden; de uitzondering geldt alleen in de beschreven situatie",
                    "De regel is voor alle deelnemers afgeschaft",
                    "De regel geldt alleen na de bijeenkomst",
                ]
            ),
            (
                "Alleen aanwezigen bevragen kan uitsluiting onzichtbaar maken."
                if level == "B2"
                else "Een specifieke uitzondering laat de algemene afspraak voor andere situaties intact."
            ),
            "inference",
        ),
        (
            "Waarom vraagt de organisator om een concreet alternatief?",
            [
                "Om verschillende voorstellen en hun gevolgen te kunnen bespreken",
                "Om te voorkomen dat deelnemers een eigen mening geven",
                "Om de bijeenkomst zonder discussie af te sluiten",
            ],
            "Een alternatief met gevolgen maakt een inhoudelijke vergelijking mogelijk.",
            "reasoning",
        ),
        (
            "Wat staat in de samenvatting na de bijeenkomst?",
            [
                "De besproken vervolgstappen",
                "Alle persoonlijke gegevens van aanwezigen",
                "Alleen de namen van afwezige deelnemers",
            ],
            "De samenvatting beschrijft de vervolgstappen en bevat geen persoonlijke gegevens.",
            "detail",
        ),
    ]
    if level == "B2":
        questions = [
            (
                "Welke omschrijving past het best bij het doel van dit bericht?",
                [
                    "Een werkwijze toelichten en verzamelen welke gevolgen die voor verschillende groepen heeft",
                    "Aankondigen dat alle bestaande afspraken definitief worden afgeschaft",
                    "Aantonen dat de huidige dienstverlening al voor iedereen even toegankelijk is",
                ],
                "Het bericht combineert uitleg met onderzoek naar de uitvoering; het beleid is nog niet definitief.",
                "main_idea",
            ),
            (
                "Waarom is tevredenheid onder aanwezigen geen sluitend bewijs van goede bereikbaarheid?",
                [
                    "Mensen die vanwege een drempel wegblijven, kunnen in die meting ontbreken",
                    "Tevreden deelnemers hebben per definitie geen geldige mening",
                    "Bereikbaarheid kan uitsluitend door het aantal medewerkers worden vastgesteld",
                ],
                "De tekst waarschuwt dat ervaringen van niet-bezoekers buiten beeld kunnen blijven.",
                "evaluation",
            ),
            (
                "Welke combinatie van informatie is volgens het bericht juist?",
                [
                    "Deelnemers kunnen een persoonlijke situatie bespreken, maar persoonsgegevens komen niet in het openbare verslag",
                    "Persoonlijke situaties worden niet besproken, maar persoonsgegevens worden wel gepubliceerd",
                    "Deelnemers mogen alleen reageren als hun persoonsgegevens openbaar worden gemaakt",
                ],
                "De passage over eigen situaties en die over de samenvatting maken onderscheid tussen bespreken en publiceren.",
                "integration",
            ),
            (
                "Hoe moet de genoemde uitzondering worden geïnterpreteerd?",
                [
                    "Als een mogelijkheid voor de beschreven situatie, niet als afschaffing van de algemene regel",
                    "Als bewijs dat de algemene regel nooit wordt toegepast",
                    "Als een nieuwe algemene regel die iedere deelnemer automatisch vrijstelt",
                ],
                "Een specifieke uitzondering betekent volgens de tekst niet dat de regel voor iedereen vervalt.",
                "interpretation",
            ),
            (
                "Waarom wil de organisator alternatieven samen met hun gevolgen bespreken?",
                [
                    "Om efficiëntie en toegankelijkheid tegen elkaar af te kunnen wegen",
                    "Om ieder afwijkend voorstel zonder onderzoek af te wijzen",
                    "Om de procedure uitsluitend op aantallen afgehandelde aanvragen te beoordelen",
                ],
                "De tekst beschrijft een afweging: een efficiënte procedure kan voor bepaalde groepen een drempel zijn.",
                "reasoning",
            ),
            questions[5],
            questions[6],
            questions[7],
        ]
    if level == "A1":
        questions = [
            questions[0],
            questions[1],
            (
                "Wat kost de bijeenkomst?",
                ["Niets", "Tien euro", "Twintig euro"],
                "De tekst zegt dat de bijeenkomst gratis is.",
                "detail",
            ),
        ]
    return {
        "topic": topic,
        "title": title,
        "text": text,
        "questions": questions,
        "name": name,
        "activity": activity,
        "action": action,
        "intent": INTENT[topic],
        "reason": reason,
        "date": date,
        "venue": venue,
    }


def base_question(level, skill, number, position, task_type, topic):
    return {
        "id": f"v3-{level.lower()}-{skill}-{number:02d}-{position:02d}",
        "level": level,
        "skill": skill,
        "setNumber": number,
        "bankVersion": BANK_VERSION,
        "provenance": "original",
        "reviewStatus": "draft",
        "difficulty": level,
        "topic": topic,
        "taskType": task_type,
        "sourceIds": [],
    }


def objective(level, skill, number, spec):
    counts = (
        [8, 8, 8, 7, 7, 1, 1]
        if skill == "listening" and level in ("B1", "B2")
        else [spec["count"] // spec["groups"]] * spec["groups"]
    )
    output = []
    for group, count in enumerate(counts):
        ctx = context(level, number, group)
        group_id = f"v3-{level.lower()}-{skill}-{number:02d}-g{group:02d}"
        for within in range(count):
            task_type = "video_listening" if group >= 5 and skill == "listening" and level in ("B1", "B2") else skill
            prompt, options, explanation, target = ctx["questions"][within % len(ctx["questions"])]
            if skill == "listening":
                prompt = prompt.replace("de tekst", "het fragment")
            question = base_question(level, skill, number, len(output), task_type, ctx["topic"])
            question.update(
                {
                    "groupId": group_id,
                    "groupOrder": group,
                    "withinGroup": within,
                    "title": ctx["title"],
                    "prompt": prompt,
                    "options": options,
                    "answer": 0,
                    "explanation": explanation,
                    "target": target,
                }
            )
            if skill == "reading":
                question["text"] = ctx["text"]
            else:
                # NT2 segments are separately played once after each question's preview.
                # Each segment supplies the full context required for its own question.
                if level in ("B1", "B2"):
                    paragraphs = ctx["text"].split("\n\n")
                    segment = (
                        paragraphs[0] + " " + paragraphs[1]
                        if within <= 2
                        else (
                            paragraphs[2]
                            if within in (3, 4)
                            else (
                                " ".join(paragraphs[-2:])
                                if within == 5 and level == "B2"
                                else paragraphs[3] if within == 5 else paragraphs[4]
                            )
                        )
                    )
                    if level == "B2":
                        segment = (
                            " ".join(paragraphs[-2:])
                            if within in (1, 5)
                            else (
                                paragraphs[3] + " " + paragraphs[4]
                                if within in (2, 7)
                                else (
                                    paragraphs[2] + " " + paragraphs[3]
                                    if within == 3
                                    else (
                                        paragraphs[4] + " " + paragraphs[5]
                                        if within in (4, 6)
                                        else paragraphs[1] + " " + paragraphs[5]
                                    )
                                )
                            )
                        )
                    question["transcript"] = (
                        f"{ctx['name']} spreekt namens {ctx['venue']} over de bijeenkomst op {ctx['date']}. " + segment
                    )
                    question["mediaCode"] = (
                        "v3-clip-" + hashlib.sha256(question["transcript"].encode()).hexdigest()[:24]
                    )
                else:
                    question["mediaCode"] = group_id + "-audio"
                    question["transcript"] = ctx["text"].replace("\n", " ")
                question["mediaKind"] = "video" if task_type == "video_listening" else "audio"
            output.append(question)
    return output


def productive(level, skill, number, spec):
    output = []
    for task_type, count in spec["mix"].items():
        for _ in range(count):
            position = len(output)
            ctx = context(level, number, position)
            question = base_question(level, skill, number, position, task_type, ctx["topic"])
            question.update({"groupId": question["id"], "groupOrder": position, "withinGroup": 0})
            audience = f"{ctx['venue']}, voor een bijeenkomst op {ctx['date']}"
            if skill == "speaking":
                question["prompt"] = (
                    f"U spreekt met {ctx['name']} over {ctx['activity']} bij {ctx['venue']}. "
                    f"Uw afspraak is op {ctx['date']}. Vertel waarom u komt en stel een passende vraag."
                )
                if task_type in ("medium", "long"):
                    question[
                        "prompt"
                    ] += " Beschrijf ook een mogelijk probleem, stel een oplossing voor en leg uit waarom die oplossing helpt."
                if level == "B2":
                    question[
                        "prompt"
                    ] += (
                        " Licht uw standpunt toe en maak duidelijk welke beperking of voorwaarde bij uw voorstel hoort."
                    )
                if task_type == "long":
                    question["prompt"] += (
                        " Bespreek twee voordelen en een nadeel van uw voorstel. Vergelijk uw voorstel met een alternatief "
                        "en sluit af met een gemotiveerde aanbeveling."
                    )
                question["preparationSeconds"] = 60 if task_type == "long" else 15
                question["responseSeconds"] = 120 if task_type == "long" else 30 if task_type == "medium" else 20
                question["modelAnswer"] = (
                    f"Ik kom op {ctx['date']} omdat ik meer wil weten over {ctx['activity']}. "
                    "Hoe kan ik mij voorbereiden?"
                )
                if level == "A2":
                    if task_type == "video_prompt":
                        question["transcript"] = question["prompt"]
                        question["prompt"] = (
                            "Bekijk de originele oefenvideo. Vertel waarom u komt en stel een passende vraag."
                        )
                        question["mediaCode"] = question["id"] + "-video"
                        question["mediaKind"] = "video"
                    elif task_type == "one_picture":
                        question["picturePanels"] = [{"kind": "calendar", "label": f"{ctx['date']}: {ctx['activity']}"}]
                        question["prompt"] = (
                            f"Bekijk het plaatje. U spreekt met {ctx['name']} bij {ctx['venue']}. "
                            "Vertel welke afspraak u heeft en wat u meer wilt weten."
                        )
                    elif task_type == "two_pictures":
                        question["picturePanels"] = [
                            {"kind": "place", "label": ctx["venue"]},
                            {"kind": "calendar", "label": ctx["date"]},
                        ]
                        question["prompt"] = (
                            f"Bekijk de twee plaatjes. Vertel {ctx['name']} waar uw afspraak is en op welke dag u komt. "
                            "Stel ook een passende vraag."
                        )
                        question["modelAnswer"] = (
                            f"Mijn afspraak is op {ctx['date']} bij {ctx['venue']}. Hoe kan ik mij voorbereiden?"
                        )
                    else:
                        question["picturePanels"] = [
                            {"kind": "information", "label": f"Lees de informatie over {ctx['activity']}."},
                            {"kind": "place", "label": f"Meld u aan bij {ctx['venue']}."},
                            {"kind": "calendar", "label": f"Ga naar de afspraak op {ctx['date']}."},
                        ]
                        question["prompt"] = (
                            f"Bekijk de drie plaatjes over uw afspraak bij {ctx['venue']}. "
                            "Vertel wat u eerst, daarna en ten slotte doet."
                        )
                        question["modelAnswer"] = (
                            f"Eerst lees ik de informatie over {ctx['activity']}. Daarna meld ik mij aan bij {ctx['venue']}. "
                            f"Ten slotte ga ik naar de afspraak op {ctx['date']}."
                        )
                if task_type in ("medium", "long"):
                    question["modelAnswer"] += (
                        " Ik werk overdag en kan daarom niet altijd komen. Mijn voorstel is om ook een "
                        "avondbijeenkomst aan te bieden. Dan kunnen mensen met een dagdienst deelnemen."
                    )
                if task_type == "long":
                    question["modelAnswer"] += (
                        " Een tweede voordeel is dat we vooraf vragen kunnen verzamelen. "
                        "Een nadeel is dat medewerkers extra tijd nodig hebben. Als alternatief kunnen we "
                        "de uitleg schriftelijk geven, maar dan is er minder gelegenheid om vragen te stellen. "
                        "Daarom adviseer ik een avondbijeenkomst met een korte schriftelijke samenvatting."
                    )
            else:
                if task_type == "sentence":
                    question["prompt"] = (
                        f"U schrijft aan {audience}. Maak één volledige zin: "
                        f"Ik wil meer weten over {ctx['activity']}, omdat …"
                    )
                    if level == "B2":
                        question["prompt"] = (
                            f"U schrijft aan {audience}. Maak de zin grammaticaal en inhoudelijk af: "
                            f"Hoewel ik meer wil weten over {ctx['activity']}, kan ik alleen deelnemen als …"
                        )
                elif task_type == "form":
                    question["prompt"] = (
                        f"Vul een aanmeldformulier in voor {ctx['activity']} bij {ctx['venue']}, op {ctx['date']}. "
                        "Schrijf uw naam (gebruik een verzonnen naam), de gewenste datum en een vraag voor de bijeenkomst. "
                        "Gebruik geen echte privégegevens."
                    )
                elif task_type == "partial":
                    question["prompt"] = (
                        f"Vul dit bericht aan {ctx['venue']} aan. Het begin staat al vast: "
                        f"'Ik wil op {ctx['date']} naar uw bijeenkomst over {ctx['activity']} komen.' "
                        "Voeg twee of drie zinnen toe: stel een praktische vraag, geef een reden voor uw vraag "
                        "en vraag om een reactie. U hoeft het begin niet opnieuw te schrijven."
                    )
                else:
                    question["prompt"] = (
                        f"Schrijf {'een kort bericht' if task_type in ('message', 'partial', 'practical') else 'een duidelijke tekst'} "
                        f"aan {audience}. U wilt deelnemen maar hebt nog een vraag over {ctx['activity']}. "
                        "Geef aan waarom u contact opneemt, stel uw vraag en vraag om een reactie."
                    )
                    if task_type in ("short_text", "medium_text"):
                        question["prompt"] += " Beschrijf een praktisch probleem en doe een haalbaar voorstel."
                    if task_type == "medium_text":
                        question["prompt"] += (
                            " Gebruik deze gegevens uit een fictieve enquête: 48 deelnemers willen een avondbijeenkomst, "
                            "32 willen een middagbijeenkomst en 20 hebben geen voorkeur. Vergelijk de mogelijkheden, "
                            "noem een beperking van deze gegevens en motiveer uw aanbeveling. Richtlengte: 150–200 woorden."
                        )
                question["modelAnswer"] = (
                    f"Beste medewerker, ik wil op {ctx['date']} deelnemen aan de bijeenkomst over {ctx['activity']}. "
                    f"Kunt u uitleggen hoe ik mij kan voorbereiden? Ik wil graag {ctx['intent']}. "
                    "Kunt u mij laten weten of dat mogelijk is? Met vriendelijke groet, Noor."
                )
                if task_type == "medium_text":
                    question["modelAnswer"] = (
                        f"Geachte medewerker, ik schrijf over de bijeenkomst over {ctx['activity']} op {ctx['date']}. "
                        "Ik stel voor de bijeenkomst 's avonds te organiseren. In de enquête kiezen 48 deelnemers voor "
                        "de avond en 32 voor de middag; 20 hebben geen voorkeur. Een avondbijeenkomst past dus bij de "
                        "grootste groep, maar niet bij iedereen. Bovendien weten we niet of mensen die de enquête niet "
                        "hebben ingevuld dezelfde voorkeur hebben. De cijfers alleen bewijzen daarom niet dat dit "
                        "voor alle belangstellenden de beste keuze is. Een alternatief is twee kleinere bijeenkomsten "
                        "op verschillende tijden. Dat geeft meer mensen de kans om te komen, maar vraagt extra inzet "
                        "van medewerkers. Ik adviseer voorlopig één avondbijeenkomst, met een mogelijkheid om vooraf "
                        "vragen in te sturen. Daarna kunnen we ook reacties verzamelen van mensen die niet konden komen. "
                        "Zo kan een volgende keuze worden gebaseerd op meer dan alleen de antwoorden van de huidige "
                        "deelnemers. Kunt u laten weten of dit voorstel haalbaar is? Met vriendelijke groet, Noor."
                    )
                if task_type == "sentence":
                    question["modelAnswer"] = (
                        f"Ik wil meer weten over {ctx['activity']}, omdat ik mij goed wil voorbereiden."
                    )
                    if level == "B2":
                        question["modelAnswer"] = (
                            f"Hoewel ik meer wil weten over {ctx['activity']}, kan ik alleen deelnemen als "
                            "de bijeenkomst buiten mijn werktijd plaatsvindt."
                        )
                if task_type == "form":
                    question["modelAnswer"] = f"Naam: Noor. Datum: {ctx['date']}. Vraag: Hoe kan ik mij voorbereiden?"
            question["criteria"] = [
                "Taakuitvoering: beantwoord alle gevraagde onderdelen en blijf bij de beschreven situatie.",
                "Samenhang: gebruik een begrijpelijke volgorde en passende verbindingswoorden.",
                f"Woordenschat: gebruik woorden die passen bij {ctx['topic'].replace('_', ' ')} en het niveau {level}.",
                "Grammatica: maak begrijpelijke zinnen; controleer werkwoordsvormen en woordvolgorde.",
                (
                    "Verstaanbaarheid: spreek duidelijk en beoordeel of een luisteraar uw boodschap begrijpt."
                    if skill == "speaking"
                    else "Register: kies een passende aanspreekvorm en toon voor de ontvanger."
                ),
            ]
            question["rubric"] = {
                "scale": {
                    "0": "Nog niet: ontbreekt of belemmert begrip",
                    "1": "Gedeeltelijk: meestal begrijpelijk",
                    "2": "Voldoende voor deze oefentaak: volledig en begrijpelijk",
                },
                "dimensions": question["criteria"],
                "notice": "Zelfbeoordeling, geen officiële score of voorspelling van slagen.",
            }
            output.append(question)
    return output


def civic(number, spec):
    questions = []
    selected = []
    for theme, pool in KNM_THEMES.items():
        offset = (number - 1) % len(pool)
        rotated = pool[offset:] + pool[:offset]
        selected.extend((theme, item) for item in rotated[:5])
    for index, (theme, principle) in enumerate(selected):
        topic, situation, correct, distractor1, distractor2, explanation = CIVIC[principle]
        distractor1, distractor2 = CIVIC_DISTRACTORS[principle]
        person = NAMES[(number + index) % len(NAMES)]
        question = base_question("A2", "knm", number, index, "civic_scenario", topic)
        # Two uses of a principle concern different contexts/people; no duplicated prompt in an attempt.
        variant = f"Op {number + 1} {MONTHS[number % 12]} vraagt deze persoon om advies."
        question.update(
            {
                "groupId": f"v3-knm-{number:02d}-{theme}",
                "groupOrder": index // 5,
                "withinGroup": index % 5,
                "theme": theme,
                "text": f"{person} woont in Nederland. {situation} {variant}",
                "prompt": f"Welk antwoord past het best bij de situatie van {person}?",
                "options": [correct, distractor1, distractor2],
                "answer": 0,
                "explanation": explanation,
                "target": "civic_application",
                "transcript": situation,
                "mediaCode": f"v3-knm-principle-{principle:02d}",
                "mediaKind": "audio",
            }
        )
        questions.append(question)
    return questions


def main():
    questions = []
    for spec in catalog_formats():
        for number in range(1, 21):
            if spec["skill"] == "knm":
                items = civic(number, spec)
            elif spec["skill"] in ("reading", "listening"):
                items = objective(spec["level"], spec["skill"], number, spec)
            else:
                items = productive(spec["level"], spec["skill"], number, spec)
            assert len(items) == spec["count"], spec
            assert Counter(q["taskType"] for q in items) == Counter(spec["mix"]), spec
            assert len({(q.get("text", q.get("transcript", "")), q["prompt"]) for q in items}) == len(items)
            questions.extend(items)
    stimuli = {
        (
            q["level"],
            q["skill"],
            q.get("text", q.get("transcript", "")),
            q["prompt"],
            json.dumps(q.get("picturePanels", []), sort_keys=True),
        )
        for q in questions
    }
    assert len(stimuli) == len(questions), "Duplicate learner stimulus in original bank"
    path = ROOT / "exam-bank-v3.json"
    if path.exists():
        raise SystemExit("Refusing to overwrite a released bank. Use a new version and migration.")
    path.write_text(
        json.dumps(
            {"version": BANK_VERSION, "copyright": "Original GuideWisey teaching material.", "questions": questions},
            ensure_ascii=False,
            indent=2,
        )
        + "\n"
    )
    print(f"Authored {len(questions)} questions/tasks in {len(catalog_formats()) * 20} complete sets.")


if __name__ == "__main__":
    main()
