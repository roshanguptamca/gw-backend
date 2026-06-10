"""
Management command: enrich_driving_theory_v2

Enriches existing Dutch driving theory content with V2 fields:
  - color_theme, difficulty_level, learning_objectives, exam_weight (DrivingTopic)
  - learning_objectives, exam_tips, common_mistakes, key_takeaways (DrivingLesson)
  - callout_boxes, illustration_hint (DrivingLessonSection)
  - question_type, sign_hint (DrivingQuestion)

Also adds 3 new beginner topics:
  - introduction-to-dutch-driving
  - road-users
  - basic-traffic-rules

Usage:
    python manage.py enrich_driving_theory_v2
"""

from django.core.management.base import BaseCommand

# ---------------------------------------------------------------------------
# V2 enrichment data for existing 12 topics
# ---------------------------------------------------------------------------

TOPIC_ENRICHMENTS = {
    "traffic-signs": {
        "color_theme": "rgba(239,68,68,0.15)",
        "difficulty_level": "beginner",
        "exam_weight": 15,
        "learning_objectives": [
            "Identify all 11 Dutch traffic sign series (A–L) by shape and colour",
            "Distinguish between warning, prohibition, and mandatory signs",
            "Understand the STOP octagon and give-way triangle",
            "Recognise common roadwork and temporary signs",
        ],
    },
    "priority-rules": {
        "color_theme": "rgba(251,191,36,0.15)",
        "difficulty_level": "intermediate",
        "exam_weight": 18,
        "learning_objectives": [
            "Apply the right-from-right (rechts voor links) default rule",
            "Identify priority road signs and their meaning",
            "Understand when trams and emergency vehicles override priority",
            "Recognise haaientanden (shark's teeth) road markings",
            "Know roundabout entry and cyclist priority rules",
        ],
    },
    "speed-limits": {
        "color_theme": "rgba(249,115,22,0.15)",
        "difficulty_level": "beginner",
        "exam_weight": 12,
        "learning_objectives": [
            "Know default speed limits for each road type",
            "Understand the 2020 motorway daytime 100 km/h rule",
            "Identify speed limit signs (series A) and end-of-limit signs",
            "Know lower limits for trucks, buses, and towing vehicles",
            "Understand 30-zone and woonerf speed requirements",
        ],
    },
    "road-markings": {
        "color_theme": "rgba(168,85,247,0.15)",
        "difficulty_level": "intermediate",
        "exam_weight": 10,
        "learning_objectives": [
            "Distinguish solid from broken centre lines and know the rules for each",
            "Identify haaientanden (yield triangles) on the road surface",
            "Understand hatched areas (verdrijvingsvlakken) — no driving allowed",
            "Recognise cycle lane markings and bus lane markings",
            "Know the meaning of yellow kerb markings",
        ],
    },
    "parking-stopping": {
        "color_theme": "rgba(59,130,246,0.15)",
        "difficulty_level": "beginner",
        "exam_weight": 10,
        "learning_objectives": [
            "Understand the legal difference between stilstaan and parkeren",
            "Know where parking is always forbidden regardless of signs",
            "Read parking signs (series E) and time-based restrictions",
            "Understand the blue zone parking disc system",
            "Know the 5-metre rule near junctions",
        ],
    },
    "motorways": {
        "color_theme": "rgba(16,185,129,0.15)",
        "difficulty_level": "intermediate",
        "exam_weight": 10,
        "learning_objectives": [
            "Identify motorway (autosnelweg) vs expressway (autoweg) signs",
            "Understand merging and exit lane discipline",
            "Know the hard shoulder (vluchtstrook) usage rules",
            "Apply motorway speed limits including the 100 km/h daytime rule",
            "Know which vehicles are prohibited on motorways",
        ],
    },
    "roundabouts": {
        "color_theme": "rgba(20,184,166,0.15)",
        "difficulty_level": "intermediate",
        "exam_weight": 12,
        "learning_objectives": [
            "Apply the basic roundabout rule: entering traffic yields to circulating traffic",
            "Understand when cyclists have priority at roundabout exits",
            "Know correct signalling procedure on a roundabout",
            "Recognise roundabout signs and haaientanden at entry",
            "Navigate multi-lane roundabouts safely",
        ],
    },
    "cyclists-pedestrians": {
        "color_theme": "rgba(34,197,94,0.15)",
        "difficulty_level": "intermediate",
        "exam_weight": 12,
        "learning_objectives": [
            "Understand when motorists must yield to cyclists turning across a cycle path",
            "Know pedestrian rights at zebra crossings",
            "Understand the difference between fietspad and fietsstrook",
            "Know woonerf rules where children and pedestrians have priority",
            "Recognise shared-use paths and their markings",
        ],
    },
    "hazard-recognition": {
        "color_theme": "rgba(245,158,11,0.15)",
        "difficulty_level": "advanced",
        "exam_weight": 12,
        "learning_objectives": [
            "Identify developing hazards before they become dangerous",
            "Understand the 2-second following distance rule and when to increase it",
            "Recognise poor visibility conditions and the required response",
            "Know how to handle skids, aquaplaning, and tyre blowouts",
            "Apply defensive driving principles in complex traffic situations",
        ],
    },
    "safe-driving": {
        "color_theme": "rgba(236,72,153,0.15)",
        "difficulty_level": "intermediate",
        "exam_weight": 8,
        "learning_objectives": [
            "Understand Dutch alcohol limits: 0.5‰ general, 0.2‰ for novices",
            "Know the rules on mobile phone use while driving",
            "Understand fatigue management and rest requirements",
            "Know child passenger and seatbelt requirements",
            "Understand the consequences of road rage and distracted driving",
        ],
    },
    "environmental-driving": {
        "color_theme": "rgba(74,222,128,0.15)",
        "difficulty_level": "beginner",
        "exam_weight": 5,
        "learning_objectives": [
            "Apply anticipatory driving to reduce fuel consumption",
            "Understand engine braking and when to use it",
            "Know tyre pressure effects on fuel efficiency and safety",
            "Recognise low-emission zones (milieuzones) and their signs",
            "Understand the environmental benefits of smooth acceleration",
        ],
    },
    "vehicle-knowledge": {
        "color_theme": "rgba(99,102,241,0.15)",
        "difficulty_level": "beginner",
        "exam_weight": 6,
        "learning_objectives": [
            "Identify dashboard warning lights and their correct response",
            "Know pre-drive safety checks (tyres, mirrors, lights, brakes)",
            "Understand the difference between ABS, ESP, and traction control",
            "Know vehicle lighting rules for daytime and night driving",
            "Understand basic tyre safety: tread depth, pressure, condition",
        ],
    },
}

LESSON_ENRICHMENTS = {
    ("traffic-signs", "Sign Shapes and Colours"): {
        "learning_objectives": [
            "Match sign shapes to their category (warning, prohibition, mandatory, information)",
            "Identify all 11 sign series in the Dutch system",
        ],
        "exam_tips": [
            "Shape comes before content — identify the category first, then read the symbol",
            "STOP is the only octagonal sign — no other sign uses that shape",
            "Blue circles are always obligations; red circles are always prohibitions",
        ],
        "common_mistakes": [
            "Confusing warning triangles (J-series) with give-way inverted triangles (B6)",
            "Assuming a blue rectangle is mandatory — rectangles are informational",
        ],
        "key_takeaways": [
            "Triangle with red border = warning",
            "Circle with red border = prohibition",
            "Blue circle = mandatory instruction",
            "Octagon = STOP only",
        ],
    },
    ("priority-rules", "Right-of-Way Fundamentals"): {
        "learning_objectives": [
            "Apply the rechts-voor-links rule at unmarked junctions",
            "Identify all situations where the default rule does NOT apply",
        ],
        "exam_tips": [
            "Always check for haaientanden before assuming right-of-way",
            "Trams ALWAYS have priority — they cannot swerve to avoid you",
            "A yellow diamond (B1) means you are on the priority road",
        ],
        "common_mistakes": [
            "Forgetting that cyclists on a cycle path have priority when you turn across them",
            "Assuming priority road = unlimited right-of-way at all junctions",
        ],
        "key_takeaways": [
            "Default: vehicle from the right has priority",
            "Haaientanden painted on road = you must yield",
            "Trams override all other priority rules",
            "Emergency vehicles with lights and siren always have priority",
        ],
    },
    ("speed-limits", "Speed Limits by Road Type"): {
        "learning_objectives": [
            "State the default speed limit for each Dutch road type from memory",
            "Identify when a lower speed limit applies due to vehicle type",
        ],
        "exam_tips": [
            "The motorway 100 km/h limit applies from 06:00–19:00 only; at night it's 120–130 km/h on some roads",
            "Woonerf is 15 km/h — much lower than a 30-zone",
            "Speed limit signs are white with a red circle border (A-series)",
        ],
        "common_mistakes": [
            "Applying car limits to trucks and buses (they have lower limits on motorways)",
            "Forgetting that a 30-zone sign applies until an 'end of zone' sign, not just at one point",
        ],
        "key_takeaways": [
            "Woonerf: 15 km/h | 30-zone: 30 km/h | Urban: 50 km/h",
            "Rural road: 80 km/h | Expressway: 100 km/h | Motorway day: 100 km/h",
        ],
    },
    ("roundabouts", "Roundabout Priority and Entry"): {
        "learning_objectives": [
            "Apply yield rules when entering a roundabout",
            "Determine whether cyclists have priority at a given roundabout",
        ],
        "exam_tips": [
            "Look for the white bicycle sign — if present, cyclists on the outer path have priority over your exit",
            "You must always signal RIGHT when leaving a roundabout",
            "Haaientanden at the roundabout entry mean yield to circulating traffic",
        ],
        "common_mistakes": [
            "Forgetting to yield to cyclists when exiting a modern Dutch roundabout",
            "Not signalling right when leaving the roundabout",
        ],
        "key_takeaways": [
            "Entering traffic always yields to circulating traffic",
            "Modern urban roundabouts: cyclists on outer path have priority",
            "Always signal right on exit",
        ],
    },
}

SECTION_CALLOUTS = {
    ("Sign Shapes and Colours", "Understanding Shapes"): {
        "callout_boxes": [
            {
                "type": "remember",
                "content": "Shape tells you the category before you even read the symbol. Triangle = warn, circle = command, rectangle = inform.",
            },
            {
                "type": "tip",
                "content": "In the exam, if you see a red octagon, the answer is always STOP — no other sign uses this shape.",
            },
        ],
        "illustration_hint": "grid_of_sign_shapes_with_labels",
    },
    ("Sign Shapes and Colours", "Colour Meanings"): {
        "callout_boxes": [
            {
                "type": "warning",
                "content": "Orange/yellow background = temporary sign. These always override permanent signs. Follow them even if they contradict the normal rules.",
            },
        ],
        "illustration_hint": "colour_coded_sign_examples",
    },
    ("Right-of-Way Fundamentals", "Right from Right Rule"): {
        "callout_boxes": [
            {
                "type": "info",
                "content": "The rechts-voor-links rule only applies at junctions with NO signs, signals or road markings. As soon as there is a sign or haaientanden, the sign/markings rule applies instead.",
            },
        ],
        "illustration_hint": "four_way_junction_no_signs_arrows",
    },
    ("Speed Limits by Road Type", "Road Type Speed Table"): {
        "callout_boxes": [
            {
                "type": "tip",
                "content": "The 2020 motorway rule: 100 km/h during the day (06:00–19:00) on all motorways. Some roads allow 120 or 130 km/h at night — check the signs.",
            },
            {
                "type": "warning",
                "content": "Speed limits shown are for passenger cars. Trucks (>3,500 kg), buses, and vehicles towing are subject to lower limits.",
            },
        ],
        "illustration_hint": "speed_limit_table_by_road_type",
    },
}

QUESTION_TYPE_MAP = {
    "sign": "sign_recognition",
    "triangle": "sign_recognition",
    "octagon": "sign_recognition",
    "blue circle": "sign_recognition",
    "yellow diamond": "sign_recognition",
    "haaientanden": "scenario",
    "roundabout": "scenario",
    "intersection": "scenario",
    "junction": "scenario",
    "overtaking": "scenario",
    "parking": "scenario",
    "alcohol": "scenario",
    "distance": "scenario",
    "weather": "scenario",
    "emergency": "scenario",
    "tram": "scenario",
}

# ---------------------------------------------------------------------------
# New topics for V2
# ---------------------------------------------------------------------------

NEW_TOPICS = [
    {
        "slug": "introduction-to-dutch-driving",
        "title": "Introduction to Dutch Driving",
        "summary": "Understand the Dutch traffic legal framework, the RVV 1990, and what to expect from the CBR theory exam.",
        "icon": "bi-book-half",
        "order": 0,
        "color_theme": "rgba(99,102,241,0.15)",
        "difficulty_level": "beginner",
        "exam_weight": 3,
        "learning_objectives": [
            "Understand what the RVV 1990 is and why it matters",
            "Know the structure of the CBR theory exam",
            "Understand the difference between Category A and Category B licences",
            "Know the general obligations of all road users",
        ],
        "dutch_terms": [
            {"term": "rijbewijs", "meaning": "driving licence"},
            {"term": "rijexamen", "meaning": "driving exam"},
            {"term": "theorie-examen", "meaning": "theory test"},
            {"term": "RVV 1990", "meaning": "Dutch Road Traffic Rules and Regulations 1990"},
            {"term": "CBR", "meaning": "Central Bureau for Driving Skill (exam authority)"},
            {"term": "weggebruiker", "meaning": "road user"},
            {"term": "bestuurder", "meaning": "driver / vehicle operator"},
            {"term": "voetganger", "meaning": "pedestrian"},
        ],
        "lessons": [
            {
                "title": "Dutch Traffic Law and the CBR Exam",
                "summary": "An overview of Dutch traffic law and how the theory test is structured.",
                "difficulty": "easy",
                "estimated_minutes": 12,
                "order": 1,
                "learning_objectives": [
                    "State the purpose of the RVV 1990",
                    "Describe the CBR theory exam format and pass mark",
                    "Identify the main categories of road users",
                ],
                "exam_tips": [
                    "The CBR theory exam has 65 questions; you need at least 53 correct to pass",
                    "Questions are scenario-based — read each situation carefully before answering",
                    "You get 35 minutes for the standard exam",
                ],
                "common_mistakes": [
                    "Assuming Dutch rules are identical to your home country — always check",
                    "Underestimating the priority-rules section (most failed questions come from here)",
                ],
                "key_takeaways": [
                    "RVV 1990 = the legal basis for all Dutch traffic rules",
                    "CBR exam: 65 questions, 53 correct to pass, 35 minutes",
                    "All road users have a duty of care to others",
                ],
                "sections": [
                    {
                        "title": "What is the RVV 1990?",
                        "content": (
                            "The Reglement verkeersregels en verkeerstekens 1990 (RVV 1990) is the Dutch "
                            "national law that sets out all traffic rules, signs, and road markings.\n\n"
                            "It covers:\n"
                            "• Who counts as a road user and what rules apply to each type\n"
                            "• Speed limits on every type of road\n"
                            "• Right-of-way rules at intersections\n"
                            "• The meaning of every official traffic sign\n"
                            "• Parking and stopping rules\n"
                            "• Rules for special situations like motorways, level crossings, and tunnels\n\n"
                            "The law applies to everyone on Dutch public roads: drivers, cyclists, "
                            "motorcyclists, moped riders, and pedestrians."
                        ),
                        "examples": [
                            "A 50 km/h speed limit sign is legally valid because the RVV 1990 defines speed limit signs (A-series) and their binding meaning.",
                            "A cyclist riding on a footpath is breaking the RVV 1990, which reserves footpaths for pedestrians only.",
                        ],
                        "dutch_keywords": ["RVV 1990", "verkeersregels", "verkeerstekens", "weggebruiker"],
                        "order": 1,
                        "callout_boxes": [
                            {
                                "type": "info",
                                "content": "The RVV 1990 is publicly available at wetten.overheid.nl. Knowing the law gives you confidence in the exam — rules always have a legal basis.",
                            }
                        ],
                        "illustration_hint": "rvv_1990_cover_and_road_scene",
                    },
                    {
                        "title": "The CBR Theory Exam",
                        "content": (
                            "The CBR (Centraal Bureau Rijvaardigheidsbewijzen) is the official Dutch "
                            "organisation that administers driving tests.\n\n"
                            "Theory exam format:\n"
                            "• 65 multiple-choice questions\n"
                            "• 35 minutes allowed\n"
                            "• Pass mark: 53 correct answers (about 82%)\n"
                            "• Questions cover all topics: signs, priority, speed limits, parking, "
                            "hazard recognition, safe driving, and vehicle knowledge\n\n"
                            "Types of questions:\n"
                            "• Scenario questions — you see a road situation and must decide the correct action\n"
                            "• Sign recognition — identify what a sign means\n"
                            "• Rule application — choose the correct rule for a given situation\n\n"
                            "The exam is available in Dutch and in English."
                        ),
                        "examples": [
                            "A scenario question might show a junction with no signs and ask: 'You arrive from the left. A car arrives from the right. Who has priority?'",
                            "A sign recognition question might show a yellow diamond and ask: 'What does this sign tell you about your priority on this road?'",
                        ],
                        "dutch_keywords": ["CBR", "theorie-examen", "rijbewijs B", "slagingspercentage"],
                        "order": 2,
                        "callout_boxes": [
                            {
                                "type": "tip",
                                "content": "65 questions, need 53 correct. That means you can get at most 12 questions wrong. Practise the hardest topics (priority rules, roundabouts) the most.",
                            },
                            {
                                "type": "remember",
                                "content": "The exam is scenario-based. Always read the full situation before choosing your answer. The 'trick' is usually in a small detail in the description.",
                            },
                        ],
                        "illustration_hint": "cbr_exam_screen_mockup",
                    },
                ],
                "questions": [
                    {
                        "text": "How many questions must you answer correctly to pass the Dutch CBR theory exam?",
                        "explanation": "The CBR theory exam has 65 questions and requires at least 53 correct answers (approximately 82%) to pass within 35 minutes.",
                        "difficulty": 1,
                        "question_type": "multiple_choice",
                        "options": [
                            ("50 out of 60", False),
                            ("53 out of 65", True),
                            ("45 out of 55", False),
                            ("60 out of 70", False),
                        ],
                    },
                    {
                        "text": "What does the RVV 1990 regulate?",
                        "explanation": "The RVV 1990 (Reglement verkeersregels en verkeerstekens 1990) is the Dutch law that defines all traffic rules, traffic signs, and road marking meanings for all road users.",
                        "difficulty": 1,
                        "question_type": "multiple_choice",
                        "options": [
                            ("Only the rules for car drivers", False),
                            ("Traffic rules, signs, and road markings for all road users in the Netherlands", True),
                            ("Vehicle registration and insurance requirements", False),
                            ("Speed limits only", False),
                        ],
                    },
                    {
                        "text": "Which organisation conducts the official Dutch driving theory and practical tests?",
                        "explanation": "The CBR (Centraal Bureau Rijvaardigheidsbewijzen) is the official Dutch organisation that administers all driving tests — both theory and practical.",
                        "difficulty": 1,
                        "question_type": "multiple_choice",
                        "options": [
                            ("ANWB", False),
                            ("RDW", False),
                            ("CBR", True),
                            ("Rijkswaterstaat", False),
                        ],
                    },
                    {
                        "text": "The Dutch theory exam has 65 questions. How much time are you allowed?",
                        "explanation": "Candidates have 35 minutes to answer 65 questions in the CBR theory exam, averaging about 32 seconds per question.",
                        "difficulty": 1,
                        "question_type": "multiple_choice",
                        "options": [
                            ("25 minutes", False),
                            ("45 minutes", False),
                            ("35 minutes", True),
                            ("60 minutes", False),
                        ],
                    },
                    {
                        "text": "Which of the following is NOT a road user under Dutch traffic law?",
                        "explanation": "Under the RVV 1990, road users (weggebruikers) include pedestrians, cyclists, moped riders, motorcyclists, car drivers, and lorry drivers. A railway train operates on a separate track system and is not classified as a weggebruiker on public roads.",
                        "difficulty": 2,
                        "question_type": "multiple_choice",
                        "options": [
                            ("A pedestrian", False),
                            ("A cyclist", False),
                            ("A railway train", True),
                            ("A moped rider", False),
                        ],
                    },
                ],
            }
        ],
    },
    {
        "slug": "road-users",
        "title": "Road Users and Vehicle Categories",
        "summary": "Learn the different categories of road users, the rules that apply to each, and how they interact on Dutch roads.",
        "icon": "bi-people-fill",
        "order": 1,
        "color_theme": "rgba(6,182,212,0.15)",
        "difficulty_level": "beginner",
        "exam_weight": 5,
        "learning_objectives": [
            "Distinguish between all types of Dutch road users",
            "Understand the difference between a bromfiets and a snorfiets",
            "Know which roads and paths each vehicle category may use",
            "Understand the priority hierarchy among road users",
        ],
        "dutch_terms": [
            {"term": "voetganger", "meaning": "pedestrian"},
            {"term": "fietser", "meaning": "cyclist"},
            {"term": "bromfiets", "meaning": "moped (up to 45 km/h, requires helmet)"},
            {"term": "snorfiets", "meaning": "light moped (up to 25 km/h)"},
            {"term": "motorrijder", "meaning": "motorcyclist"},
            {"term": "personenauto", "meaning": "passenger car"},
            {"term": "vrachtauto", "meaning": "lorry / heavy goods vehicle (>3,500 kg)"},
            {"term": "bestelauto", "meaning": "van / light goods vehicle (≤3,500 kg)"},
            {"term": "lijnbus", "meaning": "public service bus"},
            {"term": "tram", "meaning": "tram / streetcar — always has right of way"},
            {"term": "voorrangsvoertuig", "meaning": "emergency vehicle with active lights and siren"},
        ],
        "lessons": [
            {
                "title": "Categories of Road Users",
                "summary": "From pedestrians to lorries — understanding who can go where and what rules apply.",
                "difficulty": "easy",
                "estimated_minutes": 15,
                "order": 1,
                "learning_objectives": [
                    "Name all main road user categories under Dutch law",
                    "Know which roads each category may and may not use",
                    "Understand bromfiets vs snorfiets distinctions",
                ],
                "exam_tips": [
                    "Trams always have right of way — this is tested frequently",
                    "A bromfiets may reach 45 km/h and rides on the road; a snorfiets is limited to 25 km/h and usually uses the cycle path",
                    "Emergency vehicles with both lights AND siren active have absolute priority",
                ],
                "common_mistakes": [
                    "Confusing snorfiets (25 km/h, often on cycle path) with bromfiets (45 km/h, on road)",
                    "Forgetting that buses leaving a bus stop within a built-up area have right of way",
                ],
                "key_takeaways": [
                    "Pedestrians → footpath | Cyclists → cycle path | Bromfiets → road | Snorfiets → cycle path",
                    "Trams > emergency vehicles > buses at stops > all other vehicles",
                ],
                "sections": [
                    {
                        "title": "Pedestrians and Cyclists",
                        "content": (
                            "Pedestrians (voetgangers) must use pavements (trottoir) or footpaths (voetpad). "
                            "Where no footpath exists, they may walk on the left side of the road facing traffic.\n\n"
                            "Cyclists (fietsers) should use cycle paths (fietspad) when one is present. "
                            "If there is no cycle path, cyclists ride on the road, keeping to the right.\n\n"
                            "Pedestrians at a zebra crossing (zebrapad) have right of way over vehicles. "
                            "Cyclists do not automatically have right of way at all junctions — they follow "
                            "the same priority rules as other vehicles unless specific signs say otherwise."
                        ),
                        "examples": [
                            "A pedestrian crosses at a marked zebra crossing. You are driving at 50 km/h. You must slow down and give way.",
                            "A cycle path runs alongside the road. A cyclist is on it. You wish to turn right across it. You must yield to the cyclist.",
                        ],
                        "dutch_keywords": ["voetganger", "fietser", "trottoir", "fietspad", "zebrapad"],
                        "order": 1,
                        "callout_boxes": [
                            {
                                "type": "warning",
                                "content": "When turning right across a cycle path, you MUST yield to cyclists — even if you have a green light. This is a very common exam question.",
                            }
                        ],
                        "illustration_hint": "road_cross_section_showing_footpath_cycle_path_road",
                    },
                    {
                        "title": "Mopeds, Motorcycles, and Cars",
                        "content": (
                            "Mopeds (tweewielers met motor) come in two types in the Netherlands:\n\n"
                            "Bromfiets: maximum speed 45 km/h, uses the road (not cycle path), rider must wear "
                            "a helmet. Requires a Category AM licence.\n\n"
                            "Snorfiets: maximum speed 25 km/h, must use cycle path where available, rider must "
                            "wear a helmet (since 2023). Also Category AM.\n\n"
                            "Motorcycles (motor): Category A licence, ride on the road, subject to the same "
                            "rules as cars except they may not ride side-by-side in the same lane.\n\n"
                            "Passenger cars (personenauto): Category B licence. Maximum authorised mass "
                            "≤ 3,500 kg. May use all roads except cycle paths, footpaths, and woonerven "
                            "except to access a destination."
                        ),
                        "examples": [
                            "A bromfiets rider approaches a cycle path. They may NOT use the cycle path — bromfiets must use the road.",
                            "A snorfiets approaches a road with a marked cycle path. They MUST use the cycle path, not the road.",
                        ],
                        "dutch_keywords": ["bromfiets", "snorfiets", "motor", "personenauto", "rijbewijs AM"],
                        "order": 2,
                        "callout_boxes": [
                            {
                                "type": "info",
                                "content": "Memory trick: Brom = road (Brom has 4 letters, roads have 4 wheels). Snor = cycle path (Snor sounds like snail — slow, uses cycle path).",
                            },
                            {
                                "type": "tip",
                                "content": "In the exam: if a question mentions a two-wheeled motorised vehicle, first identify if it's a bromfiets (45 km/h, road) or snorfiets (25 km/h, cycle path) before answering.",
                            },
                        ],
                        "illustration_hint": "bromfiets_vs_snorfiets_comparison_diagram",
                    },
                    {
                        "title": "Trams, Buses, and Emergency Vehicles",
                        "content": (
                            "Trams (tram): Trams always have right of way over all other traffic. "
                            "You must never cut in front of a tram or cross its tracks carelessly. "
                            "Trams ring a bell as a warning — when you hear it, give way immediately.\n\n"
                            "Public buses (lijnbus): A bus that is indicating to leave a bus stop within "
                            "a built-up area has right of way. Other drivers must let it pull out.\n\n"
                            "Emergency vehicles (voorrangsvoertuigen): Police, fire, ambulance, and other "
                            "designated emergency vehicles with both blue lights AND siren active have "
                            "absolute right of way. You must move to the right and stop if necessary to "
                            "create a clear path."
                        ),
                        "examples": [
                            "A tram approaches an intersection at the same time as your car. The tram has no stop sign. You must give way to the tram regardless of who arrives first.",
                            "A bus is indicating to leave a bus stop on a 50 km/h urban road. You are approaching from behind. You must slow down and let the bus out.",
                            "An ambulance with lights and siren is approaching. You are on a two-lane road. You must pull to the right and stop to allow it to pass.",
                        ],
                        "dutch_keywords": ["tram", "lijnbus", "voorrangsvoertuig", "politie", "ambulance"],
                        "order": 3,
                        "callout_boxes": [
                            {
                                "type": "warning",
                                "content": "Never cross tram tracks diagonally — your tyres can get caught in the rail groove. Always cross at a right angle (perpendicular).",
                            },
                            {
                                "type": "remember",
                                "content": "Priority order: Trams > Emergency vehicles (lights+siren) > Buses leaving stops > All other vehicles.",
                            },
                        ],
                        "illustration_hint": "tram_bus_emergency_vehicle_illustrations",
                    },
                ],
                "questions": [
                    {
                        "text": "A snorfiets approaches a road that has a marked cycle path alongside it. Where must the snorfiets rider go?",
                        "explanation": "A snorfiets (limited to 25 km/h) must use the cycle path where one is available. Only if no cycle path exists may the rider use the road.",
                        "difficulty": 1,
                        "question_type": "scenario",
                        "options": [
                            ("Use the road, as mopeds must always use the road", False),
                            ("Use the cycle path", True),
                            ("Use either the road or the cycle path — their choice", False),
                            ("Stop, as snorfietsen are not allowed in this zone", False),
                        ],
                    },
                    {
                        "text": "A public bus is indicating to leave a bus stop. You are driving behind the bus in the same direction. What must you do?",
                        "explanation": "Within a built-up area, a bus indicating to leave a bus stop has right of way. Other drivers must slow down and let it merge back into traffic.",
                        "difficulty": 2,
                        "question_type": "scenario",
                        "options": [
                            ("Overtake the bus quickly before it moves", False),
                            ("Sound your horn to warn the bus driver", False),
                            ("Give way to the bus and let it pull out", True),
                            ("Flash your headlights to signal permission", False),
                        ],
                    },
                    {
                        "text": "At a junction, a tram and a car arrive at the same time. The tram approaches from the left. Who has priority?",
                        "explanation": "Trams always have right of way over all other road users at all times — regardless of which direction they come from. The right-from-right rule does not apply to trams.",
                        "difficulty": 2,
                        "question_type": "scenario",
                        "options": [
                            ("The car, because it arrives from the right", False),
                            ("The tram, because trams always have priority", True),
                            ("Whoever arrived first", False),
                            ("The car, because it is on the main road", False),
                        ],
                    },
                    {
                        "text": "A bromfiets rider approaches a roundabout with a marked cycle path around it. May the bromfiets rider use the cycle path?",
                        "explanation": "A bromfiets (up to 45 km/h) is classified as a road vehicle and must use the road, not the cycle path. Only snorfietsen may use the cycle path.",
                        "difficulty": 2,
                        "question_type": "scenario",
                        "options": [
                            ("Yes — all two-wheeled vehicles may use cycle paths", False),
                            ("No — bromfiets must use the road", True),
                            ("Yes — but only at this type of roundabout", False),
                            ("Only if the cycle path is wider than 2 metres", False),
                        ],
                    },
                    {
                        "text": "An ambulance with flashing blue lights but WITHOUT a siren approaches from behind. Must you give way?",
                        "explanation": "The priority rule for emergency vehicles (voorrangsvoertuigen) applies only when BOTH the blue lights AND the siren are in use simultaneously. Lights alone do not trigger the priority rule, though it is always courteous to make way.",
                        "difficulty": 3,
                        "question_type": "scenario",
                        "options": [
                            ("Yes — blue lights alone are enough to require right of way", False),
                            ("No — priority only applies when both lights and siren are active", True),
                            ("Only if it is travelling faster than 80 km/h", False),
                            ("Only on motorways", False),
                        ],
                    },
                ],
            }
        ],
    },
    {
        "slug": "basic-traffic-rules",
        "title": "Basic Traffic Rules",
        "summary": "Core driving rules every driver must know — from overtaking and turning to level crossings and traffic lights.",
        "icon": "bi-traffic-light",
        "order": 3,
        "color_theme": "rgba(234,179,8,0.15)",
        "difficulty_level": "beginner",
        "exam_weight": 8,
        "learning_objectives": [
            "Know when overtaking is permitted and when it is forbidden",
            "Understand correct procedure at traffic lights",
            "Know the rules at level crossings (overwegen)",
            "Understand the rules for turning left and right",
            "Apply lane discipline on multi-lane roads",
        ],
        "dutch_terms": [
            {"term": "inhalen", "meaning": "overtaking"},
            {"term": "verkeerslicht", "meaning": "traffic light"},
            {"term": "overweg", "meaning": "level crossing (road crosses railway)"},
            {"term": "invoegstrook", "meaning": "merging lane"},
            {"term": "uitrijstrook", "meaning": "exit lane"},
            {"term": "rijstrook", "meaning": "driving lane"},
            {"term": "bocht", "meaning": "bend / curve"},
            {"term": "inrijden", "meaning": "to enter (a road or zone)"},
            {"term": "uitrijden", "meaning": "to exit (a road or zone)"},
        ],
        "lessons": [
            {
                "title": "Overtaking, Turning, and Lane Rules",
                "summary": "When and how to safely overtake, how to turn correctly, and what lane discipline means.",
                "difficulty": "easy",
                "estimated_minutes": 18,
                "order": 1,
                "learning_objectives": [
                    "List all situations where overtaking is forbidden",
                    "Describe the correct mirror-signal-check procedure",
                    "Apply turning rules for left and right turns at intersections",
                ],
                "exam_tips": [
                    "Overtaking is forbidden near intersections, on bends, near STOP signs, and on pedestrian crossings",
                    "You must always overtake on the LEFT in the Netherlands (right-hand traffic)",
                    "Before turning left, move to the centre of the road; before turning right, move to the right edge",
                ],
                "common_mistakes": [
                    "Forgetting that a solid centre line means no overtaking regardless of visibility",
                    "Turning right without first checking for cyclists on the right",
                ],
                "key_takeaways": [
                    "Overtake on the left, pass stationary trams on the right (when passengers are boarding)",
                    "Solid white line = no overtaking; broken line = overtaking permitted if safe",
                    "Always give way to cyclists when turning right across a cycle path",
                ],
                "sections": [
                    {
                        "title": "Overtaking Rules",
                        "content": (
                            "In the Netherlands, you drive on the right and normally overtake on the left.\n\n"
                            "You may NOT overtake when:\n"
                            "• There is a solid centre line (you must not cross it)\n"
                            "• You are at or near a junction (unless the junction is clearly marked as safe)\n"
                            "• You are on a bend where you cannot see far enough ahead\n"
                            "• You are approaching a pedestrian crossing\n"
                            "• You are on a hill crest or just after one\n"
                            "• A STOP sign or give-way sign is just ahead\n"
                            "• The vehicle ahead is signalling to turn left and is moving to the centre line\n\n"
                            "Passing a stationary tram is an exception: you must pass a stationary tram "
                            "on the RIGHT when passengers are boarding or alighting, because passengers "
                            "step into the road on the right side of the tram."
                        ),
                        "examples": [
                            "You approach a solid white centre line. A slow tractor is ahead. You must NOT overtake — wait until the line becomes broken.",
                            "A tram has stopped to let passengers board. You must carefully pass it on the right, watching for passengers stepping into the road.",
                        ],
                        "dutch_keywords": ["inhalen", "doorgetrokken streep", "onderbroken streep", "tram"],
                        "order": 1,
                        "callout_boxes": [
                            {
                                "type": "warning",
                                "content": "A solid white centre line is an absolute prohibition. Even if you can see clearly for 500 metres ahead, you may NOT cross it to overtake.",
                            },
                            {
                                "type": "info",
                                "content": "You pass a stationary tram on the RIGHT — the only time you move to the right to pass a vehicle. This is because tram doors open on the right (street side).",
                            },
                        ],
                        "illustration_hint": "overtaking_scenarios_solid_vs_broken_line",
                    },
                    {
                        "title": "Traffic Lights",
                        "content": (
                            "Dutch traffic lights follow the standard sequence:\n\n"
                            "• Red: Stop before the stop line. Do not cross.\n"
                            "• Red + Amber (together): Prepare to go. Engine ready. Do NOT move yet.\n"
                            "• Green: Proceed if the way is clear. Yield to any remaining pedestrians or cyclists.\n"
                            "• Amber alone: Stop if you can do so safely. Only continue if stopping would be dangerous.\n\n"
                            "Green arrow signs:\n"
                            "A separate green arrow sign allows you to proceed in that specific direction "
                            "even when the main light is red — but you must still yield to crossing pedestrians "
                            "and cyclists who have a green signal.\n\n"
                            "Flashing amber: Proceed with caution. Treat the junction as an unmarked junction "
                            "and apply right-from-right priority rules."
                        ),
                        "examples": [
                            "The light turns amber as you approach at 50 km/h and are only 15 metres from the line. You may continue — stopping safely is not possible.",
                            "A green arrow allows you to turn right on red. A pedestrian is crossing with a green walking signal. You must yield to the pedestrian.",
                        ],
                        "dutch_keywords": [
                            "rood licht",
                            "groen licht",
                            "oranje licht",
                            "groenpijl",
                            "knipperend oranje",
                        ],
                        "order": 2,
                        "callout_boxes": [
                            {
                                "type": "remember",
                                "content": "Red + Amber together = be ready to go, but do NOT move. This phase is a warning — not permission. Only GREEN is permission.",
                            },
                            {
                                "type": "tip",
                                "content": "At a flashing amber light, apply right-from-right (rechts voor links) priority rules. The light is telling you to be cautious, not that you have automatic priority.",
                            },
                        ],
                        "illustration_hint": "traffic_light_sequence_diagram",
                    },
                    {
                        "title": "Level Crossings",
                        "content": (
                            "A level crossing (overweg) is where a road crosses a railway track.\n\n"
                            "Rules at level crossings:\n"
                            "• Slow down and be prepared to stop well before the crossing\n"
                            "• If barriers are down or lowering, or red lights are flashing, you MUST stop\n"
                            "• Never cross if a train is visible or audible, even if lights have stopped\n"
                            "• Never stop ON the crossing\n"
                            "• Never race to beat the barrier — trains cannot brake quickly\n\n"
                            "Types of level crossings:\n"
                            "• With barriers and flashing lights — most protected\n"
                            "• With flashing lights only (no barriers)\n"
                            "• With an X-shaped warning sign only — least protected, most dangerous\n\n"
                            "The St Andrew's Cross (Andreaskruis) is the white X-shaped sign that marks "
                            "ALL level crossings. One stripe means one track; two stripes mean two tracks."
                        ),
                        "examples": [
                            "The red lights are flashing at a level crossing and you can hear a train approaching. You must stop before the stop line and wait until the lights stop flashing and the barrier has fully risen.",
                            "An unguarded crossing has only an X-sign. You must slow to a speed where you can stop if a train appears — there are no barriers or lights to warn you.",
                        ],
                        "dutch_keywords": ["overweg", "Andreaskruis", "slagboom", "spoorwegovergang"],
                        "order": 3,
                        "callout_boxes": [
                            {
                                "type": "warning",
                                "content": "Never stop ON a level crossing. If your vehicle breaks down on a crossing, get everyone out immediately and move away from the tracks.",
                            },
                            {
                                "type": "tip",
                                "content": "One stripe on the St Andrew's Cross = 1 track. Two stripes = 2 tracks. More tracks means a longer time before the barrier rises again.",
                            },
                        ],
                        "illustration_hint": "level_crossing_types_diagrams",
                    },
                ],
                "questions": [
                    {
                        "text": "You are driving at 50 km/h and are 10 metres from a traffic light when it turns amber. What should you do?",
                        "explanation": "When you are too close to stop safely, you may continue through an amber light. At 10 metres distance travelling at 50 km/h, stopping safely is not possible, so you should continue carefully.",
                        "difficulty": 2,
                        "question_type": "scenario",
                        "options": [
                            ("Brake hard and stop before the line", False),
                            ("Continue, as stopping would be dangerous at this distance and speed", True),
                            ("Speed up to clear the junction faster", False),
                            ("Stop in the junction to wait for green", False),
                        ],
                    },
                    {
                        "text": "A solid white centre line runs along the middle of the road. A slow tractor is ahead. May you overtake?",
                        "explanation": "A solid white centre line is an absolute prohibition on crossing or overtaking. You must not overtake, regardless of how clearly you can see ahead.",
                        "difficulty": 1,
                        "question_type": "scenario",
                        "options": [
                            ("Yes, if you can see the road is clear for at least 200 metres", False),
                            ("Yes, but only at speeds below 50 km/h", False),
                            ("No — a solid centre line prohibits overtaking absolutely", True),
                            ("Yes, a tractor is so slow that it counts as a stationary vehicle", False),
                        ],
                    },
                    {
                        "text": "You approach a level crossing. Red lights are flashing and you can hear a train. The barrier has not yet come down. What must you do?",
                        "explanation": "Flashing red lights at a level crossing are an absolute command to stop. The barrier position is irrelevant — flashing lights mean a train is approaching. You must stop and wait.",
                        "difficulty": 1,
                        "question_type": "scenario",
                        "options": [
                            ("Cross quickly before the barrier comes down", False),
                            ("Stop and wait until the lights stop flashing and the crossing is clear", True),
                            ("Slow down and cross carefully", False),
                            ("Stop only when the barrier starts to move", False),
                        ],
                    },
                    {
                        "text": "A tram has stopped at a tram stop. Passengers are getting on and off. Where do you pass?",
                        "explanation": "You pass a stationary tram on the RIGHT because tram doors open on the right (street) side. Passengers step onto the road, so you pass slowly and carefully on the right.",
                        "difficulty": 2,
                        "question_type": "scenario",
                        "options": [
                            ("On the left, as with all other vehicles", False),
                            ("On the right, watching for passengers stepping into the road", True),
                            ("You may not pass — wait until all passengers have boarded", False),
                            ("On whichever side has more space", False),
                        ],
                    },
                    {
                        "text": "Traffic lights show red + amber together. What does this mean?",
                        "explanation": "Red and amber together is a preparation phase meaning 'get ready to go'. You must NOT move yet — only green is permission to proceed. This phase warns you to prepare your vehicle.",
                        "difficulty": 1,
                        "question_type": "multiple_choice",
                        "options": [
                            ("You may proceed if the junction is clear", False),
                            ("Prepare to move but do NOT proceed yet — only green is permission", True),
                            ("Emergency vehicles have priority — clear the junction", False),
                            ("The lights are faulty — treat as a flashing amber", False),
                        ],
                    },
                    {
                        "text": "On a bend where you cannot see ahead, you want to overtake a slow vehicle. Is this allowed?",
                        "explanation": "Overtaking on a bend where visibility is restricted is forbidden. You cannot assess whether oncoming traffic is present, making overtaking extremely dangerous.",
                        "difficulty": 1,
                        "question_type": "scenario",
                        "options": [
                            ("Yes, if you sound the horn first", False),
                            ("Yes, briefly — you only need to signal", False),
                            ("No — overtaking on a bend with restricted visibility is forbidden", True),
                            ("Yes, if the vehicle ahead is travelling under 30 km/h", False),
                        ],
                    },
                ],
            }
        ],
    },
]


# ---------------------------------------------------------------------------
# Command
# ---------------------------------------------------------------------------


class Command(BaseCommand):
    help = "Enrich existing Dutch driving theory data with V2 fields and add 3 new beginner topics."

    def handle(self, *args, **options):
        from apps.driving_theory.models import (
            DrivingLesson,
            DrivingLessonSection,
            DrivingQuestion,
            DrivingQuestionOption,
            DrivingTopic,
        )

        # Store as instance vars so sub-methods can access
        self.DrivingTopic = DrivingTopic
        self.DrivingLesson = DrivingLesson
        self.DrivingLessonSection = DrivingLessonSection
        self.DrivingQuestion = DrivingQuestion
        self.DrivingQuestionOption = DrivingQuestionOption

        self.stdout.write(self.style.HTTP_INFO("\n=== Dutch Driving Theory V2 Enrichment ===\n"))

        self._enrich_existing_topics()
        self._enrich_lessons()
        self._enrich_sections()
        self._enrich_questions()
        self._add_new_topics()

        self.stdout.write(self.style.SUCCESS("\n✅ V2 enrichment complete.\n"))

    def _enrich_existing_topics(self):
        DrivingTopic = self.DrivingTopic
        self.stdout.write("\n[1/5] Enriching existing topic fields…")
        for slug, data in TOPIC_ENRICHMENTS.items():
            updated = DrivingTopic.objects.filter(slug=slug).update(
                color_theme=data.get("color_theme", "rgba(99,102,241,0.15)"),
                difficulty_level=data.get("difficulty_level", "beginner"),
                exam_weight=data.get("exam_weight", 8),
                learning_objectives=data.get("learning_objectives", []),
            )
            if updated:
                self.stdout.write(f"  ✓ {slug}")
            else:
                self.stdout.write(self.style.WARNING(f"  ⚠ Topic not found: {slug}"))

    def _enrich_lessons(self):
        DrivingLesson = self.DrivingLesson
        self.stdout.write("\n[2/5] Enriching lesson fields…")
        for (topic_title_fragment, lesson_title), data in LESSON_ENRICHMENTS.items():
            lessons = DrivingLesson.objects.filter(
                topic__slug=topic_title_fragment,
                title=lesson_title,
            )
            if lessons.exists():
                lessons.update(
                    learning_objectives=data.get("learning_objectives", []),
                    exam_tips=data.get("exam_tips", []),
                    common_mistakes=data.get("common_mistakes", []),
                    key_takeaways=data.get("key_takeaways", []),
                )
                self.stdout.write(f"  ✓ {lesson_title}")
            else:
                self.stdout.write(self.style.WARNING(f"  ⚠ Lesson not found: {lesson_title}"))

    def _enrich_sections(self):
        DrivingLessonSection = self.DrivingLessonSection
        self.stdout.write("\n[3/5] Enriching section callout_boxes…")
        for (section_title, subsection_title), data in SECTION_CALLOUTS.items():
            sections = DrivingLessonSection.objects.filter(
                lesson__title=section_title,
                title=subsection_title,
            )
            if sections.exists():
                sections.update(
                    callout_boxes=data.get("callout_boxes", []),
                    illustration_hint=data.get("illustration_hint", ""),
                )
                self.stdout.write(f"  ✓ {section_title} > {subsection_title}")
            else:
                self.stdout.write(self.style.WARNING(f"  ⚠ Section not found: {section_title} > {subsection_title}"))

    def _enrich_questions(self):
        DrivingQuestion = self.DrivingQuestion
        self.stdout.write("\n[4/5] Enriching question types…")
        count = 0
        for question in DrivingQuestion.objects.all():
            text_lower = question.question_text.lower()
            q_type = "multiple_choice"
            for keyword, qt in QUESTION_TYPE_MAP.items():
                if keyword in text_lower:
                    q_type = qt
                    break
            if question.question_type != q_type:
                question.question_type = q_type
                question.save(update_fields=["question_type"])
                count += 1
        self.stdout.write(f"  ✓ Updated {count} questions with appropriate types")

    def _add_new_topics(self):
        DrivingTopic = self.DrivingTopic
        DrivingLesson = self.DrivingLesson
        DrivingLessonSection = self.DrivingLessonSection
        DrivingQuestion = self.DrivingQuestion
        DrivingQuestionOption = self.DrivingQuestionOption
        self.stdout.write("\n[5/5] Adding 3 new beginner topics…")
        for topic_data in NEW_TOPICS:
            topic, created = DrivingTopic.objects.update_or_create(
                slug=topic_data["slug"],
                defaults={
                    "title": topic_data["title"],
                    "summary": topic_data["summary"],
                    "dutch_terms": topic_data["dutch_terms"],
                    "icon": topic_data["icon"],
                    "order": topic_data["order"],
                    "color_theme": topic_data["color_theme"],
                    "difficulty_level": topic_data["difficulty_level"],
                    "exam_weight": topic_data["exam_weight"],
                    "learning_objectives": topic_data["learning_objectives"],
                },
            )
            action = "Created" if created else "Updated"
            self.stdout.write(f"  {action} topic: {topic.title}")

            for lesson_data in topic_data.get("lessons", []):
                lesson, _ = DrivingLesson.objects.update_or_create(
                    topic=topic,
                    title=lesson_data["title"],
                    defaults={
                        "summary": lesson_data["summary"],
                        "difficulty": lesson_data["difficulty"],
                        "estimated_minutes": lesson_data["estimated_minutes"],
                        "order": lesson_data["order"],
                        "learning_objectives": lesson_data.get("learning_objectives", []),
                        "exam_tips": lesson_data.get("exam_tips", []),
                        "common_mistakes": lesson_data.get("common_mistakes", []),
                        "key_takeaways": lesson_data.get("key_takeaways", []),
                    },
                )

                # Delete and recreate sections (safe — no external FKs to sections)
                lesson.sections.all().delete()
                for section_data in lesson_data.get("sections", []):
                    DrivingLessonSection.objects.create(
                        lesson=lesson,
                        title=section_data["title"],
                        content=section_data["content"],
                        examples=section_data["examples"],
                        dutch_keywords=section_data.get("dutch_keywords", []),
                        order=section_data["order"],
                        callout_boxes=section_data.get("callout_boxes", []),
                        illustration_hint=section_data.get("illustration_hint", ""),
                    )

                for q_data in lesson_data.get("questions", []):
                    question, _ = DrivingQuestion.objects.get_or_create(
                        topic=topic,
                        question_text=q_data["text"],
                        defaults={
                            "lesson": lesson,
                            "explanation": q_data["explanation"],
                            "difficulty": q_data["difficulty"],
                            "question_type": q_data.get("question_type", "multiple_choice"),
                            "sign_hint": q_data.get("sign_hint", ""),
                        },
                    )
                    for order_idx, (opt_text, is_correct) in enumerate(q_data["options"]):
                        DrivingQuestionOption.objects.get_or_create(
                            question=question,
                            option_text=opt_text,
                            defaults={"is_correct": is_correct, "order": order_idx},
                        )

            self.stdout.write(
                f"    → {lesson_data['title']}: {len(lesson_data.get('sections', []))} sections, {len(lesson_data.get('questions', []))} questions"
            )
