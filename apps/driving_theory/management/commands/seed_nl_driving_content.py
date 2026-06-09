from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.driving_theory.models import DrivingLesson


LESSON_TRANSLATIONS = {
    "1": {
        "title_nl": "Aan de slag met Nederlandse wegen",
        "summary_nl": "Leer de essentiële feiten die elke beginner moet kennen voordat je de gedetailleerde regels bestudeert.",
        "exam_tips_nl": [
            "Als een antwoord zegt 'wees voorspelbaar en geef duidelijke signalen', is dit vaak de veiligste keuze.",
            "Woorden als 'altijd' en 'nooit' verdienen extra aandacht bij theorie-vragen."
        ],
        "common_mistakes_nl": [
            "Verwarring tussen de wettelijke minimumleeftijd en speciale begeleid-rijden-programma's.",
            "Vergeten dat fietsinfrastructuur een grote invloed heeft op normaal autorijden."
        ],
        "learning_objectives_nl": [
            "De basisregels kennen voor rijden in Nederland.",
            "Begrijpen hoe fietsers en voetgangers het rijgedrag beïnvloeden."
        ],
        "key_takeaways_nl": [
            "Rijd rechts en verwacht veel fietsers in elke stad.",
            "Zorg voor de juiste documenten en houd het voertuig wettelijk rijklaar."
        ],
        "sections": [
            {
                "title_nl": "Rijcultuur en basisprincipes",
                "content_nl": "Bestuurders in Nederland worden verwacht de weg te delen met veel verschillende gebruikers, met name fietsers, voetgangers, bussen en trams. Een goede bestuurder kent niet alleen de regels. Een goede bestuurder leest ook de omgeving en laat ruimte voor anderen om veilige keuzes te maken.\n\nNormaal rijd je aan de rechterkant van de weg en je haalt in aan de linkerkant, tenzij een bijzondere situatie anders toelaat. In steden en dorpen kunnen straten smal aanvoelen vanwege fietspaden, geparkeerde voertuigen en bezorgverkeer. Dat betekent een rustige snelheid, duidelijk richting aangeven en vroeg observeren als onderdeel van basisrijden, ook voordat je de meer gedetailleerde examenpunten leert.",
                "callout_boxes_nl": [
                    {
                        "type": "remember",
                        "text": "In het Nederlandse verkeer bepalen kwetsbare weggebruikers vaak hoeveel ruimte en snelheid je moet gebruiken."
                    },
                    {
                        "type": "tip",
                        "text": "Als je twijfelt, verminder dan eerst de snelheid. Gewonnen tijd is nooit een overhaaste beslissing waard."
                    }
                ],
                "examples_nl": [
                    "Op een smalle woonstraat rem je vroeg omdat een fietser een geparkeerde bestelwagen moet omrijden.",
                    "Op een bekende route scan je toch zorgvuldig de borden, want lokale regels kunnen veranderen bij scholen of wegwerkzaamheden."
                ]
            },
            {
                "title_nl": "Rijbewijs, documenten en wettelijke gereedheid",
                "content_nl": "Iemand rijdt normaal gesproken zelfstandig vanaf de leeftijd van 18 jaar, hoewel jongere leerlingen kunnen deelnemen aan begeleid-rijden-programma's zoals 2toDrive. Het voertuig moet verzekerd zijn, correct geregistreerd zijn en in veilige staat worden gehouden. Een bestuurder is ook verantwoordelijk voor het rijvaardig zijn en voor het controleren of verlichting, banden en spiegels bruikbaar zijn voor een rit.\n\nTheoriestudie gaat niet alleen over het slagen voor een examen. Het helpt je te herkennen hoe afzonderlijke plichten samenhangen met echt rijden. Als je zicht wordt geblokkeerd door vuil op de ramen, als je verzekering niet in orde is, of als je een waarschuwingslampje negeert, creëer je risico voordat het voertuig zelfs maar begint te bewegen.",
                "callout_boxes_nl": [
                    {
                        "type": "info",
                        "text": "Een legaal voertuig kan nog steeds onveilig zijn als zicht, bandenstatus of rijvaardigheid van de bestuurder slecht zijn."
                    },
                    {
                        "type": "warning",
                        "text": "Ga er nooit van uit dat een korte rit ontbrekende documenten of slechte concentratie verontschuldigt."
                    }
                ],
                "examples_nl": [
                    "Voor een winterrit verwijder je alle ijs van elk raam in plaats van alleen een klein kijkgat vrij te maken.",
                    "Je stelt een reis uit als je te moe bent om snelheid en afstand goed te beoordelen."
                ]
            }
        ]
    },
    "2": {
        "title_nl": "Andere weggebruikers herkennen",
        "summary_nl": "Leer hoe je fietsers, voetgangers, motoren en zwaar verkeer herkent en veilig met hen omgaat.",
        "exam_tips_nl": [
            "Kwetsbare weggebruikers krijgen altijd voorrang boven voertuigen wanneer dit veilig mogelijk is.",
            "Let goed op het onderscheid tussen een fietspad, een fietsstrook en een gewone rijbaan."
        ],
        "common_mistakes_nl": [
            "Voetgangers op een zebrapad over het hoofd zien.",
            "Het verschil tussen een fietspad (verplicht) en een fietsstrook (aanbevolen) vergeten."
        ],
        "learning_objectives_nl": [
            "Verschillende soorten weggebruikers herkennen.",
            "Begrijpen hoe je veilig omgaat met kwetsbare verkeersdeelnemers."
        ],
        "key_takeaways_nl": [
            "Fietsers, voetgangers en scooters hebben speciale rechten in Nederland.",
            "Houd altijd rekening met blinde hoeken bij grote voertuigen."
        ],
        "sections": [
            {
                "title_nl": "Fietsers en voetgangers begrijpen",
                "content_nl": "Nederland heeft het dichtstbijzijnde fietsnetwerk ter wereld. Fietsers rijden op fietspaden of fietsstroken en hebben vaak voorrang op bepaalde kruispunten. Een bestuurder moet herkennen wanneer een fietser de rijbaan kan oprijden, met name wanneer het fietspad eindigt of wanneer een fietser linksaf slaat.\n\nVoetgangers kunnen plotseling van richting veranderen, met name kinderen en ouderen. Een zebrapad geeft voetgangers het recht om over te steken en een bestuurder moet stoppen als iemand wacht of oversteekt.",
                "callout_boxes_nl": [
                    {
                        "type": "remember",
                        "text": "Een fietser die rechtdoor gaat heeft voorrang op een auto die rechtsaf slaat bij een kruispunt."
                    },
                    {
                        "type": "tip",
                        "text": "Controleer altijd de rechterzijspiegel voordat je rechtsaf slaat, ook in steden."
                    }
                ],
                "examples_nl": [
                    "Bij een school rij je langzamer en let je op kinderen die plotseling kunnen oversteken.",
                    "Op een kruispunt geef je voorrang aan een fietser die rechtdoor gaat wanneer jij rechtsaf wilt slaan."
                ]
            },
            {
                "title_nl": "Motoren, bromfietsen en groot verkeer",
                "content_nl": "Motoren en bromfietsen zijn kleiner en sneller dan auto's en kunnen moeilijk te zien zijn in spiegels. Een motorrijder kan snel naderen en zal niet altijd zichtbaar zijn in de dode hoek.\n\nVrachtwagens en bussen hebben grotere blinde vlekken dan personenauto's. Wanneer je een vrachtwagen volgt, verhoog dan je volgafstand. Als je de zijspiegels van de vrachtwagen niet kunt zien, kan de chauffeur jou ook niet zien.",
                "callout_boxes_nl": [
                    {
                        "type": "warning",
                        "text": "Als je de chauffeur van een vrachtwagen niet in zijn spiegels kunt zien, ben jij ook niet zichtbaar voor hem."
                    },
                    {
                        "type": "tip",
                        "text": "Geef motoren extra ruimte bij het inhalen, omdat wind en wegoppervlak hun stabiliteit beïnvloedt."
                    }
                ],
                "examples_nl": [
                    "Je wacht extra lang voordat je een vrachtwagen inhaalt, omdat zijn lengte betekent dat de inhaalmanoeuvre meer tijd kost.",
                    "Bij het wegrijden van de stoeprand controleer je eerst de blinde hoek rechts op fietsers."
                ]
            }
        ]
    },
    "3": {
        "title_nl": "Verkeersborden efficiënt lezen",
        "summary_nl": "Leer hoe je verkeersborden snel herkent en reageert op basis van kleur, vorm en positie.",
        "exam_tips_nl": [
            "Ronde borden met rode rand zijn geboden of verboden. Driehoekige borden zijn waarschuwingen.",
            "Blauwe ronde borden zijn verplichtingen, zoals een verplicht rijwielpad."
        ],
        "common_mistakes_nl": [
            "Gele waarschuwingsborden verwarren met voorrangsborden.",
            "Tijdelijke borden op wegwerkzaamheden negeren omdat ze anders uitzien dan permanente borden."
        ],
        "learning_objectives_nl": [
            "Verkeersborden categoriseren op vorm en kleur.",
            "Correct reageren op gebodsborden, verbodsborden en waarschuwingsborden."
        ],
        "key_takeaways_nl": [
            "Rood betekent verbod of gevaar. Blauw betekent verplichting.",
            "Lees borden in combinatie met de omgeving, niet geïsoleerd."
        ],
        "sections": [
            {
                "title_nl": "Borden herkennen aan vorm en kleur",
                "content_nl": "Verkeersborden in Nederland volgen Europese standaarden. Driehoekige borden met rode rand waarschuwen voor gevaar. Ronde borden met rode rand verbieden iets, terwijl ronde blauwe borden iets verplichten. Vierkante of rechthoekige borden geven informatie.\n\nDe kleur en vorm vertellen je al veel voordat je de symbolen leest. Een driver die dit systeem begrijpt, kan sneller en zelfverzekerder reageren, zelfs bij een onbekend bord.",
                "callout_boxes_nl": [
                    {
                        "type": "remember",
                        "text": "Driehoekig rood = waarschuwing. Rond rood = verbod. Rond blauw = verplichting."
                    },
                    {
                        "type": "tip",
                        "text": "Wanneer je twijfelt over een bord, kies dan de veiligste interpretatie en controleer later."
                    }
                ],
                "examples_nl": [
                    "Je ziet een rood driehoekig bord met een kindersymbool en remt automatisch omdat je een school-/speelgebied verwacht.",
                    "Een blauw rond bord met een pijl omhoog vertelt je dat je de rijbaan moet volgen, zonder links of rechts te rijden."
                ]
            },
            {
                "title_nl": "Tijdelijke borden en wegwerkzaamheden",
                "content_nl": "Tijdelijke borden, vaak op oranje achtergrond of op draagbare borden, gelden zolang de situatie aanwezig is. Ze kunnen de normale regels tijdelijk vervangen. Een tijdelijk maximumsnelheidsbord op een wegwerkzaamhedenzone vervangt het permanente bord.\n\nBewegwijzering nabij wegwerkzaamheden moet snel worden gelezen. Rij niet harder dan aangegeven, ook al lijkt de weg leeg, want werkers kunnen aanwezig zijn buiten uw zichtlijn.",
                "callout_boxes_nl": [
                    {
                        "type": "warning",
                        "text": "Tijdelijke snelheidslimieten bij wegwerkzaamheden zijn wettelijk verplicht en kunnen gecontroleerd worden."
                    },
                    {
                        "type": "info",
                        "text": "Oranje pijlborden bij wegwerkzaamheden geven aan welke rijstrook je moet volgen."
                    }
                ],
                "examples_nl": [
                    "Je rijdt 30 km/h door een wegwerkzaamhedenzone zelfs als het leeg lijkt, omdat het bord dit vereist.",
                    "Je volgt de oranje pijlen die de versmalde rijbaan aanwijzen en rijdt voorzichtig langs de afzetting."
                ]
            }
        ]
    },
    "4": {
        "title_nl": "Dagelijkse verkeersregels in beweging",
        "summary_nl": "Begrijp de basisregels die gelden bij elke rit: rijbaan, inhalen, afslaan en rijden in de file.",
        "exam_tips_nl": [
            "Rijstrookdiscipline is een veelgestelde examenvraag: rij zo ver rechts als veilig mogelijk.",
            "Geef altijd richting aan voordat je van rijstrook wisselt, ook op wegen zonder ander verkeer."
        ],
        "common_mistakes_nl": [
            "Niet tijdig richting aangeven voor een manoeuvre.",
            "Rijden op de linkerrijstrook terwijl de rechterrijstrook vrij is."
        ],
        "learning_objectives_nl": [
            "Basisrijregels kennen voor rijstrookgebruik en inhalen.",
            "Correct rijden in files en bij afslagen."
        ],
        "key_takeaways_nl": [
            "Houd rechts tenzij je inhaalt.",
            "Geef altijd richting aan en controleer je spiegels."
        ],
        "sections": [
            {
                "title_nl": "Rijstrookgebruik en inhalen",
                "content_nl": "In Nederland rijd je zo ver mogelijk rechts op de rijbaan. Je haalt in via de linkerrijstrook en keert daarna terug naar rechts. Op snelwegen met drie rijstroken is de middelste rijstrook voor inhalen, de linkerrijstrook alleen voor snel voortgaand verkeer.\n\nVoor het inhalen controleer je achteruitkijkspiegel, buitenspiegel, blinde hoek, geef je richting aan, haal in en geef richting terug voor het terugkeren.",
                "callout_boxes_nl": [
                    {
                        "type": "remember",
                        "text": "Rij altijd terug naar rechts na het inhalen — de linkerrijstrook is geen rijstrook om op te blijven."
                    },
                    {
                        "type": "tip",
                        "text": "Controleer altijd drie keer: achteruitkijkspiegel, buitenspiegel, en blinde hoek."
                    }
                ],
                "examples_nl": [
                    "Op de snelweg haal je een vrachtwagen in via de middelste rijstrook en keer je daarna terug naar rechts.",
                    "Op een tweebaansweg wacht je tot de weg lang genoeg is vrij voordat je inhaalt."
                ]
            },
            {
                "title_nl": "Voorrang geven en afslaan",
                "content_nl": "Bij het afslaan moet je altijd richting aangeven en je positie aanpassen. Linksaf slaan vereist dat je naar het midden rijdt; rechtsaf slaan vereist dat je naar rechts rijdt.\n\nVoorrang geven aan tegenliggers bij linksafslaan is verplicht, tenzij een bord of markering anders aangeeft. In een file blijf je geduldig en laat je verkeer invoegen wanneer dit veilig is.",
                "callout_boxes_nl": [
                    {
                        "type": "info",
                        "text": "Bij linksafslaan geef je altijd voorrang aan tegenliggers, tenzij een bord anders aangeeft."
                    },
                    {
                        "type": "warning",
                        "text": "Rij niet op een kruispunt in als je ziet dat je er niet volledig doorheen kunt rijden zonder te blokkeren."
                    }
                ],
                "examples_nl": [
                    "Je wilt linksaf slaan bij een kruispunt en wacht op tegenliggers die voorrang hebben.",
                    "Op een drukke weg laat je een auto invoegen uit een zijstraat als er ruimte is."
                ]
            }
        ]
    },
    "5": {
        "title_nl": "Wie heeft voorrang?",
        "summary_nl": "Leer de voorrangsregels bij kruispunten, rotondes en speciale situaties.",
        "exam_tips_nl": [
            "Rechts heeft voorrang tenzij een bord of markering anders aangeeft.",
            "Een driehoekig bord met punt naar boven (voorrangsbord) verplicht je te stoppen of te wachten."
        ],
        "common_mistakes_nl": [
            "Aannemen dat een grote weg altijd voorrang heeft zonder het bord te controleren.",
            "Vergeten dat trams altijd voorrang hebben in Nederland."
        ],
        "learning_objectives_nl": [
            "Voorrangsregels begrijpen bij kruispunten en rotondes.",
            "Weten wanneer trams en hulpdiensten voorrang hebben."
        ],
        "key_takeaways_nl": [
            "Van rechts, tenzij een bord anders zegt.",
            "Trams hebben altijd voorrang."
        ],
        "sections": [
            {
                "title_nl": "Kruispunten en rechts-voor-links",
                "content_nl": "Bij een kruispunt zonder borden of markeringen geldt de regel: van rechts. Dit betekent dat je voorrang geeft aan voertuigen die van rechts komen. In de praktijk kennen de meeste kruispunten een bord of markering die aangeeft wie voorrang heeft.\n\nEen haaientanden-markering (driehoekjes op de rijbaan) betekent dat je voorrang moet geven. Een stopstreep betekent dat je volledig stopt, ook als er geen verkeer is.",
                "callout_boxes_nl": [
                    {
                        "type": "remember",
                        "text": "Haaientanden op de rijbaan = voorrang geven. Stopstreep = stoppen."
                    },
                    {
                        "type": "tip",
                        "text": "Controleer altijd of er haaientanden zijn voordat je een kruispunt oprijdt dat ongemarkeerd lijkt."
                    }
                ],
                "examples_nl": [
                    "Op een ongemarkeerd kruispunt geef je voorrang aan een auto die van rechts komt.",
                    "Je nadert een stopstreep bij een T-kruising en stopt volledig, ook al zie je geen verkeer."
                ]
            },
            {
                "title_nl": "Trams, hulpdiensten en bijzondere voertuigen",
                "content_nl": "Trams rijden op vaste rails en kunnen niet uitwijken. Ze hebben altijd voorrang, ook als dit niet expliciet is aangegeven. Een bestuurder moet zijn rijpad aanpassen zodat trams ongehinderd kunnen rijden.\n\nHulpdienstvoertuigen (brandweer, ambulance, politie) met actieve sirene en blauw zwaailicht hebben altijd voorrang. Je moet zo snel mogelijk de weg vrijmaken door rechts te gaan staan.",
                "callout_boxes_nl": [
                    {
                        "type": "warning",
                        "text": "Blokkeer nooit een tramrail, zelfs niet tijdelijk bij langzaamverkeer."
                    },
                    {
                        "type": "info",
                        "text": "Geef bij een hulpdienstvoertuig met sirene zo snel mogelijk de weg vrij aan de rechterkant."
                    }
                ],
                "examples_nl": [
                    "Je rijdt op een tramtraject en remt vroeg zodat de tram soepel door kan rijden.",
                    "Een ambulance nadert van achter met sirene; je rijdt naar rechts en stopt zodat hij voorbij kan."
                ]
            }
        ]
    },
    "6": {
        "title_nl": "De juiste snelheid kiezen",
        "summary_nl": "Begrijp maximumsnelheden, rijomstandigheden en wanneer je langzamer moet rijden.",
        "exam_tips_nl": [
            "De snelheidslimiet is een maximum, geen aanbevolen snelheid — pas aan op basis van de situatie.",
            "Bij regen, mist of duisternis moet je langzamer rijden dan de maximumsnelheid."
        ],
        "common_mistakes_nl": [
            "Vergeten dat schoolzones en woongebieden vaak 30 km/h zones zijn.",
            "De maximumsnelheid handhaven bij slechte weersomstandigheden."
        ],
        "learning_objectives_nl": [
            "Snelheidslimieten kennen voor verschillende wegtypes.",
            "Begrijpen wanneer je langzamer moet rijden dan de maximumlimiet."
        ],
        "key_takeaways_nl": [
            "Buiten bebouwde kom: 80 km/h, snelweg: 100-130 km/h, bebouwde kom: 50 km/h.",
            "Pas je snelheid altijd aan op de omstandigheden."
        ],
        "sections": [
            {
                "title_nl": "Snelheidslimieten in Nederland",
                "content_nl": "In Nederland gelden de volgende standaard snelheidslimieten: 50 km/h in bebouwde kom, 80 km/h buiten bebouwde kom op gewone wegen, 100 km/h op autowegen en 130 km/h op snelwegen (tenzij anders aangegeven). Op schooltijden of in woongebieden kunnen lagere limieten van 30 km/h gelden.\n\nSnelheidslimieten worden aangegeven met ronde borden met rode rand. Wanneer de limiet verandert, staat er een nieuw bord. Einde zone-borden met diagonale streep geven aan dat de beperking niet meer geldt.",
                "callout_boxes_nl": [
                    {
                        "type": "remember",
                        "text": "130 km/h op de snelweg geldt alleen als dit expliciet is aangegeven. Standaard is 100 km/h."
                    },
                    {
                        "type": "tip",
                        "text": "Zoek naar het beginbord van een bebouwde kom (wit bord met plaatsnaam) — daarna geldt 50 km/h."
                    }
                ],
                "examples_nl": [
                    "Je rijdt een snelweg op zonder snelheidsbord en houdt je standaard aan 100 km/h.",
                    "Je rijdt een woonwijk in en ziet een 30-bord — je past onmiddellijk je snelheid aan."
                ]
            },
            {
                "title_nl": "Aanpassen aan omstandigheden",
                "content_nl": "De maximumsnelheid is de hoogst toegestane snelheid onder ideale omstandigheden. Bij regen is het wegdek glad en is de remafstand groter — je moet langzamer rijden. Bij mist moet je kunnen stoppen binnen de afstand die je kunt zien.\n\nIn de nacht is de remafstand ook bij droog weer groter vanwege verminderd zicht. Houd meer afstand tot de voorligger bij slechte omstandigheden.",
                "callout_boxes_nl": [
                    {
                        "type": "warning",
                        "text": "Bij sneeuw of ijs kan je remafstand tienmaal groter zijn dan normaal — pas je snelheid drastisch aan."
                    },
                    {
                        "type": "info",
                        "text": "Bij mist met een zicht van minder dan 50 meter moet je mistlampen gebruiken en langzamer rijden."
                    }
                ],
                "examples_nl": [
                    "Bij hevige regen rijd je 60 km/h op een weg waar 80 km/h is toegestaan, vanwege verminderde grip.",
                    "Bij mist op de snelweg rijd je 60 km/h en gebruik je mistlampen, hoewel 130 km/h de limiet is."
                ]
            }
        ]
    },
    "7": {
        "title_nl": "Lijnen op de weg",
        "summary_nl": "Leer wat wegmarkeringen betekenen en hoe je ze correct volgt.",
        "exam_tips_nl": [
            "Een dubbele ononderbroken streep mag nooit worden overschreden.",
            "Haaientanden zijn voorrangsindicatoren op de rijbaan, niet alleen decoraties."
        ],
        "common_mistakes_nl": [
            "Een onderbroken streep aanzien voor een veilige overgang zonder te controleren.",
            "Vergeten dat gele markeringen (parkeerverbod) tijdelijk of permanent kunnen zijn."
        ],
        "learning_objectives_nl": [
            "Wegmarkeringen begrijpen voor rijstrookscheiding en voorrang.",
            "Weten wat markering in parkeergebieden betekent."
        ],
        "key_takeaways_nl": [
            "Ononderbroken streep = niet oversteken. Onderbroken = mag, maar controleer.",
            "Haaientanden = voorrang geven."
        ],
        "sections": [
            {
                "title_nl": "Rijbaanmarkeringen",
                "content_nl": "Rijbaanmarkeringen zijn lijnen en symbolen op het wegdek. Een ononderbroken witte lijn scheidt rijstroken die niet mogen worden overgestoken, tenzij het absoluut noodzakelijk is. Een onderbroken lijn mag worden overschreden na het controleren van het verkeer.\n\nEen dubbele middenlijn (twee ononderbroken lijnen) is een absoluut verbod om over te rijden. Gele lijnen geven parkeer- of stopverboden aan.",
                "callout_boxes_nl": [
                    {
                        "type": "remember",
                        "text": "Dubbele ononderbroken gele of witte lijn = nooit oversteken, ook niet voor parkeren."
                    },
                    {
                        "type": "tip",
                        "text": "Let op pijlen op de rijbaan — ze geven de verplichte rijrichting aan voor jouw rijstrook."
                    }
                ],
                "examples_nl": [
                    "Je nadert een onderbroken lijn en wil inhalen — je controleert of het vrij is en gaat dan voorbij.",
                    "Je ziet een dubbele ononderbroken gele lijn en rijdt er niet overheen, ook niet om te parkeren."
                ]
            },
            {
                "title_nl": "Parkeer- en stopmarkeringen",
                "content_nl": "Gele lijnen langs de stoeprand geven parkeer- of stopverboden aan. Een ononderbroken gele lijn betekent absoluut parkeerverbod. Een dubbele gele lijn kan een stopverbod betekenen.\n\nZigzagmarkeringen zijn te vinden bij zebrapaden en schoolingangen. Parkeren op deze markeringen is verboden en kan het zicht op overstekende voetgangers blokkeren.",
                "callout_boxes_nl": [
                    {
                        "type": "warning",
                        "text": "Parkeren op zigzagmarkeringen bij een zebrapad is verboden en gevaarlijk — je blokkeert het zicht."
                    },
                    {
                        "type": "info",
                        "text": "Blauwe parkeerzone-borden en markeringen geven aan dat je een parkeerschijf nodig hebt."
                    }
                ],
                "examples_nl": [
                    "Je ziet een ononderbroken gele lijn langs de stoeprand en zoekt een andere parkeerplaats.",
                    "Je parkeert niet op de zigzagmarkeringen voor een school, ook al haal je je kind op voor slechts twee minuten."
                ]
            }
        ]
    },
    "8": {
        "title_nl": "Uw voertuig veilig verlaten",
        "summary_nl": "Leer waar je veilig kunt parkeren, stoppen en hoe je uitstapt zonder gevaar.",
        "exam_tips_nl": [
            "Parkeren op een zebrapad, voor een oprit of op een kruispunt is altijd verboden.",
            "De 'Hollandse methode' voor uitstappen: gebruik je rechterhand om het portier te openen zodat je automatisch naar achteren kijkt."
        ],
        "common_mistakes_nl": [
            "Parkeren op een parkeervak dat duidelijk is gereserveerd voor gehandicapten zonder kenteken.",
            "Vergeten te controleren op fietsers in de fietssuggestiestrook voor het openen van het portier."
        ],
        "learning_objectives_nl": [
            "Wettige en verboden parkeerplaatsen kennen.",
            "Veilig uitstappen zonder andere weggebruikers in gevaar te brengen."
        ],
        "key_takeaways_nl": [
            "Controleer altijd op fietsers voor het openen van het portier.",
            "Ken de parkeerborden en markeringen in je omgeving."
        ],
        "sections": [
            {
                "title_nl": "Legale parkeerplaatsen",
                "content_nl": "Je mag parkeren op plaatsen die niet worden beperkt door borden of markeringen. Verboden parkeerzones zijn aangegeven met borden, gele strepen of zigzagmarkeringen. Bijzonder verboden plaatsen zijn: voor brandkranen, voor een inrit, op een kruispunt, op een zebrapad en in een tunnel.\n\nIn blauwe zones heb je een parkeerschijf nodig met de aankomsttijd. De maximum parkeerduur staat op het bord.",
                "callout_boxes_nl": [
                    {
                        "type": "remember",
                        "text": "Voorbij een stopverbodsbord mag je niet eens even stoppen om iemand in of uit te laten stappen."
                    },
                    {
                        "type": "tip",
                        "text": "Stel de parkeerschijf in op het volgende volle kwartier na aankomst in een blauwe zone."
                    }
                ],
                "examples_nl": [
                    "Je zoekt naar een parkeerplek en slaat een plek over omdat er een ononderbroken gele lijn staat.",
                    "In de blauwe zone stel je de parkeerschijf in op 14:15 als je aankomt om 14:05."
                ]
            },
            {
                "title_nl": "Veilig uitstappen",
                "content_nl": "Voor het uitstappen controleer je in de buitenspiegel en blinde hoek op fietsers en andere weggebruikers. De 'Hollandse methode' houdt in dat je het portier opent met je rechterhand (als je links zit), waardoor je automatisch over je rechterschouder kijkt in de richting van fietsers.\n\nPassagiers moeten ook worden geïnstrueerd om te controleren voor het openen van het portier aan de straatkant.",
                "callout_boxes_nl": [
                    {
                        "type": "warning",
                        "text": "Dooropen van een portier in het pad van een fietser kan ernstig letsel veroorzaken — gebruik altijd de Hollandse methode."
                    },
                    {
                        "type": "tip",
                        "text": "Stap uit aan de stoepkant als dat mogelijk is, om het risico op het doorkruisen van fietsrijstroken te vermijden."
                    }
                ],
                "examples_nl": [
                    "Je opent je portier met je rechterhand en kijkt automatisch naar achteren op fietsers.",
                    "Je instrueert je kind op de achterbank om eerst te controleren op fietsers voor het openen van het portier."
                ]
            }
        ]
    },
    "9": {
        "title_nl": "Een rotonde nemen",
        "summary_nl": "Begrijp hoe je een rotonde correct en veilig doorrijdt.",
        "exam_tips_nl": [
            "Op de meeste rotondes in Nederland hebben voertuigen op de rotonde voorrang.",
            "Geef altijd richting aan bij het verlaten van de rotonde, niet bij het oprijden."
        ],
        "common_mistakes_nl": [
            "Richting aangeven bij het oprijden van de rotonde (niet verplicht in Nederland).",
            "Vergeten dat fietsers op een fietsrotonde altijd voorrang hebben."
        ],
        "learning_objectives_nl": [
            "Voorrangsregels op Nederlandse rotondes begrijpen.",
            "Correct rijden op rotondes met fietsstroken."
        ],
        "key_takeaways_nl": [
            "Geef voorrang aan voertuigen op de rotonde.",
            "Geef richting aan bij het verlaten."
        ],
        "sections": [
            {
                "title_nl": "Voorrang op de rotonde",
                "content_nl": "In Nederland hebben voertuigen op de rotonde in de meeste gevallen voorrang. Dit wordt aangegeven door haaientanden voor de oprijstrook. Je rijdt de rotonde op zodra er een veilige opening is.\n\nOp de rotonde rijd je linksom. Kies bij een rotonde met twee rijstroken je rijstrook voor het oprijden op basis van de uitgang die je neemt: rechts voor de eerste of tweede uitgang, links voor verdere uitgangen.",
                "callout_boxes_nl": [
                    {
                        "type": "remember",
                        "text": "Haaientanden voor de rotonde betekenen dat het verkeer op de rotonde altijd voorrang heeft."
                    },
                    {
                        "type": "tip",
                        "text": "Kies al voor de rotonde de juiste rijstrook om voorkomen dat je van rijstrook moet wisselen op de rotonde."
                    }
                ],
                "examples_nl": [
                    "Je nadert een rotonde met haaientanden en wacht op een veilige opening voor je oprijdt.",
                    "Op een tweestrooks rotonde rij je in de rechterrijstrook omdat je de eerste uitgang neemt."
                ]
            },
            {
                "title_nl": "Fietsers op rotondes",
                "content_nl": "Op rotondes met een fietsrotonde hebben fietsers altijd voorrang op het auto-verkeer. Dit geldt zelfs als er geen haaientanden zijn. De bestuurder moet stoppen voor het fietspad rondom de rotonde.\n\nVeel rotondes in steden en dorpen hebben een verhoogd fietspad. Let goed op fietsers die je oversteekt bij elk oprit en afrit van de rotonde.",
                "callout_boxes_nl": [
                    {
                        "type": "warning",
                        "text": "Bij een fietsrotonde geldt: fietsers altijd voorrang, ongeacht haaientanden of andere markeringen."
                    },
                    {
                        "type": "info",
                        "text": "De kans op een botsing met een fietser op een rotonde is groot als je dit aandachtspunt mist."
                    }
                ],
                "examples_nl": [
                    "Op een stadsrotonde stop je voor het fietspad voordat je de rotonde oprijdt, ook al is er geen fietser zichtbaar.",
                    "Je verlaat de rotonde en geeft richting aan terwijl je controleert of er fietsers zijn op het fietspad."
                ]
            }
        ]
    },
    "10": {
        "title_nl": "De meest kwetsbare weggebruikers beschermen",
        "summary_nl": "Leer hoe je veilig omgaat met fietsers, voetgangers en kinderen in het verkeer.",
        "exam_tips_nl": [
            "Kwetsbare weggebruikers hebben in twijfelgevallen altijd recht op extra ruimte en bescherming.",
            "Een voetganger op een zebrapad heeft altijd voorrang, ook als er geen verkeerslicht is."
        ],
        "common_mistakes_nl": [
            "Denken dat een leeg zebrapad betekent dat je er gewoon snel overheen kunt rijden.",
            "Vergeten te controleren op fietsers in een fietsstrook bij het rechtsafslaan."
        ],
        "learning_objectives_nl": [
            "Weten wanneer en hoe je voorrang geeft aan voetgangers en fietsers.",
            "Gevaarlijke situaties herkennen in gebieden met kwetsbare weggebruikers."
        ],
        "key_takeaways_nl": [
            "Stop altijd voor een voetganger op of naast een zebrapad.",
            "Bescherm fietsers door voldoende afstand te houden."
        ],
        "sections": [
            {
                "title_nl": "Zebrapadregels en voetgangersgebieden",
                "content_nl": "Een zebrapad geeft voetgangers het recht om over te steken. Als een voetganger wacht op of naast het zebrapad, moet je stoppen. Als meerdere rijstroken aanwezig zijn, geldt dit voor alle rijstroken.\n\nIn voetgangersgebieden is autoverkeer vaak verboden of sterk beperkt. Buurtbewoners kunnen een speciale toestemming hebben. Rijden door zulke zones is gevaarlijk vanwege plotselinge bewegingen van voetgangers.",
                "callout_boxes_nl": [
                    {
                        "type": "remember",
                        "text": "Als één rijstrook stopt voor een zebrapad, moeten alle rijstroken stoppen — rij niet voorbij een stoppende auto bij een zebrapad."
                    },
                    {
                        "type": "tip",
                        "text": "Let op voetgangers die tussen geparkeerde auto's tevoorschijn komen, met name kinderen."
                    }
                ],
                "examples_nl": [
                    "Een voetganger wacht aan de rand van het zebrapad — je stopt, ook al is het nog niet opgestapt.",
                    "Je rijdt langs geparkeerde auto's en remt preventief, omdat een voetganger plotseling kan opduiken."
                ]
            },
            {
                "title_nl": "Fietsersveiligheid en blinde hoeken",
                "content_nl": "In Nederland zijn fietsers overal. Bij elke manoeuvre — rechtsafslaan, parkeren, de weg oprijden — moet je controleren op fietsers. De 'dode hoek' rechts is het meest gevaarlijke gebied bij vrachtwagens en bussen.\n\nBij het rechtsafslaan geef je altijd voorrang aan een rechtdoorgaande fietser op een fietspad of fietsstrook rechts. Dit geldt ook als je een grotere weg verlaat en een kleinere weg inrijdt.",
                "callout_boxes_nl": [
                    {
                        "type": "warning",
                        "text": "De dode hoek rechts van een vrachtwagen is een dodelijke zone — rij er nooit naast bij een kruispunt."
                    },
                    {
                        "type": "tip",
                        "text": "Controleer bij rechtsafslaan altijd nog een keer in de spiegel en blinde hoek op fietsers."
                    }
                ],
                "examples_nl": [
                    "Je slaat rechtsaf bij een kruispunt en geeft voorrang aan een fietser die rechtdoor rijdt op het fietspad.",
                    "Je nadert een vrachtwagen bij een kruispunt en houdt afstand zodat de chauffeur jou kan zien."
                ]
            }
        ]
    },
    "11": {
        "title_nl": "Discipline op de snelweg",
        "summary_nl": "Leer veilig rijden op de snelweg: invoegen, inhalen, rijstrookgebruik en afstand.",
        "exam_tips_nl": [
            "Invoegen op de snelweg gaat via de invoegstrook — pas je snelheid aan op het verkeer op de hoofdbaan.",
            "Rijstrookdiscipline: rij zo ver mogelijk rechts. De linkerrijstrook is alleen voor inhalen."
        ],
        "common_mistakes_nl": [
            "Links blijven rijden na het inhalen op de snelweg.",
            "Te kort achter de voorligger rijden (twee-seconden-regel vergeten)."
        ],
        "learning_objectives_nl": [
            "Veilig invoegen en uitvoegen op de snelweg.",
            "Rijstrookdiscipline en veilige afstand begrijpen."
        ],
        "key_takeaways_nl": [
            "Pas je snelheid aan bij het invoegen. Keer terug naar rechts na inhalen.",
            "Houd minstens twee seconden afstand."
        ],
        "sections": [
            {
                "title_nl": "Invoegen en uitvoegen",
                "content_nl": "Invoegen op de snelweg doe je via de invoegstrook. Pas je snelheid aan op het verkeer op de hoofdbaan en voeg soepel in. Geef richting aan en wacht op een veilige opening. Je mag niet van het rijdende verkeer verwachten dat het voor jou ruimte maakt, hoewel het vriendelijk is als dat gebeurt.\n\nUitvoegen doe je ruim van tevoren via de uitvoegstrook. Geef tijdig richting aan, verlaat de hoofdrijbaan en rem pas op de uitvoegstrook.",
                "callout_boxes_nl": [
                    {
                        "type": "remember",
                        "text": "Op de invoegstrook is het jouw verantwoordelijkheid om je te voegen — het doorgaande verkeer heeft voorrang."
                    },
                    {
                        "type": "tip",
                        "text": "Begin al te versnellen aan het begin van de invoegstrook zodat je de juiste snelheid hebt bij het invoegen."
                    }
                ],
                "examples_nl": [
                    "Je voegt in op de snelweg via de invoegstrook, past je snelheid aan op 100 km/h en controleert de blinde hoek.",
                    "Je gaat ruim 500 meter voor je afrit naar de rechterrijstrook en geeft richting aan."
                ]
            },
            {
                "title_nl": "Rijstrookdiscipline en veilige afstand",
                "content_nl": "Op Nederlandse snelwegen rij je zo ver mogelijk rechts. De middelste en linker rijstroken zijn alleen voor inhalen. Na het inhalen keer je onmiddellijk terug naar rechts. Links blijven rijden zonder in te halen is verboden en gevaarlijk.\n\nVeilige afstand is minstens twee seconden bij droog weer. Kies een vast punt op de weg, begin te tellen wanneer de auto voor je dat punt passeert, en tel tot je zelf dat punt passeert. Twee seconden is het minimum.",
                "callout_boxes_nl": [
                    {
                        "type": "warning",
                        "text": "Links rijden zonder in te halen is verboden op de snelweg en kan worden beboet."
                    },
                    {
                        "type": "info",
                        "text": "Bij regen: vier seconden afstand. Bij mist of ijs: nog meer."
                    }
                ],
                "examples_nl": [
                    "Na het inhalen van een vrachtwagen rij je terug naar de rechterrijstrook zodra je hem volledig voorbij bent.",
                    "Je meet je volgafstand met de twee-seconden-regel en vergroot hem bij regenachtig weer."
                ]
            }
        ]
    },
    "12": {
        "title_nl": "Gevaar vroeg zien",
        "summary_nl": "Ontwikkel gevaarherkenning en leer hoe je risicosituaties vroeg kunt inschatten.",
        "exam_tips_nl": [
            "Gevaar herkennen betekent ook: zien wat je niet ziet. Wat zit er achter die vrachtwagen?",
            "Een stilstaande auto op een smalle weg is een aanwijzing dat er verderop een obstakel kan zijn."
        ],
        "common_mistakes_nl": [
            "Uitsluitend op de auto voor je focussen in plaats van verder vooruit kijken.",
            "Verkeerssituaties onderschatten bij goed zicht (je kunt sneller in gevaar komen dan verwacht)."
        ],
        "learning_objectives_nl": [
            "Potentieel gevaarlijke situaties vroegtijdig herkennen.",
            "Juist reageren op gevaarindicatoren."
        ],
        "key_takeaways_nl": [
            "Scan de weg ver vooruit, niet alleen vlak voor je auto.",
            "Vertraag bij twijfel."
        ],
        "sections": [
            {
                "title_nl": "Observeren en anticiperen",
                "content_nl": "Gevaarherkenning begint met correct kijken. Scan de weg ver vooruit (15-20 seconden rijafstand), niet alleen vlak voor je bumper. Zoek naar aanwijzingen: stopt het verkeer voor je? Zwaait er een kind heen en weer? Staat er een auto scheef geparkeerd?\n\nAnticiperen betekent dat je je rijgedrag aanpast voordat het gevaar zichtbaar en urgent wordt. Rij langzamer bij bochten, kruispunten, scholen en marktplaatsen.",
                "callout_boxes_nl": [
                    {
                        "type": "remember",
                        "text": "Scan 15-20 seconden vooruit. Als het niet klopt, verminder snelheid en bereid je voor op het onverwachte."
                    },
                    {
                        "type": "tip",
                        "text": "Wissel regelmatig van focus: dichtbij, middel, ver — scan ook de zijkanten en spiegels."
                    }
                ],
                "examples_nl": [
                    "Je ziet een bal de straat in rollen en vertraagt direct — een kind kan niet ver weg zijn.",
                    "Voor een blinde bocht rijd je langzamer zodat je kunt stoppen als er een obstakel is."
                ]
            },
            {
                "title_nl": "Gevaarlijke situaties in stad en buitenweg",
                "content_nl": "In de stad zijn de gevaren dichter op elkaar: overstekende voetgangers, openende autodeuren, fietsers die van rechts komen, kinderen die spelen. Op buiten-wegen zijn de gevaren anders: wild dat de weg oversteekt, slecht verlichte bochten, traktoren die plotseling opduiken.\n\nPasseer langzaam de gevaarzone en wees voorbereid om te stoppen. Gevaar herkennen is meer waard dan een snelle reactie achteraf.",
                "callout_boxes_nl": [
                    {
                        "type": "warning",
                        "text": "Bij wegwerkzaamheden: werkers kunnen plotseling de rijbaan betreden — rij veel langzamer dan de limiet aangeeft."
                    },
                    {
                        "type": "info",
                        "text": "In de schemering zijn voetgangers en fietsers het minst goed zichtbaar — wees extra alert."
                    }
                ],
                "examples_nl": [
                    "Op een buitenweg 's avonds zie je reflecterende ogen aan de kant van de weg en rem je langzaam.",
                    "In de stad rij je langzamer langs rijen geparkeerde auto's, klaar voor opende portieren."
                ]
            }
        ]
    },
    "13": {
        "title_nl": "Goed oordeel achter het stuur",
        "summary_nl": "Leer hoe verantwoord rijgedrag, concentratie en zelfbeoordeling de veiligheid verbeteren.",
        "exam_tips_nl": [
            "Afleiding (telefoon, eten, aanpassen gps) is in de meeste gevallen net zo gevaarlijk als rijden onder invloed.",
            "Een goede bestuurder past zijn gedrag aan aan de omstandigheden, niet alleen aan de regels."
        ],
        "common_mistakes_nl": [
            "Denken dat je goed kunt rijden terwijl je moe of afgeleid bent.",
            "De risico's van rijden onder invloed van medicijnen onderschatten."
        ],
        "learning_objectives_nl": [
            "Eigen rijvaardigheid realistisch beoordelen.",
            "Gevaren van afleiding en vermoeidheid begrijpen."
        ],
        "key_takeaways_nl": [
            "Rijden vereist volledige concentratie — telefoon wegleggen.",
            "Als je twijfelt of je fit bent, rijd dan niet."
        ],
        "sections": [
            {
                "title_nl": "Concentratie en afleiding",
                "content_nl": "Een bestuurder die zijn telefoon gebruikt, rijdt even gevaarlijk als iemand met 0,8 promille alcohol. Afleiding vertraagt de reactietijd, versmalt het gezichtsveld en verlaagt het situationeel bewustzijn. Zelfs handsfree bellen vermindert de rijprestatie merkbaar.\n\nAndere afleidingen zijn: eten, drinken, aanpassen van de radio, het navigatiesysteem bedienen en gesprekken met passagiers. Rij nooit terwijl je afgeleid bent.",
                "callout_boxes_nl": [
                    {
                        "type": "remember",
                        "text": "Telefoon vasthouden achter het stuur is verboden en levert een boete én punten op het rijbewijs op."
                    },
                    {
                        "type": "warning",
                        "text": "Zelfs handsfree bellen verlaagt je rijprestatie — stel het gesprek uit tot na aankomst."
                    }
                ],
                "examples_nl": [
                    "Je telefoon gaat over tijdens het rijden — je laat hem rinkelen en bekijkt het bericht pas na het parkeren.",
                    "Je bent moe na een lange dag en besluit niet te rijden maar de trein te nemen."
                ]
            },
            {
                "title_nl": "Vermoeidheid en rijvaardigheid",
                "content_nl": "Vermoeidheid is een onderschat rijgevaar. Na 17 uur wakker zijn rijdt je vergelijkbaar met iemand met 0,5 promille. Microslaapjes — heel korte slaapperiodes — kunnen optreden zonder dat je het merkt en duren lang genoeg om van de weg te raken.\n\nAls je begint te geeuwen, de ogen zwaar worden of je rijstrook niet meer kunt volgen, stop dan. Een korte pauze van 20 minuten slapen kan levensreddend zijn op een lange rit.",
                "callout_boxes_nl": [
                    {
                        "type": "warning",
                        "text": "Stop en slaap als je moe bent — koffie en frisse lucht maskeren vermoeidheid maar lossen het niet op."
                    },
                    {
                        "type": "info",
                        "text": "Houd op lange ritten elke 2 uur een pauze van minstens 15 minuten."
                    }
                ],
                "examples_nl": [
                    "Tijdens een nachtelijk rijden voel je dat je ogen zwaar worden — je stopt bij een tankstation en neemt een dutje.",
                    "Je merkt dat je twee keer bijna over de lijn reed en besluit te stoppen."
                ]
            }
        ]
    },
    "14": {
        "title_nl": "Vlot en zuinig rijden",
        "summary_nl": "Leer zuinig en milieubewust rijden door anticiperen, juiste versnelling en remmen.",
        "exam_tips_nl": [
            "Vooruit kijken en anticiperen vermindert onnodig remmen en accelereren — dit spaart brandstof.",
            "Rijden op de juiste versnelling verlaagt het brandstofverbruik aanzienlijk."
        ],
        "common_mistakes_nl": [
            "Laat van versnelling wisselen (te hoge toerentallen rijden).",
            "Onnodig hard optrekken bij groen licht."
        ],
        "learning_objectives_nl": [
            "Zuinig rijden door correcte rijstijl.",
            "De milieuvoordelen van anticiperend rijden begrijpen."
        ],
        "key_takeaways_nl": [
            "Anticipeer op het verkeer en rem zo min mogelijk.",
            "Schakel vroeg op en late af."
        ],
        "sections": [
            {
                "title_nl": "Anticiperend rijden en brandstofbesparing",
                "content_nl": "Anticiperend rijden betekent dat je vooruit kijkt en reageert op wat komen gaat, niet pas op het laatste moment. Als je een rood licht ziet van ver, laat je het gas eerder los en rol je naar het stoplicht toe. Dit bespaart brandstof en vermindert slijtage aan remmen.\n\nOp de snelweg is een constante snelheid zuiniger dan steeds optrekken en afremmen. Gebruik de cruise control wanneer dit veilig is.",
                "callout_boxes_nl": [
                    {
                        "type": "remember",
                        "text": "Laat gas los in plaats van te remmen wanneer je een file of rood licht voorziet — dit is de meest effectieve brandstofbesparing."
                    },
                    {
                        "type": "tip",
                        "text": "Op de snelweg bespaart cruise control meer brandstof dan handmatig een constante snelheid proberen te houden."
                    }
                ],
                "examples_nl": [
                    "Je ziet van ver een rood stoplicht en laat het gas los — je rolt naar het stoplicht toe zonder te remmen.",
                    "Op de snelweg gebruik je de cruise control bij een constante snelheid van 100 km/h."
                ]
            },
            {
                "title_nl": "Juist gebruik van versnellingen",
                "content_nl": "Schakel vroeg op naar een hogere versnelling (bij 2000-2500 toeren voor benzine, 1500-2000 voor diesel) en schakel laat terug. In de hogere versnelling ben je zuiniger. Rij nooit langdurig in een lagere versnelling dan nodig.\n\nBij het afremmen voor een stoplicht of rotonde: zet de auto in de versnelling, schakel laat terug of schakel de versnelling eruit en rem zachtjes. Zo gebruik je motorremming en koppelingsremming voor efficiënt remmen.",
                "callout_boxes_nl": [
                    {
                        "type": "info",
                        "text": "Modern rijden: schakel bij 2000 toeren op voor benzine, 1500 voor diesel — je motor wordt dankbaar."
                    },
                    {
                        "type": "tip",
                        "text": "In de stad is de 4e of 5e versnelling bij 50 km/h zuiniger dan de 3e."
                    }
                ],
                "examples_nl": [
                    "Je rijdt 50 km/h in de stad in de 4e versnelling voor maximale zuinigheid.",
                    "Bij een naderende bocht schakel je een versnelling lager en gebruik je de motorremming."
                ]
            }
        ]
    },
    "15": {
        "title_nl": "Uw voertuig kennen",
        "summary_nl": "Begrijp de basiscontroles, veiligheidsuitrusting en verplichte onderdelen van uw voertuig.",
        "exam_tips_nl": [
            "Je bent verantwoordelijk voor de staat van je voertuig — rijden met defecte rem- of achterlichten is een overtreding.",
            "Bandenspanning beïnvloedt het brandstofverbruik, de slijtage en met name de rijstabiliteit."
        ],
        "common_mistakes_nl": [
            "Vergeten dat de APK (periodieke technische keuring) jaarlijks verplicht is na 4 jaar.",
            "Denken dat een klein olieverlies 'niet erg' is."
        ],
        "learning_objectives_nl": [
            "Basiscontroles kennen die je voor elke rit uitvoert.",
            "Weten welke documenten en uitrusting wettelijk verplicht zijn."
        ],
        "key_takeaways_nl": [
            "Controleer lichten, banden, olie en ruitensproeier regelmatig.",
            "Zorg dat APK, verzekering en rijbewijs altijd geldig zijn."
        ],
        "sections": [
            {
                "title_nl": "Verplichte controles voor vertrek",
                "content_nl": "Voordat je vertrekt, controleer je verlichting (koplichten, richtingaanwijzers, remlichten), bandendruk en zichtbaar profiel, ruitenvloeistof en ruitenwisserstand, achteruitkijkspiegels en stoelinstellingen, en of alle inzittenden hun gordel dragen.\n\nEen defect licht of een slechte band kan gevaarlijk zijn voor jou en anderen. Als je een waarschuwingslampje op het dashboard ziet, negeer het dan niet.",
                "callout_boxes_nl": [
                    {
                        "type": "remember",
                        "text": "Gordels zijn voor alle inzittenden verplicht — als bestuurder ben je verantwoordelijk voor passagiers jonger dan 18 jaar."
                    },
                    {
                        "type": "tip",
                        "text": "Controleer voor een lange rit ook het koelvloeistofniveau en breng het voertuig naar de garage als een lamp brandt."
                    }
                ],
                "examples_nl": [
                    "Voor een lange trip controleer je banden, koelvloeistof, olie en alle lichten.",
                    "Je ziet een remlamp op het dashboard — je rijdt naar een garage voor inspectie voor je verder rijdt."
                ]
            },
            {
                "title_nl": "Wettelijk verplichte uitrusting en documenten",
                "content_nl": "In Nederland moet je altijd bij je hebben: een geldig rijbewijs, het kentekenbewijs van het voertuig en bewijs van verzekering (groene kaart of digitaal equivalent). In bepaalde gevallen kan een APK-bewijs gevraagd worden.\n\nWettelijk verplichte uitrusting omvat een brandblusser (aanbevolen maar niet verplicht voor personenauto's), een gevarendriehoek en een veiligheidshesje. Voor internationaal rijden zijn extra vereisten van kracht.",
                "callout_boxes_nl": [
                    {
                        "type": "warning",
                        "text": "Rijden zonder geldig rijbewijs of verzekering kan leiden tot hoge boetes en inbeslagname van het voertuig."
                    },
                    {
                        "type": "info",
                        "text": "Digitale versies van kentekenbewijs en rijbewijs worden in steeds meer gevallen geaccepteerd via de RDW-app."
                    }
                ],
                "examples_nl": [
                    "Je wordt aangehouden en laat digitaal je kentekenbewijs en verzekering zien via de RDW-app.",
                    "Je zet een gevarendriehoek 30 meter achter je autopech op de vluchtstrook."
                ]
            }
        ]
    }
}


class Command(BaseCommand):
    help = "Seed Dutch driving lesson and section content"

    @transaction.atomic
    def handle(self, *args, **options):
        lessons_updated = 0
        sections_updated = 0

        for lesson_id, lesson_translation in LESSON_TRANSLATIONS.items():
            lesson = DrivingLesson.objects.get(id=int(lesson_id))
            sections = list(lesson.sections.all())
            expected_sections = lesson_translation["sections"]
            if len(sections) != len(expected_sections):
                raise CommandError(
                    f"Lesson {lesson_id} has {len(sections)} sections; expected {len(expected_sections)}."
                )

            for field_name in (
                "title_nl",
                "summary_nl",
                "exam_tips_nl",
                "common_mistakes_nl",
                "learning_objectives_nl",
                "key_takeaways_nl",
            ):
                setattr(lesson, field_name, lesson_translation[field_name])
            lesson.save()
            lessons_updated += 1

            for index, section_translation in enumerate(expected_sections):
                section = sections[index]
                for field_name in (
                    "title_nl",
                    "content_nl",
                    "callout_boxes_nl",
                    "examples_nl",
                ):
                    setattr(section, field_name, section_translation[field_name])
                section.save()
                sections_updated += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Seeded Dutch content for {lessons_updated} lessons and {sections_updated} sections."
            )
        )
