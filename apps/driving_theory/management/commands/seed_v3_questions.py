"""seed_v3_questions - Add 3000+ original Dutch driving theory questions."""

import random

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.driving_theory.models import DrivingQuestion, DrivingQuestionOption, DrivingTopic

TOPIC_MINIMUMS = {
    "introduction-to-dutch-driving": 50,
    "road-users": 100,
    "traffic-signs": 300,
    "basic-traffic-rules": 200,
    "priority-rules": 300,
    "speed-limits": 200,
    "road-markings": 200,
    "parking-stopping": 200,
    "roundabouts": 200,
    "cyclists-pedestrians": 200,
    "motorways": 200,
    "hazard-recognition": 200,
    "safe-driving": 150,
    "environmental-driving": 100,
    "vehicle-knowledge": 150,
}


TOPIC_TARGETS = {
    "introduction-to-dutch-driving": 60,
    "road-users": 120,
    "traffic-signs": 320,
    "basic-traffic-rules": 220,
    "priority-rules": 320,
    "speed-limits": 220,
    "road-markings": 220,
    "parking-stopping": 220,
    "roundabouts": 220,
    "cyclists-pedestrians": 220,
    "motorways": 220,
    "hazard-recognition": 220,
    "safe-driving": 160,
    "environmental-driving": 120,
    "vehicle-knowledge": 160,
}


TOTAL_TARGET = 3000


def question(
    question_text,
    explanation,
    options,
    correct_index,
    difficulty=1,
    question_type="multiple_choice",
    sign_hint="",
    points=1,
):
    """options: list of 4 strings. correct_index: 0-3."""
    return {
        "question_text": question_text,
        "explanation": explanation,
        "difficulty": difficulty,
        "question_type": question_type,
        "sign_hint": sign_hint,
        "points": points,
        "is_active": True,
        "options": [
            {"option_text": opt, "is_correct": (i == correct_index), "order": i} for i, opt in enumerate(options)
        ],
    }


def build_question(
    question_text,
    explanation,
    correct_answer,
    wrong_answers,
    difficulty=1,
    question_type="multiple_choice",
    sign_hint="",
    points=1,
):
    cleaned_wrongs = []
    for wrong in wrong_answers:
        if wrong != correct_answer and wrong not in cleaned_wrongs:
            cleaned_wrongs.append(wrong)
    if len(cleaned_wrongs) < 3:
        raise ValueError(f"Question '{question_text}' does not have enough distinct wrong answers.")
    options = [correct_answer, *cleaned_wrongs[:3]]
    rng = random.Random(question_text)
    rng.shuffle(options)
    return question(
        question_text,
        explanation,
        options,
        options.index(correct_answer),
        difficulty=difficulty,
        question_type=question_type,
        sign_hint=sign_hint,
        points=points,
    )


def add_variants(
    bucket,
    prompts,
    correct_answer,
    wrong_answers,
    explanation,
    difficulty=1,
    question_type="multiple_choice",
    sign_hint="",
    points=1,
):
    for prompt in prompts:
        bucket.append(
            build_question(
                prompt,
                explanation,
                correct_answer,
                wrong_answers,
                difficulty=difficulty,
                question_type=question_type,
                sign_hint=sign_hint,
                points=points,
            )
        )


def rule_prompts(subject):
    return [
        f"What is the correct rule about {subject}?",
        f"Which statement about {subject} is correct?",
        f"You get a Dutch theory question about {subject}. Which answer is right?",
        f"In Dutch traffic, what should you remember about {subject}?",
        f"Which option best matches the rule for {subject}?",
    ]


def sign_prompts(description):
    return [
        f"What does {description} mean?",
        f"You see {description}. Which answer is correct?",
        f"On a Dutch road, {description} tells you that...",
        f"Which statement best explains {description}?",
        f"If {description} appears before you, what rule does it give?",
    ]


def scenario_prompts(context):
    return [
        f"At {context}, what should you do?",
        f"You arrive at {context}. Which answer is correct?",
        f"In this situation - {context} - what is the right choice?",
        f"How should you react at {context}?",
        f"Which option best fits this scenario: {context}?",
    ]


def hazard_prompts(context):
    return [
        f"What is the safest response when {context}?",
        f"You notice that {context}. What should you do first?",
        f"In hazard recognition, how do you deal with this situation: {context}?",
        f"Which action is safest when {context}?",
        f"What should a careful driver do when {context}?",
    ]


def finalize_topic(slug, questions):
    seen = set()
    unique_questions = []
    for q in questions:
        text = q["question_text"].strip()
        if text in seen:
            raise ValueError(f"Duplicate question text in {slug}: {text}")
        seen.add(text)
        unique_questions.append(q)
    if len(unique_questions) < TOPIC_MINIMUMS[slug]:
        raise ValueError(f"Topic {slug} only has {len(unique_questions)} questions")
    random.Random(f"rvv-1990-{slug}").shuffle(unique_questions)
    return unique_questions


def build_introduction_questions():
    questions = []

    basics = [
        (
            "the RVV 1990, the main Dutch regulation for everyday road signs and traffic behaviour",
            "It is the main everyday traffic rules regulation.",
            [
                "It is only a handbook for driving instructors.",
                "It only applies to motorways.",
                "It is a vehicle insurance contract.",
            ],
            "RVV 1990 contains the practical traffic rules used on Dutch roads, including signs, markings, priority, and behaviour.",
            1,
        ),
        (
            "driving on ordinary Dutch roads",
            "You normally keep to the right side of the road.",
            [
                "You normally keep to the left side of the road.",
                "You drive in the middle if the road feels narrow.",
                "You choose either side if traffic is light.",
            ],
            "In the Netherlands, traffic normally keeps right. This matters for lane choice, turning, and overtaking.",
            1,
        ),
        (
            "sharing Dutch roads with cyclists and pedestrians",
            "You should expect vulnerable road users and adapt your speed and space early.",
            [
                "You may assume cyclists will always wait for cars.",
                "You should drive at the posted maximum even if space feels tight.",
                "You only need to think about vulnerable road users at zebra crossings.",
            ],
            "Dutch traffic has many cyclists and pedestrians. Safe driving means reading the environment early and leaving space.",
            1,
        ),
        (
            "your fitness to drive before starting a trip",
            "You are responsible for not driving when you are too tired, distracted, or unwell.",
            [
                "Short trips make fitness rules irrelevant.",
                "Only professional drivers must think about fitness.",
                "Coffee legally replaces the need for rest.",
            ],
            "Driver fitness is part of road safety. If you are too tired or impaired, you should not drive.",
            1,
        ),
    ]
    for subject, correct, wrongs, explanation, difficulty in basics:
        add_variants(questions, rule_prompts(subject), correct, wrongs, explanation, difficulty=difficulty)

    exam_and_documents = [
        (
            "the organisation that runs Dutch theory and practical driving exams",
            "The CBR is the organisation that runs those exams.",
            [
                "The municipality runs all driving exams.",
                "The police runs the theory exam for learners.",
                "Insurance companies run the practical exam.",
            ],
            "The Centraal Bureau Rijvaardigheidsbewijzen (CBR) organises Dutch driving exams and related assessments.",
            1,
        ),
        (
            "why theory study matters before practical driving",
            "It helps you recognise rules, hazards, and safe decisions before real traffic situations happen.",
            [
                "It only matters for professional drivers.",
                "It replaces the need to observe signs on the road.",
                "It is only about memorising road names.",
            ],
            "Good theory knowledge supports safe practical driving because you understand signs, priority, and risks earlier.",
            1,
        ),
        (
            "documents and legal readiness before you drive",
            "The driver and vehicle must be legally ready, including correct licence, registration, insurance, and safe condition.",
            [
                "Only fuel level matters before a trip.",
                "Legal readiness only matters on motorways.",
                "If the trip is short, registration and insurance do not matter.",
            ],
            "A legal trip needs a lawful driver and a lawful vehicle. Insurance, registration, and vehicle condition still matter on short journeys.",
            2,
        ),
        (
            "how to approach a difficult theory question",
            "Read calmly, look for the exact rule, and choose the safest answer that matches Dutch law.",
            [
                "Always choose the answer with the highest speed.",
                "Guess without reading all options.",
                "Ignore signs in the question and follow your habit.",
            ],
            "Dutch theory questions reward calm reading. Details such as signs, markings, and road users change the correct answer.",
            1,
        ),
    ]
    for subject, correct, wrongs, explanation, difficulty in exam_and_documents:
        add_variants(questions, rule_prompts(subject), correct, wrongs, explanation, difficulty=difficulty)

    road_user_categories = [
        (
            "the word 'road user' in Dutch traffic theory",
            "It includes everyone using the road, such as drivers, cyclists, pedestrians, riders, and tram drivers.",
            [
                "It only means car drivers.",
                "It only means people with a Dutch driving licence.",
                "It excludes cyclists and pedestrians.",
            ],
            "Road users are all people who use the road system, not only motorists.",
            1,
        ),
        (
            "how Dutch theory treats vulnerable road users",
            "They deserve extra attention because they have less physical protection.",
            [
                "They always lose priority because they move slowly.",
                "They only matter inside built-up areas.",
                "They are treated exactly like heavy vehicles in all situations.",
            ],
            "Cyclists, pedestrians, and similar users are more vulnerable, so a careful driver anticipates their mistakes and reduced protection.",
            1,
        ),
        (
            "the difference between knowing a rule and applying it",
            "A safe driver both knows the rule and adjusts speed, position, and observation in time.",
            [
                "Knowing the rule means you never need to scan the road.",
                "Application only matters in bad weather.",
                "Application means driving faster to clear the situation quickly.",
            ],
            "Dutch driving theory tests practical insight, not only memorised sentences. You must connect rules to safe behaviour.",
            2,
        ),
        (
            "the purpose of learning Dutch sign categories early",
            "It helps you understand a sign faster because shape and colour already tell you what kind of rule it is.",
            [
                "Categories do not matter if you know how to drive.",
                "Only police officers need sign categories.",
                "Colours are decorative and have no meaning.",
            ],
            "Many Dutch signs can be understood faster when you recognise the usual shape and colour family first.",
            1,
        ),
    ]
    for subject, correct, wrongs, explanation, difficulty in road_user_categories:
        add_variants(questions, rule_prompts(subject), correct, wrongs, explanation, difficulty=difficulty)

    return finalize_topic("introduction-to-dutch-driving", questions)


def build_road_user_questions():
    questions = []

    brom_snor_items = [
        (
            "the main difference between a bromfiets and a snorfiets",
            "A bromfiets has a higher maximum design speed than a snorfiets.",
            [
                "A snorfiets is always faster than a bromfiets.",
                "There is no legal difference between them.",
                "Only the colour of the helmet makes the difference.",
            ],
            "A bromfiets is the faster moped category, while a snorfiets is the slower category.",
        ),
        (
            "the usual maximum design speed of a bromfiets",
            "It is 45 km/h.",
            [
                "It is 25 km/h.",
                "It is 60 km/h.",
                "It is 80 km/h.",
            ],
            "A bromfiets is the moped category with a normal maximum design speed of 45 km/h.",
        ),
        (
            "the usual maximum design speed of a snorfiets",
            "It is 25 km/h.",
            [
                "It is 15 km/h.",
                "It is 45 km/h.",
                "It is 70 km/h.",
            ],
            "A snorfiets is the slower moped category and normally has a maximum design speed of 25 km/h.",
        ),
        (
            "the number plate colour used to recognise a bromfiets",
            "A bromfiets normally has a yellow number plate.",
            [
                "A bromfiets normally has a blue number plate.",
                "A bromfiets has no number plate.",
                "A bromfiets always uses a white temporary plate.",
            ],
            "A yellow moped plate is the common visual clue for a bromfiets.",
        ),
        (
            "the number plate colour used to recognise a snorfiets",
            "A snorfiets normally has a blue number plate.",
            [
                "A snorfiets normally has a yellow number plate.",
                "A snorfiets has no number plate.",
                "A snorfiets always uses a red plate.",
            ],
            "A blue moped plate is the common clue for a snorfiets.",
        ),
        (
            "helmet rules for moped riders in modern Dutch traffic",
            "Riders of both bromfietsen and snorfietsen should follow the mandatory helmet rules.",
            [
                "Only passengers need helmets.",
                "A helmet is optional for every moped if the trip is short.",
                "Helmet rules only apply outside built-up areas.",
            ],
            "Modern Dutch moped rules require helmets for these categories. A short trip does not remove that duty.",
        ),
    ]
    for subject, correct, wrongs, explanation in brom_snor_items:
        add_variants(questions, rule_prompts(subject), correct, wrongs, explanation, difficulty=1)

    tram_items = [
        (
            "meeting a tram in normal traffic without a sign that changes priority",
            "You should assume the tram has priority unless signs or signals clearly state otherwise.",
            [
                "You always have priority because you are more manoeuvrable.",
                "The tram must always wait for cars turning right.",
                "A tram only has priority at night.",
            ],
            "Because a tram cannot easily leave its track, Dutch theory teaches that you should normally let it go unless signs or signals say otherwise.",
        ),
        (
            "turning across tram tracks in town",
            "You should not block the tram and should let it pass when its path would be obstructed.",
            [
                "You may stop on the tracks if your indicator is on.",
                "A tram must brake for any turning car.",
                "Tracks may be used as a waiting lane whenever traffic is busy.",
            ],
            "Blocking tram tracks creates danger and delay. If your movement would obstruct the tram, wait and leave the track area clear.",
        ),
        (
            "overtaking or passing a stopped tram where passengers may step onto the road",
            "You should slow down sharply and be ready to stop for passengers.",
            [
                "You should accelerate before passengers notice you.",
                "You may ignore passengers if you stay in your lane.",
                "You only slow down if it is raining.",
            ],
            "Passengers entering or leaving a tram are vulnerable road users. Passing carefully and slowly is essential.",
        ),
        (
            "choosing priority only because your vehicle is smaller than a tram",
            "Vehicle size does not give you priority over a tram.",
            [
                "Smaller vehicles always go first near rails.",
                "Cars always outrank trams because they can travel faster.",
                "Whoever reaches the crossing later goes first.",
            ],
            "Priority depends on rules and signs, not on vehicle size. In practice a tram is usually given room because it cannot steer away.",
        ),
    ]
    for subject, correct, wrongs, explanation in tram_items:
        add_variants(
            questions, rule_prompts(subject), correct, wrongs, explanation, difficulty=2, question_type="scenario"
        )

    bus_items = [
        (
            "a bus indicating away from a bus stop inside a built-up area",
            "You should give the bus the opportunity to leave the stop.",
            [
                "The bus must always wait for every car behind it.",
                "You may sound your horn and continue past the bus.",
                "This rule only applies outside built-up areas.",
            ],
            "Inside built-up areas, drivers should allow a bus that signals from an official stop to pull away safely.",
        ),
        (
            "a bus leaving a stop without using its indicator",
            "You still observe carefully, but the clear legal expectation for giving room starts when the bus indicates.",
            [
                "You must ignore the bus because buses never re-enter traffic.",
                "You should accelerate to prevent the bus from merging.",
                "You may drive on the pavement to pass the bus.",
            ],
            "The special courtesy rule is linked to the bus indicating from the stop, but a careful driver still reads the situation calmly.",
        ),
        (
            "passing a bus stop where people may step into the road",
            "You should lower your speed and be prepared for unpredictable pedestrian movement.",
            [
                "You should keep maximum speed because the bus is stationary.",
                "You may assume nobody will cross near a bus stop.",
                "You only need to look at the bus mirrors.",
            ],
            "Bus stops create extra pedestrian movement. Good observation and lower speed reduce risk.",
        ),
        (
            "assuming that every bus has priority in every situation",
            "That is incorrect; the special pull-away rule applies in a specific built-up area situation and normal signs still matter.",
            [
                "It is correct because buses always outrank cars.",
                "It is correct because buses are larger vehicles.",
                "It is correct because buses never need indicators.",
            ],
            "Buses are not automatically first in every situation. The rule is specific and signs, markings, and signals still apply.",
        ),
    ]
    for subject, correct, wrongs, explanation in bus_items:
        add_variants(
            questions, rule_prompts(subject), correct, wrongs, explanation, difficulty=2, question_type="scenario"
        )

    emergency_items = [
        (
            "an emergency vehicle using blue flashing lights and a siren",
            "You must give way and create a safe path as soon as you can.",
            [
                "You keep your own priority if you are already in a turn.",
                "You only give way on motorways.",
                "You may continue because emergency vehicles can drive around you.",
            ],
            "Blue flashing lights together with the siren indicate an emergency vehicle on priority duty. Other road users must let it pass safely.",
        ),
        (
            "hearing a siren but not yet seeing the emergency vehicle",
            "Stay calm, look around, and avoid blocking junctions until you know where it is coming from.",
            [
                "Brake hard in every lane without looking.",
                "Speed up to clear the road faster.",
                "Ignore the sound until you see the vehicle next to you.",
            ],
            "Good drivers search early for the source of a siren and avoid making unpredictable movements.",
        ),
        (
            "moving aside for an ambulance on a narrow street",
            "Make space without creating a new danger for cyclists or pedestrians.",
            [
                "Mount the pavement without checking first.",
                "Stop in the middle of the road and do nothing.",
                "Force cyclists into parked cars to create a gap.",
            ],
            "You must help an emergency vehicle pass, but you still have to avoid causing a collision with other vulnerable road users.",
        ),
        (
            "an emergency vehicle that uses only blue lights or only a siren",
            "You still stay alert, but the strongest legal command to give way is the combination of blue flashing lights and siren.",
            [
                "You may race the emergency vehicle to the junction.",
                "You never need to pay attention unless the driver waves.",
                "You should stop on railway tracks immediately.",
            ],
            "The classic priority signal is blue flashing lights together with the siren. Even before that, a calm, observant driver prepares not to obstruct.",
        ),
        (
            "another driver freezing in front of an approaching fire engine",
            "You should stay predictable and help create space instead of copying a panicked reaction.",
            [
                "Copy the panic stop regardless of what is around you.",
                "Overtake the fire engine to stay ahead of it.",
                "Ignore the fire engine because the other driver has already stopped.",
            ],
            "Emergency situations are handled best by calm, predictable movements that create a clear path.",
        ),
        (
            "thinking that blue lights give an emergency vehicle permission to ignore all safety",
            "That is wrong; other drivers must give way, but everyone still has to act safely.",
            [
                "It is correct because emergency vehicles can never be dangerous.",
                "It is correct because emergency drivers never need to watch other traffic.",
                "It is correct because the law stops applying during an emergency.",
            ],
            "Emergency vehicles receive priority, but safety and observation still matter for all road users.",
        ),
    ]
    for subject, correct, wrongs, explanation in emergency_items:
        add_variants(
            questions, rule_prompts(subject), correct, wrongs, explanation, difficulty=2, question_type="scenario"
        )

    misc_users = [
        (
            "why pedestrians and cyclists are often called vulnerable road users",
            "They have much less physical protection in a collision.",
            [
                "They always know the rules better than motorists.",
                "They are slower than buses.",
                "They are only vulnerable in bad weather.",
            ],
            "Vulnerability mainly refers to reduced physical protection, which means a driver should anticipate and leave extra space.",
        ),
        (
            "meeting a horse rider or an animal on or near the road",
            "You should slow down and avoid startling the animal.",
            [
                "You should use the horn to make the animal move faster.",
                "You may pass closely because animals always stay calm.",
                "You only need to react if the animal enters the motorway.",
            ],
            "Animals can react unpredictably. Slow, calm behaviour reduces risk for everyone.",
        ),
        (
            "road workers next to a narrowed lane",
            "Treat them as vulnerable road users and adapt speed and position early.",
            [
                "Keep the normal maximum speed because they are wearing bright clothing.",
                "Assume they will move out of your way.",
                "Only trucks need to slow near road works.",
            ],
            "Road workers have limited space and deserve careful passing with lower speed and extra room.",
        ),
        (
            "mobility-impaired pedestrians using the road space slowly",
            "Give them time and do not pressure them with speed or horn use.",
            [
                "Pressure them to move faster so traffic can keep flowing.",
                "Assume they will always hear your engine in time.",
                "Only yield if a zebra crossing is painted.",
            ],
            "A patient driver gives slower pedestrians time and space, especially when they may move unpredictably.",
        ),
    ]
    for subject, correct, wrongs, explanation in misc_users:
        add_variants(questions, rule_prompts(subject), correct, wrongs, explanation, difficulty=1)

    return finalize_topic("road-users", questions)


def build_traffic_sign_questions():
    questions = []

    for speed in [15, 30, 50, 60, 70, 80, 90, 100, 120, 130]:
        if speed == 15:
            description = "the blue woonerf or erf sign together with the special residential area rules"
            correct = "You must drive at walking pace, about 15 km/h, and expect pedestrians in the street."
            wrongs = [
                "You may drive 30 km/h because it is a residential road.",
                "You may park anywhere because speeds are low.",
                "Cyclists and pedestrians must always leave the road for cars.",
            ]
            explanation = "An erf or woonerf is a special shared residential area. Walking pace and extra care for pedestrians are required."
            sign_hint = "G5-woonerf"
        else:
            description = f"the round white sign with a red border showing {speed}"
            correct = f"The maximum speed is {speed} km/h from that point until another rule changes it."
            wrongs = [
                f"The advised speed is {speed} km/h but you may drive faster.",
                f"The minimum speed is {speed} km/h.",
                f"The speed limit only applies to trucks.",
            ]
            explanation = f"A round sign with a red border and the number {speed} sets a maximum speed of {speed} km/h."
            sign_hint = f"A-speed-{speed}"
        add_variants(
            questions,
            sign_prompts(description),
            correct,
            wrongs,
            explanation,
            difficulty=1,
            question_type="sign",
            sign_hint=sign_hint,
        )

    b_signs = [
        (
            "the yellow diamond priority-road sign",
            "You are on a priority road until signs or markings end that priority.",
            [
                "You must always stop at the next junction.",
                "You only have priority over cyclists.",
                "The sign only warns about a bend.",
            ],
            "The yellow diamond means priority road. Traffic entering from side roads usually has to yield unless another sign changes the rule.",
            "B1-priority-road",
        ),
        (
            "the white diamond with a black diagonal stripe",
            "It means the priority road status ends here.",
            [
                "It means overtaking is forbidden.",
                "It means you are entering a motorway.",
                "It means you must park on the shoulder.",
            ],
            "The slashed diamond marks the end of the priority-road rule.",
            "B2-end-priority-road",
        ),
        (
            "the inverted triangle give-way sign",
            "You must give way to traffic on the priority road or approaching road you are entering.",
            [
                "You may continue first if you are going straight.",
                "You only need to slow down for buses.",
                "It gives you priority because the sign points down.",
            ],
            "The give-way sign requires you to yield to other traffic that has priority.",
            "B6-give-way",
        ),
        (
            "the octagonal STOP sign",
            "You must come to a complete stop and then give way.",
            [
                "You only stop if you see a tram.",
                "You may roll through slowly without stopping.",
                "It means parking is prohibited.",
            ],
            "A STOP sign requires a full stop, normally at the stop line or where you can safely see the road.",
            "B7-stop",
        ),
        (
            "a priority-road sign with a plate showing that the priority road bends to the left",
            "Priority follows the thick line shown on the plate.",
            [
                "Priority always follows the straight line only.",
                "The plate only shows a scenic route.",
                "All roads at the junction have equal priority.",
            ],
            "When a priority road changes direction, the plate shows where the priority continues.",
            "B1-bending-left",
        ),
        (
            "a priority-road sign with a plate showing that the priority road bends to the right",
            "Priority follows the thick line shown on the plate.",
            [
                "Priority automatically belongs to the fastest vehicle.",
                "The plate means there is a sharp speed hump ahead.",
                "Side roads gain priority because of the bend.",
            ],
            "The additional plate explains which road remains the priority road through the junction.",
            "B1-bending-right",
        ),
        (
            "a give-way sign together with shark teeth on the road",
            "Both the sign and the markings tell you to yield.",
            [
                "The markings cancel the sign.",
                "You only yield to emergency vehicles.",
                "You may ignore the sign if you are already indicating.",
            ],
            "Shark teeth reinforce the give-way rule and show where yielding traffic approaches the junction.",
            "B6-shark-teeth",
        ),
        (
            "the difference between a give-way sign and a STOP sign",
            "A STOP sign requires a full stop; a give-way sign requires yielding and stopping only if needed.",
            [
                "They mean exactly the same thing.",
                "A give-way sign requires a longer stop than a STOP sign.",
                "A STOP sign only applies to heavy traffic.",
            ],
            "Both signs deal with priority, but STOP adds the duty to come to a complete halt first.",
            "B-priority-comparison",
        ),
    ]
    for description, correct, wrongs, explanation, hint in b_signs:
        add_variants(
            questions,
            sign_prompts(description),
            correct,
            wrongs,
            explanation,
            difficulty=2,
            question_type="sign",
            sign_hint=hint,
        )

    c_signs = [
        (
            "the no-entry sign with a red circle and horizontal white bar",
            "You may not enter that road from this side.",
            [
                "You may enter if the road looks empty.",
                "It only forbids pedestrians.",
                "It means parking is prohibited.",
            ],
            "The no-entry sign bans entering from that direction.",
            "C1-no-entry",
        ),
        (
            "the sign meaning road closed to all vehicles in both directions",
            "No vehicles may use that road section unless an exception plate says otherwise.",
            [
                "Only trucks are banned.",
                "Only overtaking is banned.",
                "The road is reserved for emergency parking.",
            ],
            "A closure sign for all vehicles blocks that route for vehicle traffic unless a stated exception applies.",
            "C2-closed-both-directions",
        ),
        (
            "the sign closing a road to motor vehicles",
            "Motor vehicles covered by the sign may not enter the road.",
            [
                "It only means a temporary advice.",
                "It orders you to switch on headlights.",
                "It means the road becomes a motorway.",
            ],
            "A prohibition sign closes the road to the vehicle category shown.",
            "C6-no-motor-vehicles",
        ),
        (
            "the no-overtaking sign",
            "You may not overtake the vehicle categories covered by the sign from that point onward.",
            [
                "You must overtake before the next junction.",
                "You may overtake if you use the horn.",
                "It only applies in rain.",
            ],
            "The no-overtaking sign creates a prohibition from the point where it stands until the rule ends.",
            "C10-no-overtaking",
        ),
        (
            "the end-of-no-overtaking sign",
            "The earlier overtaking prohibition ends here.",
            [
                "A new overtaking ban begins here.",
                "The road ends here.",
                "You must change lane immediately.",
            ],
            "The slashed sign ends the earlier no-overtaking rule.",
            "C11-end-no-overtaking",
        ),
        (
            "the sign prohibiting U-turns",
            "You may not make a U-turn where the sign applies.",
            [
                "You may turn if you use hazard lights.",
                "The sign only applies to buses.",
                "The sign means there is a roundabout ahead.",
            ],
            "A prohibition sign for U-turns means that turning back is forbidden at that location.",
            "C12-no-u-turn",
        ),
        (
            "the sign prohibiting bicycles",
            "Cyclists may not use that road section.",
            [
                "Cyclists must ride in the middle of the road.",
                "Only cars are prohibited.",
                "It means a cycle path starts.",
            ],
            "A bicycle inside a prohibition sign means bicycles are not allowed there.",
            "C14-no-bicycles",
        ),
        (
            "the sign prohibiting pedestrians",
            "Pedestrians may not use that part of the road.",
            [
                "Pedestrians must cross immediately.",
                "Only dogs are prohibited.",
                "It means a footpath begins.",
            ],
            "A pedestrian inside a prohibition sign bars pedestrians from that route.",
            "C16-no-pedestrians",
        ),
        (
            "the sign showing a maximum height restriction",
            "Vehicles higher than the shown limit may not enter.",
            [
                "It shows the minimum bridge height.",
                "Only motorcycles must obey it.",
                "It is only advice for tall vehicles.",
            ],
            "Height restriction signs protect low bridges or structures by banning vehicles above the stated height.",
            "C18-max-height",
        ),
        (
            "the sign showing a maximum width restriction",
            "Vehicles wider than the shown limit may not pass.",
            [
                "It only applies to parked vehicles.",
                "It means the road becomes one-way.",
                "It is only a recommendation.",
            ],
            "A width restriction sign prohibits vehicles above the stated width.",
            "C19-max-width",
        ),
    ]
    for description, correct, wrongs, explanation, hint in c_signs:
        add_variants(
            questions,
            sign_prompts(description),
            correct,
            wrongs,
            explanation,
            difficulty=2,
            question_type="sign",
            sign_hint=hint,
        )

    d_signs = [
        (
            "the blue mandatory sign for straight ahead",
            "You must continue straight in the direction shown.",
            [
                "You may turn either left or right.",
                "You must stop before the sign.",
                "It only advises the fastest route.",
            ],
            "A blue circular mandatory sign orders the movement shown on it.",
            "D-straight-ahead",
        ),
        (
            "the blue mandatory sign for turning left",
            "You must turn left as shown by the sign.",
            [
                "You may continue straight if traffic is light.",
                "You must turn right.",
                "The sign only applies to cyclists.",
            ],
            "Mandatory blue signs require the direction shown.",
            "D-turn-left",
        ),
        (
            "the blue mandatory sign for turning right",
            "You must turn right as shown by the sign.",
            [
                "You may continue straight because the sign is blue.",
                "You must make a U-turn.",
                "It only applies on Sundays.",
            ],
            "A mandatory direction sign instructs the road users covered by it to follow the shown path.",
            "D-turn-right",
        ),
        (
            "the blue sign ordering traffic to pass an obstacle on the left",
            "You must pass the obstacle on the left side indicated.",
            [
                "You may choose either side.",
                "You must stop next to the obstacle.",
                "You must overtake on the right.",
            ],
            "Keep-left and keep-right signs direct traffic around islands or obstacles.",
            "D-pass-left",
        ),
        (
            "the blue sign ordering traffic to pass an obstacle on the right",
            "You must pass the obstacle on the right side indicated.",
            [
                "You may drive over the obstacle.",
                "You must pass on the left.",
                "It means parking is allowed beside the obstacle.",
            ],
            "The sign makes the direction around the obstacle mandatory.",
            "D-pass-right",
        ),
        (
            "the blue roundabout-direction sign",
            "You must follow the roundabout circulation shown by the arrows.",
            [
                "You may drive straight through the centre if empty.",
                "You always have priority when entering.",
                "It means a U-turn is mandatory.",
            ],
            "The mandatory roundabout sign shows that traffic circulates around the central island in the direction indicated.",
            "D-roundabout",
        ),
    ]
    for description, correct, wrongs, explanation, hint in d_signs:
        add_variants(
            questions,
            sign_prompts(description),
            correct,
            wrongs,
            explanation,
            difficulty=1,
            question_type="sign",
            sign_hint=hint,
        )

    e_signs = [
        (
            "the blue P parking sign",
            "Parking is allowed there, subject to any extra plates or local rules.",
            [
                "Stopping is forbidden there.",
                "You may only let passengers out there.",
                "It means the road ahead is closed.",
            ],
            "The blue P sign marks a parking place or parking area, but extra plates can add conditions.",
            "E-parking-place",
        ),
        (
            "the no-parking sign",
            "You may not park there, but a very brief stop for immediate boarding or loading may still be different from parking.",
            [
                "You may park there at night.",
                "You must stop there.",
                "It only forbids bicycles.",
            ],
            "A no-parking sign prohibits parking. Dutch theory separates parking from a brief necessary stop.",
            "E1-no-parking",
        ),
        (
            "the no-stopping sign",
            "You may not stop there except when forced by traffic conditions.",
            [
                "You may stop for a quick phone call.",
                "You may park for five minutes.",
                "It only bans overnight parking.",
            ],
            "A no-stopping sign is stricter than a no-parking sign. Even a voluntary brief stop is not allowed.",
            "E2-no-stopping",
        ),
        (
            "a blue zone parking sign with a parking disc condition",
            "You must use a parking disc and follow the maximum time shown.",
            [
                "You may park all day without any time display.",
                "You must pay a motorway toll.",
                "It only applies to motorcycles.",
            ],
            "Blue-zone parking uses a parking disc and the local maximum duration stated on the signs.",
            "E10-blue-zone",
        ),
        (
            "a parking sign with an arrow plate showing where the restriction starts or ends",
            "The arrow plate explains the direction and stretch of the parking rule.",
            [
                "The arrow plate is decorative only.",
                "Arrows always point to the nearest bus stop.",
                "The arrow cancels the parking rule.",
            ],
            "Additional arrow plates show whether a parking restriction begins, continues, or ends at the sign.",
            "E-arrow-plate",
        ),
        (
            "a disabled-parking sign or plate",
            "Only the vehicles or permit holders covered by the sign may use the place.",
            [
                "Anyone may use it briefly for shopping.",
                "It becomes a loading bay after 18:00.",
                "It is only advice for wide parking spaces.",
            ],
            "Reserved parking places may only be used by the category shown, such as disabled permit holders.",
            "E-disabled-parking",
        ),
    ]
    for description, correct, wrongs, explanation, hint in e_signs:
        add_variants(
            questions,
            sign_prompts(description),
            correct,
            wrongs,
            explanation,
            difficulty=2,
            question_type="sign",
            sign_hint=hint,
        )

    j_signs = [
        (
            "the warning sign for a dangerous bend",
            "A bend is approaching, so you should reduce speed and choose a safe position.",
            [
                "It gives you priority through the bend.",
                "It means overtaking is encouraged.",
                "It marks a parking zone.",
            ],
            "Warning signs alert you to a hazard ahead. A bend sign calls for lower speed and better observation.",
            "J-bend",
        ),
        (
            "the warning sign for a double bend",
            "Two bends follow, so you should prepare for changing direction more than once.",
            ["It means the road becomes one-way.", "It is only for trucks.", "It means a tunnel begins."],
            "A double-bend warning means the road will change direction repeatedly.",
            "J-double-bend",
        ),
        (
            "the warning sign for a slippery road",
            "Grip may be reduced, so you should avoid harsh steering, braking, or acceleration.",
            [
                "You should test the grip by braking hard.",
                "The sign gives you priority over oncoming traffic.",
                "It only matters for motorcycles.",
            ],
            "A slippery-road warning means available grip may suddenly be lower.",
            "J-slippery-road",
        ),
        (
            "the warning sign for loose gravel or chippings",
            "You should slow down and avoid close following because stones can reduce grip and damage vehicles.",
            [
                "You should accelerate to get through quickly.",
                "It means parking is allowed on the shoulder.",
                "It only applies in winter.",
            ],
            "Loose material can reduce grip and create flying stones, so lower speed and greater distance are sensible.",
            "J-loose-gravel",
        ),
        (
            "the warning sign for road works",
            "Road works are ahead, so expect changed lanes, workers, and lower safe speed.",
            [
                "It means the road is fully closed to all traffic.",
                "It gives you motorway status.",
                "It only warns cyclists.",
            ],
            "Road-work warnings tell you to expect a changed road layout and extra hazards.",
            "J-roadworks",
        ),
        (
            "the warning sign for traffic lights ahead",
            "Signals are ahead, so you should prepare for a possible stop.",
            [
                "It means the next lights are always green.",
                "It means a level crossing begins.",
                "It only applies after dark.",
            ],
            "A traffic-light warning sign gives advance notice so you can adjust speed and be ready to stop.",
            "J-traffic-lights",
        ),
        (
            "the warning sign for a level crossing without barriers",
            "A railway crossing is ahead and you must be ready to stop if lights or a train appear.",
            [
                "It means trams have priority in the next street.",
                "It means parking is prohibited for 100 metres.",
                "It allows overtaking before the tracks.",
            ],
            "Level-crossing warning signs tell you to approach with caution and never assume the crossing will stay clear.",
            "J-level-crossing",
        ),
        (
            "the warning sign for children",
            "Children may suddenly enter the road, so you should reduce speed and observe more widely.",
            [
                "It means adults are prohibited.",
                "It means a school bus stop is also a parking place.",
                "It only applies outside school hours.",
            ],
            "Children can behave unpredictably. Lower speed and better anticipation are essential near this warning sign.",
            "J-children",
        ),
        (
            "the warning sign for cyclists crossing",
            "Cyclists may cross your path, so you should look carefully and adjust speed.",
            [
                "Cyclists must always stop regardless of markings.",
                "It means the road becomes a cycle motorway for cars.",
                "It only applies on Sundays.",
            ],
            "Cyclist warnings tell drivers to expect crossing bicycle traffic and to prepare early.",
            "J-cyclists",
        ),
        (
            "the warning sign for pedestrians",
            "Pedestrians may be on or crossing the road ahead, so extra caution is needed.",
            [
                "It means pedestrians are prohibited.",
                "It gives you priority over pedestrians everywhere.",
                "It only applies in rain.",
            ],
            "Pedestrian warnings remind you to expect people walking or crossing unexpectedly.",
            "J-pedestrians",
        ),
        (
            "the warning sign for an opening bridge",
            "A bridge that can open is ahead, so you should watch signals and barriers carefully.",
            [
                "It means there is a permanent speed hump.",
                "It guarantees the bridge is open to traffic.",
                "It only matters for heavy lorries.",
            ],
            "Opening bridges create a special hazard, so warning signs prepare you for signals or stopping traffic.",
            "J-opening-bridge",
        ),
        (
            "the warning sign for a steep hill or descent",
            "You should adjust speed early and keep the vehicle under control before the slope begins.",
            [
                "You should shift attention away from the road to your satnav.",
                "It means towing is required.",
                "It gives downhill traffic automatic priority.",
            ],
            "Steep gradients require early speed control and careful observation.",
            "J-steep-hill",
        ),
    ]
    for description, correct, wrongs, explanation, hint in j_signs:
        add_variants(
            questions,
            sign_prompts(description),
            correct,
            wrongs,
            explanation,
            difficulty=2,
            question_type="sign",
            sign_hint=hint,
        )

    g_signs = [
        (
            "the motorway start sign G1",
            "The road becomes a motorway with motorway rules such as access restrictions and motorway speed rules.",
            [
                "It means you enter a woonerf.",
                "It only warns that traffic may be fast.",
                "It means parking is allowed on the hard shoulder.",
            ],
            "G1 marks the start of a motorway and motorway-specific rules then apply.",
            "G1-motorway",
        ),
        (
            "the motorway end sign G2",
            "Motorway rules end here and the next road type rules apply.",
            [
                "The road is now one-way only.",
                "You must stop at the sign.",
                "You may use the hard shoulder as a normal lane.",
            ],
            "G2 marks the end of motorway status.",
            "G2-end-motorway",
        ),
        (
            "the expressway sign G3",
            "The road becomes an expressway with expressway access rules and generally high-speed through traffic.",
            ["It means the road is a cycle path.", "It gives you free parking rights.", "It only applies to buses."],
            "G3 marks an autoweg, often translated as expressway, with its own access and speed rules.",
            "G3-expressway",
        ),
        (
            "the expressway end sign G4",
            "Expressway rules end here.",
            [
                "A new speed limit of 130 automatically begins.",
                "You must make a U-turn.",
                "It means no overtaking for the next kilometre.",
            ],
            "G4 marks the end of the expressway road type.",
            "G4-end-expressway",
        ),
        (
            "the woonerf or erf start sign",
            "You enter a shared residential area where walking pace and extra care for pedestrians apply.",
            [
                "You enter a motorway service area.",
                "The road becomes priority-only for cars.",
                "You may park on junctions because speeds are low.",
            ],
            "The start of an erf or woonerf changes the road environment and calls for walking pace.",
            "G5-start-erf",
        ),
        (
            "the woonerf or erf end sign",
            "The special erf rules end and the next normal road rules apply.",
            ["The road closes to residents only.", "A 130 km/h limit begins.", "You must stop for ten seconds."],
            "The end sign marks where the special residential shared-space rules stop applying.",
            "G6-end-erf",
        ),
    ]
    for description, correct, wrongs, explanation, hint in g_signs:
        add_variants(
            questions,
            sign_prompts(description),
            correct,
            wrongs,
            explanation,
            difficulty=1,
            question_type="sign",
            sign_hint=hint,
        )

    general_sign_items = [
        (
            "a red-bordered triangle warning sign",
            "It warns you about a hazard ahead.",
            ["It gives you priority.", "It means parking is allowed.", "It always sets a speed limit."],
            "In Dutch traffic, warning signs usually use a red-bordered triangle shape.",
            "warning-triangle",
        ),
        (
            "a red-bordered circle sign",
            "It normally gives a prohibition or restriction.",
            [
                "It always gives directions to follow.",
                "It always marks a parking place.",
                "It is only used for tourist information.",
            ],
            "Red-bordered circles usually show prohibitions or restrictions.",
            "prohibition-circle",
        ),
        (
            "a blue circular sign",
            "It usually gives a mandatory instruction.",
            ["It always marks a danger.", "It always means no entry.", "It is always only advisory."],
            "Blue circular signs often require a specific direction or movement.",
            "mandatory-blue-circle",
        ),
        (
            "an octagonal sign",
            "It is used for STOP so that drivers recognise it quickly.",
            ["It always means no parking.", "It means the road bends sharply.", "It is used for motorway entry."],
            "The STOP sign has a special octagonal shape for quick recognition.",
            "octagon-stop",
        ),
        (
            "the built-up area sign",
            "It marks the start of a built-up area and the normal built-up-area default speed becomes relevant unless signs set another limit.",
            ["It starts a motorway.", "It bans pedestrians.", "It only applies to buses."],
            "The built-up area sign is important because Dutch default urban rules, including the ordinary 50 km/h default, then matter unless another sign changes them.",
            "H1-built-up-area",
        ),
        (
            "the end-of-built-up-area sign",
            "It marks the end of the built-up area, so outside-built-up default rules apply unless signs say otherwise.",
            [
                "It means parking is free everywhere.",
                "It only ends footpath rules.",
                "It automatically gives motorway status.",
            ],
            "Leaving the built-up area changes the default environment and usually the default speed rule.",
            "H2-end-built-up-area",
        ),
        (
            "a one-way street sign",
            "Traffic may only proceed in the direction shown by the sign.",
            [
                "You may drive either way if the street is quiet.",
                "It only applies to buses.",
                "It means the road is closed to all traffic.",
            ],
            "A one-way sign is an important directional regulation and must be read before entering the street.",
            "F-one-way",
        ),
        (
            "the sign giving priority over oncoming traffic at a narrow passage",
            "Traffic in your direction has priority through the narrow section shown.",
            [
                "You must always reverse.",
                "The sign only warns about a bend.",
                "It means no overtaking for bicycles only.",
            ],
            "Some signs regulate who should pass first when road width is limited.",
            "F-priority-over-oncoming",
        ),
        (
            "the sign telling you to give priority to oncoming traffic at a narrow passage",
            "You must let the oncoming traffic go first if the passage cannot be used safely by both directions together.",
            [
                "You have priority because you saw the sign first.",
                "It only applies at night.",
                "It means the road ahead is one-way.",
            ],
            "A narrow-passage priority sign can require your direction to wait for oncoming traffic.",
            "F-give-priority-oncoming",
        ),
        (
            "a dead-end road sign",
            "The road does not continue through for normal traffic beyond the point shown.",
            [
                "It means the road becomes a motorway.",
                "It means parking is compulsory there.",
                "It gives priority over side roads.",
            ],
            "Information signs can warn you that a road has no exit, helping route choice and turning decisions.",
            "L-dead-end",
        ),
        (
            "a yellow temporary diversion or detour sign",
            "Follow the temporary route shown while the normal route is interrupted.",
            [
                "Ignore it because yellow signs are only decorative.",
                "It only applies to cyclists.",
                "It always sets a 30 km/h speed limit.",
            ],
            "Temporary yellow signs are commonly used to guide traffic safely around road works or closures.",
            "K-L-detour",
        ),
    ]
    for description, correct, wrongs, explanation, hint in general_sign_items:
        add_variants(
            questions,
            sign_prompts(description),
            correct,
            wrongs,
            explanation,
            difficulty=1,
            question_type="sign",
            sign_hint=hint,
        )

    return finalize_topic("traffic-signs", questions)


def build_basic_traffic_rule_questions():
    questions = []

    overtaking_items = [
        (
            "overtaking another vehicle on an ordinary road",
            "You normally overtake on the left unless a recognised exception applies.",
            [
                "You normally overtake on the right.",
                "You may overtake on either side whenever you indicate.",
                "You must use the horn before every overtake.",
            ],
            "Dutch traffic normally overtakes on the left. Right-side passing is only for special situations.",
        ),
        (
            "overtaking near a zebra crossing",
            "You should be very careful and avoid overtaking if it would endanger people approaching or using the crossing.",
            [
                "A zebra crossing is the best place to overtake because traffic is slow.",
                "You may overtake if you flash your lights.",
                "Pedestrians at a zebra crossing never affect overtaking decisions.",
            ],
            "Overtaking near pedestrian crossings can hide people from view and create immediate danger.",
        ),
        (
            "overtaking just before a level crossing",
            "You must not overtake immediately before or on a level crossing.",
            [
                "You may overtake if the train barriers are open.",
                "You may overtake motorcycles only.",
                "You should overtake quickly before the tracks.",
            ],
            "Level crossings need maximum attention. Overtaking there is prohibited because it increases risk severely.",
        ),
        (
            "overtaking when the view ahead is blocked",
            "Do not overtake unless you can see enough distance to complete the manoeuvre safely.",
            [
                "Visibility does not matter if your engine is powerful.",
                "You may overtake if you sound the horn first.",
                "A blocked view only matters at night.",
            ],
            "Safe overtaking depends on clear view, enough distance, and no danger to other road users.",
        ),
        (
            "passing a tram where passengers may step into the road",
            "Slow down and give space to passengers instead of treating it like a normal overtake.",
            [
                "Accelerate because the tram cannot move sideways.",
                "Ignore passengers if you remain in lane.",
                "Use the hard shoulder to pass faster.",
            ],
            "A stopped tram creates a special pedestrian hazard. Careful passing is more important than speed.",
        ),
        (
            "overtaking cyclists on a narrow road",
            "Only do it when you can leave enough lateral space and complete the manoeuvre safely.",
            [
                "Pass as closely as possible to save time.",
                "Cyclists do not count as traffic for overtaking decisions.",
                "Use the horn so they move into the gutter.",
            ],
            "Cyclists need room because they may wobble, avoid drains, or move around parked cars.",
        ),
        (
            "overtaking where a solid centre line applies",
            "You must respect the solid line and not cross it as part of the overtake.",
            [
                "You may cross it if the road seems empty.",
                "Solid lines only apply in rain.",
                "You must overtake before the solid line ends.",
            ],
            "A solid centre line restricts crossing. If overtaking would require crossing it, the manoeuvre is not allowed.",
        ),
        (
            "overtaking on a multi-lane road when traffic is dense",
            "Stay patient and keep lane discipline instead of weaving between lanes.",
            [
                "Frequent lane changes are always the fastest and safest option.",
                "Dense traffic means right-side overtaking is always forbidden.",
                "You should tailgate to create a gap for the overtake.",
            ],
            "Dense traffic punishes aggressive lane changes. Predictable lane discipline is safer.",
        ),
        (
            "overtaking near a junction",
            "Be cautious because turning traffic and hidden road users make overtaking riskier.",
            [
                "Junctions are ideal because vehicles are slower.",
                "Turning traffic does not affect overtaking.",
                "You only need to check the road behind you.",
            ],
            "Junctions create extra movements, reduced sight, and more vulnerable road users.",
        ),
        (
            "thinking that overtaking is mainly a question of engine power",
            "It is mainly a question of visibility, space, legality, and safety.",
            [
                "The strongest engine always creates a legal overtake.",
                "Only motorcycles need to judge space.",
                "If you can accelerate hard enough, signs no longer matter.",
            ],
            "Even a quick car cannot make an illegal or unsafe overtake acceptable.",
        ),
    ]
    for subject, correct, wrongs, explanation in overtaking_items:
        add_variants(questions, rule_prompts(subject), correct, wrongs, explanation, difficulty=2)

    traffic_light_items = [
        (
            "a red traffic light",
            "You must stop before the stop line or signal unless traffic conditions force you beyond it.",
            [
                "You may continue if no cross traffic is visible.",
                "Red only applies to trucks.",
                "Red means prepare to go if you are first in line.",
            ],
            "A red light means stop. You should wait until the signal allows you to proceed.",
        ),
        (
            "a green traffic light",
            "You may continue if the way ahead is clear and safe.",
            [
                "You may continue without checking for blocked traffic.",
                "Green means you have priority over every pedestrian everywhere.",
                "Green means you must accelerate to the maximum speed at once.",
            ],
            "Green allows movement, but you still need a clear and safe path.",
        ),
        (
            "an amber traffic light",
            "You should stop unless stopping would create a danger.",
            [
                "Amber always means accelerate before red.",
                "Amber means pedestrians now have priority instead.",
                "Amber is the same as green.",
            ],
            "Amber is a warning to stop if you can do so safely, not a signal to speed up.",
        ),
        (
            "red and amber shown together",
            "Prepare to move, but only start when green appears.",
            [
                "It means reverse out of the junction.",
                "It means cross traffic now has amber.",
                "It means you must stay stopped until the police wave you on.",
            ],
            "Red plus amber is the transition before green. You get ready, but you do not move off yet.",
        ),
        (
            "a flashing amber light",
            "Proceed with caution and follow the normal signs and priority rules that remain relevant.",
            [
                "It gives you automatic priority over all traffic.",
                "It means the junction is closed.",
                "It means you must turn around.",
            ],
            "Flashing amber means extra caution. The signal is not fully controlling the junction in the normal way.",
        ),
        (
            "a green arrow or filtered signal for a specific direction",
            "It applies to the direction shown, but you still need a safe path.",
            [
                "It cancels every pedestrian crossing rule.",
                "It applies to all directions at the junction.",
                "It means you may enter a blocked junction.",
            ],
            "Directional signals control the movement shown, while the driver still checks that the path is clear.",
        ),
        (
            "entering a junction on green when traffic is already queued beyond it",
            "Do not enter if you would block the junction.",
            [
                "Green always requires you to enter immediately.",
                "Blocking the junction is allowed if your light is green.",
                "You may stop on the pedestrian crossing instead.",
            ],
            "A green light does not justify entering a space you cannot clear.",
        ),
        (
            "traffic lights being out of order",
            "Slow down, observe carefully, and follow the remaining signs, markings, and general priority rules.",
            [
                "Keep normal speed because the junction now has no rules.",
                "Only the biggest vehicle may continue.",
                "You may ignore road markings until power returns.",
            ],
            "When signals fail, the junction still has to be handled with the other applicable road rules.",
        ),
    ]
    for subject, correct, wrongs, explanation in traffic_light_items:
        add_variants(questions, rule_prompts(subject), correct, wrongs, explanation, difficulty=1)

    level_crossing_items = [
        (
            "red flashing lights at a level crossing",
            "You must stop and wait until the crossing is completely safe again.",
            [
                "You may continue if the train is still far away.",
                "You only stop if barriers are also lowered.",
                "Flashing red means slow down and listen only.",
            ],
            "Red flashing lights at a level crossing mean stop. Never gamble with train distance or speed.",
        ),
        (
            "a closed or closing barrier at a level crossing",
            "You must stop and never weave around the barrier.",
            [
                "You may pass if you are certain your car fits.",
                "You may cross if another car has already done so.",
                "It only applies to trucks.",
            ],
            "Going around barriers is extremely dangerous and forbidden.",
        ),
        (
            "queuing traffic beyond a level crossing",
            "Do not enter the crossing unless you can clear it completely.",
            [
                "Stop on the tracks if the barrier is still up.",
                "Enter slowly and hope the queue moves.",
                "Only buses need to wait for space.",
            ],
            "You must never risk becoming trapped on a railway crossing.",
        ),
        (
            "overtaking immediately before a level crossing",
            "It is forbidden because it creates extra risk and reduces visibility.",
            [
                "It is allowed if you are overtaking a bicycle.",
                "It is required if the vehicle ahead is slow.",
                "It is only forbidden at night.",
            ],
            "A level crossing demands full attention. Overtaking there is not allowed.",
        ),
        (
            "stopping on a level crossing",
            "You should avoid it completely unless traffic conditions unexpectedly trap you and you are trying to escape safely.",
            [
                "It is a good place to check directions.",
                "It is allowed for loading goods quickly.",
                "It is allowed if hazard lights are on.",
            ],
            "Rail tracks must stay clear. A stopped vehicle on the crossing creates extreme danger.",
        ),
        (
            "an open level crossing with no train visible",
            "You still approach carefully and stay ready for signals or a train.",
            [
                "You may assume no train can come suddenly.",
                "You may overtake because the crossing is open.",
                "You should speed up far above the limit.",
            ],
            "An apparently quiet crossing still needs careful observation because trains approach fast.",
        ),
        (
            "a level crossing with poor visibility in bad weather",
            "Reduce speed early and be especially ready to stop.",
            [
                "Weather does not matter at rail crossings.",
                "Use only your horn instead of slowing.",
                "Drive faster so you spend less time near the tracks.",
            ],
            "Reduced visibility increases the need for early speed control and observation.",
        ),
        (
            "a cyclist or pedestrian hesitating near a level crossing",
            "Stay patient and do not pressure vulnerable road users toward the tracks.",
            [
                "Use the horn to hurry them across.",
                "Overtake them on the crossing.",
                "Ignore them because trains have right of way anyway.",
            ],
            "Pressure near a rail crossing can cause panic and dangerous mistakes.",
        ),
    ]
    for subject, correct, wrongs, explanation in level_crossing_items:
        add_variants(questions, rule_prompts(subject), correct, wrongs, explanation, difficulty=2)

    turning_items = [
        (
            "turning right or left across the path of cyclists or pedestrians going straight on the same road",
            "You must let the straight-on cyclists and pedestrians go first.",
            [
                "Your indicator gives you priority.",
                "Cars always go before cyclists when turning.",
                "Only pedestrians at zebra crossings matter.",
            ],
            "When you turn off a road, straight-on traffic on that road, including cyclists and pedestrians, must not be cut off.",
        ),
        (
            "turning at a junction without looking into mirrors and blind spots",
            "It is unsafe because cyclists and mopeds may be beside you.",
            [
                "It is acceptable if your indicator is on.",
                "Blind spots only matter on motorways.",
                "Mirror checks are optional below 30 km/h.",
            ],
            "Mirror, shoulder, and blind-spot checks are essential before any turn.",
        ),
        (
            "preparing early for a turn",
            "Choose position, speed, and signal in good time without confusing other road users.",
            [
                "Brake only at the last second.",
                "Move across lanes suddenly to save time.",
                "Signal after you have already turned.",
            ],
            "Good preparation makes your movement predictable and safer for others.",
        ),
        (
            "turning in a narrow residential street with many parked cars",
            "Turn slowly because hidden cyclists or pedestrians can appear from between vehicles.",
            [
                "Use more speed to clear the street quickly.",
                "Assume nobody is walking between parked cars.",
                "Only traffic behind you matters.",
            ],
            "Parked cars reduce sight lines, so a lower turning speed gives you time to react.",
        ),
        (
            "turning when the junction is partly blocked ahead",
            "Wait until you can complete the turn without stopping in a dangerous position.",
            [
                "Enter the turn and stop on the crossing area.",
                "Turn anyway because you are already signalling.",
                "Use the horn to force space.",
            ],
            "A turn should only be started when there is room to finish it safely.",
        ),
        (
            "making a turn mainly by watching the vehicle in front",
            "You must still scan your own mirrors, blind spots, and road users around you.",
            [
                "Copying the vehicle ahead is enough.",
                "Only buses need blind-spot checks while turning.",
                "Pedestrians are irrelevant if the road is wide.",
            ],
            "Safe turning is your own responsibility. Another driver's movement does not make your turn safe.",
        ),
    ]
    for subject, correct, wrongs, explanation in turning_items:
        add_variants(questions, rule_prompts(subject), correct, wrongs, explanation, difficulty=2)

    lane_items = [
        (
            "normal lane choice on a multi-lane road in the Netherlands",
            "Keep right when possible and use other lanes mainly for overtaking or when traffic conditions require them.",
            [
                "Stay in the left lane to avoid lane changes.",
                "Use any lane permanently because all lanes are equal.",
                "Keep in the lane with the smoothest surface regardless of traffic.",
            ],
            "Dutch lane discipline follows the general keep-right principle.",
        ),
        (
            "weaving across lanes to gain a few car lengths",
            "It creates unnecessary risk and usually saves very little time.",
            [
                "It is the best way to improve safety in queues.",
                "It is required in dense traffic.",
                "It gives you priority over slower drivers.",
            ],
            "Frequent unnecessary lane changes increase conflict with other traffic.",
        ),
        (
            "using the right lane after overtaking on a motorway or expressway",
            "Return to the right when it is safe and sensible.",
            [
                "Stay left forever once you have overtaken one vehicle.",
                "Return only if another driver flashes you.",
                "Move back without mirror checks.",
            ],
            "After overtaking, Dutch lane discipline says you should move back right when safe.",
        ),
        (
            "choosing a lane late at a junction or exit",
            "Plan early so you do not make sudden last-second swerves.",
            [
                "Cut across if your indicator is on.",
                "Stop in the live lane until a gap appears.",
                "Reverse if you miss the correct lane.",
            ],
            "Good lane discipline starts with early planning and clear signalling.",
        ),
        (
            "following lane arrows painted on the road",
            "They tell you which direction the lane is intended for, so choose your lane early.",
            [
                "They are only decorative if no sign repeats them.",
                "They only apply to heavy goods vehicles.",
                "They may be ignored when traffic is light.",
            ],
            "Lane arrows help organise safe movement at junctions and should be followed.",
        ),
        (
            "staying in a bus lane with an ordinary passenger car",
            "Only use it when signs permit your vehicle category.",
            [
                "Every driver may use a bus lane if traffic is slow.",
                "Bus lanes are for overtaking only.",
                "Bus lanes become parking lanes in rain.",
            ],
            "Bus lanes are reserved lanes unless signs say other vehicles may also use them.",
        ),
        (
            "lane discipline in a queue",
            "Stay predictable, keep enough distance, and avoid aggressive jumping between lanes.",
            [
                "Tailgate to stop others merging.",
                "Use the shoulder as a faster lane.",
                "Ignore mirrors because speeds are low.",
            ],
            "Queues still require good discipline, mirror use, and space.",
        ),
        (
            "moving back into lane after overtaking",
            "Check mirrors, judge the gap, and return smoothly without cutting in.",
            [
                "Move back as soon as your rear bumper is ahead.",
                "Signal only after you have moved.",
                "The overtaken vehicle must always brake to create room.",
            ],
            "A safe return after overtaking needs space and a smooth movement, not a sharp cut-in.",
        ),
    ]
    for subject, correct, wrongs, explanation in lane_items:
        add_variants(questions, rule_prompts(subject), correct, wrongs, explanation, difficulty=2)

    extra_items = [
        (
            "using direction indicators in good time before changing direction or lanes",
            "Signal early enough to warn others, but not so early that you create confusion.",
            [
                "Signal only after you have already moved.",
                "Indicators give automatic priority.",
                "Signalling is optional below 30 km/h.",
            ],
            "Good signalling makes your intentions predictable without misleading other road users.",
        ),
        (
            "entering a one-way street from the wrong side",
            "Do not enter from the forbidden side if a no-entry or one-way arrangement blocks it.",
            [
                "It is allowed if the street looks empty.",
                "It is allowed for residents even without an exception sign.",
                "It is acceptable if you only drive a short distance.",
            ],
            "One-way arrangements organise traffic flow and must be obeyed from the correct direction.",
        ),
        (
            "blocking a junction because the light is green but the road ahead is full",
            "Wait until there is space to clear the junction.",
            [
                "Enter anyway because the signal is green.",
                "Stop on the pedestrian crossing instead.",
                "Use the horn so the queue moves faster.",
            ],
            "Even with a green light, you should not enter a space you cannot clear safely.",
        ),
        (
            "using the horn in ordinary traffic",
            "Use it mainly to warn of immediate danger, not to show annoyance.",
            [
                "Use it whenever another driver irritates you.",
                "Use it to demand priority at every equal junction.",
                "Use it instead of braking for hazards.",
            ],
            "The horn is a warning device, not a tool for anger or pressure.",
        ),
    ]
    for subject, correct, wrongs, explanation in extra_items:
        add_variants(questions, rule_prompts(subject), correct, wrongs, explanation, difficulty=1)

    return finalize_topic("basic-traffic-rules", questions)


def build_priority_rule_questions():
    questions = []

    right_from_right_contexts = [
        "an equal crossroads in a quiet residential area where a cyclist approaches from your right and there are no signs or markings",
        "an unmarked T-junction where you are on the terminating road and a car approaches from your right",
        "a narrow village junction with no priority signs where a van arrives from your right at the same time as you",
        "a small town crossroads with no traffic lights where a moped comes from your right",
        "a residential junction without signs where a motorcycle appears from your right",
        "a neighbourhood crossroads at low speed where a taxi approaches from your right",
        "a junction between two ordinary roads with no markings where a cyclist comes from your right while you want to go straight",
        "an unsigned junction near parked cars where a delivery van arrives from your right",
        "a quiet side-street junction with no priority signs where a passenger car approaches from your right",
        "a low-speed crossroads in a 30-zone where a scooter arrives from your right",
        "a suburban junction without traffic lights where a bus approaches from your right and no other sign changes priority",
        "an ordinary unsigned crossroads where a learner driver approaches from your right",
    ]
    for context in right_from_right_contexts:
        add_variants(
            questions,
            scenario_prompts(context),
            "Give way to the traffic coming from your right.",
            [
                "You may go first because you are going straight.",
                "The largest vehicle always goes first.",
                "You may both continue without slowing because there are no signs.",
            ],
            "At an equal junction without signs, markings, or signals changing the rule, traffic from the right has priority.",
            difficulty=2,
            question_type="scenario",
        )

    haaientanden_contexts = [
        "a junction where shark teeth are painted on your approach",
        "the entrance to a roundabout with shark teeth on your lane",
        "a side road where you see shark teeth before joining a larger road",
        "a cycle crossing where shark teeth face your vehicle",
        "a slip road meeting another carriageway and shark teeth are painted on your lane",
        "a junction where a give-way sign and shark teeth appear together",
    ]
    for context in haaientanden_contexts:
        add_variants(
            questions,
            scenario_prompts(context),
            "Yield to the traffic on the road you are entering.",
            [
                "Drive on first because shark teeth only warn about slippery paint.",
                "Stop only for heavy vehicles.",
                "Ignore the marking if you are turning left.",
            ],
            "Shark teeth mark the approach that must yield. They work together with the signs and junction layout.",
            difficulty=2,
            question_type="scenario",
        )

    priority_road_contexts = [
        "a side road entering a yellow-diamond priority road",
        "driving on a road marked as a priority road while side traffic waits at give-way signs",
        "a junction plate showing the priority road bends left while another vehicle comes from the side road",
        "a junction plate showing the priority road bends right and you stay on the thick-line route",
        "the moment just after a sign ending the priority road status",
        "a crossroads where you are on the priority road and another driver hesitates",
        "joining a priority road from a minor road",
        "meeting cyclists crossing a side road while you remain on the priority road",
        "approaching a STOP sign from a road that crosses the priority road",
        "a complex junction where the additional plate shows exactly where priority continues",
    ]
    for context in priority_road_contexts:
        add_variants(
            questions,
            scenario_prompts(context),
            "Follow the priority signs and plates; the priority road traffic goes first.",
            [
                "The fastest vehicle automatically goes first.",
                "Side roads gain priority if the junction is busy.",
                "Priority signs never apply to cyclists.",
            ],
            "A priority road gives its traffic precedence until the signs or plates indicate otherwise.",
            difficulty=2,
            question_type="scenario",
        )

    tram_contexts = [
        "a normal town junction with tram tracks where no sign gives you clear priority over the tram",
        "turning left across tram tracks while the tram is approaching",
        "an equal junction where a tram and your car arrive together without a sign changing the rule",
        "a busy city crossing where you could block the tram path if you continue",
        "a crossroads where a tram comes from your left but no signal changes the normal tram situation",
        "choosing whether to force your way ahead of a tram because your car can accelerate faster",
    ]
    for context in tram_contexts:
        add_variants(
            questions,
            scenario_prompts(context),
            "Let the tram go and avoid blocking its path unless signs or signals clearly say otherwise.",
            [
                "Use your speed to cross in front of the tram.",
                "The tram must always wait for cars because it is larger.",
                "Block the tracks if your light is green.",
            ],
            "A tram usually has to be given room because it cannot steer away. Signs or signals can change the detail, but blocking it is unsafe.",
            difficulty=2,
            question_type="scenario",
        )

    emergency_contexts = [
        "an ambulance with blue flashing lights and siren approaches the junction you are about to enter",
        "a fire engine on priority duty comes up behind you in slow traffic",
        "you hear a siren near an equal junction but cannot yet see the emergency vehicle",
        "a police car on priority duty approaches while you are in a short queue",
        "traffic near you starts moving aside for an emergency vehicle on blue lights and siren",
        "you are considering keeping your own priority in front of an emergency vehicle because your lane is green",
    ]
    for context in emergency_contexts:
        add_variants(
            questions,
            scenario_prompts(context),
            "Give way and create a safe path for the emergency vehicle.",
            [
                "Keep going because your own signal is green.",
                "Stop without looking at cyclists or pedestrians.",
                "Race through the junction first to save time.",
            ],
            "Emergency vehicles using blue flashing lights and siren must be given priority. Do it safely and predictably.",
            difficulty=2,
            question_type="scenario",
        )

    bus_contexts = [
        "a bus indicates away from a marked stop inside a built-up area",
        "you are driving behind a bus that signals to re-enter the carriageway from a stop in town",
        "slow traffic passes a bus stop and the bus clearly wants to pull out inside the built-up area",
        "you wonder whether you should squeeze past a bus that is indicating away from its stop in town",
    ]
    for context in bus_contexts:
        add_variants(
            questions,
            scenario_prompts(context),
            "Give the bus the opportunity to leave the stop.",
            [
                "Hold your line because buses must always wait for cars.",
                "Accelerate to pass before the bus moves.",
                "Use the horn so the bus stays at the stop.",
            ],
            "Inside built-up areas, drivers should let an indicating bus leave a designated stop.",
            difficulty=2,
            question_type="scenario",
        )

    cyclist_contexts = [
        "you are turning right across a cycle path where cyclists continue straight",
        "you leave a side street and cyclists are crossing your path on the road you join",
        "a cyclist approaches from your right at an equal junction with no priority signs",
        "you want to enter a roundabout where cyclists on a separate ring have shark teeth facing you",
        "you are leaving a car park and crossing a cycle track used by cyclists",
        "you are turning left and a cyclist rides straight ahead next to you on the same road",
        "you approach a crossing where cyclists may suddenly appear from behind parked cars",
        "you think your indicator gives you priority over cyclists while turning",
    ]
    for context in cyclist_contexts:
        add_variants(
            questions,
            scenario_prompts(context),
            "Give the cyclist priority when the general rule or the markings require it, and do not cut across their path.",
            [
                "Cars always go first because they are faster.",
                "Cyclists only count if they are in bright clothing.",
                "An indicator gives you automatic priority over cyclists.",
            ],
            "Cyclists are frequently part of priority questions in the Netherlands. Turning drivers and yielding approaches must not cut them off.",
            difficulty=2,
            question_type="scenario",
        )

    complex_contexts = [
        "a crossroads where you are on a priority road, a cyclist crosses the side road, and a car from the minor road wants to join",
        "an equal junction where a cyclist comes from your right while a tram also approaches on rails ahead",
        "a roundabout entrance with shark teeth, a cyclist ring crossing, and a bus behind you",
        "a side road with a STOP sign where pedestrians are crossing the road you want to enter",
        "a town junction where an emergency vehicle approaches while a bus is signalling away from a stop",
        "a junction where the priority road bends, a cyclist goes straight, and you want to turn off the priority road",
        "an unsigned crossroads in a 30-zone with both a car from your right and a pedestrian stepping toward a zebra crossing beyond the junction",
        "a narrow city junction with tram tracks, cyclists beside you, and a green traffic light ahead",
        "a crossroads where you leave a car park, cross a cycle path, and join a priority road",
        "a roundabout exit where a pedestrian crossing lies just after the exit lane",
        "an equal junction where a moped comes from your right and an ambulance siren is suddenly heard nearby",
        "a busy town junction where you have priority by signs but your path would cut across cyclists going straight on the same road",
    ]
    for context in complex_contexts:
        add_variants(
            questions,
            scenario_prompts(context),
            "Read every sign, marking, and vulnerable road user in order; do not rely on only one rule.",
            [
                "Always follow the biggest vehicle first and ignore cyclists.",
                "Whichever driver is quickest may decide the order.",
                "One priority sign cancels every other safety duty.",
            ],
            "Complex Dutch priority questions combine several rules. You still have to respect vulnerable road users and special signals.",
            difficulty=3,
            question_type="scenario",
            points=2,
        )

    return finalize_topic("priority-rules", questions)


def build_speed_limit_questions():
    questions = []

    road_types = [
        ("a normal road inside a built-up area with no lower or higher sign", "The default maximum speed is 50 km/h."),
        (
            "a normal rural road outside the built-up area with no other sign",
            "The default maximum speed for a passenger car is 80 km/h.",
        ),
        ("an expressway unless signs set a lower limit", "The normal maximum speed is 100 km/h."),
        (
            "a motorway between 06:00 and 19:00 unless a lower sign applies",
            "The national motorway maximum is 100 km/h.",
        ),
        ("a 30-zone", "The maximum speed is 30 km/h."),
        ("a woonerf or erf", "You drive at walking pace, about 15 km/h."),
        ("a road works section signed at 50 km/h", "You follow the temporary signed limit of 50 km/h."),
        (
            "a school street with a signed temporary 30 km/h limit",
            "You follow the signed temporary 30 km/h limit while it applies.",
        ),
    ]
    for subject, correct in road_types:
        add_variants(
            questions,
            rule_prompts(subject),
            correct,
            [
                "The limit is 130 km/h.",
                "There is no legal maximum if traffic is quiet.",
                "The limit only depends on how wide the road feels.",
            ],
            "Dutch speed limits depend first on road type and any sign that changes the default rule.",
            difficulty=1,
        )

    vehicle_exceptions = [
        ("a passenger car towing a trailer on a motorway or expressway", "The maximum speed is 90 km/h."),
        ("a bromfiets by design", "Its maximum design speed is 45 km/h."),
        ("a snorfiets by design", "Its maximum design speed is 25 km/h."),
        (
            "a very heavy vehicle category that has a lower legal limit than an ordinary passenger car",
            "You follow the lower vehicle-specific maximum, not the ordinary passenger-car limit.",
        ),
        (
            "a driver towing a caravan who thinks the normal 100 km/h motorway rule for passenger cars still applies",
            "That is wrong; towing traffic has a lower motorway maximum.",
        ),
        (
            "a driver who assumes every vehicle has the same limit as a passenger car",
            "That is wrong; some vehicle categories have lower legal maxima.",
        ),
    ]
    for subject, correct in vehicle_exceptions:
        add_variants(
            questions,
            rule_prompts(subject),
            correct,
            [
                "The ordinary passenger-car limit always applies to every vehicle.",
                "There are no vehicle-specific speed exceptions in Dutch traffic law.",
                "Vehicle type only matters for parking, not speed.",
            ],
            "Dutch speed law sometimes changes the limit because of vehicle category, trailer use, or road access.",
            difficulty=2,
        )

    sign_zone_items = [
        ("a signed 30-zone", "The zone speed stays in force until an end-of-zone sign or another valid rule ends it."),
        (
            "a signed 60-zone in a rural area",
            "The zone limit applies through the zone, not only next to the first sign.",
        ),
        ("a round speed-limit sign with 70", "It creates a maximum speed of 70 km/h from that point."),
        ("an end-of-speed-limit sign with a grey diagonal stripe", "It ends the earlier specific speed restriction."),
        (
            "a variable matrix sign above the motorway lane showing 90",
            "The displayed speed is legally binding while it is shown.",
        ),
        (
            "entering a built-up area after a higher rural speed section",
            "The built-up-area rule becomes relevant unless another sign sets a different limit.",
        ),
    ]
    for subject, correct in sign_zone_items:
        add_variants(
            questions,
            rule_prompts(subject),
            correct,
            [
                "Zone signs only apply to the next junction.",
                "End-of-limit signs create a new higher speed automatically everywhere.",
                "Variable matrix speeds are only advice.",
            ],
            "Specific signs and zones override the ordinary default road-type limit.",
            difficulty=2,
        )

    woonerf_items = [
        ("driving in a woonerf", "Use walking pace and expect pedestrians to use the full street."),
        (
            "driving in a 30-zone",
            "The maximum speed is 30 km/h, but you may need to drive slower if conditions require it.",
        ),
        ("leaving a woonerf", "The special walking-pace rule ends when the erf ends and the next road rule applies."),
        (
            "comparing a woonerf with a 30-zone",
            "A woonerf is slower and more shared with pedestrians than a normal 30-zone.",
        ),
        ("a child playing in a woonerf", "You should be ready to slow almost to a crawl or stop."),
        (
            "thinking that a 30-zone means you must always drive exactly 30 km/h",
            "That is wrong; 30 km/h is a maximum, not a target in every situation.",
        ),
    ]
    for subject, correct in woonerf_items:
        add_variants(
            questions,
            rule_prompts(subject),
            correct,
            [
                "A woonerf allows normal urban speed of 50 km/h.",
                "A 30-zone has no speed limit if there are speed humps.",
                "Pedestrians must always leave the road for cars in a woonerf.",
            ],
            "Residential environments often need lower speed than the formal maximum because pedestrians and parked cars reduce safety margins.",
            difficulty=1,
        )

    night_items = [
        (
            "a Dutch motorway between 06:00 and 19:00",
            "The national motorway maximum is 100 km/h unless a lower sign applies.",
        ),
        (
            "a Dutch motorway between 19:00 and 06:00 where signs allow 130",
            "You may follow the higher posted night limit up to 130 km/h.",
        ),
        (
            "a motorway at night where the signs still show 100",
            "You must stay at 100 km/h because the displayed limit still applies.",
        ),
        (
            "thinking that every motorway automatically becomes 130 km/h at night",
            "That is wrong; you still follow the posted limit for that road section.",
        ),
    ]
    for subject, correct in night_items:
        add_variants(
            questions,
            rule_prompts(subject),
            correct,
            [
                "Every motorway is always 130 km/h after dark.",
                "Night-time removes all lower local limits.",
                "The day-time 100 km/h rule also applies inside a woonerf.",
            ],
            "Day and night motorway rules in the Netherlands still depend on the posted road-specific limit.",
            difficulty=2,
        )

    scenario_items = [
        (
            "you pass the built-up area sign after driving on an unsigned rural road",
            "Reduce to the built-up-area default unless a new sign says otherwise.",
        ),
        (
            "you leave the built-up area and no lower sign follows",
            "The outside-built-up default becomes relevant unless another sign changes it.",
        ),
        (
            "you enter road works marked 50 km/h from a 100 km/h motorway section",
            "Follow the 50 km/h road-works sign immediately.",
        ),
        ("a matrix sign above your lane shows 70 because of congestion", "You must obey the displayed 70 km/h limit."),
        (
            "a 30-zone end sign appears and you continue onto an ordinary built-up road",
            "The ordinary built-up-area rule applies again unless another sign sets a different limit.",
        ),
        ("you enter an erf from a 30-zone", "Slow to walking pace because the erf rule is stricter."),
        (
            "you tow a trailer onto a motorway at night where cars may drive 130",
            "Your lower towing limit still applies.",
        ),
        (
            "you leave an expressway and immediately enter a 50 km/h village",
            "Follow the new signed or default village speed, not the old expressway speed.",
        ),
        (
            "a road is inside the built-up area but a sign shows 30",
            "The signed 30 limit overrides the normal built-up-area default.",
        ),
        (
            "you reach the end-of-limit sign after a signed 80 section outside town",
            "The specific signed restriction ends and the next applicable default or sign takes over.",
        ),
        (
            "school traffic makes a signed 30 section busy with children",
            "Drive at or below the signed limit and slower if needed for safety.",
        ),
        (
            "heavy rain reduces visibility on a road signed at 80",
            "The legal maximum stays 80, but a safe speed may be much lower.",
        ),
        (
            "you join a motorway in daytime from a slower slip road",
            "Once on the motorway, follow the motorway limit that applies to that section.",
        ),
        (
            "you see a speed sign and assume it is only advice because the road looks wide",
            "That is wrong; a speed-limit sign is a legal maximum.",
        ),
    ]
    for context, correct in scenario_items:
        add_variants(
            questions,
            scenario_prompts(context),
            correct,
            [
                "Keep the previous speed until the next junction.",
                "Ignore the new limit if traffic is light.",
                "Choose your own speed because limits are only recommendations.",
            ],
            "Speed limits can change immediately when road type or signs change. Good drivers react early and smoothly.",
            difficulty=2,
            question_type="scenario",
        )

    return finalize_topic("speed-limits", questions)


def build_road_marking_questions():
    questions = []

    solid_broken_items = [
        ("a solid centre line", "Do not cross it if crossing would violate the marking."),
        ("a broken centre line", "You may cross it only when it is safe and otherwise allowed."),
        ("an overtake that would require crossing a solid centre line", "Do not make the overtake."),
        (
            "a road where your side has the solid line and the other side has a broken line",
            "The solid line on your side means you must not cross from your side.",
        ),
        (
            "a road where your side has the broken line and the other side has the solid line",
            "You may cross from your side only if it is otherwise safe and allowed.",
        ),
        ("using a solid centre line as a suggestion only", "That is wrong; the marking gives a real restriction."),
        (
            "choosing to overtake because the road looks empty even though a solid line is present",
            "The solid line still restricts you.",
        ),
        (
            "meeting oncoming traffic near a solid centre line",
            "Keep your position and do not use the oncoming side to create room for yourself.",
        ),
    ]
    for subject, correct in solid_broken_items:
        add_variants(
            questions,
            rule_prompts(subject),
            correct,
            [
                "Centre lines never matter if you indicate.",
                "A solid line only applies in darkness.",
                "You may always cross a solid line to save time.",
            ],
            "Centre-line markings organise safe separation between directions of travel.",
            difficulty=2,
        )

    yellow_line_items = [
        (
            "a yellow solid line along the kerb",
            "No stopping is allowed there except when forced by traffic conditions.",
        ),
        ("a yellow broken line along the kerb", "Parking is prohibited there."),
        (
            "the difference between a yellow solid kerb line and a yellow broken kerb line",
            "A yellow solid line forbids stopping, while a yellow broken line forbids parking.",
        ),
        (
            "thinking that yellow kerb lines are decorative only",
            "That is wrong; they create parking or stopping restrictions.",
        ),
    ]
    for subject, correct in yellow_line_items:
        add_variants(
            questions,
            rule_prompts(subject),
            correct,
            [
                "Yellow lines always mean motorway shoulder.",
                "Yellow kerb lines only apply to lorries.",
                "Both yellow line types mean exactly the same thing.",
            ],
            "Yellow kerb markings in the Netherlands are used for parking and stopping restrictions.",
            difficulty=1,
        )

    shark_teeth_items = [
        (
            "shark teeth painted on your approach",
            "They tell you to give way to the traffic on the road you are entering.",
        ),
        (
            "shark teeth at a roundabout entrance",
            "Yield to the circulating traffic and any other priority traffic indicated by the layout.",
        ),
        ("shark teeth before a cycle crossing", "Yield if the crossing traffic has priority there."),
        ("shark teeth together with a give-way sign", "Both confirm that your approach must yield."),
        (
            "shark teeth facing the other road instead of your lane",
            "The other approach is the one that must yield, not yours.",
        ),
        ("assuming shark teeth are only a warning and not a rule", "That is wrong; they mark a yielding approach."),
        ("a side road with shark teeth entering a priority road", "The side road traffic must yield."),
        (
            "a cyclist ring crossing at a roundabout where shark teeth face the entering car",
            "The entering car must yield at that marking.",
        ),
    ]
    for subject, correct in shark_teeth_items:
        add_variants(
            questions,
            rule_prompts(subject),
            correct,
            [
                "They mean accelerate to merge quickly.",
                "They only matter in rain.",
                "They create parking spaces.",
            ],
            "Shark teeth are one of the clearest Dutch road markings for yielding traffic.",
            difficulty=2,
        )

    stop_line_items = [
        (
            "a stop line before a red light or STOP sign",
            "Stop before the line unless traffic conditions already forced you over it.",
        ),
        ("a stop line at a level crossing signal", "Stop before the line and keep the crossing clear."),
        ("a stop line with poor weather and reduced grip", "Brake early so you stop before the line safely."),
        ("thinking that a stop line is only advice", "That is wrong; it shows where stopping should happen."),
    ]
    for subject, correct in stop_line_items:
        add_variants(
            questions,
            rule_prompts(subject),
            correct,
            [
                "Stop lines only apply to buses.",
                "You should stop beyond the line for better visibility.",
                "A stop line means parking is allowed.",
            ],
            "Stop lines help keep crossings, signals, and pedestrian space clear.",
            difficulty=1,
        )

    hatched_items = [
        (
            "a hatched area or verdrijvingsvlak",
            "Do not drive on it unless it is necessary and safe and the marking type permits it.",
        ),
        ("using a hatched area as an overtaking lane", "Do not do that."),
        (
            "a hatched area guiding traffic away from an obstacle",
            "Follow the lane around it instead of driving over it.",
        ),
        (
            "a hatched area near a junction",
            "Treat it as an area meant to separate and guide traffic, not as spare road space.",
        ),
        ("crossing a hatched area just to save time in a queue", "That is not the purpose of the marking."),
        ("a broad hatched island near lane drops", "Stay out of it and follow the marked lane transition."),
    ]
    for subject, correct in hatched_items:
        add_variants(
            questions,
            rule_prompts(subject),
            correct,
            [
                "Hatched areas are free parking zones.",
                "They are emergency overtaking spaces.",
                "They cancel all lane arrows.",
            ],
            "Hatched markings separate traffic streams and protect space that should normally remain clear.",
            difficulty=2,
        )

    lane_marking_items = [
        ("lane arrows painted before a junction", "Choose the correct lane early and follow the direction shown."),
        ("a lane-drop marking", "Merge in good time instead of forcing your way at the last moment."),
        ("edge lines on the side of the carriageway", "They help show the road boundary and should not be ignored."),
        ("dashed lane lines on a multi-lane road", "You may change lanes when it is safe and useful."),
        ("a lane reserved by markings and signs for a special direction", "Use it only for the purpose shown."),
        ("poor visibility where lane markings guide your path", "Use the markings to maintain safe road position."),
    ]
    for subject, correct in lane_marking_items:
        add_variants(
            questions,
            rule_prompts(subject),
            correct,
            [
                "Lane markings never matter if you know the road.",
                "They only apply to trucks.",
                "You may ignore them whenever traffic is slow.",
            ],
            "Lane markings organise traffic flow and reduce conflict between movements.",
            difficulty=1,
        )

    bus_lane_items = [
        ("BUS markings on a lane", "The lane is reserved for buses unless a sign also allows other categories."),
        ("using a bus lane to avoid a queue in an ordinary car", "Only do so if signs allow your vehicle."),
        ("a bus lane next to normal lanes", "Stay out of it unless your category is permitted there."),
        ("thinking that a bus lane is a convenient stopping place", "That is wrong; it is a reserved traffic lane."),
    ]
    for subject, correct in bus_lane_items:
        add_variants(
            questions,
            rule_prompts(subject),
            correct,
            [
                "Every driver may use a bus lane when in a hurry.",
                "Bus lanes are only painted to make roads look narrower.",
                "A bus lane is a cycle path after 18:00.",
            ],
            "Bus lane markings work together with signs to reserve road space for public transport and any categories named on the sign.",
            difficulty=2,
        )

    extra_marking_items = [
        ("guide arrows before road works", "Follow them early so you merge smoothly into the correct lane."),
        (
            "temporary yellow markings at road works",
            "Temporary yellow markings override conflicting old white markings.",
        ),
        (
            "a cycle lane marking beside your lane",
            "Do not drive into it unless road layout or signs clearly require or allow it.",
        ),
        (
            "a pedestrian crossing marking",
            "Be ready to stop for pedestrians who are crossing or clearly about to cross.",
        ),
    ]
    for subject, correct in extra_marking_items:
        add_variants(
            questions,
            rule_prompts(subject),
            correct,
            [
                "Temporary markings are only decoration.",
                "Pedestrian crossing markings never affect drivers.",
                "Cycle lane markings are spare overtaking space.",
            ],
            "Road markings often work as practical instructions and must be read together with signs and the road layout.",
            difficulty=2,
        )

    return finalize_topic("road-markings", questions)


def build_parking_stopping_questions():
    questions = []

    definition_items = [
        (
            "the difference between parking and stopping",
            "Parking means standing still for reasons other than immediate passenger boarding or loading and unloading.",
        ),
        ("a brief necessary stop to let a passenger get in or out", "That is generally stopping, not parking."),
        (
            "standing still to check your phone or wait for someone for several minutes",
            "That counts as parking, not a brief necessary stop.",
        ),
        (
            "why the parking-versus-stopping difference matters",
            "Because some places forbid parking while others forbid every voluntary stop.",
        ),
    ]
    for subject, correct in definition_items:
        add_variants(
            questions,
            rule_prompts(subject),
            correct,
            [
                "Parking and stopping always mean the same thing.",
                "Stopping only applies to buses.",
                "Parking only matters on motorways.",
            ],
            "Dutch traffic law distinguishes parking from a brief necessary stop for immediate boarding or loading tasks.",
            difficulty=1,
        )

    forbidden_items = [
        ("parking on a zebra crossing", "It is forbidden."),
        ("parking on the pavement or sidewalk without permission", "It is forbidden."),
        ("parking on a cycle path or cycle lane", "It is forbidden."),
        ("parking in front of an entrance or exit", "It is forbidden if you block access."),
        ("parking on a level crossing", "It is forbidden."),
        ("parking on the carriageway of a priority road outside a built-up area", "It is normally forbidden."),
        ("parking on a motorway or expressway except in emergency", "It is forbidden."),
        ("parking at a bus stop where the stop markings apply", "It is forbidden."),
        ("parking in a disabled space without the required entitlement", "It is forbidden."),
        ("parking in a no-parking area shown by signs or plates", "It is forbidden."),
    ]
    for subject, correct in forbidden_items:
        add_variants(
            questions,
            rule_prompts(subject),
            correct,
            [
                "It is allowed if you leave the hazard lights on.",
                "It is allowed for five minutes everywhere.",
                "It is allowed when the road seems quiet.",
            ],
            "Some places are always or almost always unsuitable for parking because they block visibility, safety, or reserved use.",
            difficulty=1,
        )

    distance_items = [
        ("parking within 5 metres of a junction", "It is forbidden because it harms visibility and junction safety."),
        ("stopping or parking too close to a crossing point where sight is reduced", "You should keep the area clear."),
        ("measuring the 5-metre rule from the corner of the junction", "That is the practical rule to remember."),
        ("parking close to an intersection because the road feels wide", "The 5-metre rule still matters."),
        ("a parked van near a junction blocking sight lines", "That is exactly why distance rules exist."),
        ("thinking the 5-metre junction rule applies only at night", "That is wrong; it applies all day."),
    ]
    for subject, correct in distance_items:
        add_variants(
            questions,
            rule_prompts(subject),
            correct,
            [
                "Distance rules disappear in built-up areas.",
                "Only trucks must keep 5 metres from a junction.",
                "Indicators cancel the distance rule.",
            ],
            "Keeping junction approaches clear protects sight lines for all road users.",
            difficulty=2,
        )

    sign_items = [
        ("a no-parking sign", "Parking is not allowed there."),
        ("a no-stopping sign", "Stopping voluntarily is not allowed there."),
        ("a parking sign with a time plate", "You may only park according to the shown conditions."),
        ("a parking sign with arrows", "The arrows show where the restriction starts, continues, or ends."),
        (
            "a place reserved by sign for disabled users, taxis, or deliveries",
            "Only the indicated category may use it.",
        ),
        (
            "yellow kerb lines together with signs",
            "You follow the restriction shown by the markings and the sign together.",
        ),
        (
            "a sign-based parking rule that you did not fully read",
            "You should not park until you understand the full condition on the plate.",
        ),
        (
            "assuming that a blue P sign always means unlimited free parking",
            "That is wrong; plates may add conditions such as time, permit, or vehicle category.",
        ),
    ]
    for subject, correct in sign_items:
        add_variants(
            questions,
            rule_prompts(subject),
            correct,
            [
                "Parking signs never have extra conditions.",
                "A no-stopping sign still allows long waits.",
                "Arrow plates are only decoration.",
            ],
            "Parking signs must be read carefully together with any plates, road markings, and local restrictions.",
            difficulty=2,
        )

    blue_zone_items = [
        ("parking in a blue zone", "Use a parking disc and respect the maximum time shown."),
        ("forgetting to set the parking disc in a blue zone", "You are not meeting the parking condition."),
        ("the purpose of a blue-zone parking rule", "It limits stay duration so spaces turn over."),
        (
            "seeing a blue-zone sign without reading the time plate",
            "You should read the local condition before leaving the car.",
        ),
        ("using a blue-zone space all day without a valid exemption", "That is not allowed."),
        (
            "thinking that a blue zone is the same as a no-parking area",
            "That is wrong; parking is allowed there under conditions.",
        ),
    ]
    for subject, correct in blue_zone_items:
        add_variants(
            questions,
            rule_prompts(subject),
            correct,
            [
                "A blue zone allows parking without any time control.",
                "Blue zones are only for motorcycles.",
                "A blue zone means you must pay motorway toll.",
            ],
            "Blue zones are controlled parking areas that use a parking disc and local time limit.",
            difficulty=2,
        )

    loading_items = [
        (
            "brief loading and unloading in a place where parking is prohibited",
            "It may still be different from parking if the activity is immediate and necessary, but you must not block danger areas or no-stopping areas.",
        ),
        (
            "claiming to be loading while actually waiting with no active loading",
            "That is parking, not genuine loading.",
        ),
        ("loading goods quickly in a no-stopping area", "That is not allowed because no-stopping is stricter."),
        ("using a loading bay", "Use it only for the loading or unloading purpose shown."),
        ("standing still for many minutes after unloading has ended", "That becomes parking."),
        (
            "loading on a dangerous place such as a zebra crossing",
            "It is not allowed just because you are handling goods.",
        ),
    ]
    for subject, correct in loading_items:
        add_variants(
            questions,
            rule_prompts(subject),
            correct,
            [
                "Any activity counts as loading if the boot is open.",
                "Loading lets you ignore all stopping bans.",
                "Loading is only a rule for shops, not private drivers.",
            ],
            "Immediate loading and unloading can be treated differently from parking, but it never allows you to use clearly forbidden danger locations.",
            difficulty=2,
        )

    extra_items = [
        ("stopping on the hard shoulder to check messages", "Do not do that; the shoulder is for emergencies."),
        ("parking where your vehicle blocks a clear view of signs or crossings", "You should not park there."),
        ("using hazard lights to justify illegal parking", "Hazard lights do not make illegal parking legal."),
        (
            "parking on a narrow road where emergency vehicles could not pass",
            "Choose another place and keep the route clear.",
        ),
    ]
    for subject, correct in extra_items:
        add_variants(
            questions,
            rule_prompts(subject),
            correct,
            [
                "Hazard lights create a legal parking exemption.",
                "The hard shoulder is a normal rest area.",
                "Blocking emergency access is fine for short stops.",
            ],
            "Parking decisions must still leave visibility, access, and safety for others.",
            difficulty=2,
        )

    return finalize_topic("parking-stopping", questions)


def build_roundabout_questions():
    questions = []

    entry_items = [
        ("entering a normal roundabout with shark teeth on your lane", "Yield to traffic already on the roundabout."),
        (
            "approaching a roundabout entrance with clear give-way markings",
            "Slow down and be ready to yield before entering.",
        ),
        (
            "joining a roundabout because you think entering traffic always has priority",
            "That is wrong; the markings usually make entering traffic yield.",
        ),
        (
            "a quiet roundabout that still has shark teeth at the entrance",
            "The yield rule still applies even when the roundabout is quiet.",
        ),
        (
            "a mini-roundabout with marked priority at the entry",
            "You must respect the marked yield rule before joining.",
        ),
        (
            "entering a roundabout while another vehicle is already circulating from your left",
            "Let the circulating vehicle continue first.",
        ),
        ("rushing onto a roundabout to save time", "Do not do that; enter only when there is a safe gap."),
        (
            "treating a roundabout entry like an ordinary equal junction without reading the markings",
            "That is unsafe because roundabouts usually have specific yield markings.",
        ),
    ]
    for subject, correct in entry_items:
        add_variants(
            questions,
            rule_prompts(subject),
            correct,
            [
                "Entering traffic automatically goes first.",
                "Use speed to force a gap.",
                "Roundabout markings only apply at night.",
            ],
            "Most Dutch roundabouts use shark teeth to give circulating traffic priority over entering traffic.",
            difficulty=2,
            question_type="scenario",
        )

    cyclist_items = [
        (
            "a roundabout where a separate cycle ring crossing has shark teeth facing your car",
            "You must yield at that cycle crossing.",
        ),
        (
            "a roundabout cycle crossing where the shark teeth face the cyclist instead of you",
            "The cyclist must yield there.",
        ),
        (
            "thinking cyclists always or never have priority at Dutch roundabouts",
            "That is wrong; you must read the signs and markings at each crossing.",
        ),
        (
            "leaving a roundabout across a cycle crossing with priority markings in favour of the cyclist",
            "Yield and do not cut the cyclist off.",
        ),
        (
            "entering a roundabout where cyclists are on a separate ring but your approach has clear yield markings",
            "Respect the markings and give priority where required.",
        ),
        (
            "a busy urban roundabout where cyclists may appear quickly from both directions on the ring crossing",
            "Reduce speed and scan carefully before crossing the cycle path.",
        ),
        ("assuming your indicator gives you priority over a cyclist when exiting the roundabout", "It does not."),
        (
            "a roundabout exit where a cyclist is already on the crossing you must traverse",
            "Do not cut across the cyclist's path.",
        ),
        (
            "a small roundabout near a school with frequent cycle traffic",
            "Expect cyclists and read the crossing markings carefully.",
        ),
        (
            "a multi-lane roundabout exit crossing a marked cycle path",
            "Choose your lane early and still yield if the crossing markings require it.",
        ),
    ]
    for subject, correct in cyclist_items:
        add_variants(
            questions,
            rule_prompts(subject),
            correct,
            [
                "Cyclists never matter at roundabouts.",
                "Cars always outrank cyclists when leaving a roundabout.",
                "Indicators cancel cycle-crossing priority.",
            ],
            "Cyclist priority at roundabouts is decided by the actual signs and markings. Dutch theory expects you to read them carefully.",
            difficulty=2,
            question_type="scenario",
        )

    signaling_items = [
        ("leaving a roundabout", "Signal right in good time when you are about to exit."),
        (
            "approaching the first exit on a simple roundabout",
            "Prepare early and signal right when your exit is imminent.",
        ),
        (
            "entering a roundabout without any intention to leave immediately",
            "Do not give misleading signals; signal clearly when you are actually leaving.",
        ),
        ("changing lane on a larger roundabout", "Use mirrors, signal, and move smoothly in good time."),
        (
            "thinking indicators at roundabouts are optional",
            "That is wrong; clear signalling helps other road users predict your exit.",
        ),
        (
            "signalling too late while exiting in front of cyclists or drivers waiting to enter",
            "That reduces predictability and can cause conflict.",
        ),
    ]
    for subject, correct in signaling_items:
        add_variants(
            questions,
            rule_prompts(subject),
            correct,
            [
                "Signal left when you leave every roundabout.",
                "Never use indicators on a roundabout.",
                "Only buses need to signal at roundabouts.",
            ],
            "Roundabout signalling is about making your movement predictable, especially when you exit.",
            difficulty=1,
            question_type="scenario",
        )

    multi_lane_items = [
        ("a multi-lane roundabout", "Choose the correct lane early and keep observing mirrors and blind spots."),
        (
            "cutting across from the inner lane to an exit at the last second",
            "Do not do that; plan your lane choice earlier.",
        ),
        ("a multi-lane roundabout with arrows showing the lane for your exit", "Follow the lane guidance."),
        (
            "being next to another vehicle on a multi-lane roundabout",
            "Do not assume it will stay perfectly in lane; keep space and observe.",
        ),
        ("changing lane on a roundabout without checking for motorcycles or cyclists", "That is unsafe and incorrect."),
        (
            "missing the correct lane before a roundabout exit",
            "Keep circulating safely if needed rather than forcing a dangerous late exit.",
        ),
    ]
    for subject, correct in multi_lane_items:
        add_variants(
            questions,
            rule_prompts(subject),
            correct,
            [
                "Late lane changes are always acceptable if you signal.",
                "Roundabout arrows are only advice.",
                "Blind spots disappear at low speed.",
            ],
            "Multi-lane roundabouts punish late decisions. Early planning and observation are essential.",
            difficulty=3,
            question_type="scenario",
            points=2,
        )

    haaientanden_items = [
        ("shark teeth at a roundabout entrance", "They show that your approach must yield before entering."),
        (
            "shark teeth at a cycle crossing just after the roundabout exit",
            "They show who must yield at that crossing.",
        ),
        (
            "a roundabout entry where you see both shark teeth and a give-way sign",
            "Both reinforce the same yield duty.",
        ),
        ("thinking shark teeth at roundabouts are optional in slow traffic", "That is wrong; the rule still applies."),
        (
            "a compact roundabout where the shark teeth are slightly worn but still visible",
            "Treat them as a yield marking and approach carefully.",
        ),
        (
            "a roundabout entry with poor weather and shark teeth ahead",
            "Brake early so you can yield before the marking safely.",
        ),
    ]
    for subject, correct in haaientanden_items:
        add_variants(
            questions,
            rule_prompts(subject),
            correct,
            [
                "They mean stop only for trams.",
                "They reserve the lane for buses.",
                "They mark a parking place.",
            ],
            "Shark teeth are central to many roundabout priority questions in Dutch theory.",
            difficulty=2,
            question_type="scenario",
        )

    mistake_items = [
        (
            "using the wrong exit lane at the last moment on a roundabout",
            "Continue safely and correct your route later if needed.",
        ),
        ("accelerating hard onto a roundabout to force other drivers to brake", "That is unsafe and incorrect."),
        (
            "looking only left and forgetting the cycle crossing when leaving a roundabout",
            "That is a common dangerous mistake.",
        ),
        ("stopping on the roundabout itself without need", "Do not do that unless traffic conditions force it."),
    ]
    for subject, correct in mistake_items:
        add_variants(
            questions,
            rule_prompts(subject),
            correct,
            [
                "Force your way out because others must adapt.",
                "Ignore cyclists when exiting.",
                "Stop in the roundabout to decide where to go.",
            ],
            "Many roundabout errors come from late decisions, poor signalling, or not checking the exits properly.",
            difficulty=2,
            question_type="scenario",
        )

    extra_items = [
        (
            "a pedestrian crossing immediately after a roundabout exit",
            "Be ready to stop after leaving the roundabout if pedestrians are crossing or about to cross.",
        ),
        (
            "a bus or long vehicle using more than one lane space on a small roundabout",
            "Give it room and do not sit in its blind spot.",
        ),
        (
            "driving straight through the centre of a mini-roundabout",
            "Do not do that; you still follow the circular flow unless road design clearly states otherwise.",
        ),
        (
            "a very small roundabout where visibility is partly blocked by signs",
            "Approach slowly and be ready for late-seen cyclists or other vehicles.",
        ),
    ]
    for subject, correct in extra_items:
        add_variants(
            questions,
            rule_prompts(subject),
            correct,
            [
                "Pedestrian crossings after exits do not matter.",
                "Large vehicles must stay perfectly in one lane.",
                "Mini-roundabouts can be driven across if nobody is watching.",
            ],
            "Roundabouts often combine several hazards immediately before and after the circle itself.",
            difficulty=2,
            question_type="scenario",
        )

    return finalize_topic("roundabouts", questions)


def build_cyclist_pedestrian_questions():
    questions = []

    zebra_items = [
        ("a pedestrian on a zebra crossing", "You must let the pedestrian cross."),
        (
            "a pedestrian clearly about to step onto a zebra crossing",
            "Approach ready to stop and let the pedestrian cross safely.",
        ),
        ("overtaking another vehicle near a zebra crossing", "Avoid it because the crossing may hide pedestrians."),
        ("parking on or immediately by a zebra crossing", "Do not do that."),
        ("a zebra crossing in rain where sight and stopping distance are worse", "Reduce speed and prepare earlier."),
        ("thinking that zebra crossings only matter if the pedestrian waves at you", "That is wrong."),
        ("a zebra crossing just after a bus stop", "Expect pedestrians and lower speed early."),
        (
            "a cyclist using a zebra crossing while riding instead of walking",
            "The zebra crossing rule is mainly for pedestrians, so read the exact situation carefully.",
        ),
    ]
    for subject, correct in zebra_items:
        add_variants(
            questions,
            rule_prompts(subject),
            correct,
            [
                "Pedestrians only have priority at traffic lights.",
                "You may continue if you are already slightly above the speed limit.",
                "Zebra crossings do not matter in built-up areas.",
            ],
            "Zebra crossings protect pedestrians. Dutch drivers are expected to approach them carefully and predictably.",
            difficulty=2,
            question_type="scenario",
        )

    cycle_path_items = [
        ("a mandatory cycle path sign", "The path is intended for cyclists and the categories shown by the sign."),
        ("a cycle lane beside the carriageway", "Keep out of it unless signs or road design clearly permit otherwise."),
        (
            "a combined pedestrian and cycle path",
            "Look carefully because different vulnerable users may share the space.",
        ),
        (
            "crossing a cycle path while entering or leaving another road",
            "You must read the markings and give priority where required.",
        ),
        (
            "thinking every painted bicycle symbol creates exactly the same rule",
            "That is wrong; signs, lane type, and layout matter.",
        ),
        ("a cycle path next to parked cars", "Expect cyclists to move around doors or obstacles."),
        (
            "a segregated cycle path in town",
            "Cyclists may appear faster and in larger numbers than on the carriageway.",
        ),
        ("using a cycle path as a convenient drop-off zone", "Do not do that."),
    ]
    for subject, correct in cycle_path_items:
        add_variants(
            questions,
            rule_prompts(subject),
            correct,
            [
                "Cycle paths are spare lanes for overtaking.",
                "Only sports cyclists use cycle paths.",
                "Cars may stop there if the hazard lights are on.",
            ],
            "Dutch roads often separate cyclists from cars. The markings and signs around cycle paths must be taken seriously.",
            difficulty=2,
            question_type="scenario",
        )

    turning_items = [
        (
            "turning right across a cycle path while cyclists ride straight on",
            "Let the cyclists go first and do not cut across them.",
        ),
        (
            "turning left while a cyclist rides straight ahead beside you on the same road",
            "Yield to the cyclist going straight on.",
        ),
        ("leaving a driveway across a cycle path", "Cross only when it is safe and after giving way where required."),
        ("turning at a junction without checking your blind spot for cyclists", "That is unsafe and incorrect."),
        ("a cyclist appearing from behind a parked van as you turn", "Slow down and be ready to stop."),
        ("thinking your indicator gives you priority over a cyclist you are crossing", "It does not."),
        ("turning across a two-way cycle track", "Look both ways before crossing."),
        (
            "turning across a cycle crossing in bad weather",
            "Reduce speed earlier because cyclists may be harder to see.",
        ),
        ("a delivery van blocking part of the cycle track before your turn", "Expect a cyclist to emerge around it."),
        ("starting the turn before the cyclist ring or cycle path is clear", "Wait until the path is actually clear."),
    ]
    for subject, correct in turning_items:
        add_variants(
            questions,
            rule_prompts(subject),
            correct,
            [
                "Cyclists must always stop for turning cars.",
                "Blind-spot checks only matter for trucks.",
                "You may turn first if you wave the cyclist through.",
            ],
            "Many Dutch collisions happen when turning drivers fail to read cycle traffic correctly.",
            difficulty=2,
            question_type="scenario",
        )

    woonerf_items = [
        ("pedestrians in a woonerf", "They may use the full street and you should drive at walking pace."),
        ("children playing in a woonerf", "Be ready to slow to a crawl or stop."),
        ("parking in a woonerf", "Only park in the places indicated for parking."),
        ("thinking a woonerf is just an ordinary 30-zone", "That is wrong; the shared-space rules are stricter."),
        (
            "meeting a pedestrian walking in the middle of a woonerf",
            "Do not pressure the pedestrian; adapt your speed instead.",
        ),
        ("entering a woonerf from a faster road", "Slow immediately and read the street as shared space."),
    ]
    for subject, correct in woonerf_items:
        add_variants(
            questions,
            rule_prompts(subject),
            correct,
            [
                "Cars keep normal urban priority over pedestrians in a woonerf.",
                "You may park anywhere because speeds are low.",
                "A woonerf allows ordinary 50 km/h if the road is wide enough.",
            ],
            "Woonerven are shared areas where pedestrians and low speed dominate the road environment.",
            difficulty=1,
            question_type="scenario",
        )

    children_items = [
        ("children playing near the road", "Reduce speed early and expect sudden unpredictable movement."),
        ("a ball rolling into the street near parked cars", "Expect a child to follow and be ready to stop."),
        ("driving past a school entrance at busy times", "Lower speed and scan widely for children and parents."),
        ("thinking children will always judge your speed correctly", "That is wrong."),
    ]
    for subject, correct in children_items:
        add_variants(
            questions,
            rule_prompts(subject),
            correct,
            [
                "Children are as predictable as experienced drivers.",
                "You only need to slow if a police officer is present.",
                "Use the horn so children move faster.",
            ],
            "Children are one of the most important hazard groups in Dutch road awareness.",
            difficulty=2,
            question_type="hazard",
        )

    pedestrian_only_items = [
        ("a pedestrian-only area", "Motor vehicles are not allowed unless an exception is shown."),
        ("a footpath sign", "It is intended for pedestrians."),
        (
            "crossing a pedestrian area while looking mainly for cars",
            "You should focus on pedestrians first because they are the main users.",
        ),
        (
            "thinking a pedestrian area becomes a delivery route whenever it looks empty",
            "That is wrong unless a sign gives an exception.",
        ),
    ]
    for subject, correct in pedestrian_only_items:
        add_variants(
            questions,
            rule_prompts(subject),
            correct,
            [
                "Pedestrian-only areas are just low-speed roads for any vehicle.",
                "Only cyclists count as pedestrians there.",
                "Cars may use them if they are local residents.",
            ],
            "Pedestrian areas and footpaths are designed around people on foot, not ordinary motor traffic.",
            difficulty=1,
        )

    extra_items = [
        (
            "a shared path with both pedestrians and cyclists",
            "Expect different speeds and movements and pass carefully.",
        ),
        ("a pedestrian stepping out from behind a parked delivery van", "Slow down and be ready to stop."),
        ("a cyclist avoiding a door zone near parked cars", "Expect sideways movement and leave space."),
        (
            "meeting pedestrians in heavy rain or dark clothing near an unlit road",
            "Use extra observation and lower speed because they are harder to see.",
        ),
    ]
    for subject, correct in extra_items:
        add_variants(
            questions,
            rule_prompts(subject),
            correct,
            [
                "Pedestrians and cyclists always move in straight predictable lines.",
                "Door zones only matter for motorcycles.",
                "Dark clothing removes the driver's duty to observe.",
            ],
            "Vulnerable road users often become risky when visibility or available space is reduced.",
            difficulty=2,
            question_type="hazard",
        )

    return finalize_topic("cyclists-pedestrians", questions)


def build_motorway_questions():
    questions = []

    speed_items = [
        ("a Dutch motorway between 06:00 and 19:00", "The national maximum is 100 km/h unless a lower sign applies."),
        (
            "a motorway at night where the signs allow 130",
            "You may drive up to 130 km/h if that is the posted night-time limit.",
        ),
        ("a motorway at night where the displayed speed is 100", "You must remain at 100 km/h."),
        ("a motorway work zone with a 70 km/h matrix sign", "You must obey the displayed 70 km/h limit."),
        (
            "thinking every motorway is automatically 130 at night",
            "That is wrong; follow the posted limit of that section.",
        ),
        (
            "joining a motorway from a slip road in daytime",
            "Once on the motorway, follow the motorway speed that applies there.",
        ),
        ("heavy rain on a motorway signed at 100", "The legal maximum remains 100, but a safe speed may be lower."),
        ("a passenger car towing a trailer on a motorway", "The towing maximum of 90 km/h applies."),
    ]
    for subject, correct in speed_items:
        add_variants(
            questions,
            rule_prompts(subject),
            correct,
            [
                "Motorways never have lower temporary limits.",
                "Night-time removes every lower sign.",
                "The motorway limit applies to every vehicle without exception.",
            ],
            "Motorway speed in the Netherlands depends on time of day, local signs, and sometimes vehicle type.",
            difficulty=2,
        )

    shoulder_items = [
        (
            "the hard shoulder or vluchtstrook",
            "It is for emergencies and breakdowns, not ordinary driving or stopping.",
        ),
        ("using the hard shoulder to skip a queue", "That is not allowed."),
        ("stopping on the hard shoulder to make a phone call", "Do not do that unless there is a genuine emergency."),
        ("a breakdown on the motorway", "Use the hard shoulder if possible and secure yourself safely."),
        ("driving on the hard shoulder because the live lanes feel slow", "That is forbidden."),
        (
            "a hard shoulder opened by official signals as an extra lane",
            "Only use it when the overhead signals or instructions clearly permit it.",
        ),
    ]
    for subject, correct in shoulder_items:
        add_variants(
            questions,
            rule_prompts(subject),
            correct,
            [
                "The shoulder is a normal overtaking lane.",
                "You may park on the shoulder for rest breaks.",
                "The shoulder belongs to motorcycles only.",
            ],
            "The motorway shoulder exists mainly for emergency use and incident management.",
            difficulty=2,
        )

    merge_exit_items = [
        (
            "joining a motorway from a slip road",
            "Use the slip road to build suitable speed and merge when a safe gap appears.",
        ),
        ("approaching an exit on the motorway", "Move to the correct lane early and exit smoothly."),
        ("missing your motorway exit", "Continue safely and take the next exit instead of stopping or reversing."),
        ("merging by forcing main-lane traffic to brake hard", "That is unsafe and incorrect."),
        ("a short merge lane", "Observe early, adjust speed, and merge decisively but safely."),
        ("leaving the motorway across a solid gore area", "Do not cut across the marked area."),
        (
            "joining the motorway far below the speed of traffic when you could have accelerated more",
            "That creates merging difficulty and risk.",
        ),
        ("changing several lanes at once to catch an exit", "Plan earlier instead of making a sudden risky move."),
    ]
    for subject, correct in merge_exit_items:
        add_variants(
            questions,
            rule_prompts(subject),
            correct,
            [
                "Stop at the end of the slip road until the motorway is empty.",
                "Reverse if you miss the exit.",
                "Use the shoulder as the normal merge lane.",
            ],
            "Motorway entries and exits demand early planning, speed matching, and predictable lane use.",
            difficulty=2,
            question_type="scenario",
        )

    prohibited_items = [
        (
            "vehicles that cannot or may not use a motorway",
            "Slow vehicles and prohibited categories such as bicycles or pedestrians are not allowed there.",
        ),
        ("a bicycle entering a motorway", "That is forbidden."),
        ("a pedestrian walking on the motorway except in a genuine emergency situation", "That is not allowed."),
        ("a slow vehicle that cannot reach at least about 60 km/h by design", "It is not suitable for motorway use."),
    ]
    for subject, correct in prohibited_items:
        add_variants(
            questions,
            rule_prompts(subject),
            correct,
            [
                "Every road user may use the motorway if careful.",
                "Only tractors are restricted.",
                "Motorway bans apply only at night.",
            ],
            "Motorways are reserved for faster motor traffic capable of safe motorway speed.",
            difficulty=1,
        )

    minimum_speed_items = [
        ("motorway access for vehicles unable to reach about 60 km/h", "They are not allowed on the motorway."),
        (
            "the idea of a practical minimum capability on a motorway",
            "Vehicles should be capable of about 60 km/h to use it.",
        ),
        (
            "driving far below normal traffic speed on a motorway without a reason",
            "That is dangerous and can be unlawful if your vehicle is not suitable.",
        ),
        (
            "confusing a capability requirement with a posted minimum-speed sign",
            "The important motorway rule is that unsuitable slow vehicles may not use it.",
        ),
    ]
    for subject, correct in minimum_speed_items:
        add_variants(
            questions,
            rule_prompts(subject),
            correct,
            [
                "Any vehicle may use the motorway if it stays right.",
                "There is no need to consider vehicle capability on a motorway.",
                "The motorway minimum is always the same as the posted maximum.",
            ],
            "Dutch motorway access depends partly on whether the vehicle can safely keep up with the road type.",
            difficulty=2,
        )

    lane_items = [
        ("normal motorway lane discipline", "Keep right when possible and use the left lanes mainly for overtaking."),
        ("staying in the left lane with no reason", "Move back right when it is safe and sensible."),
        ("weaving repeatedly across motorway lanes", "Avoid it because it creates unnecessary risk."),
        ("returning after an overtake on the motorway", "Check mirrors, judge the gap, and move back smoothly."),
        ("tailgating in the left lane to force others aside", "That is unsafe and aggressive."),
        (
            "using a lane-closed signal on the motorway",
            "Leave the lane in good time and follow the overhead instructions.",
        ),
    ]
    for subject, correct in lane_items:
        add_variants(
            questions,
            rule_prompts(subject),
            correct,
            [
                "Keep left permanently to avoid lane changes.",
                "Tailgating helps traffic flow.",
                "Lane-closed signals are only advice.",
            ],
            "Motorway safety depends heavily on lane discipline, distance, and reading overhead signs.",
            difficulty=2,
        )

    sign_items = [
        ("the G1 motorway start sign", "Motorway rules start here."),
        ("the G2 motorway end sign", "Motorway rules end here."),
        ("the G3 expressway sign", "Expressway rules start here."),
        ("the G4 expressway end sign", "Expressway rules end here."),
    ]
    for subject, correct in sign_items:
        add_variants(
            questions,
            rule_prompts(subject),
            correct,
            [
                "These signs only suggest a scenic route.",
                "They are parking signs.",
                "They only apply to freight traffic.",
            ],
            "Road-type signs are essential because they change the rules that apply on that road.",
            difficulty=1,
            question_type="sign",
        )

    extra_items = [
        ("a motorway breakdown at night", "Move to a safe place if possible, warn others, and stay out of live lanes."),
        ("heavy spray from trucks on the motorway", "Increase following distance and reduce speed."),
        (
            "an approaching traffic jam on the motorway",
            "Ease off early and be ready to warn following traffic if needed.",
        ),
        ("rubbernecking past an incident on the opposite carriageway", "Keep attention on your own lane and traffic."),
    ]
    for subject, correct in extra_items:
        add_variants(
            questions,
            rule_prompts(subject),
            correct,
            [
                "Stay in the live lane after a breakdown.",
                "Spray has no effect on safety.",
                "Traffic jams are handled best by late hard braking.",
            ],
            "Motorway hazards develop quickly because speeds are high and stopping distances are long.",
            difficulty=2,
            question_type="hazard",
        )

    return finalize_topic("motorways", questions)


def build_hazard_questions():
    questions = []

    following_distance_items = [
        (
            "traffic ahead suddenly slows down on a fast road",
            "Increase your following distance so you have more reaction time.",
        ),
        (
            "you can no longer see the tyres of the vehicle ahead touching the road in town traffic",
            "You are likely too close and should create more space.",
        ),
        ("wet conditions reduce grip", "Increase following distance because stopping distance becomes longer."),
        ("a driver ahead is unpredictable", "Leave extra space and avoid sitting close behind."),
        ("tailgating to stop another driver from merging", "Do not do that; it removes your safety margin."),
        ("darkness on an unlit road", "Keep enough distance to stop within the space you can see."),
        ("a large van ahead blocks your view", "Increase distance so you can see more and react earlier."),
        ("dense motorway traffic with repeated braking", "A larger following gap reduces chain-reaction risk."),
    ]
    for context, correct in following_distance_items:
        add_variants(
            questions,
            hazard_prompts(context),
            correct,
            [
                "Move closer so others cannot merge.",
                "Ignore distance because ABS solves everything.",
                "Follow closely to read the vehicle ahead better.",
            ],
            "Following distance is one of the main tools for managing reaction time and stopping distance.",
            difficulty=2,
            question_type="hazard",
        )

    weather_items = [
        ("heavy rain reduces visibility and grip", "Slow down, increase distance, and use lights as needed."),
        ("fog makes it hard to judge distance", "Reduce speed and use the correct lights for the visibility."),
        ("snow or ice may be on the road", "Brake, steer, and accelerate gently."),
        ("strong side wind affects your lane position", "Hold the wheel firmly and reduce speed if needed."),
        (
            "spray from lorries covers your windscreen",
            "Increase distance and make sure your wipers and lights are effective.",
        ),
        ("a sun glare moment after coming out of a tunnel", "Slow slightly and create space until vision improves."),
        (
            "a wet road after the first rain following a dry period",
            "Expect reduced grip because the surface can be especially slippery.",
        ),
        ("a flooded patch of road may hide deep water", "Slow down and avoid entering it quickly."),
    ]
    for context, correct in weather_items:
        add_variants(
            questions,
            hazard_prompts(context),
            correct,
            [
                "Keep normal speed because weather changes everyone equally.",
                "Use harsh steering to test grip.",
                "Weather only matters on motorways.",
            ],
            "Bad weather changes grip, visibility, and reaction time, so safe speed is often lower than the legal maximum.",
            difficulty=2,
            question_type="hazard",
        )

    night_items = [
        ("you drive on an unlit road at night", "Adjust speed so you can stop within the distance you can see."),
        ("an oncoming vehicle dazzles you", "Look slightly to the right side of your lane and reduce speed if needed."),
        ("pedestrians in dark clothing are near the roadside", "Expect them late and lower speed early."),
        ("your windscreen reflects lights at night because it is dirty", "Clean it because dirty glass worsens glare."),
        ("fatigue combines with night driving", "Take a break instead of relying on willpower."),
        (
            "you leave a brightly lit city street for a dark rural road",
            "Give your eyes time to adapt and reduce speed if needed.",
        ),
    ]
    for context, correct in night_items:
        add_variants(
            questions,
            hazard_prompts(context),
            correct,
            [
                "Night driving changes nothing important.",
                "Dazzle is solved by speeding up past it.",
                "Pedestrians are easy to see at night on all roads.",
            ],
            "Night driving reduces sight distance and increases fatigue risk, so anticipation matters more.",
            difficulty=2,
            question_type="hazard",
        )

    skid_items = [
        (
            "your car starts to skid on a slippery surface",
            "Stay calm, look where you want to go, and avoid abrupt inputs.",
        ),
        (
            "you suspect aquaplaning because steering suddenly feels light in standing water",
            "Ease off the accelerator and avoid sudden steering or braking.",
        ),
        (
            "you enter a bend too fast on a wet road",
            "Reduce speed before the bend next time; grip is limited in the corner.",
        ),
        ("ABS activates during hard braking", "Keep braking firmly and steer if needed instead of pumping the pedal."),
        ("a rear-wheel slide begins while you panic", "Calm smooth correction works better than harsh movements."),
        ("you think electronic aids make skidding impossible", "That is wrong; they help, but physics still matters."),
    ]
    for context, correct in skid_items:
        add_variants(
            questions,
            hazard_prompts(context),
            correct,
            [
                "Brake and steer as hard as possible in random directions.",
                "Close your eyes and hold the wheel tight.",
                "Acceleration is the safest answer to every skid.",
            ],
            "Grip can disappear suddenly. Smooth inputs and earlier speed choice are central to skid prevention and recovery.",
            difficulty=3,
            question_type="hazard",
            points=2,
        )

    blind_spot_items = [
        (
            "a cyclist is next to your vehicle before you turn right",
            "Check mirrors and blind spot, then wait if needed.",
        ),
        ("a lorry is about to change lane", "Do not stay in the blind spot beside it."),
        ("you prepare to open your door on the traffic side", "Check carefully for cyclists and other traffic first."),
        ("a motorcycle may be hidden beside your rear quarter", "Use a shoulder check before moving sideways."),
        ("changing lane after overtaking", "Check mirrors and blind spots before moving back."),
        ("thinking a mirror alone shows every road user around you", "That is wrong."),
    ]
    for context, correct in blind_spot_items:
        add_variants(
            questions,
            hazard_prompts(context),
            correct,
            [
                "Blind spots disappear if your indicator is on.",
                "Only trucks have blind spots.",
                "Shoulder checks are never needed in city traffic.",
            ],
            "Blind spots are critical around cyclists, motorcycles, and lane changes.",
            difficulty=2,
            question_type="hazard",
        )

    reversing_items = [
        (
            "you reverse out of a driveway onto a pavement or road",
            "Reverse very slowly and make sure the path is truly clear.",
        ),
        ("you reverse where children may be nearby", "Get maximum observation and stop if you lose sight of the area."),
        ("you rely only on a reversing camera", "Use it as help, but still check mirrors and surroundings directly."),
        (
            "you reverse from a parking space into a busy cycle route",
            "Expect cyclists to appear quickly and keep the movement very slow.",
        ),
        (
            "you reverse because it seems easier than turning around on a narrow street",
            "Only do it if you can control the risk fully and safely.",
        ),
        ("another driver pressures you while you reverse", "Ignore the pressure and continue only at a safe pace."),
    ]
    for context, correct in reversing_items:
        add_variants(
            questions,
            hazard_prompts(context),
            correct,
            [
                "Reverse faster so you spend less time doing it.",
                "Only look through the rear window and ignore the sides.",
                "Cameras remove the need for direct observation.",
            ],
            "Reversing is a high-risk manoeuvre because observation is limited and vulnerable road users may appear suddenly.",
            difficulty=2,
            question_type="hazard",
        )

    extra_items = [
        (
            "you approach a row of parked cars near a school at home time",
            "Expect a pedestrian or cyclist to emerge unexpectedly.",
        ),
        ("a driver ahead behaves erratically", "Increase distance and avoid relying on them."),
        (
            "your own attention drifts because the road feels familiar",
            "Refocus and keep scanning because familiar roads still contain hazards.",
        ),
        ("low sun hides a crossing ahead", "Slow down and prepare for hidden road users."),
    ]
    for context, correct in extra_items:
        add_variants(
            questions,
            hazard_prompts(context),
            correct,
            [
                "Familiar roads do not need active observation.",
                "Low sun makes crossings safer because people are more visible.",
                "Erratic traffic is best handled by tailgating closely.",
            ],
            "Hazard recognition is about expecting risk before it becomes an emergency.",
            difficulty=2,
            question_type="hazard",
        )

    return finalize_topic("hazard-recognition", questions)


def build_safe_driving_questions():
    questions = []

    alcohol_items = [
        ("the normal alcohol limit for an experienced driver", "It is 0.5‰."),
        ("the lower alcohol limit for a novice driver", "It is 0.2‰."),
        ("thinking one strong drink can never affect driving", "That is wrong."),
        (
            "using alcohol and then trying to judge your own fitness honestly",
            "Alcohol reduces judgement, so self-assessment becomes less reliable.",
        ),
        (
            "driving the morning after heavy drinking",
            "You may still be impaired, so do not assume you are automatically fit to drive.",
        ),
        ("combining alcohol with fatigue", "The risk is greater because both reduce attention and reaction ability."),
    ]
    for subject, correct in alcohol_items:
        add_variants(
            questions,
            rule_prompts(subject),
            correct,
            [
                "Alcohol only matters on motorways.",
                "Coffee cancels alcohol legally.",
                "Novice drivers have the same 0.5‰ limit as everyone else.",
            ],
            "Dutch drink-driving limits are strict, and even small amounts can harm judgement and reaction time.",
            difficulty=2,
        )

    mobile_items = [
        ("holding a mobile phone while driving", "It is not allowed."),
        (
            "reading a message at a red light while still part of traffic",
            "Do not do that; distraction rules still matter.",
        ),
        (
            "using a phone that distracts your eyes and attention from the road",
            "That is dangerous even if the trip is short.",
        ),
        ("thinking hands-free use removes every distraction risk", "That is wrong; attention can still be reduced."),
    ]
    for subject, correct in mobile_items:
        add_variants(
            questions,
            rule_prompts(subject),
            correct,
            [
                "Phone rules only apply above 50 km/h.",
                "A short call while holding the phone is acceptable.",
                "Red lights create a free phone-use moment.",
            ],
            "Mobile-phone use can seriously reduce observation and reaction, so Dutch law bans holding the phone while driving.",
            difficulty=2,
        )

    seatbelt_items = [
        ("seatbelt use in a car", "Seatbelts should be worn by driver and passengers when required."),
        (
            "a child travelling in a car",
            "Use the correct child restraint or seat according to the child and legal requirements.",
        ),
        ("thinking a seatbelt is unnecessary for a short local trip", "That is wrong."),
        ("an unsecured passenger in the back seat", "That passenger still creates danger for everyone in the vehicle."),
        ("adjusting the seatbelt correctly", "It should lie properly across the body, not twisted or under the arm."),
        ("a child restraint that does not match the child's size", "Use a suitable restraint instead of improvising."),
    ]
    for subject, correct in seatbelt_items:
        add_variants(
            questions,
            rule_prompts(subject),
            correct,
            [
                "Seatbelts only matter on motorways.",
                "Children may use any adult belt in any way.",
                "Rear passengers do not influence front-seat safety.",
            ],
            "Seatbelts and child restraints greatly reduce injury risk and are basic legal safety requirements.",
            difficulty=1,
        )

    fatigue_items = [
        ("driving while very tired", "Stop and rest instead of relying on willpower."),
        ("yawning, heavy eyes, and drifting concentration", "Treat them as warnings to take a break."),
        ("opening the window to solve serious fatigue", "That is not a reliable solution."),
        (
            "a long night drive after poor sleep",
            "Plan rest or postpone the trip because fatigue seriously harms safety.",
        ),
    ]
    for subject, correct in fatigue_items:
        add_variants(
            questions,
            rule_prompts(subject),
            correct,
            [
                "Fatigue only matters if you are above the speed limit.",
                "Music completely replaces rest.",
                "Yawning is not a driving warning sign.",
            ],
            "Fatigue reduces attention, judgement, and reaction time, sometimes as badly as alcohol.",
            difficulty=2,
        )

    medication_items = [
        ("medicine that causes drowsiness", "Read the warning and do not drive if the medicine makes you unfit."),
        ("combining alcohol with medicine that affects alertness", "The risk becomes even greater."),
        (
            "illegal drugs and driving",
            "They can seriously impair judgement and control, so driving is unsafe and unlawful.",
        ),
        (
            "thinking prescription medicine is always safe for driving because a doctor prescribed it",
            "That is wrong; some medicines still impair driving.",
        ),
        ("starting new medicine before a long trip", "Check whether it affects alertness or reaction time first."),
        (
            "using stimulants to cover fatigue after taking impairing substances",
            "That does not make you safely fit to drive.",
        ),
    ]
    for subject, correct in medication_items:
        add_variants(
            questions,
            rule_prompts(subject),
            correct,
            [
                "Medicine can never affect driving if it is legal.",
                "Drugs only matter for very long trips.",
                "Alertness warnings on medicine are optional advice with no safety value.",
            ],
            "Drugs and some medicines can affect vision, reaction time, mood, and judgement.",
            difficulty=2,
        )

    aggressive_items = [
        ("tailgating to pressure another driver", "It is unsafe and aggressive."),
        ("using the horn or lights to bully slower traffic", "That is poor and unsafe driving behaviour."),
        ("responding to another driver's mistake with anger", "Stay calm and create safety instead of escalating."),
        ("treating the road as a competition", "That mindset increases risk and bad decisions."),
    ]
    for subject, correct in aggressive_items:
        add_variants(
            questions,
            rule_prompts(subject),
            correct,
            [
                "Aggressive driving saves time safely.",
                "Tailgating improves communication.",
                "Road rage is acceptable if another driver was wrong first.",
            ],
            "Safe driving depends on patience, distance, and self-control rather than anger or competition.",
            difficulty=1,
        )

    extra_items = [
        ("putting social pressure above safety", "Choose safety even if passengers want you to hurry."),
        ("driving after an emotional shock or argument", "Take time to regain concentration before driving."),
    ]
    for subject, correct in extra_items:
        add_variants(
            questions,
            rule_prompts(subject),
            correct,
            [
                "Passenger pressure changes the law.",
                "Strong emotions improve alertness safely.",
                "Only alcohol can make you unfit to drive.",
            ],
            "Safe driving depends on both legal rules and honest self-control.",
            difficulty=2,
        )

    return finalize_topic("safe-driving", questions)


def build_environmental_questions():
    questions = []

    anticipatory_items = [
        (
            "environmentally friendly anticipatory driving",
            "Look far ahead and avoid unnecessary braking and acceleration.",
        ),
        ("lifting off early when you can already see a red light ahead", "That saves fuel and often reduces wear."),
        ("keeping a bigger gap so you can drive more smoothly", "That can help both safety and fuel use."),
        ("rushing to the next queue and then braking hard", "That wastes fuel and reduces comfort."),
        (
            "thinking eco-driving always means driving very slowly everywhere",
            "That is wrong; it means smooth, appropriate driving.",
        ),
    ]
    for subject, correct in anticipatory_items:
        add_variants(
            questions,
            rule_prompts(subject),
            correct,
            [
                "Eco-driving means accelerating hard and braking late.",
                "Fuel use is only about the engine, not driving style.",
                "Anticipation has no safety benefit.",
            ],
            "Smooth anticipation reduces unnecessary speed changes, fuel use, and wear.",
            difficulty=1,
        )

    engine_braking_items = [
        (
            "using engine braking by easing off early",
            "It helps control speed smoothly and can reduce wear on the brakes.",
        ),
        ("descending a slope", "Use an appropriate gear and engine braking instead of riding the brakes constantly."),
        ("approaching a lower speed limit", "Ease off early so the car slows smoothly."),
        ("thinking engine braking means switching the engine off while moving", "That is completely wrong and unsafe."),
    ]
    for subject, correct in engine_braking_items:
        add_variants(
            questions,
            rule_prompts(subject),
            correct,
            [
                "Engine braking means braking at the last second only.",
                "It has no value on hills.",
                "It should replace all brake use in emergencies.",
            ],
            "Engine braking is about using the vehicle's resistance by easing off in good time, not by turning the engine off.",
            difficulty=2,
        )

    cruise_items = [
        ("cruise control on a quiet steady motorway section", "It can help keep a steady speed efficiently."),
        (
            "cruise control in busy stop-start traffic",
            "It is usually not the best choice because conditions change too often.",
        ),
        ("cruise control on slippery roads", "Use it cautiously or avoid it if grip is poor."),
    ]
    for subject, correct in cruise_items:
        add_variants(
            questions,
            rule_prompts(subject),
            correct,
            [
                "Cruise control is ideal in every condition.",
                "Cruise control cancels the need to observe the road.",
                "It should be used to hold maximum speed in fog.",
            ],
            "Cruise control can support efficient steady-speed driving, but it is not right for every road or weather situation.",
            difficulty=2,
        )

    tyre_pressure_items = [
        ("tyres with the correct pressure", "They improve efficiency, stability, and tyre life."),
        ("driving with tyres that are under-inflated", "Fuel use rises and handling may worsen."),
        ("checking tyre pressure only by looking at the tyres", "That is not reliable enough."),
        ("eco-driving and tyre maintenance", "Correct pressure supports lower rolling resistance and safer control."),
    ]
    for subject, correct in tyre_pressure_items:
        add_variants(
            questions,
            rule_prompts(subject),
            correct,
            [
                "Tyre pressure only matters for racing.",
                "Lower pressure always saves fuel.",
                "Pressure has no effect on tyre wear.",
            ],
            "Tyre pressure matters for both road safety and environmental efficiency.",
            difficulty=1,
        )

    speed_fuel_items = [
        ("higher speed and fuel use", "Fuel consumption usually rises as speed rises, especially at motorway pace."),
        ("keeping unnecessary extra speed on a journey", "It usually costs more fuel for limited time gain."),
        ("aggressive acceleration between lights", "It wastes fuel."),
        (
            "a calm, legal speed with smooth inputs",
            "That is generally better for fuel use than repeated hard acceleration.",
        ),
    ]
    for subject, correct in speed_fuel_items:
        add_variants(
            questions,
            rule_prompts(subject),
            correct,
            [
                "Faster driving is always more fuel efficient.",
                "Fuel use never changes with speed.",
                "Aggressive acceleration saves fuel by shortening the trip.",
            ],
            "Driving style and speed strongly affect fuel consumption.",
            difficulty=1,
        )

    extra_items = [
        ("removing unnecessary load from the car", "It can help reduce fuel use."),
        ("idling longer than needed", "It wastes fuel and creates unnecessary emissions."),
        ("planning ahead to avoid unnecessary trips", "That reduces fuel use and traffic load."),
        ("maintaining the car properly", "A well-maintained vehicle usually runs more efficiently and safely."),
    ]
    for subject, correct in extra_items:
        add_variants(
            questions,
            rule_prompts(subject),
            correct,
            [
                "Extra weight never affects fuel use.",
                "Long idling is the greenest option.",
                "Vehicle maintenance only affects comfort, not efficiency.",
            ],
            "Environmental driving is a mix of smooth behaviour, planning, and good vehicle condition.",
            difficulty=1,
        )

    return finalize_topic("environmental-driving", questions)


def build_vehicle_knowledge_questions():
    questions = []

    warning_items = [
        (
            "an oil-pressure warning light while the engine is running",
            "Stop safely and investigate because low oil pressure can damage the engine.",
        ),
        ("a battery or charging-system warning light", "The charging system may have a fault."),
        ("an engine-management warning light", "A fault may be present and should be checked."),
        ("a coolant temperature warning", "The engine may be overheating and needs attention."),
        (
            "an ABS warning light",
            "The anti-lock braking system may be faulty even though normal braking may still work.",
        ),
        (
            "a brake-system warning light",
            "There may be a brake problem or another serious issue needing immediate attention.",
        ),
        ("an airbag warning light", "The airbag or restraint system may have a fault."),
        (
            "a tyre-pressure warning light",
            "At least one tyre may have low pressure or the monitoring system may need checking.",
        ),
    ]
    for subject, correct in warning_items:
        add_variants(
            questions,
            rule_prompts(subject),
            correct,
            [
                "Warning lights are only decorative reminders.",
                "Every warning light can be ignored until the next service.",
                "All warning lights mean exactly the same thing.",
            ],
            "Dashboard warning lights give early information about faults that may affect safety or vehicle health.",
            difficulty=2,
        )

    tyre_items = [
        ("the legal minimum tread depth for car tyres", "It is 1.6 mm."),
        ("checking tyres before a long trip", "Look at pressure, tread, and visible damage."),
        ("uneven tyre wear", "It can signal a maintenance or inflation problem."),
        ("driving with badly damaged tyres", "That is unsafe and unlawful."),
        ("under-inflated tyres", "They can worsen handling and increase fuel use."),
        ("thinking tread depth only matters in winter", "That is wrong; it matters all year."),
    ]
    for subject, correct in tyre_items:
        add_variants(
            questions,
            rule_prompts(subject),
            correct,
            [
                "Tyres are legal as long as they hold air.",
                "Tread depth matters only above 100 km/h.",
                "Pressure never affects handling.",
            ],
            "Tyres are safety-critical for grip, braking, steering, and water clearance.",
            difficulty=1,
        )

    lighting_items = [
        ("using dipped headlights at night", "That is the normal lighting rule."),
        ("poor visibility in rain or fog", "Use the correct lights so you can see and be seen."),
        ("rear fog light use", "Use it only when visibility is very poor, such as about 50 metres or less."),
        ("driving with broken lights", "Fix them because working lights are a basic safety requirement."),
        ("a dirty headlamp lens", "Clean it because dirt reduces light output and visibility."),
        ("thinking front and rear fog lights should be used in every rain shower", "That is wrong."),
    ]
    for subject, correct in lighting_items:
        add_variants(
            questions,
            rule_prompts(subject),
            correct,
            [
                "Lights only matter after midnight.",
                "Rear fog lights should be used in all light rain.",
                "Broken lights only matter if the police stop you.",
            ],
            "Correct lighting helps you see hazards and helps others judge your position and speed.",
            difficulty=2,
        )

    check_items = [
        ("a basic pre-drive vehicle check", "Check tyres, lights, mirrors, windows, and warning signs of faults."),
        ("an icy windscreen before departure", "Clear all windows properly before driving."),
        ("low washer fluid in dirty weather", "Top it up because visibility matters."),
        ("ignoring a new unusual noise or smell from the car", "Investigate it instead of assuming it will disappear."),
    ]
    for subject, correct in check_items:
        add_variants(
            questions,
            rule_prompts(subject),
            correct,
            [
                "Only fuel level matters before driving.",
                "A small viewing hole in the windscreen is enough.",
                "Unusual noises never affect safety.",
            ],
            "Simple pre-drive checks can prevent breakdowns, poor visibility, and unsafe trips.",
            difficulty=1,
        )

    system_items = [
        ("ABS", "It helps prevent the wheels from locking during hard braking."),
        ("ESP or stability control", "It helps the driver maintain stability by reducing skids or unintended yaw."),
        ("traction control", "It helps reduce wheel spin when accelerating."),
        (
            "thinking ABS shortens braking distance in every condition without exception",
            "That is wrong; its main purpose is maintaining steering control during hard braking.",
        ),
        ("an ABS-equipped emergency stop", "Press the brake firmly and let the system work."),
        (
            "thinking electronic aids replace careful speed choice",
            "That is wrong; they help, but physics still applies.",
        ),
    ]
    for subject, correct in system_items:
        add_variants(
            questions,
            rule_prompts(subject),
            correct,
            [
                "Electronic aids remove the need for tyre grip.",
                "ABS means you should pump the brake pedal repeatedly.",
                "ESP is only for comfort, not safety.",
            ],
            "Vehicle safety systems are helpful, but they support the driver rather than replacing judgement and grip.",
            difficulty=2,
        )

    extra_items = [
        (
            "a cracked mirror or badly damaged windscreen in the driver's view",
            "It can harm visibility and should be fixed.",
        ),
        ("keeping the registration and safety equipment in order", "That supports legal and practical road readiness."),
    ]
    for subject, correct in extra_items:
        add_variants(
            questions,
            rule_prompts(subject),
            correct,
            [
                "Visibility defects never matter if you know the route.",
                "Vehicle readiness is only for annual inspection day.",
                "Mirrors are optional in city traffic.",
            ],
            "Vehicle knowledge is not just for maintenance; it directly supports daily road safety.",
            difficulty=1,
        )

    return finalize_topic("vehicle-knowledge", questions)


def build_questions_by_topic():
    questions_by_topic = {
        "introduction-to-dutch-driving": build_introduction_questions(),
        "road-users": build_road_user_questions(),
        "traffic-signs": build_traffic_sign_questions(),
        "basic-traffic-rules": build_basic_traffic_rule_questions(),
        "priority-rules": build_priority_rule_questions(),
        "speed-limits": build_speed_limit_questions(),
        "road-markings": build_road_marking_questions(),
        "parking-stopping": build_parking_stopping_questions(),
        "roundabouts": build_roundabout_questions(),
        "cyclists-pedestrians": build_cyclist_pedestrian_questions(),
        "motorways": build_motorway_questions(),
        "hazard-recognition": build_hazard_questions(),
        "safe-driving": build_safe_driving_questions(),
        "environmental-driving": build_environmental_questions(),
        "vehicle-knowledge": build_vehicle_knowledge_questions(),
    }
    total = sum(len(topic_questions) for topic_questions in questions_by_topic.values())
    if total < TOTAL_TARGET:
        raise ValueError(f"Expected at least {TOTAL_TARGET} questions, got {total}")
    for slug, topic_questions in questions_by_topic.items():
        expected = TOPIC_TARGETS[slug]
        if len(topic_questions) < expected:
            raise ValueError(f"Topic {slug} expected {expected} questions, got {len(topic_questions)}")
    return questions_by_topic


QUESTIONS_BY_TOPIC = build_questions_by_topic()


class Command(BaseCommand):
    help = "Add 3000+ original Dutch driving theory questions (V3)"

    @transaction.atomic
    def handle(self, *args, **options):
        total = 0
        for slug, questions in QUESTIONS_BY_TOPIC.items():
            try:
                topic = DrivingTopic.objects.only("id", "slug", "title").get(slug=slug)
            except DrivingTopic.DoesNotExist:
                self.stdout.write(f"  ⚠ Topic not found: {slug}")
                continue

            lesson = topic.lessons.filter(is_active=True).first()
            added = 0
            for q_data in questions:
                payload = {**q_data}
                options_data = payload.pop("options")
                q, created = DrivingQuestion.objects.get_or_create(
                    topic=topic,
                    question_text=payload["question_text"],
                    defaults={"lesson": lesson, **payload},
                )
                if created:
                    for opt in options_data:
                        DrivingQuestionOption.objects.create(question=q, **opt)
                    added += 1
                    total += 1

            self.stdout.write(
                f"  {slug}: {added} new questions ({len(questions)} prepared, lesson={'yes' if lesson else 'no'})"
            )

        self.stdout.write(self.style.SUCCESS(f"\n✅ Added {total} new questions total"))
