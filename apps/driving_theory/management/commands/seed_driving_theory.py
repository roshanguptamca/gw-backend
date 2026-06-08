"""
Management command: seed_driving_theory

Populates the database with original Dutch driving theory content.
All questions and lessons are written in original language — not copied from CBR.

Usage:
    python manage.py seed_driving_theory
    python manage.py seed_driving_theory --clear   # wipe and re-seed
"""

from django.core.management.base import BaseCommand

from apps.driving_theory.models import (
    DrivingLesson,
    DrivingLessonSection,
    DrivingQuestion,
    DrivingQuestionOption,
    DrivingTopic,
)

# ---------------------------------------------------------------------------
# Seed data — all content is original, not copied from CBR
# ---------------------------------------------------------------------------

TOPICS = [
    {
        "slug": "traffic-signs",
        "title": "Traffic Signs",
        "summary": "Master the shapes, colours, and meanings of Dutch traffic signs to navigate roads safely.",
        "icon": "bi-sign-stop",
        "order": 1,
        "dutch_terms": [
            {"term": "verkeersbord", "meaning": "traffic sign"},
            {"term": "verbodsbord", "meaning": "prohibition sign (red circle)"},
            {"term": "gebodsbord", "meaning": "mandatory sign (blue circle)"},
            {"term": "waarschuwingsbord", "meaning": "warning sign (yellow/white triangle)"},
            {"term": "informatiebord", "meaning": "information sign (blue rectangle)"},
        ],
        "lessons": [
            {
                "title": "Sign Shapes and Colours",
                "summary": "The shape and colour of a sign tells you the category before you read it.",
                "difficulty": "easy",
                "estimated_minutes": 10,
                "order": 1,
                "sections": [
                    {
                        "title": "Understanding Shapes",
                        "content": (
                            "Dutch traffic signs follow a consistent international design:\n"
                            "• Triangles with a red border warn of a hazard ahead.\n"
                            "• Circles with a red border prohibit an action.\n"
                            "• Blue circles give a mandatory instruction (you must do this).\n"
                            "• Rectangles and squares provide information or directions.\n"
                            "• Octagons are reserved for STOP signs."
                        ),
                        "examples": [
                            "A red-bordered triangle with a bicycle symbol warns of a cycle crossing.",
                            "A red circle with '50' inside means maximum speed 50 km/h.",
                            "A blue circle with a white arrow means you must drive in that direction.",
                        ],
                        "dutch_keywords": ["driehoek", "cirkel", "rechthoek", "achthoek"],
                        "order": 1,
                    },
                    {
                        "title": "Colour Meanings",
                        "content": (
                            "Colours reinforce the message:\n"
                            "• Red: prohibition or danger.\n"
                            "• Blue: mandatory instruction or information on motorways.\n"
                            "• Yellow/white background: temporary or warning.\n"
                            "• Green: route guidance on highways.\n"
                            "• Orange background: temporary signs (roadworks)."
                        ),
                        "examples": [
                            "An orange sign with a detour arrow means a temporary diversion is in place.",
                            "A green sign shows the direction to a motorway destination.",
                        ],
                        "dutch_keywords": ["rood", "blauw", "geel", "groen", "oranje"],
                        "order": 2,
                    },
                ],
                "questions": [
                    {
                        "text": "A triangular sign with a red border and a skidding car symbol means:",
                        "explanation": "Triangular red-bordered signs always warn of a hazard. A skidding car symbol warns of a slippery road surface ahead.",
                        "difficulty": 1,
                        "options": [
                            ("Road is closed for maintenance", False),
                            ("Slippery road surface ahead", True),
                            ("No motor vehicles allowed", False),
                            ("Bumpy road ahead", False),
                        ],
                    },
                    {
                        "text": "Which shape is exclusively used for a STOP sign in the Netherlands?",
                        "explanation": "The octagon is internationally reserved for STOP signs. No other traffic sign uses this shape.",
                        "difficulty": 1,
                        "options": [
                            ("Triangle", False),
                            ("Circle", False),
                            ("Octagon", True),
                            ("Rectangle", False),
                        ],
                    },
                    {
                        "text": "A blue circular sign with a white car and bicycle separated by a line indicates:",
                        "explanation": "Blue circles are mandatory instructions. This particular sign tells drivers that cars and bicycles must use separate lanes or paths.",
                        "difficulty": 2,
                        "options": [
                            ("Cars and bicycles may share the road", False),
                            ("Bicycles are prohibited", False),
                            ("Separate lanes are mandatory for cars and bicycles", True),
                            ("Priority given to bicycles", False),
                        ],
                    },
                    {
                        "text": "An orange background on a traffic sign most commonly indicates:",
                        "explanation": "Orange background signs are temporary, usually deployed during roadworks to redirect or warn traffic.",
                        "difficulty": 1,
                        "options": [
                            ("A permanent road restriction", False),
                            ("A temporary measure, often related to roadworks", True),
                            ("A motorway information sign", False),
                            ("A school zone warning", False),
                        ],
                    },
                    {
                        "text": "You see a red circle with a horizontal white bar inside. What does this mean?",
                        "explanation": "A red circle with a single horizontal white bar means no entry in that direction. It is commonly seen at one-way street entrances.",
                        "difficulty": 1,
                        "options": [
                            ("No parking", False),
                            ("No overtaking", False),
                            ("No entry", True),
                            ("Speed limit 0 km/h", False),
                        ],
                    },
                ],
            },
        ],
    },
    {
        "slug": "priority-rules",
        "title": "Priority Rules",
        "summary": "Understand who has right of way on Dutch roads to avoid dangerous situations.",
        "icon": "bi-arrow-up-circle",
        "order": 2,
        "dutch_terms": [
            {"term": "voorrang", "meaning": "right of way"},
            {"term": "verleen voorrang", "meaning": "give way"},
            {"term": "haaientanden", "meaning": "shark teeth (give-way markings)"},
            {"term": "voorrangsweg", "meaning": "priority road"},
            {"term": "gelijkwaardig", "meaning": "equal priority intersection"},
        ],
        "lessons": [
            {
                "title": "Right of Way Fundamentals",
                "summary": "Learn the core rules that determine who goes first at intersections.",
                "difficulty": "medium",
                "estimated_minutes": 15,
                "order": 1,
                "sections": [
                    {
                        "title": "Right Before Left",
                        "content": (
                            "At intersections without signs or markings, the right-before-left rule applies:\n"
                            "• Traffic coming from your right has priority over you.\n"
                            "• You must yield to vehicles approaching from the right.\n"
                            "• This rule applies on roads of equal importance.\n"
                            "• Trams always have priority over other road users, regardless of direction."
                        ),
                        "examples": [
                            "At a quiet residential crossroads with no signs, a car approaching from the right goes first.",
                            "Even if you are on a wider road, a car from the right on a side street has priority if no signs indicate otherwise.",
                        ],
                        "dutch_keywords": ["rechts voor links", "gelijkwaardig kruispunt", "tram"],
                        "order": 1,
                    },
                    {
                        "title": "Give Way and Stop Signs",
                        "content": (
                            "Two signs override the right-before-left rule:\n"
                            "• GIVE WAY (inverted triangle / shark teeth markings): you must let all crossing traffic pass.\n"
                            "• STOP (octagon): you must stop completely at the line and only proceed when safe.\n"
                            "• A priority road sign (yellow diamond) means you are on the main road and have priority over side roads."
                        ),
                        "examples": [
                            "Shark teeth painted on the road tell you to give way before entering the main road.",
                            "A yellow diamond sign means you are on the priority road — side road traffic must wait for you.",
                        ],
                        "dutch_keywords": ["haaientanden", "stopbord", "voorrangsweg", "gele ruit"],
                        "order": 2,
                    },
                ],
                "questions": [
                    {
                        "text": "At an unmarked intersection, a vehicle approaches from your right. What should you do?",
                        "explanation": "The right-before-left rule requires you to give way to traffic approaching from the right at equal-priority intersections.",
                        "difficulty": 1,
                        "options": [
                            ("Accelerate to clear the junction first", False),
                            ("Sound your horn and proceed", False),
                            ("Yield and let the vehicle from the right pass", True),
                            ("Flash your headlights to signal you have priority", False),
                        ],
                    },
                    {
                        "text": "You are driving on a road marked with a yellow diamond sign. What does this mean?",
                        "explanation": "The yellow diamond (voorrangsweg) indicates you are on a priority road. Side road vehicles must give way to you.",
                        "difficulty": 1,
                        "options": [
                            ("You must give way to all other traffic", False),
                            ("You are on a priority road and have right of way over side roads", True),
                            ("Speed limit is 80 km/h", False),
                            ("No overtaking is permitted", False),
                        ],
                    },
                    {
                        "text": "Shark teeth (haaientanden) painted across your lane mean:",
                        "explanation": "Shark teeth are the road-marking version of a give-way sign. You must allow all traffic on the road you are entering to pass before proceeding.",
                        "difficulty": 1,
                        "options": [
                            ("You have priority over crossing traffic", False),
                            ("Slow down to 30 km/h", False),
                            ("Give way to all traffic on the road you are entering", True),
                            ("Stop completely and wait for a signal", False),
                        ],
                    },
                    {
                        "text": "A tram approaches from your left at an unmarked intersection. You should:",
                        "explanation": "Trams always have priority over other road users in the Netherlands, regardless of direction or the right-before-left rule.",
                        "difficulty": 2,
                        "options": [
                            ("Apply right-before-left and proceed because the tram is from the left", False),
                            ("Always give way to the tram", True),
                            ("Sound your horn and cross quickly", False),
                            ("Flash your lights and continue at low speed", False),
                        ],
                    },
                    {
                        "text": "You approach a STOP sign. What is the correct action?",
                        "explanation": "A STOP sign requires a full stop at the stop line. You may not simply slow down. Proceed only when the road is completely clear.",
                        "difficulty": 1,
                        "options": [
                            ("Slow down to 10 km/h and look both ways", False),
                            ("Stop completely, then proceed when safe", True),
                            ("Stop only if traffic is present", False),
                            ("Give way but stopping is optional", False),
                        ],
                    },
                    {
                        "text": "You are turning right onto a main road. Pedestrians are crossing the road you are entering. You should:",
                        "explanation": "When turning, pedestrians who are already crossing on the road you are entering have right of way.",
                        "difficulty": 2,
                        "options": [
                            ("Sound your horn to warn them and proceed", False),
                            ("Wait for the pedestrians to finish crossing before completing your turn", True),
                            ("Flash your headlights and turn slowly", False),
                            ("Accelerate to pass behind the pedestrians", False),
                        ],
                    },
                ],
            },
        ],
    },
    {
        "slug": "speed-limits",
        "title": "Speed Limits",
        "summary": "Know the legal speed limits across different road types and special zones in the Netherlands.",
        "icon": "bi-speedometer2",
        "order": 3,
        "dutch_terms": [
            {"term": "snelheidslimiet", "meaning": "speed limit"},
            {"term": "bebouwde kom", "meaning": "built-up area"},
            {"term": "autosnelweg", "meaning": "motorway"},
            {"term": "autoweg", "meaning": "expressway (not full motorway)"},
            {"term": "zone 30", "meaning": "30 km/h zone"},
        ],
        "lessons": [
            {
                "title": "Standard Dutch Speed Limits",
                "summary": "Overview of default speed limits for each road category.",
                "difficulty": "easy",
                "estimated_minutes": 10,
                "order": 1,
                "sections": [
                    {
                        "title": "Road Category Limits",
                        "content": (
                            "Default speed limits in the Netherlands:\n"
                            "• Built-up areas (bebouwde kom): 50 km/h\n"
                            "• Outside built-up areas (rural roads): 80 km/h\n"
                            "• Expressways (autoweg, green signs, no grade crossings): 100 km/h\n"
                            "• Motorways (autosnelweg): 100 km/h during the day (06:00–19:00) and 130 km/h at night (19:00–06:00)\n\n"
                            "Always follow posted signs — they override the defaults."
                        ),
                        "examples": [
                            "Driving through a Dutch town without a sign means 50 km/h applies.",
                            "On the A2 motorway during the day, the limit is 100 km/h unless a variable sign shows otherwise.",
                        ],
                        "dutch_keywords": ["bebouwde kom", "autosnelweg", "autoweg", "buiten de bebouwde kom"],
                        "order": 1,
                    },
                    {
                        "title": "Special Zones",
                        "content": (
                            "Special speed zones:\n"
                            "• Zone 30: Residential or school areas, max 30 km/h throughout the zone.\n"
                            "• Erf (home zone / woonerf): max 15 km/h, pedestrians and cyclists have priority.\n"
                            "• Roadworks zones: posted limits must be obeyed, often reduced to 50 or 70 km/h.\n"
                            "• Variable message signs (matrix signs) on motorways can lower limits to 50 km/h in congestion."
                        ),
                        "examples": [
                            "A Zone 30 sign at the entrance of a street means 30 km/h applies until the end-of-zone sign.",
                            "In a woonerf, children may play on the road — drive at walking pace.",
                        ],
                        "dutch_keywords": ["zone 30", "woonerf", "erf", "matrixbord"],
                        "order": 2,
                    },
                ],
                "questions": [
                    {
                        "text": "What is the default speed limit inside a built-up area (bebouwde kom) in the Netherlands?",
                        "explanation": "The default limit in a built-up area is 50 km/h unless a different limit is posted.",
                        "difficulty": 1,
                        "options": [
                            ("30 km/h", False),
                            ("50 km/h", True),
                            ("70 km/h", False),
                            ("80 km/h", False),
                        ],
                    },
                    {
                        "text": "On a Dutch motorway (autosnelweg) at 20:00, what is the general speed limit?",
                        "explanation": "From 19:00 to 06:00 the motorway limit is 130 km/h unless a variable sign shows a lower limit.",
                        "difficulty": 2,
                        "options": [
                            ("100 km/h", False),
                            ("120 km/h", False),
                            ("130 km/h", True),
                            ("150 km/h", False),
                        ],
                    },
                    {
                        "text": "You enter a Zone 30 area. The limit applies:",
                        "explanation": "A Zone 30 sign at the zone entrance applies to all streets within the zone until the end-of-zone sign. You do not need repeated signs on each street.",
                        "difficulty": 1,
                        "options": [
                            ("Only on the street where the sign is posted", False),
                            ("Only near schools", False),
                            ("Throughout the entire zone until the end-of-zone sign", True),
                            ("Only between 08:00 and 18:00", False),
                        ],
                    },
                    {
                        "text": "In a woonerf (home zone), who has priority?",
                        "explanation": "In a woonerf (erf), pedestrians and cyclists have priority. The maximum speed is 15 km/h and drivers must not obstruct pedestrians.",
                        "difficulty": 2,
                        "options": [
                            ("Motorists, because it is a road", False),
                            ("Pedestrians and cyclists", True),
                            ("Cyclists only", False),
                            ("No one — it is shared equally", False),
                        ],
                    },
                    {
                        "text": "A variable speed sign on a motorway shows 70. You should:",
                        "explanation": "Variable message signs (matrixborden) are legally binding. A displayed speed overrides the standard limit. 70 km/h must be obeyed.",
                        "difficulty": 1,
                        "options": [
                            ("Treat it as advisory and drive at 100 km/h", False),
                            ("Obey the displayed limit of 70 km/h", True),
                            ("Continue at 130 km/h — variable signs are not enforceable", False),
                            ("Slow down to 50 km/h to be safe", False),
                        ],
                    },
                ],
            },
        ],
    },
    {
        "slug": "road-markings",
        "title": "Road Markings",
        "summary": "Understand lines, arrows, and symbols painted on Dutch roads.",
        "icon": "bi-layout-three-columns",
        "order": 4,
        "dutch_terms": [
            {"term": "doorgetrokken streep", "meaning": "continuous (solid) line"},
            {"term": "onderbroken streep", "meaning": "broken line"},
            {"term": "rijstrookmarkering", "meaning": "lane marking"},
            {"term": "voetgangersoversteekplaats", "meaning": "pedestrian crossing (zebra)"},
            {"term": "busstrook", "meaning": "bus lane"},
        ],
        "lessons": [
            {
                "title": "Lines and Their Meanings",
                "summary": "Solid and broken lines guide traffic flow and separate lanes.",
                "difficulty": "easy",
                "estimated_minutes": 12,
                "order": 1,
                "sections": [
                    {
                        "title": "Solid vs Broken Lines",
                        "content": (
                            "White lines on the road convey critical rules:\n"
                            "• Solid white line: do not cross — this is a firm boundary between lanes or at road edges.\n"
                            "• Broken white line: you may cross when safe, for example to overtake.\n"
                            "• Double solid lines: never cross from either direction.\n"
                            "• Short dashes (1m dashes, 3m gaps): normal lane separation.\n"
                            "• Long dashes (3m dashes, 1m gaps): approaching a solid line or hazard — treat with care."
                        ),
                        "examples": [
                            "A solid centre line on a rural road means overtaking is not permitted.",
                            "Broken dashes in the middle of a two-lane road mean overtaking is permitted when safe.",
                        ],
                        "dutch_keywords": ["doorgetrokken streep", "onderbroken streep", "dubbele streep"],
                        "order": 1,
                    },
                    {
                        "title": "Special Markings",
                        "content": (
                            "Other important road markings:\n"
                            "• Zebra crossing (zebrapad): white alternating stripes — pedestrians have priority.\n"
                            "• Shark teeth (haaientanden): triangles pointing at you — give way.\n"
                            "• Yellow lines at kerb: no stopping or parking.\n"
                            "• Bicycle lane markings (fietspad): white bicycle symbol or coloured surface.\n"
                            "• Bus-only lane (busstrook): marked 'BUS' — only buses, taxis (sometimes), and cyclists may use it."
                        ),
                        "examples": [
                            "A white bicycle stencil on the road reminds drivers to watch for cyclists.",
                            "Yellow lines at the side of the road mean no stopping at any time.",
                        ],
                        "dutch_keywords": ["zebrapad", "haaientanden", "fietspad", "busstrook"],
                        "order": 2,
                    },
                ],
                "questions": [
                    {
                        "text": "A continuous (solid) white line along the centre of the road means:",
                        "explanation": "A solid centre line is a firm boundary. Crossing it for overtaking is not permitted.",
                        "difficulty": 1,
                        "options": [
                            ("You may overtake if the road is clear", False),
                            ("You must not cross the line to overtake", True),
                            ("The road narrows ahead", False),
                            ("Cyclists may use this lane", False),
                        ],
                    },
                    {
                        "text": "Zebra stripes (zebrapad) on the road mean:",
                        "explanation": "Zebra crossings give pedestrians priority. Drivers must yield to any pedestrian on or clearly intending to cross.",
                        "difficulty": 1,
                        "options": [
                            ("Drivers have priority if no pedestrians are present", False),
                            ("Pedestrians have priority and you must yield", True),
                            ("You must stop and wait even if no pedestrians are present", False),
                            ("School children only may cross here", False),
                        ],
                    },
                    {
                        "text": "Long dashes (3m dashes with 1m gaps) on the road warn you that:",
                        "explanation": "Long dashes indicate you are approaching a solid line or a hazardous area. Treat the upcoming section with increased caution.",
                        "difficulty": 2,
                        "options": [
                            ("You are entering a bus lane", False),
                            ("A solid line or hazard is ahead — overtaking is about to be restricted", True),
                            ("The road ends here", False),
                            ("You are leaving a motorway", False),
                        ],
                    },
                    {
                        "text": "A yellow line painted along the kerb indicates:",
                        "explanation": "Yellow kerb lines in the Netherlands mean no stopping or parking at any time.",
                        "difficulty": 2,
                        "options": [
                            ("Parking is allowed for 30 minutes", False),
                            ("Loading and unloading is permitted", False),
                            ("No stopping or parking is permitted", True),
                            ("Parking for disabled drivers only", False),
                        ],
                    },
                ],
            },
        ],
    },
    {
        "slug": "parking-stopping",
        "title": "Parking and Stopping",
        "summary": "Rules for where and when you can park or stop your vehicle in the Netherlands.",
        "icon": "bi-p-circle",
        "order": 5,
        "dutch_terms": [
            {"term": "parkeren", "meaning": "parking (leaving vehicle unattended)"},
            {"term": "stoppen", "meaning": "stopping (briefly, driver remains)"},
            {"term": "parkeerschijf", "meaning": "parking disc (time-limited parking)"},
            {"term": "parkeerverbod", "meaning": "parking prohibition"},
            {"term": "stopverbod", "meaning": "stopping prohibition"},
        ],
        "lessons": [
            {
                "title": "Parking Rules and Restrictions",
                "summary": "Where you can and cannot park, and how to interpret parking signs.",
                "difficulty": "medium",
                "estimated_minutes": 12,
                "order": 1,
                "sections": [
                    {
                        "title": "Where Parking is Forbidden",
                        "content": (
                            "You must not park in the following locations:\n"
                            "• Less than 5 metres from a junction or intersection.\n"
                            "• On pedestrian crossings or within 5 metres before one.\n"
                            "• In front of an entrance to a home or property (driveway).\n"
                            "• At bus stops, taxi ranks, or disabled bays (without permit).\n"
                            "• Where a no-parking sign (E1) is displayed.\n"
                            "• In a no-stopping zone (E2 sign) — stopping is also forbidden here."
                        ),
                        "examples": [
                            "Parking on a corner forces other drivers to edge out blindly — always leave 5 metres.",
                            "Blocking a dropped kerb (lowered pavement for wheelchair access) is illegal.",
                        ],
                        "dutch_keywords": ["parkeerverbod", "stopverbod", "E1", "E2", "invalidenparkeerplaats"],
                        "order": 1,
                    },
                    {
                        "title": "Parking with a Disc",
                        "content": (
                            "Time-limited parking zones require a parkeerschijf (parking disc):\n"
                            "• Set the disc to the nearest half-hour after your arrival time.\n"
                            "• Display it visibly on the dashboard.\n"
                            "• Leave before the allowed time expires.\n"
                            "• Blue zone signs show permitted hours and maximum duration."
                        ),
                        "examples": [
                            "If you arrive at 13:47, set the disc to 14:00 (the next half-hour).",
                            "A blue P sign with '1 uur' means you may park for 1 hour maximum.",
                        ],
                        "dutch_keywords": ["parkeerschijf", "blauwe zone", "tijdzone"],
                        "order": 2,
                    },
                ],
                "questions": [
                    {
                        "text": "How close to a junction may you park?",
                        "explanation": "Parking within 5 metres of a junction obstructs visibility for other drivers. The minimum safe distance is 5 metres.",
                        "difficulty": 1,
                        "options": [
                            ("1 metre", False),
                            ("3 metres", False),
                            ("5 metres", True),
                            ("10 metres", False),
                        ],
                    },
                    {
                        "text": "You arrive at a blue zone at 14:23. What time should you set on the parking disc?",
                        "explanation": "The disc must be set to the next half-hour after your arrival. 14:23 rounds up to 14:30.",
                        "difficulty": 2,
                        "options": [
                            ("14:00", False),
                            ("14:23", False),
                            ("14:30", True),
                            ("15:00", False),
                        ],
                    },
                    {
                        "text": "An E2 sign (no stopping zone) means:",
                        "explanation": "An E2 sign prohibits all stopping, including very brief stops. Even dropping off a passenger is not allowed.",
                        "difficulty": 2,
                        "options": [
                            ("Parking is forbidden but brief stopping is allowed", False),
                            ("Both parking and stopping are forbidden", True),
                            ("Loading and unloading is allowed for 5 minutes", False),
                            ("Parking is forbidden during rush hour only", False),
                        ],
                    },
                    {
                        "text": "You want to park in front of a private driveway. Is this allowed?",
                        "explanation": "Parking in front of a driveway or entrance blocks vehicle access and is always prohibited.",
                        "difficulty": 1,
                        "options": [
                            ("Yes, if you will only be gone for a few minutes", False),
                            ("Yes, if it is after working hours", False),
                            ("No, it is always prohibited", True),
                            ("Yes, if you leave a note with your phone number", False),
                        ],
                    },
                ],
            },
        ],
    },
    {
        "slug": "motorways",
        "title": "Motorways",
        "summary": "Rules and safe practices for driving on Dutch motorways (autosnelwegen).",
        "icon": "bi-diagram-2",
        "order": 6,
        "dutch_terms": [
            {"term": "autosnelweg", "meaning": "motorway (A-roads)"},
            {"term": "invoegstrook", "meaning": "merging lane"},
            {"term": "uitvoegstrook", "meaning": "exit lane"},
            {"term": "vluchtstrook", "meaning": "hard shoulder / emergency lane"},
            {"term": "inhaalverbod", "meaning": "overtaking ban"},
        ],
        "lessons": [
            {
                "title": "Motorway Rules and Lane Discipline",
                "summary": "How to enter, use, and exit motorways safely.",
                "difficulty": "medium",
                "estimated_minutes": 15,
                "order": 1,
                "sections": [
                    {
                        "title": "Entering and Exiting",
                        "content": (
                            "Joining a motorway (invoegen):\n"
                            "• Use the acceleration lane (invoegstrook) to reach motorway speed.\n"
                            "• Traffic already on the motorway has priority.\n"
                            "• Merge smoothly — do not stop or slow down at the end of the on-ramp.\n\n"
                            "Leaving a motorway (uitvoegen):\n"
                            "• Move to the exit lane early.\n"
                            "• Reduce speed on the exit ramp, not on the main carriageway.\n"
                            "• Follow the posted speed limit for the exit."
                        ),
                        "examples": [
                            "Match your speed to motorway traffic before merging — not after.",
                            "Braking on the motorway while still in the main lane to make an exit causes rear-end collisions.",
                        ],
                        "dutch_keywords": ["invoegstrook", "uitvoegstrook", "versnellingsbaan", "afritten"],
                        "order": 1,
                    },
                    {
                        "title": "Lane Discipline and Hard Shoulder",
                        "content": (
                            "Lane rules on motorways:\n"
                            "• Keep right unless overtaking — driving unnecessarily in the middle or left lane is illegal.\n"
                            "• The left lane is the overtaking lane only.\n"
                            "• After overtaking, return to the right lane promptly.\n\n"
                            "Hard shoulder (vluchtstrook):\n"
                            "• For emergencies and breakdowns only.\n"
                            "• Do not use it for parking, stopping, or overtaking.\n"
                            "• Some motorways open the hard shoulder during peak hours — follow the signs."
                        ),
                        "examples": [
                            "Staying in the middle lane when the right lane is free is a fineable offence.",
                            "Breaking down: move to the hard shoulder, switch on hazard lights, exit from the passenger side.",
                        ],
                        "dutch_keywords": ["vluchtstrook", "linker rijstrook", "rechtsrijden", "inhalen"],
                        "order": 2,
                    },
                ],
                "questions": [
                    {
                        "text": "When joining a motorway, who has priority?",
                        "explanation": "Traffic already on the motorway has right of way. You must adapt your speed to theirs during merging.",
                        "difficulty": 1,
                        "options": [
                            ("The vehicle joining, because it is on an on-ramp", False),
                            ("Traffic already on the motorway", True),
                            ("The larger vehicle", False),
                            ("Whoever reaches the merge point first", False),
                        ],
                    },
                    {
                        "text": "When should you reduce speed before a motorway exit?",
                        "explanation": "You must reduce speed on the exit ramp (deceleration lane), not on the main carriageway, to avoid disrupting traffic flow.",
                        "difficulty": 2,
                        "options": [
                            ("On the main carriageway as soon as you see the exit sign", False),
                            ("On the exit ramp, after leaving the main carriageway", True),
                            ("200 metres before the exit sign", False),
                            ("Only after stopping at the traffic light at the end of the ramp", False),
                        ],
                    },
                    {
                        "text": "Driving in the middle lane of a three-lane motorway when the right lane is empty is:",
                        "explanation": "Dutch law requires drivers to keep right unless overtaking. Unnecessary lane hogging in the middle lane is illegal.",
                        "difficulty": 2,
                        "options": [
                            ("Allowed — it provides a safety buffer", False),
                            ("Allowed at speeds above 100 km/h", False),
                            ("Illegal — you must keep right unless overtaking", True),
                            ("Allowed if you are about to overtake someone", False),
                        ],
                    },
                    {
                        "text": "In which situation may you use the hard shoulder (vluchtstrook)?",
                        "explanation": "The hard shoulder is strictly for emergencies and breakdowns. It is never to be used for overtaking or regular stopping.",
                        "difficulty": 1,
                        "options": [
                            ("To overtake slow traffic on the right", False),
                            ("When the left lane is blocked", False),
                            ("Only in a genuine emergency or breakdown", True),
                            ("During rush hour when traffic is slow", False),
                        ],
                    },
                    {
                        "text": "You break down on a motorway. What is the recommended first action?",
                        "explanation": "Immediately activate hazard lights to warn following traffic, then safely steer to the hard shoulder.",
                        "difficulty": 2,
                        "options": [
                            ("Stop in your lane and call emergency services", False),
                            ("Switch on hazard lights and move to the hard shoulder", True),
                            ("Open the door and wave down other drivers", False),
                            ("Try to restart the vehicle before moving to the shoulder", False),
                        ],
                    },
                ],
            },
        ],
    },
    {
        "slug": "roundabouts",
        "title": "Roundabouts",
        "summary": "Navigate Dutch roundabouts correctly including priority rules and cyclist interactions.",
        "icon": "bi-arrow-repeat",
        "order": 7,
        "dutch_terms": [
            {"term": "rotonde", "meaning": "roundabout"},
            {"term": "voorrang op de rotonde", "meaning": "priority on the roundabout"},
            {"term": "fietsers op de rotonde", "meaning": "cyclists on the roundabout"},
            {"term": "invoegen", "meaning": "merging into the roundabout"},
        ],
        "lessons": [
            {
                "title": "Roundabout Priority and Navigation",
                "summary": "Who yields at Dutch roundabouts and how to navigate them safely.",
                "difficulty": "medium",
                "estimated_minutes": 12,
                "order": 1,
                "sections": [
                    {
                        "title": "Priority at Dutch Roundabouts",
                        "content": (
                            "In the Netherlands, vehicles on the roundabout generally have priority:\n"
                            "• Most roundabouts have shark teeth at the entry — give way to circulating traffic.\n"
                            "• Do NOT apply right-before-left on a roundabout.\n"
                            "• Some older roundabouts have different rules — always check the road markings.\n\n"
                            "Cyclists on the roundabout:\n"
                            "• Cyclists on a separate cycle path around the roundabout have priority over entering cars.\n"
                            "• Always check for cyclists before entering or exiting the roundabout."
                        ),
                        "examples": [
                            "You wait at the entry of a roundabout — look left and give way before entering.",
                            "A cyclist on the dedicated cycle path around the roundabout has priority as you exit.",
                        ],
                        "dutch_keywords": ["rotonde", "haaientanden", "fietspad", "uitvoegen"],
                        "order": 1,
                    },
                ],
                "questions": [
                    {
                        "text": "At a typical Dutch roundabout with shark teeth at the entry, who has priority?",
                        "explanation": "Shark teeth at the entry mean vehicles already on the roundabout have priority. You must wait until the way is clear.",
                        "difficulty": 1,
                        "options": [
                            ("The vehicle entering from the right", False),
                            ("Traffic already circulating on the roundabout", True),
                            ("The larger vehicle", False),
                            ("The vehicle that arrived first", False),
                        ],
                    },
                    {
                        "text": "There is a dedicated cycle path running around a Dutch roundabout. When exiting, you must:",
                        "explanation": "Cyclists on the roundabout's dedicated cycle path have priority over motorists exiting. Always yield to them.",
                        "difficulty": 2,
                        "options": [
                            ("Exit quickly so cyclists can pass behind you", False),
                            ("Sound your horn to warn cyclists", False),
                            ("Give way to cyclists on the cycle path", True),
                            ("Cyclists must wait for you to exit first", False),
                        ],
                    },
                    {
                        "text": "You are on a roundabout and need to take the third exit. You should:",
                        "explanation": "On a single-lane roundabout, stay in your lane and signal right before your exit. On multi-lane roundabouts, choose the appropriate lane on entry.",
                        "difficulty": 2,
                        "options": [
                            ("Signal left throughout and take the third exit", False),
                            ("Stay in your lane, signal right just before the third exit", True),
                            ("Change lanes to the right after the first exit", False),
                            ("No signalling is needed on roundabouts", False),
                        ],
                    },
                    {
                        "text": "Do right-before-left rules apply inside a roundabout?",
                        "explanation": "Right-before-left does not apply on roundabouts. The special roundabout priority rules (shark teeth at entry) override it.",
                        "difficulty": 2,
                        "options": [
                            ("Yes, always", False),
                            ("Yes, but only if the roundabout has no signs", False),
                            ("No — roundabout priority rules override right-before-left", True),
                            ("Only for cyclists entering from the right", False),
                        ],
                    },
                ],
            },
        ],
    },
    {
        "slug": "cyclists-pedestrians",
        "title": "Cyclists and Pedestrians",
        "summary": "Understand the rights and special rules for cyclists and pedestrians on Dutch roads.",
        "icon": "bi-bicycle",
        "order": 8,
        "dutch_terms": [
            {"term": "fietspad", "meaning": "cycle path"},
            {"term": "fietsstrook", "meaning": "cycle lane (on road)"},
            {"term": "oversteekplaats", "meaning": "crossing point"},
            {"term": "voetpad", "meaning": "pavement / footpath"},
            {"term": "dode hoek", "meaning": "blind spot (dead angle)"},
        ],
        "lessons": [
            {
                "title": "Sharing the Road with Cyclists",
                "summary": "Rules and best practices when encountering cyclists.",
                "difficulty": "medium",
                "estimated_minutes": 13,
                "order": 1,
                "sections": [
                    {
                        "title": "Cycle Paths and Lanes",
                        "content": (
                            "Cyclists in the Netherlands have extensive infrastructure:\n"
                            "• A red or marked cycle path (fietspad) is exclusively for cyclists.\n"
                            "• A cycle lane (fietsstrook) is a marked section of the road — do not drive in it.\n"
                            "• When turning, always check your mirrors and blind spot for cyclists.\n"
                            "• When opening a car door, check for approaching cyclists (dooring danger).\n"
                            "• At intersections where cyclists have their own traffic light, obey it."
                        ),
                        "examples": [
                            "Turning right at an intersection — a cyclist may be overtaking you on the right. Check blind spot.",
                            "Opening a door without checking can cause a serious collision with a passing cyclist.",
                        ],
                        "dutch_keywords": ["fietspad", "fietsstrook", "dode hoek", "richtingaanwijzer"],
                        "order": 1,
                    },
                    {
                        "title": "Pedestrian Safety",
                        "content": (
                            "Protecting pedestrians:\n"
                            "• Always yield to pedestrians on a zebrapad.\n"
                            "• When reversing, check for pedestrians behind the vehicle.\n"
                            "• In a woonerf, pedestrians may use the full road width.\n"
                            "• School zones (school zones signs): extra caution, reduced speed.\n"
                            "• Elderly and disabled pedestrians may move slowly — be patient."
                        ),
                        "examples": [
                            "A pedestrian stepping off the kerb towards a zebra crossing must be allowed to cross.",
                            "A child running between parked cars is a hazard — always reduce speed near parked cars.",
                        ],
                        "dutch_keywords": ["zebrapad", "schoolzone", "woonerf", "stoep"],
                        "order": 2,
                    },
                ],
                "questions": [
                    {
                        "text": "You are about to turn right. A cyclist is riding straight ahead in a cycle lane on your right. You should:",
                        "explanation": "Cyclists going straight ahead have priority over turning vehicles. Check mirrors and blind spot before turning.",
                        "difficulty": 2,
                        "options": [
                            ("Turn quickly before the cyclist reaches you", False),
                            ("Sound your horn and turn", False),
                            ("Give way to the cyclist, then turn", True),
                            ("The cyclist must stop because you are turning", False),
                        ],
                    },
                    {
                        "text": "Opening a car door without checking for cyclists is dangerous because:",
                        "explanation": "A cyclist may be passing at speed. An open door can cause a serious collision. Always use the 'Dutch reach' — check with the far hand.",
                        "difficulty": 1,
                        "options": [
                            ("It wastes time", False),
                            ("It may cause a collision with a passing cyclist", True),
                            ("It is only dangerous at night", False),
                            ("It is not dangerous if you open the door slowly", False),
                        ],
                    },
                    {
                        "text": "A pedestrian is waiting at a zebrapad (zebra crossing). What must you do?",
                        "explanation": "Any pedestrian at or clearly approaching a zebra crossing must be given priority. You must stop and allow them to cross.",
                        "difficulty": 1,
                        "options": [
                            ("Continue if the pedestrian is not yet on the crossing", False),
                            ("Flash your headlights to signal they can cross", False),
                            ("Stop and give way to the pedestrian", True),
                            ("Slow down but only stop if they step onto the road", False),
                        ],
                    },
                    {
                        "text": "In a woonerf (home zone), pedestrians are walking in the middle of the road. You should:",
                        "explanation": "In a woonerf, pedestrians have the right to use the full road. Drivers must yield and wait patiently.",
                        "difficulty": 2,
                        "options": [
                            ("Sound the horn to move them aside", False),
                            ("Drive around them quickly", False),
                            ("Wait patiently — pedestrians have full road use in a woonerf", True),
                            ("Drive at maximum 15 km/h past them", False),
                        ],
                    },
                ],
            },
        ],
    },
    {
        "slug": "hazard-recognition",
        "title": "Hazard Recognition",
        "summary": "Train yourself to spot and respond to hazards before they become dangerous situations.",
        "icon": "bi-exclamation-triangle",
        "order": 9,
        "dutch_terms": [
            {"term": "gevaarherkenning", "meaning": "hazard recognition"},
            {"term": "reactietijd", "meaning": "reaction time"},
            {"term": "remweg", "meaning": "braking distance"},
            {"term": "stopping distance", "meaning": "totale remweg (reaction + braking)"},
            {"term": "aquaplaning", "meaning": "aquaplaning (tyre loses grip on water)"},
        ],
        "lessons": [
            {
                "title": "Identifying and Reacting to Hazards",
                "summary": "How hazards develop and what to do about them.",
                "difficulty": "hard",
                "estimated_minutes": 18,
                "order": 1,
                "sections": [
                    {
                        "title": "Types of Hazards",
                        "content": (
                            "Hazards can be static or dynamic:\n"
                            "• Static: parked vehicles, road damage, sharp bends, obscured junctions.\n"
                            "• Dynamic: other vehicles, cyclists, children, animals, weather changes.\n\n"
                            "Key hazard hotspots:\n"
                            "• Junctions and roundabouts — conflict between different road users.\n"
                            "• School entrances — sudden child movements.\n"
                            "• Narrow streets — oncoming traffic, cyclists close to the edge.\n"
                            "• After a large vehicle — hidden cyclists, pedestrians stepping out."
                        ),
                        "examples": [
                            "A bus stopped ahead may have passengers crossing from the front — always check.",
                            "A ball rolling into the road means a child may follow immediately.",
                        ],
                        "dutch_keywords": ["gevaar", "schoolzone", "zijstraat", "doorzicht"],
                        "order": 1,
                    },
                    {
                        "title": "Stopping Distance and Speed",
                        "content": (
                            "Stopping distance = reaction distance + braking distance.\n"
                            "• At 50 km/h: approx 35 m total stopping distance.\n"
                            "• At 80 km/h: approx 70 m.\n"
                            "• At 120 km/h: approx 145 m.\n\n"
                            "Factors that increase stopping distance:\n"
                            "• Wet or icy roads.\n"
                            "• Worn tyres.\n"
                            "• Driver fatigue or distraction.\n"
                            "• Heavier vehicle load.\n\n"
                            "Rule of thumb: follow the 2-second rule in dry conditions, 4 seconds in wet."
                        ),
                        "examples": [
                            "At 120 km/h, closing the gap from 145 m to 50 m takes only about 2 seconds.",
                            "On wet roads, your braking distance can double — double your following distance.",
                        ],
                        "dutch_keywords": ["remweg", "reactietijd", "volgafstand", "natte weg"],
                        "order": 2,
                    },
                ],
                "questions": [
                    {
                        "text": "A bus has stopped at a bus stop ahead on your side of the road. You should:",
                        "explanation": "Passengers alighting from a bus may cross the road from the front or rear of the bus. Slow down and be prepared to stop.",
                        "difficulty": 2,
                        "options": [
                            ("Overtake quickly while the bus is stationary", False),
                            ("Sound your horn so passengers know you are approaching", False),
                            ("Slow down and watch for pedestrians crossing", True),
                            ("Switch lanes and maintain speed", False),
                        ],
                    },
                    {
                        "text": "A ball bounces into the road from between parked cars. What is the most important immediate concern?",
                        "explanation": "A ball often signals a child running after it. Brake immediately and watch for the child who may appear at any moment.",
                        "difficulty": 1,
                        "options": [
                            ("Avoid the ball by steering around it", False),
                            ("A child may follow the ball into the road", True),
                            ("Check if the ball damaged the road surface", False),
                            ("Sound the horn to alert anyone nearby", False),
                        ],
                    },
                    {
                        "text": "At 80 km/h on a wet road, your stopping distance compared to a dry road is:",
                        "explanation": "Wet roads significantly reduce tyre grip, roughly doubling the braking distance. Increase your following distance accordingly.",
                        "difficulty": 2,
                        "options": [
                            ("About the same", False),
                            ("Slightly shorter due to water on tyres", False),
                            ("Roughly double", True),
                            ("Triple", False),
                        ],
                    },
                    {
                        "text": "What does aquaplaning mean?",
                        "explanation": "Aquaplaning occurs when a layer of water builds under the tyres at speed, causing loss of steering control. Lift off the accelerator smoothly — do not brake hard.",
                        "difficulty": 3,
                        "options": [
                            ("Hydroelectric braking on wet roads", False),
                            ("Loss of tyre grip due to a water layer under the tyres", True),
                            ("Windscreen fogging in heavy rain", False),
                            ("Engine overheating from water splash", False),
                        ],
                    },
                    {
                        "text": "You are driving in heavy fog. The best action is to:",
                        "explanation": "In fog, use fog lights if visibility is below 50 m. Reduce speed significantly, increase following distance, and never rely solely on other cars' lights.",
                        "difficulty": 2,
                        "options": [
                            ("Use full beam headlights", False),
                            ("Use fog lights and reduce speed significantly", True),
                            ("Maintain normal speed to keep up with traffic", False),
                            ("Stop on the hard shoulder until fog lifts", False),
                        ],
                    },
                ],
            },
        ],
    },
    {
        "slug": "safe-driving",
        "title": "Safe and Responsible Driving",
        "summary": "Core principles of defensive and responsible driving to keep everyone safe.",
        "icon": "bi-shield-check",
        "order": 10,
        "dutch_terms": [
            {"term": "defensief rijden", "meaning": "defensive driving"},
            {"term": "rijden onder invloed", "meaning": "driving under influence (DUI)"},
            {"term": "mobiel rijden", "meaning": "using a mobile phone while driving"},
            {"term": "rijbewijs", "meaning": "driving licence"},
            {"term": "gordel", "meaning": "seatbelt"},
        ],
        "lessons": [
            {
                "title": "Defensive Driving Principles",
                "summary": "How to anticipate, communicate, and stay safe on Dutch roads.",
                "difficulty": "medium",
                "estimated_minutes": 15,
                "order": 1,
                "sections": [
                    {
                        "title": "Anticipation and Communication",
                        "content": (
                            "Defensive driving is about anticipating hazards before they occur:\n"
                            "• Scan ahead — look 12–15 seconds down the road.\n"
                            "• Check mirrors every 5–8 seconds.\n"
                            "• Indicate early before manoeuvres.\n"
                            "• Maintain a safe following distance (minimum 2-second gap).\n"
                            "• Avoid distractions: mobile phone use while driving is illegal."
                        ),
                        "examples": [
                            "Checking mirrors before braking prevents being rear-ended.",
                            "Indicating when changing lanes gives other drivers time to react.",
                        ],
                        "dutch_keywords": ["defensief rijden", "spiegels", "richtingaanwijzer", "volgafstand"],
                        "order": 1,
                    },
                    {
                        "title": "Alcohol, Drugs, and Fatigue",
                        "content": (
                            "Legal limits and responsibilities:\n"
                            "• Blood alcohol limit: 0.5 mg/ml (0.2 mg/ml for new drivers in the first 5 years).\n"
                            "• Drugs: zero tolerance for several substances — drugged driving is illegal.\n"
                            "• Fatigue: causes slow reactions and microsleep. Take breaks every 2 hours.\n"
                            "• Medicines: some prescription drugs affect driving ability — check the label.\n"
                            "• Seatbelts are compulsory for all occupants, front and rear."
                        ),
                        "examples": [
                            "A new driver may not have any alcohol at all — 0.2 mg/ml is already over the limit.",
                            "Driving after less than 6 hours of sleep significantly increases crash risk.",
                        ],
                        "dutch_keywords": ["alcohol", "promillage", "gordel", "rijden onder invloed", "moeheid"],
                        "order": 2,
                    },
                ],
                "questions": [
                    {
                        "text": "What is the blood alcohol limit for experienced drivers in the Netherlands?",
                        "explanation": "Experienced drivers must stay below 0.5 mg/ml blood alcohol. New drivers (first 5 years) have a stricter limit of 0.2 mg/ml.",
                        "difficulty": 1,
                        "options": [
                            ("0.2 mg/ml", False),
                            ("0.5 mg/ml", True),
                            ("0.8 mg/ml", False),
                            ("1.0 mg/ml", False),
                        ],
                    },
                    {
                        "text": "Using a hand-held mobile phone while driving is:",
                        "explanation": "Using a handheld phone while driving is illegal in the Netherlands. You must use a fully hands-free system.",
                        "difficulty": 1,
                        "options": [
                            ("Allowed at speeds under 30 km/h", False),
                            ("Allowed if you use earphones", False),
                            ("Illegal at all times while the vehicle is moving", True),
                            ("Allowed in traffic jams when stationary", False),
                        ],
                    },
                    {
                        "text": "How often should you check your mirrors during normal driving?",
                        "explanation": "Regular mirror checks every 5–8 seconds help you maintain awareness of traffic around you and prepare for safe manoeuvres.",
                        "difficulty": 2,
                        "options": [
                            ("Only when changing lanes", False),
                            ("Every 5–8 seconds", True),
                            ("Every 30 seconds is sufficient", False),
                            ("Only when braking", False),
                        ],
                    },
                    {
                        "text": "You feel very drowsy on a motorway. What should you do?",
                        "explanation": "Fatigue is as dangerous as drunk driving. The only safe solution is to stop at a service area and rest, or switch drivers.",
                        "difficulty": 1,
                        "options": [
                            ("Open the window and increase speed", False),
                            ("Turn up the radio and drink coffee", False),
                            ("Stop safely at the next service area and rest", True),
                            ("Continue driving — motorway roads are straight and safe", False),
                        ],
                    },
                    {
                        "text": "Seatbelts in the Netherlands are:",
                        "explanation": "Seatbelts are compulsory for all occupants in all seats. The driver is responsible for ensuring all passengers under 18 are buckled.",
                        "difficulty": 1,
                        "options": [
                            ("Compulsory only in front seats", False),
                            ("Recommended but not legally required in rear seats", False),
                            ("Compulsory for all occupants in all seats", True),
                            ("Only required on motorways", False),
                        ],
                    },
                ],
            },
        ],
    },
    {
        "slug": "environmental-driving",
        "title": "Environmental Driving",
        "summary": "Eco-friendly driving techniques that save fuel and reduce emissions.",
        "icon": "bi-leaf",
        "order": 11,
        "dutch_terms": [
            {"term": "zuinig rijden", "meaning": "eco-driving / fuel-efficient driving"},
            {"term": "uitstoot", "meaning": "emissions"},
            {"term": "brandstofverbruik", "meaning": "fuel consumption"},
            {"term": "anticiperen", "meaning": "anticipating ahead to avoid braking"},
            {"term": "motorremmen", "meaning": "engine braking (lifting off throttle)"},
        ],
        "lessons": [
            {
                "title": "Eco-Driving Techniques",
                "summary": "Practical tips for reducing fuel use and emissions.",
                "difficulty": "easy",
                "estimated_minutes": 10,
                "order": 1,
                "sections": [
                    {
                        "title": "Smooth and Anticipatory Driving",
                        "content": (
                            "Key eco-driving principles:\n"
                            "• Accelerate gently — harsh acceleration burns extra fuel.\n"
                            "• Anticipate traffic flow: lift off early instead of braking late.\n"
                            "• Use engine braking by releasing the accelerator — modern injected engines use no fuel on the overrun.\n"
                            "• Drive in the highest suitable gear — lower RPM means lower fuel use.\n"
                            "• Maintain a steady speed — avoid unnecessary acceleration and deceleration."
                        ),
                        "examples": [
                            "Seeing a red light ahead, lift off early and coast to a stop — uses less fuel than braking late.",
                            "Driving at 120 km/h uses roughly 25% more fuel than 100 km/h.",
                        ],
                        "dutch_keywords": ["zuinig rijden", "anticiperen", "motorremmen", "hoge versnelling"],
                        "order": 1,
                    },
                ],
                "questions": [
                    {
                        "text": "Which driving behaviour reduces fuel consumption the most?",
                        "explanation": "Smooth, anticipatory driving — avoiding unnecessary acceleration and braking — is the single biggest fuel saver.",
                        "difficulty": 1,
                        "options": [
                            ("Driving at maximum speed limits at all times", False),
                            ("Using air conditioning constantly", False),
                            ("Smooth, anticipatory driving with gentle acceleration", True),
                            ("Keeping the engine running at idle when stopped", False),
                        ],
                    },
                    {
                        "text": "When approaching a red traffic light, what is the eco-friendly action?",
                        "explanation": "Lifting off the accelerator early uses engine braking (no fuel on modern cars on overrun) and avoids the need for heavy braking.",
                        "difficulty": 1,
                        "options": [
                            ("Maintain speed and brake sharply at the line", False),
                            ("Lift off the accelerator early and coast towards the light", True),
                            ("Switch to neutral and rev the engine", False),
                            ("Brake hard and keep the clutch down", False),
                        ],
                    },
                    {
                        "text": "Driving at 130 km/h instead of 100 km/h on a motorway increases fuel consumption by approximately:",
                        "explanation": "Aerodynamic drag increases with the square of speed. Going from 100 to 130 km/h increases fuel use by roughly 40-50%.",
                        "difficulty": 3,
                        "options": [
                            ("5%", False),
                            ("10%", False),
                            ("40–50%", True),
                            ("100%", False),
                        ],
                    },
                    {
                        "text": "Switching off the engine during a stop of more than 60 seconds:",
                        "explanation": "Idling for more than about 60 seconds uses more fuel than restarting the engine. Modern stop-start systems do this automatically.",
                        "difficulty": 2,
                        "options": [
                            ("Damages the engine and should be avoided", False),
                            ("Saves fuel and reduces emissions", True),
                            ("Has no effect on fuel use", False),
                            ("Is only beneficial for diesel engines", False),
                        ],
                    },
                ],
            },
        ],
    },
    {
        "slug": "vehicle-knowledge",
        "title": "Vehicle Knowledge",
        "summary": "Basic vehicle systems, maintenance checks, and what to do when things go wrong.",
        "icon": "bi-wrench-adjustable",
        "order": 12,
        "dutch_terms": [
            {"term": "bandenspanning", "meaning": "tyre pressure"},
            {"term": "APK", "meaning": "vehicle roadworthiness test (MOT equivalent)"},
            {"term": "motorolie", "meaning": "engine oil"},
            {"term": "ruitenwissers", "meaning": "windscreen wipers"},
            {"term": "waarschuwingslicht", "meaning": "warning light"},
        ],
        "lessons": [
            {
                "title": "Pre-Drive Checks and Warning Lights",
                "summary": "What to check before driving and how to respond to dashboard warnings.",
                "difficulty": "easy",
                "estimated_minutes": 12,
                "order": 1,
                "sections": [
                    {
                        "title": "Essential Pre-Drive Checks",
                        "content": (
                            "Before every journey, quickly check:\n"
                            "• Tyres: correct pressure, no visible damage or unusual wear.\n"
                            "• Lights: all working — headlights, brake lights, indicators.\n"
                            "• Mirrors: clean and correctly adjusted.\n"
                            "• Fuel level: enough for the journey.\n"
                            "• Windscreen: clean and wipers functional.\n"
                            "• Engine oil and coolant: should be checked weekly or per dashboard warning."
                        ),
                        "examples": [
                            "An under-inflated tyre reduces fuel efficiency and increases blowout risk.",
                            "A cracked windscreen may fail the annual APK inspection.",
                        ],
                        "dutch_keywords": ["bandenspanning", "verlichting", "spiegels", "koelvloeistof"],
                        "order": 1,
                    },
                    {
                        "title": "Dashboard Warning Lights",
                        "content": (
                            "Common warning lights and appropriate responses:\n"
                            "• Red oil can: oil pressure critical — stop safely and immediately.\n"
                            "• Red temperature gauge: engine overheating — stop and let cool.\n"
                            "• Orange engine light: engine fault — get it checked soon.\n"
                            "• Red battery: charging system fault — complete the journey and get checked.\n"
                            "• Tyre pressure warning (TPMS): check and correct pressure when safe.\n"
                            "• Red brake warning: check handbrake is off; if still on, stop and seek help."
                        ),
                        "examples": [
                            "Ignoring a red oil pressure light can destroy the engine within minutes.",
                            "An orange engine warning that has been on for weeks usually indicates an emissions fault.",
                        ],
                        "dutch_keywords": ["olielampje", "motorlampje", "bandenspanningssensor", "remlicht"],
                        "order": 2,
                    },
                ],
                "questions": [
                    {
                        "text": "The red oil pressure warning light comes on while driving. You should:",
                        "explanation": "A red oil pressure warning means the engine has critically low oil pressure. Continuing to drive can destroy the engine within minutes. Stop immediately.",
                        "difficulty": 1,
                        "options": [
                            ("Add oil at the next petrol station", False),
                            ("Stop safely as soon as possible and do not continue driving", True),
                            ("It is a sensor fault — ignore it", False),
                            ("Reduce speed to 30 km/h and drive home", False),
                        ],
                    },
                    {
                        "text": "The APK (roadworthiness test) in the Netherlands is required:",
                        "explanation": "Vehicles older than 4 years must have an annual APK test. Driving without a valid APK is illegal and may invalidate insurance.",
                        "difficulty": 1,
                        "options": [
                            ("Every 5 years for all vehicles", False),
                            ("Annually for vehicles older than 4 years", True),
                            ("Only when you sell the vehicle", False),
                            ("Only for vehicles over 10 years old", False),
                        ],
                    },
                    {
                        "text": "Under-inflated tyres primarily affect:",
                        "explanation": "Under-inflated tyres increase rolling resistance, reduce fuel efficiency, cause uneven wear, and increase the risk of a blowout.",
                        "difficulty": 2,
                        "options": [
                            ("Engine performance only", False),
                            ("Fuel efficiency, tyre wear, and blowout risk", True),
                            ("Braking distance only", False),
                            ("Headlight alignment", False),
                        ],
                    },
                    {
                        "text": "The orange engine warning light comes on. The correct action is:",
                        "explanation": "An orange engine light indicates a non-critical fault, often emissions-related. The vehicle can be driven to a garage, but should be checked promptly.",
                        "difficulty": 2,
                        "options": [
                            ("Stop immediately and call a breakdown service", False),
                            ("Ignore it — it comes on occasionally in all cars", False),
                            ("Continue to destination, but have it checked at a garage promptly", True),
                            ("Reset it by turning the engine off and on", False),
                        ],
                    },
                ],
            },
        ],
    },
]


class Command(BaseCommand):
    help = "Seed the Dutch driving theory database with original learning content."

    def add_arguments(self, parser):
        parser.add_argument(
            "--clear",
            action="store_true",
            help="Delete all existing driving theory data before seeding.",
        )

    def handle(self, *args, **options):
        if options["clear"]:
            self.stdout.write("Clearing existing driving theory data…")
            DrivingTopic.objects.all().delete()
            self.stdout.write(self.style.WARNING("All driving theory data deleted."))

        total_topics = 0
        total_lessons = 0
        total_questions = 0

        for topic_data in TOPICS:
            topic, created = DrivingTopic.objects.get_or_create(
                slug=topic_data["slug"],
                defaults={
                    "title": topic_data["title"],
                    "summary": topic_data["summary"],
                    "dutch_terms": topic_data["dutch_terms"],
                    "icon": topic_data["icon"],
                    "order": topic_data["order"],
                },
            )
            if not created:
                # Update in case content changed
                topic.title = topic_data["title"]
                topic.summary = topic_data["summary"]
                topic.dutch_terms = topic_data["dutch_terms"]
                topic.icon = topic_data["icon"]
                topic.order = topic_data["order"]
                topic.save()

            total_topics += 1
            action = "Created" if created else "Updated"
            self.stdout.write(f"  {action} topic: {topic.title}")

            for lesson_data in topic_data.get("lessons", []):
                lesson, _ = DrivingLesson.objects.get_or_create(
                    topic=topic,
                    title=lesson_data["title"],
                    defaults={
                        "summary": lesson_data["summary"],
                        "difficulty": lesson_data["difficulty"],
                        "estimated_minutes": lesson_data["estimated_minutes"],
                        "order": lesson_data["order"],
                    },
                )
                total_lessons += 1

                for section_data in lesson_data.get("sections", []):
                    DrivingLessonSection.objects.get_or_create(
                        lesson=lesson,
                        title=section_data["title"],
                        defaults={
                            "content": section_data["content"],
                            "examples": section_data["examples"],
                            "dutch_keywords": section_data["dutch_keywords"],
                            "order": section_data["order"],
                        },
                    )

                for q_data in lesson_data.get("questions", []):
                    question, _ = DrivingQuestion.objects.get_or_create(
                        topic=topic,
                        question_text=q_data["text"],
                        defaults={
                            "lesson": lesson,
                            "explanation": q_data["explanation"],
                            "difficulty": q_data["difficulty"],
                        },
                    )
                    for order_idx, (opt_text, is_correct) in enumerate(q_data["options"]):
                        DrivingQuestionOption.objects.get_or_create(
                            question=question,
                            option_text=opt_text,
                            defaults={"is_correct": is_correct, "order": order_idx},
                        )
                    total_questions += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"\nSeeding complete: {total_topics} topics, {total_lessons} lessons, {total_questions} questions."
            )
        )
        self.stdout.write(
            self.style.WARNING(
                "\nDisclaimer: All content is original and for educational purposes only.\n"
                "GuideWisey is not affiliated with or endorsed by the CBR.\n"
            )
        )
