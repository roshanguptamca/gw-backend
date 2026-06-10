from django.core.management.base import BaseCommand
from django.db import transaction


def section(title, content, examples, dutch_keywords, callouts, illustration_hint):
    return {
        "title": title,
        "content": content,
        "examples": examples,
        "dutch_keywords": dutch_keywords,
        "callout_boxes": [{"type": box_type, "text": text} for box_type, text in callouts],
        "illustration_hint": illustration_hint,
    }


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
    if len(options) != 4:
        raise ValueError(f"Question '{question_text}' must have exactly 4 options.")
    if correct_index not in range(4):
        raise ValueError(f"Question '{question_text}' has an invalid correct option index.")
    return {
        "question_text": question_text,
        "explanation": explanation,
        "difficulty": difficulty,
        "question_type": question_type,
        "sign_hint": sign_hint,
        "points": points,
        "is_active": True,
        "options": [
            {
                "option_text": option_text,
                "is_correct": index == correct_index,
            }
            for index, option_text in enumerate(options)
        ],
    }


def lesson(
    title,
    summary,
    difficulty,
    estimated_minutes,
    learning_objectives,
    exam_tips,
    common_mistakes,
    key_takeaways,
    sections,
    questions,
    order=0,
):
    return {
        "title": title,
        "summary": summary,
        "difficulty": difficulty,
        "estimated_minutes": estimated_minutes,
        "learning_objectives": learning_objectives,
        "exam_tips": exam_tips,
        "common_mistakes": common_mistakes,
        "key_takeaways": key_takeaways,
        "sections": sections,
        "questions": questions,
        "order": order,
        "is_active": True,
    }


def topic(
    slug,
    title,
    summary,
    dutch_terms,
    icon,
    color_theme,
    difficulty_level,
    learning_objectives,
    exam_weight,
    order,
    lessons,
):
    return {
        "slug": slug,
        "title": title,
        "summary": summary,
        "dutch_terms": dutch_terms,
        "icon": icon,
        "color_theme": color_theme,
        "difficulty_level": difficulty_level,
        "learning_objectives": learning_objectives,
        "exam_weight": exam_weight,
        "order": order,
        "lessons": lessons,
        "is_active": True,
    }


TOPICS = [
    topic(
        slug="introduction-to-dutch-driving",
        title="Introduction to Dutch Driving",
        summary="Build a practical foundation for driving in the Netherlands, including licensing, documents, and the culture of sharing the road.",
        dutch_terms=[
            {"term": "rijbewijs", "meaning": "driving licence"},
            {"term": "bebouwde kom", "meaning": "built-up area"},
            {"term": "verkeersregels", "meaning": "traffic rules"},
            {"term": "verzekering", "meaning": "insurance"},
        ],
        icon="bi-map",
        color_theme="rgba(16,185,129,0.15)",
        difficulty_level="beginner",
        learning_objectives=[
            "Understand the basic framework of Dutch road traffic.",
            "Recognise the key documents and responsibilities of a driver.",
            "Describe the habits expected from a calm and predictable driver.",
        ],
        exam_weight=5,
        order=0,
        lessons=[
            lesson(
                title="Getting Started with Dutch Roads",
                summary="Learn the essential facts every beginner needs before studying detailed rules.",
                difficulty="easy",
                estimated_minutes=14,
                learning_objectives=[
                    "Explain how road use is organised in the Netherlands.",
                    "Identify important legal documents for driving.",
                    "Connect basic road culture with safe behaviour.",
                ],
                exam_tips=[
                    "When an answer says 'be predictable and give clear signals', it is often the safest choice.",
                    "Words like 'always' and 'never' deserve extra attention in theory questions.",
                ],
                common_mistakes=[
                    "Mixing up the legal minimum driving age with special supervised schemes.",
                    "Forgetting that cycling infrastructure strongly influences normal car driving decisions.",
                ],
                key_takeaways=[
                    "Drive on the right and expect many cyclists in every town.",
                    "Carry the correct documents and keep the vehicle legally roadworthy.",
                    "Dutch traffic culture rewards patience, observation, and smooth decisions.",
                ],
                sections=[
                    section(
                        title="Road culture and first principles",
                        content=(
                            "Drivers in the Netherlands are expected to share the road with many different users, especially cyclists, pedestrians, buses, and trams. A good driver does not only know the rules. A good driver also reads the environment and leaves space for others to make safe choices.\n\n"
                            "You normally drive on the right side of the road and overtake on the left unless a special situation allows otherwise. In towns and cities, streets may feel narrow because of cycle tracks, parked vehicles, and delivery traffic. That means a calm speed, clear signalling, and early observation are part of basic driving, even before you learn the more detailed exam topics."
                        ),
                        examples=[
                            "On a narrow residential street, you slow down early because a cyclist may move around a parked van.",
                            "At a familiar route, you still scan signs carefully because local rules can change near schools or roadworks.",
                        ],
                        dutch_keywords=["rechts rijden", "fietspad", "inhalen", "verkeersinzicht"],
                        callouts=[
                            (
                                "remember",
                                "In Dutch traffic, vulnerable road users often determine how much space and speed you should use.",
                            ),
                            (
                                "tip",
                                "If you are unsure, reduce speed first. Time gained is never worth a rushed decision.",
                            ),
                        ],
                        illustration_hint="shared-road-overview",
                    ),
                    section(
                        title="Licence, documents, and legal readiness",
                        content=(
                            "A person usually drives independently from the age of 18, although younger learners may participate in supervised driving schemes such as 2toDrive. The vehicle must be insured, registered correctly, and kept in safe condition. A driver is also responsible for being fit to drive and for checking whether lights, tyres, and mirrors are usable before a trip.\n\n"
                            "Theory study is not just about passing an exam. It helps you recognise how separate duties connect to real driving. If your view is blocked by dirt on the windows, if your insurance is not in order, or if you ignore a warning light, you create risk before the vehicle even starts moving."
                        ),
                        examples=[
                            "Before a winter trip, you remove all ice from every window instead of clearing only a small viewing hole.",
                            "You postpone a journey when you feel too tired to judge speed and distance properly.",
                        ],
                        dutch_keywords=["rijbewijs", "kenteken", "APK", "WA-verzekering"],
                        callouts=[
                            (
                                "info",
                                "A legal vehicle can still be unsafe if visibility, tyre condition, or driver fitness is poor.",
                            ),
                            (
                                "warning",
                                "Never assume that a short trip excuses missing documents or poor concentration.",
                            ),
                        ],
                        illustration_hint="licence-and-documents",
                    ),
                ],
                questions=[
                    question(
                        "Which side of the road should you normally drive on in the Netherlands?",
                        "Dutch traffic keeps to the right. This affects lane choice, turning, and overtaking habits.",
                        [
                            "The left side",
                            "The right side",
                            "The centre of the road",
                            "Any side if the road is quiet",
                        ],
                        1,
                        difficulty=1,
                        question_type="multiple_choice",
                    ),
                    question(
                        "What does the Dutch word 'rijbewijs' mean?",
                        "'Rijbewijs' is the ordinary Dutch word for a driving licence.",
                        [
                            "Registration certificate",
                            "Driving licence",
                            "Insurance paper",
                            "Road map",
                        ],
                        1,
                        difficulty=1,
                        question_type="multiple_choice",
                    ),
                    question(
                        "A learner driver is 17 years old and has completed the required supervised scheme. What is allowed?",
                        "With the supervised youth scheme, a 17-year-old may drive under the required supervision until the age for independent driving is reached.",
                        [
                            "Driving alone at any time",
                            "Driving only on motorways",
                            "Driving with an approved coach or supervisor",
                            "Driving only after dark",
                        ],
                        2,
                        difficulty=2,
                        question_type="scenario",
                    ),
                    question(
                        "Which document or obligation makes sure damage to others can be covered if you cause a crash?",
                        "Third-party motor insurance is required so damage to others is financially covered.",
                        [
                            "A parking disc",
                            "Third-party vehicle insurance",
                            "A navigation subscription",
                            "A road tax receipt in the glove box",
                        ],
                        1,
                        difficulty=1,
                        question_type="multiple_choice",
                    ),
                    question(
                        "You start driving through a city centre with many cyclists and narrow streets. What basic attitude is safest?",
                        "Busy Dutch urban roads reward early observation, patience, and predictable positioning.",
                        [
                            "Drive assertively so others adapt to you",
                            "Keep speed low and expect vulnerable road users to appear",
                            "Use the horn whenever space is tight",
                            "Stay close behind cyclists to avoid delays",
                        ],
                        1,
                        difficulty=1,
                        question_type="scenario",
                    ),
                    question(
                        "Which sign shape is reserved for a complete STOP instruction?",
                        "The octagonal shape is used for STOP so drivers can recognise it quickly.",
                        [
                            "Triangle",
                            "Circle",
                            "Octagon",
                            "Rectangle",
                        ],
                        2,
                        difficulty=1,
                        question_type="sign",
                        sign_hint="stop-octagon",
                    ),
                    question(
                        "Before a morning trip, frost still covers most of your windscreen. What should you do?",
                        "You need a clear view in all necessary directions before setting off. A small cleared patch is not enough.",
                        [
                            "Drive slowly and clear the rest later",
                            "Ask a passenger to guide you",
                            "Clear the windows properly before driving",
                            "Open the side window and begin the trip",
                        ],
                        2,
                        difficulty=1,
                        question_type="hazard",
                    ),
                    question(
                        "What is the best reason to study theory even if you already know how to control a car?",
                        "Vehicle control alone is not enough. Theory teaches road priority, sign meaning, and risk awareness.",
                        [
                            "Theory is only useful for professional drivers",
                            "Theory links rules and hazard awareness to real situations",
                            "Theory replaces practical lessons completely",
                            "Theory only matters on motorways",
                        ],
                        1,
                        difficulty=1,
                        question_type="multiple_choice",
                    ),
                    question(
                        "A dashboard symbol appears before your trip and you are not sure what it means. What is the safest approach?",
                        "Unknown warning symbols should be checked before driving because they may indicate a safety problem.",
                        [
                            "Ignore it if the engine still starts",
                            "Drive only if you stay below 30 km/h",
                            "Check the warning and solve the issue before relying on the car",
                            "Cover the light so it is less distracting",
                        ],
                        2,
                        difficulty=2,
                        question_type="sign",
                        sign_hint="dashboard-warning",
                    ),
                    question(
                        "You feel very tired after a long workday but the journey home is short. What is true?",
                        "Fitness to drive matters on every trip. Fatigue reduces attention and reaction time.",
                        [
                            "Short trips are exempt from fitness rules",
                            "Tiredness is only a problem above 80 km/h",
                            "You are still responsible for being fit to drive",
                            "Coffee removes all fatigue risk immediately",
                        ],
                        2,
                        difficulty=2,
                        question_type="hazard",
                    ),
                    question(
                        "What does 'bebouwde kom' refer to in Dutch traffic language?",
                        "'Bebouwde kom' refers to a built-up area, where urban rules such as default speed often change.",
                        [
                            "A motorway service area",
                            "A built-up area or town zone",
                            "A rural cycle path",
                            "A vehicle inspection centre",
                        ],
                        1,
                        difficulty=1,
                        question_type="multiple_choice",
                    ),
                    question(
                        "Why is predictable signalling important in the Netherlands?",
                        "Clear signalling gives cyclists, pedestrians, and other drivers time to understand your intention and react safely.",
                        [
                            "It allows you to keep higher speed in towns",
                            "It is only needed on roads with three or more lanes",
                            "It helps other road users plan around your movement safely",
                            "It replaces mirror checks",
                        ],
                        2,
                        difficulty=1,
                        question_type="scenario",
                    ),
                ],
            )
        ],
    ),
    topic(
        slug="road-users",
        title="Road Users",
        summary="Recognise how different road users behave and what extra care they may need.",
        dutch_terms=[
            {"term": "fietser", "meaning": "cyclist"},
            {"term": "bromfiets", "meaning": "moped up to 45 km/h"},
            {"term": "voetganger", "meaning": "pedestrian"},
            {"term": "tram", "meaning": "tram"},
        ],
        icon="bi-people",
        color_theme="rgba(6,182,212,0.15)",
        difficulty_level="beginner",
        learning_objectives=[
            "Identify common categories of Dutch road users.",
            "Explain why vulnerable users need extra space and time.",
            "Adapt driving to public transport and small powered vehicles.",
        ],
        exam_weight=6,
        order=1,
        lessons=[
            lesson(
                title="Recognising Other Road Users",
                summary="Learn to read the behaviour and legal position of cyclists, pedestrians, trams, and light vehicles.",
                difficulty="easy",
                estimated_minutes=15,
                learning_objectives=[
                    "Describe the needs of vulnerable road users.",
                    "Differentiate between bicycles, mopeds, and mobility devices.",
                    "Respond correctly to public transport movements.",
                ],
                exam_tips=[
                    "If the question involves a vulnerable road user, think about visibility and stopping distance first.",
                    "Look for clues such as zebra crossing, cycle track, tram stop, or bus indicator.",
                ],
                common_mistakes=[
                    "Treating a cyclist as if they can accelerate or brake like a car.",
                    "Forgetting that public transport and passengers create moving hazards around stops.",
                ],
                key_takeaways=[
                    "Cyclists and pedestrians often need the most protection.",
                    "Trams are difficult to stop quickly and deserve special care.",
                    "Different small vehicles may use different lanes, paths, or speed limits.",
                ],
                sections=[
                    section(
                        title="Vulnerable road users",
                        content=(
                            "Cyclists and pedestrians are a central part of everyday traffic in the Netherlands. They are less protected than car occupants and may react differently to weather, road surface, or obstacles. A cyclist may move sideways to avoid a drain cover or open car door. A pedestrian may hesitate, stop, or step back before crossing.\n\n"
                            "Good drivers do not expect perfect behaviour from vulnerable road users. Instead, they leave space, reduce speed, and prepare for sudden changes. This is especially important near schools, shopping streets, bus stops, and residential areas where children and older people may behave unpredictably."
                        ),
                        examples=[
                            "You keep extra distance when passing a child on a bicycle because the child may wobble unexpectedly.",
                            "Near a zebra crossing, you ease off the accelerator early even before someone steps onto the road.",
                        ],
                        dutch_keywords=["fietser", "voetganger", "zebrapad", "kwetsbare weggebruiker"],
                        callouts=[
                            ("warning", "Never rely on eye contact alone with children or distracted pedestrians."),
                            (
                                "tip",
                                "A cyclist looking over one shoulder may be preparing to turn or move around an obstacle.",
                            ),
                        ],
                        illustration_hint="cyclist-pedestrian-street",
                    ),
                    section(
                        title="Public transport and light powered vehicles",
                        content=(
                            "Road users also include buses, trams, mopeds, delivery scooters, mobility scooters, and riders on horseback. These users do not all behave like cars. Trams follow tracks and cannot swerve around danger. Buses stop frequently and re-enter traffic. Mopeds may travel faster than bicycles but are still less stable than a car.\n\n"
                            "When you meet these users, ask what limits their movement. A tram is tied to rails. A moped rider may be exposed to wind or rain. A bus may hide pedestrians crossing in front of it. Thinking this way helps you predict hazards instead of only reacting at the last second."
                        ),
                        examples=[
                            "You wait behind a tram at a stop because passengers may step directly into the road.",
                            "You avoid squeezing past a moped in a narrow lane because the rider needs balancing space.",
                        ],
                        dutch_keywords=["tram", "bus", "bromfiets", "scootmobiel"],
                        callouts=[
                            (
                                "remember",
                                "Different vehicles have different blind spots, braking ability, and lane position.",
                            ),
                            (
                                "info",
                                "A bus leaving a stop within a built-up area may require you to let it merge when the driver indicates.",
                            ),
                        ],
                        illustration_hint="tram-bus-moped",
                    ),
                ],
                questions=[
                    question(
                        "Who normally uses a dedicated cycle path marked for cyclists?",
                        "A dedicated cycle path is intended primarily for cyclists and the road users indicated by the sign.",
                        [
                            "Only cars",
                            "Cyclists",
                            "Heavy lorries only",
                            "Pedestrians only",
                        ],
                        1,
                        difficulty=1,
                        question_type="multiple_choice",
                    ),
                    question(
                        "A tram is standing at a stop and passengers are entering or leaving. What is the safest action?",
                        "Passengers may step into the road unexpectedly, so you must wait and avoid creating danger near the tram stop.",
                        [
                            "Pass quickly on the side with the most space",
                            "Wait and avoid endangering passengers",
                            "Use the horn to warn people and keep moving",
                            "Drive around the tram if your hazard lights are on",
                        ],
                        1,
                        difficulty=1,
                        question_type="scenario",
                    ),
                    question(
                        "What is a 'bromfiets' in ordinary traffic language?",
                        "A bromfiets is a moped category commonly associated with a maximum design speed around 45 km/h.",
                        [
                            "A cargo bicycle without a motor",
                            "A moped",
                            "A farm tractor",
                            "A tram carriage",
                        ],
                        1,
                        difficulty=1,
                        question_type="multiple_choice",
                    ),
                    question(
                        "You approach a zebra crossing where an older pedestrian is waiting with a walking aid. What should you expect?",
                        "Older pedestrians may need more time and may move more slowly once they begin crossing.",
                        [
                            "They will cross quickly once they see your car",
                            "They may need extra time and caution",
                            "They must always wait for you because you are faster",
                            "They cannot use a zebra crossing without a signal",
                        ],
                        1,
                        difficulty=1,
                        question_type="hazard",
                    ),
                    question(
                        "Which road user is least able to change direction freely because of the way the vehicle moves?",
                        "A tram follows rails and cannot steer around danger like a car or bicycle can.",
                        [
                            "Cyclist",
                            "Pedestrian",
                            "Tram",
                            "Moped rider",
                        ],
                        2,
                        difficulty=2,
                        question_type="multiple_choice",
                    ),
                    question(
                        "A blue sign with a white pedestrian figure usually indicates what kind of area?",
                        "This style of sign indicates a pedestrian-related facility or area, depending on the exact symbol and shape.",
                        [
                            "A pedestrian facility or area",
                            "A fuel station",
                            "A motorway lane",
                            "A no-overtaking zone",
                        ],
                        0,
                        difficulty=1,
                        question_type="sign",
                        sign_hint="pedestrian-symbol",
                    ),
                    question(
                        "Why should you give extra room when overtaking a cyclist in wind or rain?",
                        "Poor weather can make bicycle handling unstable, so extra lateral space reduces risk.",
                        [
                            "Because cyclists must always stop for cars",
                            "Because weather can make the cyclist wobble or change line",
                            "Because your mirrors are not needed in rain",
                            "Because overtaking distance only matters at night",
                        ],
                        1,
                        difficulty=2,
                        question_type="hazard",
                    ),
                    question(
                        "Within a built-up area, a bus indicates to leave a stop and merge back into traffic. What should you generally do?",
                        "A bus signalling to leave a stop within a built-up area should generally be allowed to merge safely.",
                        [
                            "Accelerate past before it moves",
                            "Let the bus merge if it is safe to do so",
                            "Block the lane so it stays behind you",
                            "Use your horn and maintain speed",
                        ],
                        1,
                        difficulty=2,
                        question_type="scenario",
                    ),
                    question(
                        "Which statement about pedestrians is correct?",
                        "Pedestrians are vulnerable and may be hard to predict, especially near crossings or parked vehicles.",
                        [
                            "Pedestrians never have priority at crossings",
                            "Pedestrians are always faster to clear the road than cyclists",
                            "Pedestrians can be hidden by parked vehicles and need anticipation",
                            "Pedestrians may only cross at traffic lights",
                        ],
                        2,
                        difficulty=1,
                        question_type="multiple_choice",
                    ),
                    question(
                        "You see a mobility scooter joining the road slowly from a side entrance. What is the main risk?",
                        "Slow acceleration and limited protection mean you should anticipate a careful, slower manoeuvre.",
                        [
                            "It will usually accelerate faster than a car",
                            "It may move slowly and need extra room",
                            "It must always reverse before entering the road",
                            "It cannot legally use any road space",
                        ],
                        1,
                        difficulty=2,
                        question_type="hazard",
                    ),
                    question(
                        "A sign showing a bicycle symbol helps you recognise what kind of road user is especially relevant there?",
                        "A bicycle symbol warns of or indicates cycling traffic, depending on the sign design.",
                        [
                            "Cyclists",
                            "Only pedestrians",
                            "Only buses",
                            "Agricultural vehicles",
                        ],
                        0,
                        difficulty=1,
                        question_type="sign",
                        sign_hint="bicycle-symbol",
                    ),
                    question(
                        "Why is it unsafe to drive close behind a bus that has just stopped?",
                        "The bus can hide crossing pedestrians, cyclists, or passengers stepping into the road ahead of it.",
                        [
                            "Because buses are not allowed to stop twice",
                            "Because the bus may hide people crossing ahead",
                            "Because following distance does not matter behind large vehicles",
                            "Because buses must always give way to you",
                        ],
                        1,
                        difficulty=2,
                        question_type="scenario",
                    ),
                ],
            )
        ],
    ),
    topic(
        slug="traffic-signs",
        title="Traffic Signs",
        summary="Recognise Dutch sign families quickly by shape, colour, and symbol so you can act without hesitation.",
        dutch_terms=[
            {"term": "waarschuwingsbord", "meaning": "warning sign"},
            {"term": "verbodsbord", "meaning": "prohibition sign"},
            {"term": "gebodsbord", "meaning": "mandatory sign"},
            {"term": "voorrangsweg", "meaning": "priority road"},
        ],
        icon="bi-sign-stop",
        color_theme="rgba(239,68,68,0.15)",
        difficulty_level="beginner",
        learning_objectives=[
            "Classify signs by shape and colour.",
            "Recognise important priority and prohibition signs.",
            "Link sign families to the action required from a driver.",
        ],
        exam_weight=15,
        order=2,
        lessons=[
            lesson(
                title="Reading Signs Efficiently",
                summary="Learn to identify signs before you can read every detail on them.",
                difficulty="easy",
                estimated_minutes=18,
                learning_objectives=[
                    "Recognise warning, prohibition, mandatory, and information signs.",
                    "Explain how background colours support meaning.",
                    "Use sign clues together with road layout and markings.",
                ],
                exam_tips=[
                    "Shape is often the fastest clue. Use it before reading the symbol.",
                    "If a sign and a road marking support each other, treat the rule as especially important.",
                ],
                common_mistakes=[
                    "Confusing a blue information sign with a blue mandatory sign.",
                    "Forgetting that temporary orange signs can override the normal route.",
                ],
                key_takeaways=[
                    "Triangle warns, red circle restricts, blue circle commands.",
                    "STOP and give-way signs control priority immediately.",
                    "Background colours can hint at road type or temporary situations.",
                ],
                sections=[
                    section(
                        title="Shapes and sign families",
                        content=(
                            "Sign recognition starts with shape. A red-bordered triangle warns of danger ahead, such as a bend, crossing, or slippery road. A red-bordered circle usually prohibits something, for example entering a street or exceeding a speed. A blue circle normally gives an instruction that must be followed, such as a required direction or a compulsory path.\n\n"
                            "Some shapes are unique enough to trigger an immediate reaction. The octagonal STOP sign means you must stop fully. The inverted red-bordered triangle means give way. The yellow diamond shows a priority road. When you recognise these shapes quickly, you save time for scanning the road itself."
                        ),
                        examples=[
                            "A red triangle with children warns you to expect a school area or crossing activity ahead.",
                            "A blue circle with a white arrow means the indicated movement is required, not optional.",
                        ],
                        dutch_keywords=["driehoek", "cirkel", "stopbord", "voorrang"],
                        callouts=[
                            ("remember", "Shape often tells you the category before the symbol confirms the detail."),
                            (
                                "tip",
                                "If you spot a priority sign, immediately think about which vehicles may expect you to yield or proceed.",
                            ),
                        ],
                        illustration_hint="sign-shapes-grid",
                    ),
                    section(
                        title="Colour and context",
                        content=(
                            "Colour gives extra information. Red is linked with danger or prohibition. Blue may indicate instruction or route information, depending on the sign shape. Green route signs are often used for major through routes, while blue backgrounds are common on motorways. Orange signs are usually temporary and are often placed during roadworks or diversions.\n\n"
                            "A sign should never be read in isolation. Look at the road layout, lane arrows, shark teeth, and the behaviour of other road users. If you see a give-way sign plus road markings and a fast flow of traffic on the crossing road, you should prepare early instead of braking sharply at the last moment."
                        ),
                        examples=[
                            "An orange detour sign tells you the normal route is temporarily changed because of works ahead.",
                            "A yellow diamond together with a wider through road confirms that traffic from side roads must usually wait for you.",
                        ],
                        dutch_keywords=["oranje omleiding", "gele ruit", "blauwe borden", "tijdelijke borden"],
                        callouts=[
                            (
                                "info",
                                "Temporary orange signs deserve immediate attention because they may change the usual route or priority pattern.",
                            ),
                            (
                                "warning",
                                "Do not follow other vehicles blindly if the sign says something different from what you expected.",
                            ),
                        ],
                        illustration_hint="priority-and-detour-signs",
                    ),
                ],
                questions=[
                    question(
                        "A red-bordered triangle with a black symbol inside is mainly a sign of what category?",
                        "Red-bordered triangles warn of a hazard or situation ahead.",
                        [
                            "Warning",
                            "Mandatory instruction",
                            "Motorway information",
                            "Parking permission",
                        ],
                        0,
                        difficulty=1,
                        question_type="sign",
                        sign_hint="warning-triangle",
                    ),
                    question(
                        "What does a circular sign with a red border usually show?",
                        "Red-bordered circles usually indicate a prohibition or restriction.",
                        [
                            "A tourist route",
                            "A prohibition or restriction",
                            "A recommended speed only",
                            "A bus timetable",
                        ],
                        1,
                        difficulty=1,
                        question_type="sign",
                        sign_hint="red-circle",
                    ),
                    question(
                        "A blue circular sign with a white symbol indicates what kind of message?",
                        "Blue circular signs generally give mandatory instructions.",
                        [
                            "A warning that you may ignore if the road is empty",
                            "A mandatory instruction",
                            "A temporary diversion",
                            "A prohibition on pedestrians only",
                        ],
                        1,
                        difficulty=1,
                        question_type="sign",
                        sign_hint="blue-circle",
                    ),
                    question(
                        "You see a red octagonal sign before an intersection. What must you do?",
                        "The STOP sign requires a complete stop before proceeding when safe.",
                        [
                            "Only slow down if you see traffic",
                            "Stop completely",
                            "Keep moving if you are on time pressure",
                            "Use your hazard lights and continue",
                        ],
                        1,
                        difficulty=1,
                        question_type="scenario",
                        sign_hint="stop-octagon",
                    ),
                    question(
                        "What colour background is commonly used on Dutch motorway direction signs?",
                        "Motorway direction signs commonly use a blue background.",
                        [
                            "Blue",
                            "Pink",
                            "Brown",
                            "White with red border",
                        ],
                        0,
                        difficulty=1,
                        question_type="multiple_choice",
                    ),
                    question(
                        "A yellow diamond sign on your route tells you what?",
                        "The yellow diamond indicates that you are on a priority road.",
                        [
                            "You are entering a pedestrian zone",
                            "You are on a priority road",
                            "Parking is free on both sides",
                            "The road is closed ahead",
                        ],
                        1,
                        difficulty=1,
                        question_type="sign",
                        sign_hint="priority-diamond",
                    ),
                    question(
                        "An inverted red-bordered triangle means you should do what?",
                        "This sign means give way to traffic on the crossing road.",
                        [
                            "Accelerate through the junction",
                            "Give way",
                            "Turn around immediately",
                            "Only stop for buses",
                        ],
                        1,
                        difficulty=1,
                        question_type="sign",
                        sign_hint="give-way-triangle",
                    ),
                    question(
                        "Roadworks have changed your normal route. Which sign colour deserves special attention for this temporary situation?",
                        "Orange signs are commonly used for temporary instructions and diversions.",
                        [
                            "Orange",
                            "Purple",
                            "Silver",
                            "Black only",
                        ],
                        0,
                        difficulty=1,
                        question_type="scenario",
                    ),
                    question(
                        "You follow another driver into a street, but you now notice a red circle with a white horizontal bar facing you. What is true?",
                        "The sign means no entry from your direction, even if another driver made a mistake.",
                        [
                            "You may continue slowly because one car already went in",
                            "You may continue if no one is coming out",
                            "You must not enter from this direction",
                            "The sign only applies at night",
                        ],
                        2,
                        difficulty=2,
                        question_type="hazard",
                        sign_hint="no-entry",
                    ),
                    question(
                        "Why is it useful to recognise the sign shape before reading the symbol?",
                        "Shape gives a quick first warning or instruction, which helps when time is limited.",
                        [
                            "Because symbols do not matter on Dutch roads",
                            "Because shape gives an early clue to the sign category",
                            "Because colours are always hidden in bad weather",
                            "Because all signs have the same legal meaning",
                        ],
                        1,
                        difficulty=1,
                        question_type="multiple_choice",
                    ),
                    question(
                        "A lane sign above your lane shows a downward green arrow. What does that usually tell you?",
                        "A green arrow above a lane usually indicates that the lane is open for use.",
                        [
                            "The lane is closed ahead",
                            "The lane is open to use",
                            "You must stop under the sign",
                            "Only police may use the lane",
                        ],
                        1,
                        difficulty=2,
                        question_type="sign",
                        sign_hint="lane-green-arrow",
                    ),
                    question(
                        "You see warning and give-way signs together before a busy crossing. What is the safest response?",
                        "Combined signs should lead to early speed reduction and strong preparation to yield.",
                        [
                            "Increase speed so you pass before others arrive",
                            "Prepare early and be ready to give way",
                            "Ignore the warning if the road looks wide",
                            "Move to the centre of the road to show confidence",
                        ],
                        1,
                        difficulty=2,
                        question_type="hazard",
                    ),
                ],
            )
        ],
    ),
    topic(
        slug="basic-traffic-rules",
        title="Basic Traffic Rules",
        summary="Understand the everyday rules that guide lane use, signalling, overtaking, and behaviour at simple intersections.",
        dutch_terms=[
            {"term": "rechts voor links", "meaning": "priority from the right"},
            {"term": "richting aangeven", "meaning": "to signal direction"},
            {"term": "inhalen", "meaning": "overtaking"},
            {"term": "kruispunt", "meaning": "intersection"},
        ],
        icon="bi-clipboard-check",
        color_theme="rgba(251,146,60,0.15)",
        difficulty_level="beginner",
        learning_objectives=[
            "Apply the most common everyday driving rules.",
            "Use indicators, mirrors, and positioning correctly.",
            "Recognise when overtaking or turning is unsafe.",
        ],
        exam_weight=10,
        order=3,
        lessons=[
            lesson(
                title="Everyday Rules in Motion",
                summary="Practice the core rules that appear again and again in Dutch theory questions.",
                difficulty="easy",
                estimated_minutes=18,
                learning_objectives=[
                    "Apply basic priority at equal intersections.",
                    "Recognise safe overtaking conditions.",
                    "Describe the correct sequence for turning and changing direction.",
                ],
                exam_tips=[
                    "At a plain intersection with no signs, think right-before-left unless another rule clearly applies.",
                    "When changing position, the safe order is mirrors, signal, check, then move.",
                ],
                common_mistakes=[
                    "Assuming a wider road automatically gives priority.",
                    "Treating a solid line as a suggestion instead of a clear restriction.",
                ],
                key_takeaways=[
                    "Use clear signals and mirror checks before moving sideways or turning.",
                    "Do not overtake where visibility, markings, or road users make it unsafe.",
                    "At equal intersections, traffic from the right usually has priority.",
                ],
                sections=[
                    section(
                        title="Intersections, turning, and signals",
                        content=(
                            "Many basic rules are really about communication. Before turning, changing lane, or leaving the kerb, you must observe, signal in time, and position the vehicle clearly. Signals do not create priority on their own. They tell others what you plan to do, so they must be combined with mirror checks and a final look for cyclists, pedestrians, and traffic in blind spots.\n\n"
                            "At simple equal intersections, priority from the right applies unless signs or markings say otherwise. This rule seems simple, but it becomes harder when the street is narrow, visibility is limited, or one road feels more important. The exam often checks whether you can ignore appearances and follow the actual rule."
                        ),
                        examples=[
                            "You signal before turning right, but still wait because a cyclist is alongside on the cycle track.",
                            "At a small residential crossroads with no signs, you yield to a van approaching from your right.",
                        ],
                        dutch_keywords=["richting aangeven", "spiegels", "blind spot", "rechts voor links"],
                        callouts=[
                            (
                                "tip",
                                "A signal is a message, not permission. Always check if the movement is truly safe.",
                            ),
                            (
                                "remember",
                                "Priority from the right applies at equal roads, even when one road looks wider.",
                            ),
                        ],
                        illustration_hint="basic-junction-turn",
                    ),
                    section(
                        title="Overtaking and road position",
                        content=(
                            "Overtaking requires more than a speed advantage. You need enough sight distance, a legal road marking, and confidence that no one ahead will turn, change lane, or meet you from the opposite direction. A solid centre line is a strong signal that overtaking is not allowed because crossing that line creates extra risk.\n\n"
                            "Normal lane discipline is also part of basic rule knowledge. You should drive predictably, avoid weaving, and return to the proper lane after overtaking when it is safe. On narrower roads, simply waiting behind a slower road user is often the mature and correct decision."
                        ),
                        examples=[
                            "You stay behind a cyclist near a pedestrian crossing because overtaking there could endanger crossing traffic.",
                            "You do not cross a solid white centre line even though the opposite lane looks empty.",
                        ],
                        dutch_keywords=["inhalen", "doorgetrokken streep", "rijstrook", "positie"],
                        callouts=[
                            ("warning", "If you cannot see far enough ahead, you cannot judge overtaking safely."),
                            ("info", "Good drivers often show skill by waiting, not by forcing an overtake."),
                        ],
                        illustration_hint="solid-line-overtake",
                    ),
                ],
                questions=[
                    question(
                        "At an intersection with no signs or markings, who normally has priority?",
                        "At equal intersections, traffic from the right normally has priority.",
                        [
                            "Traffic from the right",
                            "The largest vehicle",
                            "Traffic going straight only",
                            "Whoever reaches the centre first",
                        ],
                        0,
                        difficulty=1,
                        question_type="multiple_choice",
                    ),
                    question(
                        "You want to turn left. What should come before moving across the road?",
                        "A safe turn needs observation, signalling, and a final check for other road users.",
                        [
                            "Turn first and signal midway through the turn",
                            "Check mirrors, signal, observe again, then turn when safe",
                            "Only look in the interior mirror",
                            "Sound the horn and move across quickly",
                        ],
                        1,
                        difficulty=1,
                        question_type="scenario",
                    ),
                    question(
                        "When is overtaking clearly not permitted?",
                        "A solid white centre line indicates you must not cross to overtake.",
                        [
                            "When the weather is dry",
                            "When there is a broken line",
                            "When a solid white centre line is present",
                            "When the vehicle ahead is a bicycle",
                        ],
                        2,
                        difficulty=1,
                        question_type="multiple_choice",
                    ),
                    question(
                        "Why does using your indicator not automatically give you priority?",
                        "A signal informs others of your intention, but you must still yield when required and move only when safe.",
                        [
                            "Because indicators are optional on weekdays",
                            "Because a signal only communicates intention and does not create right of way",
                            "Because indicators only matter on motorways",
                            "Because signalling transfers responsibility to others",
                        ],
                        1,
                        difficulty=2,
                        question_type="multiple_choice",
                    ),
                    question(
                        "You are driving on a narrow street and want to pass a parked van. What should you check carefully?",
                        "Parked vans can hide cyclists, pedestrians, or oncoming traffic, so visibility is critical.",
                        [
                            "Only your fuel level",
                            "Whether the opposite side is clear and whether hidden users may appear",
                            "Whether your radio volume is low",
                            "Whether the van has Dutch number plates",
                        ],
                        1,
                        difficulty=2,
                        question_type="hazard",
                    ),
                    question(
                        "A sign showing a red-bordered circle with two cars side by side usually warns about what kind of rule?",
                        "This sign family is used for overtaking restrictions.",
                        [
                            "Mandatory parking",
                            "No overtaking or an overtaking restriction",
                            "A pedestrian zone",
                            "A minimum speed",
                        ],
                        1,
                        difficulty=2,
                        question_type="sign",
                        sign_hint="no-overtaking",
                    ),
                    question(
                        "You are about to leave the kerb after parking. Who must you watch for first?",
                        "When moving off, you must give way to road users already on the carriageway and on nearby cycle facilities.",
                        [
                            "Only vehicles behind you",
                            "Road users already using the road, including cyclists",
                            "Only traffic coming from the left",
                            "Only pedestrians on the opposite pavement",
                        ],
                        1,
                        difficulty=2,
                        question_type="scenario",
                    ),
                    question(
                        "Why is late signalling a problem?",
                        "Late signalling gives others too little time to understand and react to your intended movement.",
                        [
                            "Because late signals are brighter",
                            "Because it reduces predictability for others",
                            "Because it saves battery power",
                            "Because it makes overtaking easier",
                        ],
                        1,
                        difficulty=1,
                        question_type="multiple_choice",
                    ),
                    question(
                        "At a quiet junction you intend to go straight on, but a car arrives from your right. What do you do?",
                        "At an equal-priority junction, the car from your right normally goes first.",
                        [
                            "Continue because going straight always wins",
                            "Yield to the car from the right",
                            "Take priority because you arrived earlier",
                            "Use your horn and continue",
                        ],
                        1,
                        difficulty=1,
                        question_type="scenario",
                    ),
                    question(
                        "What is the main danger of overtaking near a junction or crossing point?",
                        "Other road users may turn, cross, or appear unexpectedly, leaving little time or space to react.",
                        [
                            "Your fuel use will always rise",
                            "Hidden turning or crossing traffic can create sudden conflict",
                            "Road signs become invalid near junctions",
                            "The indicator will not work there",
                        ],
                        1,
                        difficulty=2,
                        question_type="hazard",
                    ),
                    question(
                        "Which road marking tells you crossing into the other lane is especially restricted?",
                        "A solid line shows a stronger legal and safety restriction than a broken line.",
                        [
                            "A solid white line",
                            "A broken white line",
                            "A parking bay line",
                            "A bicycle symbol",
                        ],
                        0,
                        difficulty=1,
                        question_type="sign",
                        sign_hint="solid-centre-line",
                    ),
                    question(
                        "You plan to turn right across a cycle track. What is an essential final check?",
                        "A cyclist may be alongside or in your blind spot, especially in urban areas.",
                        [
                            "Check only the navigation screen",
                            "Make a final check for cyclists on the right and in the blind spot",
                            "Assume no cyclist will pass on your right",
                            "Use the horn instead of checking",
                        ],
                        1,
                        difficulty=2,
                        question_type="hazard",
                    ),
                ],
            )
        ],
    ),
    topic(
        slug="priority-rules",
        title="Priority Rules",
        summary="Master the Dutch right-of-way system at priority roads, give-way situations, crossings, and mixed traffic points.",
        dutch_terms=[
            {"term": "voorrang", "meaning": "right of way"},
            {"term": "haaientanden", "meaning": "shark teeth give-way markings"},
            {"term": "voorrangsweg", "meaning": "priority road"},
            {"term": "gelijkwaardig", "meaning": "equal priority"},
        ],
        icon="bi-arrow-up-circle",
        color_theme="rgba(251,191,36,0.15)",
        difficulty_level="intermediate",
        learning_objectives=[
            "Apply right-of-way rules in layered situations.",
            "Use signs and markings to resolve conflicting movement.",
            "Separate priority rules from assumptions about size or speed.",
        ],
        exam_weight=12,
        order=4,
        lessons=[
            lesson(
                title="Who Goes First?",
                summary="Work through the rules that decide priority at roads, crossings, and turning movements.",
                difficulty="medium",
                estimated_minutes=18,
                learning_objectives=[
                    "Use give-way and priority-road clues correctly.",
                    "Recognise when turning traffic must wait.",
                    "Deal with trams and vulnerable road users in priority questions.",
                ],
                exam_tips=[
                    "List the clues in order: signs, markings, special road users, then basic equal-road rules.",
                    "If someone is turning, check whether they must also yield to crossing pedestrians or cyclists.",
                ],
                common_mistakes=[
                    "Assuming the main road is always obvious without checking signs.",
                    "Forgetting that a tram can override an otherwise simple right-before-left situation.",
                ],
                key_takeaways=[
                    "Priority signs and shark teeth override appearances.",
                    "Turning traffic often has extra duties toward crossing users.",
                    "Never give yourself priority because your vehicle is larger or faster.",
                ],
                sections=[
                    section(
                        title="Signs, markings, and priority roads",
                        content=(
                            "Priority rules become easier when you read the strongest clue first. Signs such as STOP, give way, and priority road usually answer the question before you look at anything else. Shark teeth on the road surface mean the same as a give-way sign: you must let traffic on the road you are entering proceed first.\n\n"
                            "A priority road continues to give its users right of way over side roads until the priority ends. However, priority never removes the duty to observe carefully. A driver on a priority road should still anticipate mistakes from others, especially where visibility is poor or where cyclists cross near the junction."
                        ),
                        examples=[
                            "You remain cautious on a priority road because a driver from a side street may misread the junction.",
                            "You stop at shark teeth before crossing a cycle track and joining the main carriageway.",
                        ],
                        dutch_keywords=["voorrangsweg", "haaientanden", "verleen voorrang", "stop"],
                        callouts=[
                            ("remember", "Shark teeth are not decoration. They are a clear order to give way."),
                            ("tip", "When you see a yellow diamond, keep scanning for where that priority may end."),
                        ],
                        illustration_hint="priority-road-junction",
                    ),
                    section(
                        title="Priority while turning and crossing",
                        content=(
                            "Priority questions often include more than one conflict. A car may have priority over another car yet still need to wait for a cyclist crossing the road it is turning into. Turning movements create a wider area of responsibility because you cross the path of different users during the manoeuvre.\n\n"
                            "Trams deserve special attention because they are hard to stop and follow fixed rails. Pedestrians at crossings, cyclists on adjacent tracks, and buses re-entering traffic all add layers to what looks like a simple junction. The safest driver resolves every conflict in a calm order instead of rushing because the answer appears obvious."
                        ),
                        examples=[
                            "You are allowed to enter a junction first, but you still wait mid-turn until a cyclist clears the crossing line.",
                            "At an equal intersection, you give way to the tram even when it approaches from the left.",
                        ],
                        dutch_keywords=["afslaand verkeer", "tram", "fietsoversteek", "kruisen"],
                        callouts=[
                            ("warning", "Having priority does not justify forcing another road user to brake sharply."),
                            (
                                "info",
                                "Turning right or left often creates extra crossing conflicts that must be checked separately.",
                            ),
                        ],
                        illustration_hint="turning-cyclist-priority",
                    ),
                ],
                questions=[
                    question(
                        "A car is on a signed priority road. Another car approaches from the right on a minor road without priority. Who normally goes first?",
                        "The signed priority road takes precedence over the side road, even if the side road is on the right.",
                        [
                            "The car on the priority road",
                            "The car from the right on the minor road",
                            "Both must reverse",
                            "The smaller vehicle",
                        ],
                        0,
                        difficulty=1,
                        question_type="multiple_choice",
                    ),
                    question(
                        "What do shark teeth painted across your lane mean?",
                        "Shark teeth indicate that you must give way to the traffic on the road you are entering or crossing.",
                        [
                            "You have priority if you signal",
                            "You must give way",
                            "Parking is prohibited",
                            "The road surface is slippery",
                        ],
                        1,
                        difficulty=1,
                        question_type="sign",
                        sign_hint="shark-teeth",
                    ),
                    question(
                        "You are turning right into a side street. A cyclist is crossing the entrance of that street. What should you do?",
                        "Turning traffic must be alert for cyclists crossing the road being entered and wait if necessary.",
                        [
                            "Turn quickly before the cyclist reaches the crossing",
                            "Wait for the cyclist if your turn would cut across their path",
                            "Use the horn and continue because you are motor traffic",
                            "Ignore the cyclist if there is no zebra crossing",
                        ],
                        1,
                        difficulty=2,
                        question_type="scenario",
                    ),
                    question(
                        "At an equal intersection, a tram approaches from your left. What is generally correct?",
                        "Trams generally have priority over other road users because of their operating limitations.",
                        [
                            "You go first because the tram is on the left",
                            "The tram goes first",
                            "You and the tram must stop and wave",
                            "The rule depends only on vehicle size",
                        ],
                        1,
                        difficulty=2,
                        question_type="scenario",
                    ),
                    question(
                        "Why can a turning manoeuvre create more than one priority decision?",
                        "Turning may bring you across the path of vehicles, cyclists, and pedestrians in sequence.",
                        [
                            "Because turning removes all normal road rules",
                            "Because you may cross several traffic streams during one movement",
                            "Because signals create priority one second later",
                            "Because turning is only allowed on priority roads",
                        ],
                        1,
                        difficulty=2,
                        question_type="multiple_choice",
                    ),
                    question(
                        "You have a give-way sign but the main road looks empty except for a fast cyclist on a parallel crossing. What is safest?",
                        "You still need to check the full conflict area. Fast cyclists can arrive sooner than expected.",
                        [
                            "Proceed immediately because the main carriageway is empty",
                            "Wait until the cyclist and any other conflicting traffic are no longer affected",
                            "Block the cycle crossing to judge speed better",
                            "Only check for cars, not cyclists",
                        ],
                        1,
                        difficulty=3,
                        question_type="hazard",
                    ),
                    question(
                        "What does a yellow diamond sign show?",
                        "The yellow diamond means priority road.",
                        [
                            "Hospital nearby",
                            "Priority road",
                            "Minimum speed",
                            "Danger of side wind",
                        ],
                        1,
                        difficulty=1,
                        question_type="sign",
                        sign_hint="priority-diamond",
                    ),
                    question(
                        "You approach a STOP sign with good visibility and no traffic in sight. Must you stop fully?",
                        "Yes. A STOP sign requires a complete stop, regardless of how quiet the road seems.",
                        [
                            "No, slowing is enough when visibility is good",
                            "Yes, you must stop completely",
                            "No, only buses must stop fully",
                            "Only if another driver flashes headlights",
                        ],
                        1,
                        difficulty=1,
                        question_type="scenario",
                    ),
                    question(
                        "Why is it wrong to claim priority just because your road looks wider?",
                        "Priority comes from rules, signs, and markings, not from how important a road appears.",
                        [
                            "Because wide roads are for parking only",
                            "Because road width alone does not decide right of way",
                            "Because narrow roads always have priority",
                            "Because only colour of buildings matters",
                        ],
                        1,
                        difficulty=1,
                        question_type="multiple_choice",
                    ),
                    question(
                        "A car on your left has a give-way sign, but it starts to roll forward. What should you anticipate?",
                        "Even when you have priority, you should be ready for another road user to make a mistake.",
                        [
                            "Continue without preparing because you are right",
                            "Be ready to slow or stop because the other driver may fail to yield",
                            "Look away to avoid confusion",
                            "Accelerate to teach the other driver a lesson",
                        ],
                        1,
                        difficulty=2,
                        question_type="hazard",
                    ),
                    question(
                        "At an equal crossroads, vehicle A is from your right and vehicle B is straight ahead from the opposite side. Which vehicle affects your priority first?",
                        "Traffic from the right is the primary equal-road priority conflict for you.",
                        [
                            "Vehicle A from your right",
                            "Vehicle B from straight ahead only",
                            "Neither, because you may go first",
                            "Only the largest vehicle",
                        ],
                        0,
                        difficulty=2,
                        question_type="scenario",
                    ),
                    question(
                        "What is the safest mindset when you technically have priority?",
                        "Priority is a legal position, not a shield against crashes. You must still avoid danger where possible.",
                        [
                            "Use your priority to maintain speed at all costs",
                            "Proceed carefully and remain ready for errors from others",
                            "Ignore cyclists because you are legally correct",
                            "Use the horn instead of observation",
                        ],
                        1,
                        difficulty=2,
                        question_type="hazard",
                    ),
                ],
            )
        ],
    ),
    topic(
        slug="speed-limits",
        title="Speed Limits",
        summary="Learn Dutch speed environments and how road type, area, signs, and conditions affect the safe and legal maximum speed.",
        dutch_terms=[
            {"term": "maximumsnelheid", "meaning": "maximum speed"},
            {"term": "30-zone", "meaning": "30 km/h zone"},
            {"term": "autosnelweg", "meaning": "motorway"},
            {"term": "autoweg", "meaning": "expressway or motor road"},
        ],
        icon="bi-speedometer2",
        color_theme="rgba(239,68,68,0.15)",
        difficulty_level="intermediate",
        learning_objectives=[
            "Recall common Dutch default speed limits.",
            "Distinguish between road types and local zones.",
            "Adjust actual speed when conditions make the limit unsafe.",
        ],
        exam_weight=10,
        order=5,
        lessons=[
            lesson(
                title="Choosing the Right Speed",
                summary="Understand how legal limits and safe speed work together.",
                difficulty="medium",
                estimated_minutes=16,
                learning_objectives=[
                    "State important default limits for common Dutch roads.",
                    "Recognise how zone signs override expectation.",
                    "Reduce speed appropriately for visibility and traffic conditions.",
                ],
                exam_tips=[
                    "Learn the default limits, then watch for the signs that change them.",
                    "The legal limit is a maximum, not a target when conditions are poor.",
                ],
                common_mistakes=[
                    "Treating a motorway number as valid in all weather and traffic conditions.",
                    "Mixing up the built-up area default with special 30-zones.",
                ],
                key_takeaways=[
                    "Know the defaults, but always obey the latest local sign.",
                    "A lower safe speed may be necessary in rain, darkness, or congestion.",
                    "Zones are designed for environment and risk, not only traffic flow.",
                ],
                sections=[
                    section(
                        title="Default limits and common zones",
                        content=(
                            "Dutch roads use a combination of default speed rules and local signs. In built-up areas, the common default maximum is 50 km/h unless a different zone or sign applies. Residential 30-zones are common where there are homes, schools, frequent crossings, and vulnerable road users. Outside built-up areas, limits depend on road type, design, and signs.\n\n"
                            "Motorways and motor roads have their own signed environments, and the posted maximum may vary by place and time. That is why theory questions often test whether you can combine category knowledge with the actual sign you most recently passed. The correct answer is never based on memory of a different road."
                        ),
                        examples=[
                            "After entering a signed 30-zone, you follow 30 km/h even if the street feels wide and open.",
                            "You remain alert for a lower temporary speed near roadworks on a road that is usually faster.",
                        ],
                        dutch_keywords=["50 km/h", "30-zone", "autosnelweg", "bebouwde kom"],
                        callouts=[
                            (
                                "remember",
                                "The last valid sign and the road category together determine the legal maximum.",
                            ),
                            (
                                "tip",
                                "When entering a town, look early for the built-up area sign because it changes several rules at once.",
                            ),
                        ],
                        illustration_hint="speed-zone-signs",
                    ),
                    section(
                        title="Legal speed versus safe speed",
                        content=(
                            "A posted limit tells you the highest speed normally allowed, not the speed you must maintain. If visibility is poor, traffic is dense, or the road is wet, the safe speed may be lower. Good drivers choose a speed that leaves enough time to observe, brake, and respond.\n\n"
                            "This difference is important in theory exam questions. A road may legally allow one speed in perfect conditions, but the safest answer becomes much lower if there is fog, ice, children near the road, or a vehicle reversing from a driveway. Safety always comes before the wish to keep pace with traffic behind you."
                        ),
                        examples=[
                            "In heavy rain on a motorway, you slow down well below the posted maximum because spray reduces visibility.",
                            "Near a school at closing time, you drive below the legal limit because children may step into the street suddenly.",
                        ],
                        dutch_keywords=["weersomstandigheden", "zicht", "remsafstand", "veilige snelheid"],
                        callouts=[
                            (
                                "warning",
                                "Driving at the maximum can still be dangerous if you cannot stop within the distance you can see.",
                            ),
                            (
                                "info",
                                "Examiners often reward the safer adjusted speed rather than the highest legal number.",
                            ),
                        ],
                        illustration_hint="wet-road-speed",
                    ),
                ],
                questions=[
                    question(
                        "What is the usual default maximum speed in a built-up area unless signs show otherwise?",
                        "The common default maximum in a built-up area is 50 km/h unless a local rule changes it.",
                        [
                            "30 km/h",
                            "40 km/h",
                            "50 km/h",
                            "70 km/h",
                        ],
                        2,
                        difficulty=1,
                        question_type="multiple_choice",
                    ),
                    question(
                        "What maximum speed normally applies in a signed 30-zone?",
                        "A 30-zone sets a maximum of 30 km/h throughout the zone until it ends.",
                        [
                            "20 km/h",
                            "30 km/h",
                            "50 km/h",
                            "60 km/h",
                        ],
                        1,
                        difficulty=1,
                        question_type="sign",
                        sign_hint="speed-30-zone",
                    ),
                    question(
                        "You are on a Dutch motorway during the day and there are no lower posted limits. What maximum is commonly expected?",
                        "On many Dutch motorways, 100 km/h is the daytime maximum unless signs indicate otherwise.",
                        [
                            "80 km/h",
                            "90 km/h",
                            "100 km/h",
                            "160 km/h",
                        ],
                        2,
                        difficulty=1,
                        question_type="multiple_choice",
                    ),
                    question(
                        "Why might you choose a speed lower than the posted maximum on a wet road?",
                        "Rain increases stopping distance and may reduce visibility, so the safe speed can be lower than the legal maximum.",
                        [
                            "Because the law bans all driving in rain",
                            "Because the safe speed may be lower in poor conditions",
                            "Because the speedometer stops working in rain",
                            "Because lane markings become irrelevant",
                        ],
                        1,
                        difficulty=1,
                        question_type="hazard",
                    ),
                    question(
                        "You pass a sign marking the start of a built-up area. What should you think immediately?",
                        "Entering a built-up area affects the default speed environment and the presence of vulnerable road users.",
                        [
                            "Motorway rules now apply",
                            "Urban rules such as the built-up area default now apply unless another sign changes them",
                            "You may ignore pedestrians",
                            "The road becomes a priority road automatically",
                        ],
                        1,
                        difficulty=2,
                        question_type="sign",
                        sign_hint="built-up-area",
                    ),
                    question(
                        "A road is normally 50 km/h, but dense fog leaves only a short visible distance. What is correct?",
                        "You must reduce speed to match the limited visibility even if the legal limit is higher.",
                        [
                            "Stay at 50 km/h because that is the legal maximum",
                            "Drive at a lower speed that matches the visibility",
                            "Only use the horn instead of slowing down",
                            "Increase speed so you spend less time in fog",
                        ],
                        1,
                        difficulty=2,
                        question_type="hazard",
                    ),
                    question(
                        "What is the main purpose of a low-speed zone near homes or schools?",
                        "These zones reduce risk where people may cross, play, or appear unexpectedly.",
                        [
                            "To test engine power",
                            "To reduce risk for residents and vulnerable road users",
                            "To help drivers arrive later",
                            "To reserve space for trucks only",
                        ],
                        1,
                        difficulty=1,
                        question_type="multiple_choice",
                    ),
                    question(
                        "If a temporary roadworks sign shows a lower speed than the normal road limit, which speed applies?",
                        "The temporary roadworks sign overrides the usual expectation for that location.",
                        [
                            "The highest number you know from memory",
                            "The temporary lower speed on the sign",
                            "The speed chosen by the vehicle behind you",
                            "The speed for the next town",
                        ],
                        1,
                        difficulty=1,
                        question_type="scenario",
                    ),
                    question(
                        "You are driving at the legal limit, but children are playing near parked cars. What is safest?",
                        "The legal limit is not always the safest speed when children may run out unexpectedly.",
                        [
                            "Maintain the limit because you are legally protected",
                            "Reduce speed and prepare to stop",
                            "Move closer to the centre line and continue",
                            "Sound the horn continuously instead of slowing",
                        ],
                        1,
                        difficulty=2,
                        question_type="hazard",
                    ),
                    question(
                        "A red-bordered circular sign with '50' inside tells you what?",
                        "This sign sets a maximum speed of 50 km/h.",
                        [
                            "Minimum speed 50 km/h",
                            "Advised speed 50 km/h",
                            "Maximum speed 50 km/h",
                            "Distance to town 50 km",
                        ],
                        2,
                        difficulty=1,
                        question_type="sign",
                        sign_hint="speed-50",
                    ),
                    question(
                        "Why is copying the speed of surrounding traffic not always correct?",
                        "Other drivers may be speeding or may have noticed conditions differently. You remain responsible for your own speed choice.",
                        [
                            "Because you must always drive slower than everyone else",
                            "Because you are responsible for obeying signs and conditions yourself",
                            "Because surrounding traffic decides the law",
                            "Because convoy driving is always illegal",
                        ],
                        1,
                        difficulty=2,
                        question_type="multiple_choice",
                    ),
                    question(
                        "A fast road becomes crowded and the flow starts compressing. What hazard does keeping the old speed create?",
                        "Crowded traffic reduces space and reaction time, so keeping a higher speed increases crash risk.",
                        [
                            "It improves braking distance",
                            "It can leave too little time to react to sudden slowing",
                            "It makes signs easier to read",
                            "It gives priority over merging traffic",
                        ],
                        1,
                        difficulty=2,
                        question_type="hazard",
                    ),
                ],
            )
        ],
    ),
    topic(
        slug="road-markings",
        title="Road Markings",
        summary="Interpret lines, symbols, and kerb markings so you can understand lane use, overtaking rules, and stopping restrictions.",
        dutch_terms=[
            {"term": "doorgetrokken streep", "meaning": "solid line"},
            {"term": "onderbroken streep", "meaning": "broken line"},
            {"term": "haaientanden", "meaning": "shark teeth"},
            {"term": "gele streep", "meaning": "yellow line"},
        ],
        icon="bi-layout-three-columns",
        color_theme="rgba(99,102,241,0.15)",
        difficulty_level="intermediate",
        learning_objectives=[
            "Read lane and edge markings correctly.",
            "Use markings to support priority and overtaking decisions.",
            "Recognise yellow markings related to parking and stopping restrictions.",
        ],
        exam_weight=8,
        order=6,
        lessons=[
            lesson(
                title="Lines on the Road",
                summary="Learn what common Dutch road markings require from a driver.",
                difficulty="medium",
                estimated_minutes=16,
                learning_objectives=[
                    "Differentiate solid and broken centre lines.",
                    "Recognise give-way markings and lane guidance.",
                    "Explain yellow kerb restrictions in simple terms.",
                ],
                exam_tips=[
                    "Markings often repeat the message of nearby signs. Use both clues together.",
                    "If a line is solid, assume the manoeuvre is more restricted and ask why.",
                ],
                common_mistakes=[
                    "Crossing solid lines because the road looks empty.",
                    "Ignoring kerb markings when searching for parking quickly.",
                ],
                key_takeaways=[
                    "Solid lines mean strong restrictions; broken lines allow more flexibility when safe.",
                    "Shark teeth support give-way obligations.",
                    "Yellow markings often control stopping or parking near the kerb.",
                ],
                sections=[
                    section(
                        title="Centre lines and lane meaning",
                        content=(
                            "Road markings guide where you should drive and what movements are allowed. A solid centre line shows that crossing the line is restricted, which often means overtaking is not permitted there. A broken line allows lane changes or crossing when it is otherwise safe and legal. The marking itself is a clue about visibility, conflict risk, and traffic flow.\n\n"
                            "Lane arrows, bicycle symbols, and edge lines add more detail. They help separate traffic streams and show which road users belong where. When you combine markings with signs and road shape, you can often understand the rule before you reach the exact conflict point."
                        ),
                        examples=[
                            "A broken centre line may allow an overtake, but only if visibility and oncoming traffic still make it safe.",
                            "A lane arrow telling traffic to turn right means late lane changes can become dangerous and disruptive.",
                        ],
                        dutch_keywords=["doorgetrokken", "onderbroken", "rijstrookpijl", "fietssymbool"],
                        callouts=[
                            (
                                "remember",
                                "A broken line is not a promise that changing lanes is safe. It only means the marking itself does not forbid it.",
                            ),
                            ("tip", "Use markings to predict where others may move next, especially near lane arrows."),
                        ],
                        illustration_hint="solid-and-broken-lines",
                    ),
                    section(
                        title="Give-way and kerb markings",
                        content=(
                            "Some markings affect priority directly. Shark teeth tell you to give way to the road you are entering or crossing. These markings should trigger early braking and a careful look to both sides. Other markings affect where you may stop or park. Yellow kerb markings are especially important because they often control stopping or parking near the edge of the road.\n\n"
                            "Exam questions may combine these ideas. For example, a place may have shark teeth, a cycle crossing, and a kerb restriction all in one picture. A strong theory answer comes from reading each marking separately and then combining them into one safe decision."
                        ),
                        examples=[
                            "You do not stop on yellow kerb markings just because you are only unloading for one minute.",
                            "You treat shark teeth before a cycle crossing as a clear order to wait for crossing users if needed.",
                        ],
                        dutch_keywords=["haaientanden", "gele markering", "stilstaan", "parkeren"],
                        callouts=[
                            (
                                "warning",
                                "Stopping 'for only a moment' can still be illegal or dangerous where markings forbid it.",
                            ),
                            (
                                "info",
                                "Road markings are legally meaningful even when there is no extra roadside sign next to them.",
                            ),
                        ],
                        illustration_hint="kerb-yellow-markings",
                    ),
                ],
                questions=[
                    question(
                        "What does a solid white line in the centre of the road generally mean?",
                        "A solid centre line indicates a stronger restriction, usually meaning you must not cross it for overtaking.",
                        [
                            "Overtaking is not permitted across it",
                            "You may park on it",
                            "It marks a pedestrian zone",
                            "It means minimum speed applies",
                        ],
                        0,
                        difficulty=1,
                        question_type="multiple_choice",
                    ),
                    question(
                        "What does a broken centre line usually allow, if the road is otherwise clear and safe?",
                        "A broken line allows crossing when it is otherwise safe and legal.",
                        [
                            "Nothing at all",
                            "Crossing or changing position when safe",
                            "Parking in the middle of the road",
                            "Driving against traffic",
                        ],
                        1,
                        difficulty=1,
                        question_type="multiple_choice",
                    ),
                    question(
                        "Shark teeth painted on the road mean what?",
                        "Shark teeth tell you to give way.",
                        [
                            "You may accelerate through the crossing",
                            "You must give way",
                            "The road is one-way only",
                            "No pedestrians allowed",
                        ],
                        1,
                        difficulty=1,
                        question_type="sign",
                        sign_hint="shark-teeth",
                    ),
                    question(
                        "You are behind a slow cyclist and a solid centre line runs along the road. What should you do?",
                        "You must wait until overtaking becomes legal and safe; the solid line warns against crossing.",
                        [
                            "Cross the line if no one is coming",
                            "Wait behind the cyclist",
                            "Use the horn and pass anyway",
                            "Drive on the kerb to pass",
                        ],
                        1,
                        difficulty=2,
                        question_type="scenario",
                    ),
                    question(
                        "Yellow markings on or near the kerb commonly indicate what kind of rule?",
                        "Yellow kerb markings are commonly used for parking or stopping restrictions.",
                        [
                            "A school route only",
                            "Parking or stopping restrictions",
                            "A bicycle lane",
                            "A motorway shoulder",
                        ],
                        1,
                        difficulty=1,
                        question_type="multiple_choice",
                    ),
                    question(
                        "Why can lane arrows painted on the road be important before an intersection?",
                        "They tell road users which movements are expected from each lane and reduce late conflicts.",
                        [
                            "They show where rainwater flows",
                            "They indicate the permitted or intended direction from that lane",
                            "They replace traffic lights permanently",
                            "They only matter to buses",
                        ],
                        1,
                        difficulty=1,
                        question_type="sign",
                        sign_hint="lane-arrow-right",
                    ),
                    question(
                        "A cycle symbol is painted in a lane beside you. What should you infer?",
                        "The marking indicates a cycling-related space or crossing where cyclists are especially relevant.",
                        [
                            "Cyclists are likely expected in that marked area",
                            "Cars should speed up there",
                            "Parking is free there",
                            "Only pedestrians may enter",
                        ],
                        0,
                        difficulty=1,
                        question_type="sign",
                        sign_hint="bicycle-lane-marking",
                    ),
                    question(
                        "You want to stop for a quick delivery next to yellow kerb markings that forbid parking. What is true?",
                        "Restrictions near the kerb still apply even for short stops, depending on the marking type.",
                        [
                            "Short stops are always allowed",
                            "You may ignore the marking if you leave the engine running",
                            "You must obey the restriction shown by the yellow marking",
                            "Hazard lights cancel the rule",
                        ],
                        2,
                        difficulty=2,
                        question_type="scenario",
                    ),
                    question(
                        "Why should you read road markings together with signs?",
                        "The two often reinforce each other and create a clearer picture of the rule.",
                        [
                            "Because markings are only decoration without signs",
                            "Because signs and markings often support the same rule",
                            "Because signs cancel all markings",
                            "Because markings matter only in dry weather",
                        ],
                        1,
                        difficulty=1,
                        question_type="multiple_choice",
                    ),
                    question(
                        "You notice shark teeth before crossing a busy cycle track. What hazard should you expect?",
                        "Cyclists may approach quickly, and the markings tell you to yield to the crossing traffic.",
                        [
                            "Cyclists will always stop for you",
                            "Fast crossing cyclists may have priority",
                            "The cycle track is closed",
                            "Only pedestrians use the crossing",
                        ],
                        1,
                        difficulty=2,
                        question_type="hazard",
                    ),
                    question(
                        "What is the danger of crossing a solid line just because the road looks empty?",
                        "The line is often placed where visibility or conflict risk changes quickly, even if the road seems clear for a moment.",
                        [
                            "There is no danger if you look once",
                            "You may enter a conflict area where the restriction exists for safety reasons",
                            "Solid lines only protect paint quality",
                            "The road legally becomes yours while crossing it",
                        ],
                        1,
                        difficulty=2,
                        question_type="hazard",
                    ),
                    question(
                        "Which marking most directly repeats the meaning of a give-way sign?",
                        "Shark teeth are the road-marking version of a give-way instruction.",
                        [
                            "A parking bay",
                            "Shark teeth",
                            "A bus stop box",
                            "A lane number",
                        ],
                        1,
                        difficulty=1,
                        question_type="sign",
                        sign_hint="shark-teeth-marking",
                    ),
                ],
            )
        ],
    ),
    topic(
        slug="parking-stopping",
        title="Parking and Stopping",
        summary="Learn where you may stop or park, where you must keep clear, and how local parking controls work.",
        dutch_terms=[
            {"term": "parkeren", "meaning": "parking"},
            {"term": "stilstaan", "meaning": "stopping"},
            {"term": "parkeerschijf", "meaning": "parking disc"},
            {"term": "parkeerverbod", "meaning": "parking prohibition"},
        ],
        icon="bi-p-circle",
        color_theme="rgba(168,85,247,0.15)",
        difficulty_level="intermediate",
        learning_objectives=[
            "Distinguish between stopping and parking rules.",
            "Recall common prohibited places such as junction approaches.",
            "Use parking disc zones and local restrictions correctly.",
        ],
        exam_weight=7,
        order=7,
        lessons=[
            lesson(
                title="Leaving Your Vehicle Safely",
                summary="Understand how parking rules protect visibility, access, and traffic flow.",
                difficulty="medium",
                estimated_minutes=15,
                learning_objectives=[
                    "Identify places where parking creates danger.",
                    "Use time-limited parking controls correctly.",
                    "Recognise the difference between a short stop and parking.",
                ],
                exam_tips=[
                    "If your vehicle blocks sight lines, crossings, or access, the answer is usually that the location is unsuitable.",
                    "Remember that local zone signs can create rules for a whole area, not just one bay.",
                ],
                common_mistakes=[
                    "Thinking hazard lights make an illegal stop acceptable.",
                    "Forgetting the five-metre rule near intersections.",
                ],
                key_takeaways=[
                    "Never park where you block visibility or access.",
                    "Parking zones may require a disc or special payment rules.",
                    "A quick errand is still parking if the vehicle is left standing beyond an immediate traffic need.",
                ],
                sections=[
                    section(
                        title="Where parking becomes dangerous",
                        content=(
                            "Parking rules are not only about convenience. They protect sight lines, access routes, and the movement of other road users. A vehicle parked too close to a junction can hide approaching traffic. A vehicle left near a crossing point can force pedestrians or cyclists into unsafe positions. That is why theory rules often focus on places that must remain clear.\n\n"
                            "Drivers should also think about emergency access, bus routes, loading areas, and entrances. Even if there is enough physical space to fit your vehicle, the place may still be unsuitable because it obstructs movement or visibility. Safe parking means leaving the road system easier to read, not harder."
                        ),
                        examples=[
                            "You avoid parking close to a junction because another driver would struggle to see cross traffic.",
                            "You choose a slightly longer walk instead of stopping in front of a driveway.",
                        ],
                        dutch_keywords=["kruispunt", "oprit", "zicht", "verboden te parkeren"],
                        callouts=[
                            ("warning", "Hazard lights do not give permission to stop in a prohibited place."),
                            (
                                "remember",
                                "A legal parking place should leave enough space for others to see and move safely.",
                            ),
                        ],
                        illustration_hint="parking-near-junction",
                    ),
                    section(
                        title="Parking discs, zones, and short stops",
                        content=(
                            "Some parking areas use a blue zone system that requires a parking disc. The disc shows your arrival time so authorities can check how long you have stayed. This system keeps spaces available for many users instead of allowing long-term occupation of a valuable spot.\n\n"
                            "It is also useful to separate parking from stopping. If you stop because traffic requires it, such as waiting at a red light or yielding to pedestrians, that is not parking. But if you leave the vehicle standing to make a delivery, check your phone, or visit a shop, parking and stopping rules become relevant immediately."
                        ),
                        examples=[
                            "You set the parking disc correctly after entering a blue zone rather than guessing later from memory.",
                            "Waiting in a queue at roadworks is not parking because the traffic situation requires the vehicle to remain there.",
                        ],
                        dutch_keywords=["blauwe zone", "parkeerschijf", "stilstaan", "laden en lossen"],
                        callouts=[
                            (
                                "info",
                                "A time-controlled bay still needs careful placement so you do not obstruct others.",
                            ),
                            (
                                "tip",
                                "Before leaving the car, ask whether you are stopping because of traffic or because of your own plan.",
                            ),
                        ],
                        illustration_hint="parking-disc-zone",
                    ),
                ],
                questions=[
                    question(
                        "How close to an intersection may you generally not park?",
                        "Parking too close to a junction reduces sight lines. A common rule is that parking within 5 metres is not permitted.",
                        [
                            "Within 1 metre",
                            "Within 3 metres",
                            "Within 5 metres",
                            "Within 10 metres only at night",
                        ],
                        2,
                        difficulty=1,
                        question_type="multiple_choice",
                    ),
                    question(
                        "What is commonly required in a blue parking zone?",
                        "A blue zone commonly requires a parking disc showing the arrival time.",
                        [
                            "A parking disc",
                            "Snow chains",
                            "A fuel receipt",
                            "A reflective vest on the seat",
                        ],
                        0,
                        difficulty=1,
                        question_type="sign",
                        sign_hint="parking-disc-zone",
                    ),
                    question(
                        "Why is parking near a junction usually prohibited?",
                        "A parked vehicle near a junction can block the view of approaching traffic and create danger.",
                        [
                            "Because engines cool down too quickly there",
                            "Because it blocks visibility and safe movement",
                            "Because only buses may use junctions",
                            "Because signs cannot be installed there",
                        ],
                        1,
                        difficulty=1,
                        question_type="multiple_choice",
                    ),
                    question(
                        "You stop in front of a driveway for two minutes to send a message. Is that acceptable?",
                        "Blocking access can still be problematic even for a short time. A brief personal stop is not automatically permitted.",
                        [
                            "Yes, because two minutes is never parking",
                            "No, you should not obstruct a driveway",
                            "Yes, if you leave hazard lights on",
                            "Only if the house looks empty",
                        ],
                        1,
                        difficulty=2,
                        question_type="scenario",
                    ),
                    question(
                        "What is the difference between waiting at a red light and parking?",
                        "Waiting because traffic requires it is not parking. Parking begins when you leave the vehicle standing for your own purpose.",
                        [
                            "There is no difference",
                            "Traffic-required waiting is not parking",
                            "Parking only exists when the engine is off",
                            "Parking only exists after five minutes",
                        ],
                        1,
                        difficulty=1,
                        question_type="multiple_choice",
                    ),
                    question(
                        "A sign with a white 'P' on blue usually tells you what?",
                        "This sign indicates a parking place or parking-related facility.",
                        [
                            "No stopping",
                            "Parking place",
                            "Pedestrian zone",
                            "Priority road",
                        ],
                        1,
                        difficulty=1,
                        question_type="sign",
                        sign_hint="parking-sign",
                    ),
                    question(
                        "You find a legal bay, but opening your door there would put you directly into a busy cycle track. What should you consider?",
                        "Parking must still be used safely. Dooring cyclists is a major hazard.",
                        [
                            "The bay is legal, so no extra care is needed",
                            "You should consider whether leaving the vehicle there can endanger cyclists when doors open",
                            "Cyclists must always stop for parked cars",
                            "Move halfway into the cycle track to create more space",
                        ],
                        1,
                        difficulty=2,
                        question_type="hazard",
                    ),
                    question(
                        "Why does a parking disc zone exist?",
                        "It limits the duration of parking so spaces can be shared by more users.",
                        [
                            "To increase engine temperature",
                            "To rotate parking availability over time",
                            "To forbid foreign vehicles",
                            "To permit parking on pavements",
                        ],
                        1,
                        difficulty=1,
                        question_type="multiple_choice",
                    ),
                    question(
                        "You stop on a corner because you are only collecting a parcel and will be very quick. What is the main problem?",
                        "A short personal stop can still be dangerous and illegal if it obstructs the corner or visibility.",
                        [
                            "Corners are suitable for quick collection stops",
                            "Your intention is short, so rules do not apply",
                            "The stop may still obstruct sight and create danger",
                            "Parcel collection gives automatic exemption",
                        ],
                        2,
                        difficulty=2,
                        question_type="scenario",
                    ),
                    question(
                        "Which statement about hazard lights is correct when parking rules are involved?",
                        "Hazard lights warn others but do not legalise an otherwise prohibited stop or parking action.",
                        [
                            "Hazard lights cancel parking prohibitions",
                            "Hazard lights make any quick stop legal",
                            "Hazard lights do not remove parking restrictions",
                            "Hazard lights are required to park in a blue zone",
                        ],
                        2,
                        difficulty=1,
                        question_type="multiple_choice",
                    ),
                    question(
                        "A sign and road markings show parking is allowed only in marked bays. Where should you leave your vehicle?",
                        "When parking is limited to marked bays, you must use those designated spaces.",
                        [
                            "Anywhere as long as part of the car remains in a bay",
                            "Only inside a marked bay",
                            "Half on the pavement if convenient",
                            "Across two bays for easy exit",
                        ],
                        1,
                        difficulty=1,
                        question_type="sign",
                        sign_hint="marked-bays-only",
                    ),
                    question(
                        "You park legally near a school just before dismissal time. What extra hazard should you expect when moving off later?",
                        "Children may appear unpredictably, so extra observation is needed before moving away.",
                        [
                            "No extra hazard exists if the bay is legal",
                            "Children and cyclists may appear suddenly around the parked car",
                            "Only teachers may use the road then",
                            "The bay automatically becomes a priority lane",
                        ],
                        1,
                        difficulty=2,
                        question_type="hazard",
                    ),
                ],
            )
        ],
    ),
    topic(
        slug="roundabouts",
        title="Roundabouts",
        summary="Learn how to approach, signal, position, and give way correctly at Dutch roundabouts, including nearby cycle crossings.",
        dutch_terms=[
            {"term": "rotonde", "meaning": "roundabout"},
            {"term": "afrit", "meaning": "exit"},
            {"term": "fietsoversteek", "meaning": "cycle crossing"},
            {"term": "haaientanden", "meaning": "give-way markings"},
        ],
        icon="bi-arrow-repeat",
        color_theme="rgba(236,72,153,0.15)",
        difficulty_level="intermediate",
        learning_objectives=[
            "Use the correct give-way rule when entering a roundabout.",
            "Signal and position clearly before leaving.",
            "Watch for cyclists and pedestrians near exits.",
        ],
        exam_weight=8,
        order=8,
        lessons=[
            lesson(
                title="Moving Through a Roundabout",
                summary="Focus on approach speed, priority, lane discipline, and exit checks.",
                difficulty="medium",
                estimated_minutes=15,
                learning_objectives=[
                    "Give way correctly on approach.",
                    "Use appropriate signalling at the exit.",
                    "Anticipate cycle crossings around the roundabout.",
                ],
                exam_tips=[
                    "Approach a roundabout slowly enough to read the signs, lane arrows, and cyclists around it.",
                    "Do not forget the extra check for cyclists when you leave the roundabout.",
                ],
                common_mistakes=[
                    "Assuming every cycle crossing near a roundabout works the same way.",
                    "Signalling too late or failing to check mirrors before taking the exit.",
                ],
                key_takeaways=[
                    "Traffic already on the roundabout often has priority, supported by signs and markings.",
                    "Exiting requires clear signalling and careful observation.",
                    "Cycle crossings can create a second conflict just after the exit.",
                ],
                sections=[
                    section(
                        title="Approach and entry",
                        content=(
                            "Roundabouts are designed to keep traffic moving safely by reducing severe crossing conflicts. On approach, you must slow down early, read the lane guidance, and look for give-way signs or shark teeth. In many Dutch roundabouts, entering traffic gives way to vehicles already circulating on the roundabout.\n\n"
                            "Good entry technique is smooth, not rushed. You should arrive at a speed that allows you to stop if necessary without sudden braking. This gives you time to judge whether a vehicle on the roundabout, a cyclist near the crossing, or a pedestrian at the edge will affect your path."
                        ),
                        examples=[
                            "You reduce speed early so you can read the exit signs instead of steering late.",
                            "You wait at shark teeth before entry because a car is already moving around the roundabout toward your crossing point.",
                        ],
                        dutch_keywords=["rotonde", "invoegen", "haaientanden", "rijstrookkeuze"],
                        callouts=[
                            (
                                "remember",
                                "Entering slowly is usually faster overall than braking hard at the last second.",
                            ),
                            (
                                "tip",
                                "Check for lane arrows before the roundabout so you are not forced into a late cut across another lane.",
                            ),
                        ],
                        illustration_hint="roundabout-entry",
                    ),
                    section(
                        title="Exits and cycle crossings",
                        content=(
                            "Leaving a roundabout is not the end of the task. You must indicate your exit in good time and check mirrors and blind spots for cyclists or motorcycles alongside. Many Dutch roundabouts include cycle paths around the outside, which create a separate crossing point after you leave the circular lane.\n\n"
                            "These cycle crossings can be the most important hazard in the whole manoeuvre. The exact priority may depend on signs and markings, but the safety principle is always the same: do not exit the roundabout until you know you will not cut across another road user."
                        ),
                        examples=[
                            "You spot a cyclist approaching the exit crossing quickly, so you delay your exit slightly and continue watching.",
                            "You signal off the roundabout before the exit, not after you have already started leaving it.",
                        ],
                        dutch_keywords=["uitrijden", "richtingaanwijzer", "fietspad", "blinde hoek"],
                        callouts=[
                            (
                                "warning",
                                "A cyclist near the exit can be hidden by the vehicle pillar if you do not move your head and check properly.",
                            ),
                            (
                                "info",
                                "Priority signs at cycle crossings differ by location, so always read the actual markings.",
                            ),
                        ],
                        illustration_hint="roundabout-cycle-exit",
                    ),
                ],
                questions=[
                    question(
                        "At a typical Dutch roundabout with give-way markings on the approach, who usually has priority?",
                        "The approach markings show that traffic entering must give way to traffic already on the roundabout.",
                        [
                            "Traffic entering the roundabout",
                            "Traffic already on the roundabout",
                            "The largest vehicle only",
                            "Whoever uses the horn first",
                        ],
                        1,
                        difficulty=1,
                        question_type="multiple_choice",
                    ),
                    question(
                        "Why should you slow down before reaching a roundabout?",
                        "A lower approach speed helps you read signs, choose the right lane, and stop smoothly if needed.",
                        [
                            "To make the engine louder",
                            "To read the situation and yield safely if required",
                            "Because indicators do not work above 20 km/h",
                            "Because roundabouts are only for cyclists",
                        ],
                        1,
                        difficulty=1,
                        question_type="multiple_choice",
                    ),
                    question(
                        "What road marking often tells you to give way before entering a roundabout?",
                        "Shark teeth are a common give-way marking at roundabout entries.",
                        [
                            "Parking bays",
                            "Shark teeth",
                            "A yellow kerb line",
                            "A centre rumble strip",
                        ],
                        1,
                        difficulty=1,
                        question_type="sign",
                        sign_hint="roundabout-shark-teeth",
                    ),
                    question(
                        "When should you usually signal right at a standard single-lane roundabout?",
                        "You normally signal to leave when approaching your chosen exit, not when simply entering the roundabout.",
                        [
                            "Before entering, regardless of exit",
                            "Only when you are about to leave the roundabout",
                            "Never on a roundabout",
                            "After you have already left",
                        ],
                        1,
                        difficulty=1,
                        question_type="scenario",
                    ),
                    question(
                        "You are leaving a roundabout and there is a cycle crossing just after the exit. What is the key check?",
                        "You must check whether cyclists are crossing your exit path before you cut across it.",
                        [
                            "Whether the car behind you is impatient",
                            "Whether cyclists are crossing or approaching the exit path",
                            "Whether your fuel tank is full",
                            "Whether the roundabout has flowers in the middle",
                        ],
                        1,
                        difficulty=2,
                        question_type="hazard",
                    ),
                    question(
                        "Why can a roundabout exit be more difficult than the entry?",
                        "The exit often combines steering out, signalling, mirror checks, and possible cycle or pedestrian conflicts.",
                        [
                            "Because exits are always downhill",
                            "Because the exit may involve extra crossing conflicts",
                            "Because traffic rules end at the exit",
                            "Because signs are not allowed there",
                        ],
                        1,
                        difficulty=2,
                        question_type="multiple_choice",
                    ),
                    question(
                        "A circular blue sign with white arrows around the centre island tells you what?",
                        "It indicates a roundabout and the direction of circulation.",
                        [
                            "No parking zone",
                            "Roundabout ahead or mandatory roundabout circulation",
                            "Motorway entrance",
                            "Minimum speed zone",
                        ],
                        1,
                        difficulty=1,
                        question_type="sign",
                        sign_hint="roundabout-sign",
                    ),
                    question(
                        "You are on the roundabout and realise your exit is the next one. What should you do?",
                        "Signal in good time, check mirrors and blind spot, and then leave only when the exit path is clear.",
                        [
                            "Swerve out immediately to avoid going around again",
                            "Signal and exit only after proper observation",
                            "Stop in the roundabout until the lane is empty",
                            "Reverse to reposition",
                        ],
                        1,
                        difficulty=2,
                        question_type="scenario",
                    ),
                    question(
                        "Why is lane choice before a multi-lane roundabout important?",
                        "Correct lane choice reduces late weaving and keeps your path predictable for others.",
                        [
                            "Because indicators are not needed then",
                            "Because it helps avoid sudden lane changes near the roundabout",
                            "Because the inner lane always has priority everywhere",
                            "Because only buses may choose lanes early",
                        ],
                        1,
                        difficulty=2,
                        question_type="multiple_choice",
                    ),
                    question(
                        "A cyclist is riding parallel to your car as you prepare to leave the roundabout. What is the hazard?",
                        "The cyclist may continue across your exit line, so turning out without checking could cut them off.",
                        [
                            "No hazard, because cars always leave first",
                            "The cyclist may be in your blind spot at the exit",
                            "The cyclist must dismount at every roundabout",
                            "The cyclist may enter the centre island",
                        ],
                        1,
                        difficulty=2,
                        question_type="hazard",
                    ),
                    question(
                        "At a roundabout without clear local knowledge, how should you deal with the nearby cycle crossing?",
                        "Read the actual signs and markings, because cycle crossing priority can vary by design.",
                        [
                            "Assume cyclists never have priority near roundabouts",
                            "Read the signs and markings at that specific crossing",
                            "Assume all roundabouts use the same rule",
                            "Follow the vehicle in front without checking",
                        ],
                        1,
                        difficulty=2,
                        question_type="scenario",
                    ),
                    question(
                        "What is the safest response if you miss your exit on a roundabout?",
                        "Continue around and take the next safe opportunity rather than making a sudden movement.",
                        [
                            "Brake sharply in the roundabout",
                            "Reverse to the missed exit",
                            "Continue around and take a later exit safely",
                            "Mount the kerb to correct the route",
                        ],
                        2,
                        difficulty=1,
                        question_type="hazard",
                    ),
                ],
            )
        ],
    ),
    topic(
        slug="cyclists-pedestrians",
        title="Cyclists and Pedestrians",
        summary="Focus on interactions with the most vulnerable road users in Dutch traffic.",
        dutch_terms=[
            {"term": "zebrapad", "meaning": "pedestrian crossing"},
            {"term": "fietspad", "meaning": "cycle path"},
            {"term": "overstekende voetganger", "meaning": "crossing pedestrian"},
            {"term": "blinde hoek", "meaning": "blind spot"},
        ],
        icon="bi-bicycle",
        color_theme="rgba(16,185,129,0.15)",
        difficulty_level="intermediate",
        learning_objectives=[
            "Protect vulnerable road users during turns and overtakes.",
            "Recognise common places where cyclists and pedestrians appear suddenly.",
            "Use anticipation rather than last-second reaction.",
        ],
        exam_weight=10,
        order=9,
        lessons=[
            lesson(
                title="Protecting the Most Vulnerable",
                summary="Use speed, space, and observation to drive safely around cyclists and pedestrians.",
                difficulty="medium",
                estimated_minutes=18,
                learning_objectives=[
                    "Check for cyclists before every turn across a cycle path.",
                    "Approach pedestrian crossings with anticipation.",
                    "Recognise blind-spot and door-zone risks in urban traffic.",
                ],
                exam_tips=[
                    "If the picture contains a cyclist beside your car, think blind spot and turning conflict.",
                    "Near a zebra crossing, your speed choice matters before anyone steps onto it.",
                ],
                common_mistakes=[
                    "Looking only for cars before turning and forgetting the cycle track.",
                    "Passing too closely because the cyclist seems stable at that moment.",
                ],
                key_takeaways=[
                    "Cyclists and pedestrians require early observation and lower speed.",
                    "Turning across a cycle track is a high-risk moment.",
                    "Good drivers leave room for hesitation, wobble, and unexpected movement.",
                ],
                sections=[
                    section(
                        title="Cyclists in everyday Dutch traffic",
                        content=(
                            "Cyclists are present on separate paths, alongside the carriageway, and at crossings near junctions and roundabouts. They often travel smoothly and confidently, which can make them seem easy to predict. In reality, they may need to avoid potholes, drains, opening doors, or pedestrians. Their position can change quickly, especially in towns.\n\n"
                            "This means you should never turn, pull away, or overtake based on a quick glance. A good driver checks mirrors, side windows, and blind spots, and judges whether the cyclist has enough room to continue safely without braking or swerving. The most dangerous errors happen when a motorist focuses only on other cars."
                        ),
                        examples=[
                            "Before turning right, you make a final shoulder check because a fast cyclist may have moved into your blind spot.",
                            "You pass a cyclist with generous space because wind from your vehicle can affect their balance.",
                        ],
                        dutch_keywords=["fietspad", "dode hoek", "rechtsaf", "inhalen"],
                        callouts=[
                            (
                                "warning",
                                "A cyclist may be hidden beside the front passenger pillar or mirror if you do not move your head.",
                            ),
                            (
                                "tip",
                                "Treat every cycle crossing as an active traffic stream, not as a painted decoration.",
                            ),
                        ],
                        illustration_hint="cyclist-right-turn",
                    ),
                    section(
                        title="Pedestrians, crossings, and hidden hazards",
                        content=(
                            "Pedestrians move more slowly and can be hidden by parked vehicles, buses, or street furniture. Children may step out without judging speed well. Older pedestrians may hesitate halfway. People using phones or carrying shopping may react late. That is why a pedestrian crossing should influence your speed long before you reach the stripes.\n\n"
                            "Urban driving often includes a chain of small clues: a school entrance, a bus stop, a market street, or a queue near a crossing. Each clue tells you that a person may enter your path unexpectedly. The safest response is not only to look harder, but to create time by reducing speed and leaving space."
                        ),
                        examples=[
                            "You cover the brake near a zebra crossing because a child beside a parent may suddenly run ahead.",
                            "A parked van near a crossing makes you slow down because it may hide a person about to step out.",
                        ],
                        dutch_keywords=["zebrapad", "schoolzone", "oversteken", "zichtbelemmering"],
                        callouts=[
                            (
                                "remember",
                                "If a pedestrian is hard to see, your speed should make up for the missing information.",
                            ),
                            (
                                "info",
                                "A safe pass near a crossing often means waiting rather than squeezing through first.",
                            ),
                        ],
                        illustration_hint="zebra-crossing-child",
                    ),
                ],
                questions=[
                    question(
                        "You are turning right and a cyclist is continuing straight on the cycle path beside you. What should you do?",
                        "Turning across a cyclist's path is a high-risk conflict. You must not cut across them.",
                        [
                            "Turn first because cars are faster",
                            "Wait if needed and do not cut across the cyclist",
                            "Use the horn so the cyclist stops",
                            "Turn closely to show your intention",
                        ],
                        1,
                        difficulty=1,
                        question_type="scenario",
                    ),
                    question(
                        "Why should you leave extra space when overtaking a cyclist?",
                        "Cyclists may wobble, avoid obstacles, or be affected by wind and road surface.",
                        [
                            "Because cyclists must count your mirrors",
                            "Because cyclists may need sideways space unexpectedly",
                            "Because close overtakes improve traffic flow",
                            "Because distance only matters at night",
                        ],
                        1,
                        difficulty=1,
                        question_type="multiple_choice",
                    ),
                    question(
                        "What is the main purpose of a zebra crossing?",
                        "A zebra crossing marks a pedestrian crossing point and requires strong anticipation from drivers.",
                        [
                            "A parking area for delivery bicycles",
                            "A pedestrian crossing point",
                            "A bus lane entry",
                            "A speed camera zone",
                        ],
                        1,
                        difficulty=1,
                        question_type="sign",
                        sign_hint="zebra-crossing",
                    ),
                    question(
                        "A van is parked close to a pedestrian crossing. What hazard should you expect?",
                        "The van may block your view of someone about to cross.",
                        [
                            "No hazard if the crossing is painted clearly",
                            "A hidden pedestrian may step out from behind the van",
                            "The van will always move away before you arrive",
                            "Only cyclists use crossings near vans",
                        ],
                        1,
                        difficulty=2,
                        question_type="hazard",
                    ),
                    question(
                        "Why is a final blind-spot check important before turning across a cycle track?",
                        "A cyclist can move from mirror view into the blind spot in a short time.",
                        [
                            "Because mirrors show everything perfectly",
                            "Because a cyclist may no longer be visible in the mirrors",
                            "Because blind spots only matter for trucks",
                            "Because signals replace observation",
                        ],
                        1,
                        difficulty=2,
                        question_type="multiple_choice",
                    ),
                    question(
                        "A blue sign with a white bicycle symbol tells you to expect what kind of user?",
                        "The sign indicates a cycling-related facility or route, so cyclists are especially relevant there.",
                        [
                            "Aircraft",
                            "Cyclists",
                            "Only police vehicles",
                            "Farm animals",
                        ],
                        1,
                        difficulty=1,
                        question_type="sign",
                        sign_hint="cycle-path-sign",
                    ),
                    question(
                        "You are driving past a school at the end of the day. Why should you lower speed even if the road is clear?",
                        "Children may appear suddenly and do not always judge speed well.",
                        [
                            "Because school roads are always one-way",
                            "Because children may step into the road unexpectedly",
                            "Because you must stop outside every school",
                            "Because cyclists are banned there",
                        ],
                        1,
                        difficulty=1,
                        question_type="hazard",
                    ),
                    question(
                        "What is unsafe about opening your car door without checking near a cycle lane?",
                        "A passing cyclist may collide with the door or swerve into traffic.",
                        [
                            "Nothing, because parked cars have priority",
                            "It can create a dooring crash with a cyclist",
                            "Cyclists must always ride around opened doors",
                            "Doors may only be opened on weekends",
                        ],
                        1,
                        difficulty=2,
                        question_type="hazard",
                    ),
                    question(
                        "A pedestrian waits uncertainly at the kerb near a zebra crossing. What is the safest response?",
                        "You should anticipate that the pedestrian may choose to cross and adjust speed early.",
                        [
                            "Accelerate before they decide",
                            "Approach with caution and be prepared to stop",
                            "Ignore them unless they wave",
                            "Drive in the opposite lane to pass faster",
                        ],
                        1,
                        difficulty=1,
                        question_type="scenario",
                    ),
                    question(
                        "Why are cyclists often hard to judge in urban traffic?",
                        "They are smaller than cars, can be hidden by parked vehicles, and may change line around obstacles.",
                        [
                            "Because they always break traffic rules",
                            "Because they are smaller, less protected, and may move around obstacles suddenly",
                            "Because they may only ride in groups",
                            "Because their speed is always identical",
                        ],
                        1,
                        difficulty=2,
                        question_type="multiple_choice",
                    ),
                    question(
                        "Which road user usually needs the most protection from a driver because of lack of physical protection?",
                        "Pedestrians are among the least protected users because they have no vehicle shell around them.",
                        [
                            "Pedestrians",
                            "Sports cars",
                            "Heavy lorries",
                            "Delivery vans",
                        ],
                        0,
                        difficulty=1,
                        question_type="multiple_choice",
                    ),
                    question(
                        "You begin to turn, then realise a cyclist is alongside. What is the safest correction?",
                        "Stop the turn if necessary and allow the cyclist to clear the conflict area rather than forcing them to brake sharply.",
                        [
                            "Continue because stopping mid-turn is always worse",
                            "Pause or stop the turn and let the cyclist clear",
                            "Steer onto the pavement",
                            "Accelerate to finish before the cyclist arrives",
                        ],
                        1,
                        difficulty=2,
                        question_type="scenario",
                    ),
                ],
            )
        ],
    ),
    topic(
        slug="motorways",
        title="Motorways",
        summary="Study the rules for joining, driving on, and leaving Dutch motorways safely and efficiently.",
        dutch_terms=[
            {"term": "autosnelweg", "meaning": "motorway"},
            {"term": "invoegstrook", "meaning": "merge lane"},
            {"term": "vluchtstrook", "meaning": "hard shoulder"},
            {"term": "uitvoegen", "meaning": "to leave or diverge"},
        ],
        icon="bi-diagram-2",
        color_theme="rgba(99,102,241,0.15)",
        difficulty_level="advanced",
        learning_objectives=[
            "Use motorway lanes, merge lanes, and exits correctly.",
            "Maintain safe spacing and lane discipline at higher speeds.",
            "Recognise restrictions on stopping and shoulder use.",
        ],
        exam_weight=7,
        order=10,
        lessons=[
            lesson(
                title="High-Speed Road Discipline",
                summary="Focus on merging, lane choice, spacing, and emergencies on Dutch motorways.",
                difficulty="hard",
                estimated_minutes=17,
                learning_objectives=[
                    "Merge smoothly using the acceleration lane.",
                    "Drive mainly in the right-hand lane unless overtaking.",
                    "Know when the shoulder may and may not be used.",
                ],
                exam_tips=[
                    "Motorway questions often test discipline rather than aggression. Smooth planning is usually best.",
                    "At higher speeds, distance and early observation become more important, not less.",
                ],
                common_mistakes=[
                    "Trying to force entry at the end of the merge lane without adjusting speed early.",
                    "Staying unnecessarily in the left lane after overtaking.",
                ],
                key_takeaways=[
                    "Merge by matching speed and selecting a safe gap.",
                    "Keep right except when overtaking or following lane instructions.",
                    "Stopping on the motorway is only for emergencies or official instructions.",
                ],
                sections=[
                    section(
                        title="Entering and moving with the flow",
                        content=(
                            "A motorway works best when drivers are predictable and maintain steady flow. When joining, use the acceleration lane to build speed and look early for a suitable gap. Merging is not a race to the very front of the lane. It is a coordinated action based on speed, timing, mirrors, and traffic awareness.\n\n"
                            "Once on the motorway, normal discipline means driving in the right-hand lane unless you are overtaking or signs direct you elsewhere. Unnecessary lane changes create risk, especially at higher speeds where a small mistake uses more distance and less reaction time than drivers expect."
                        ),
                        examples=[
                            "You adjust speed on the merge lane so you join between two vehicles without forcing either to brake sharply.",
                            "After overtaking, you return to the right lane when there is a safe gap behind you.",
                        ],
                        dutch_keywords=["invoegen", "rechterrijstrook", "inhaalstrook", "snelheidsaanpassing"],
                        callouts=[
                            ("tip", "Look far ahead on the motorway. Problems grow quickly at higher speeds."),
                            ("remember", "Good motorway driving is smooth and planned, not sudden and competitive."),
                        ],
                        illustration_hint="motorway-merge",
                    ),
                    section(
                        title="Distance, exits, and emergencies",
                        content=(
                            "Following distance is crucial on motorways because braking distances increase rapidly with speed. A simple time-based gap gives you more room to react if traffic compresses unexpectedly. Exits also require planning. You should move into the correct lane in time rather than cutting across late because you noticed the sign too late.\n\n"
                            "The hard shoulder is not a normal driving lane. It exists mainly for emergencies and authorised use. If a real breakdown occurs, your first goal is to get the vehicle to a place of relative safety and warn others. Routine calls, map checks, or short rests are not valid reasons to stop on the motorway shoulder."
                        ),
                        examples=[
                            "You miss an exit and continue to the next one instead of cutting across a striped separation area.",
                            "In an emergency, you use the shoulder to stop only when continuing would be more dangerous.",
                        ],
                        dutch_keywords=["volgafstand", "vluchtstrook", "uitrit", "pech"],
                        callouts=[
                            (
                                "warning",
                                "A last-second motorway exit is often more dangerous than missing the exit completely.",
                            ),
                            ("info", "The shoulder is a safety space, not a convenience space."),
                        ],
                        illustration_hint="motorway-exit-shoulder",
                    ),
                ],
                questions=[
                    question(
                        "On a Dutch motorway, which lane should you normally use when traffic conditions allow?",
                        "The normal rule is to drive in the right-hand lane and use left lanes mainly for overtaking.",
                        [
                            "The far-left lane",
                            "The right-hand lane",
                            "The shoulder",
                            "Any lane with the fewest cars, permanently",
                        ],
                        1,
                        difficulty=1,
                        question_type="multiple_choice",
                    ),
                    question(
                        "What is the purpose of the acceleration lane when entering a motorway?",
                        "It allows you to adjust speed and merge safely into the traffic flow.",
                        [
                            "To stop and wait for a written signal",
                            "To match motorway speed and merge safely",
                            "To overtake on the right permanently",
                            "To park before joining",
                        ],
                        1,
                        difficulty=1,
                        question_type="multiple_choice",
                    ),
                    question(
                        "What is the minimum speed capability expected for a vehicle using a motorway?",
                        "Vehicles should be capable of at least 60 km/h to use a motorway safely.",
                        [
                            "30 km/h",
                            "45 km/h",
                            "60 km/h",
                            "80 km/h",
                        ],
                        2,
                        difficulty=1,
                        question_type="multiple_choice",
                    ),
                    question(
                        "You are still in the left lane after overtaking and the right lane is clear. What should you do?",
                        "Returning to the right lane supports safe and efficient motorway flow.",
                        [
                            "Stay left to avoid future lane changes",
                            "Return to the right lane when safe",
                            "Move onto the shoulder",
                            "Brake sharply so others can pass",
                        ],
                        1,
                        difficulty=1,
                        question_type="scenario",
                    ),
                    question(
                        "Why is following distance especially important on a motorway?",
                        "At higher speeds, stopping distances and the distance travelled during reaction time increase greatly.",
                        [
                            "Because braking distance becomes shorter",
                            "Because high speed leaves less time and needs more space to react",
                            "Because lane markings disappear",
                            "Because mirrors are less useful",
                        ],
                        1,
                        difficulty=2,
                        question_type="hazard",
                    ),
                    question(
                        "A blue sign with a motorway symbol indicates what type of road?",
                        "The symbol indicates the start of motorway conditions.",
                        [
                            "Residential street",
                            "Motorway",
                            "Pedestrian area",
                            "Parking zone",
                        ],
                        1,
                        difficulty=1,
                        question_type="sign",
                        sign_hint="motorway-sign",
                    ),
                    question(
                        "When may you normally stop on the hard shoulder of a motorway?",
                        "Stopping on the shoulder is generally only for emergencies or official instructions.",
                        [
                            "To answer a message",
                            "For an emergency or authorised reason",
                            "To check directions if you are unsure",
                            "To wait for less traffic",
                        ],
                        1,
                        difficulty=1,
                        question_type="multiple_choice",
                    ),
                    question(
                        "You realise too late that your exit is approaching. What is safest?",
                        "It is safer to continue to the next exit than to cut across lanes or gore markings at the last second.",
                        [
                            "Cross the striped area sharply",
                            "Continue and take the next safe exit",
                            "Stop in the lane and wait",
                            "Reverse on the shoulder",
                        ],
                        1,
                        difficulty=2,
                        question_type="hazard",
                    ),
                    question(
                        "Why is a smooth speed adjustment on the merge lane better than a sudden last-second merge?",
                        "Smooth merging gives everyone more time to read your movement and adapt safely.",
                        [
                            "Because sudden moves make you look confident",
                            "Because smooth merging keeps traffic predictable",
                            "Because indicators are not needed then",
                            "Because all motorway traffic must stop for you",
                        ],
                        1,
                        difficulty=1,
                        question_type="multiple_choice",
                    ),
                    question(
                        "A lane control sign above your lane shows a red cross. What does that mean?",
                        "A red cross indicates that the lane is closed to traffic.",
                        [
                            "The lane is open and faster",
                            "The lane is closed",
                            "The lane is for buses only for one minute",
                            "The lane has no speed limit",
                        ],
                        1,
                        difficulty=2,
                        question_type="sign",
                        sign_hint="lane-red-cross",
                    ),
                    question(
                        "Traffic ahead begins braking hard on the motorway. What should your earlier following distance have given you?",
                        "A safe following gap gives time to react smoothly and avoid sudden panic braking.",
                        [
                            "A reason to stay in the same speed",
                            "Time and space to react safely",
                            "Priority over the vehicle ahead",
                            "Permission to use the shoulder",
                        ],
                        1,
                        difficulty=2,
                        question_type="hazard",
                    ),
                    question(
                        "Why is unnecessary use of the left lane discouraged on a motorway?",
                        "Keeping left without need can disrupt flow, block overtaking traffic, and encourage unsafe passing behaviour.",
                        [
                            "Because the left lane is reserved for tourists",
                            "Because lane discipline improves flow and safety",
                            "Because the left lane has weaker asphalt",
                            "Because it is only legal at night",
                        ],
                        1,
                        difficulty=1,
                        question_type="multiple_choice",
                    ),
                ],
            )
        ],
    ),
    topic(
        slug="hazard-recognition",
        title="Hazard Recognition",
        summary="Train yourself to notice risk early and choose whether to brake, release the accelerator, or maintain course safely.",
        dutch_terms=[
            {"term": "gevaarherkenning", "meaning": "hazard recognition"},
            {"term": "remmen", "meaning": "to brake"},
            {"term": "gas loslaten", "meaning": "release the accelerator"},
            {"term": "zicht", "meaning": "visibility"},
        ],
        icon="bi-exclamation-triangle",
        color_theme="rgba(239,68,68,0.15)",
        difficulty_level="advanced",
        learning_objectives=[
            "Spot developing danger before it becomes immediate.",
            "Judge distance, speed, and visibility together.",
            "Choose calm, proportionate responses to hazards.",
        ],
        exam_weight=8,
        order=11,
        lessons=[
            lesson(
                title="Seeing Danger Early",
                summary="Learn to read risk from speed, visibility, movement clues, and road environment.",
                difficulty="hard",
                estimated_minutes=18,
                learning_objectives=[
                    "Recognise early warning clues before a hazard fully appears.",
                    "Use following distance and observation to create reaction time.",
                    "Choose the safest response based on changing risk.",
                ],
                exam_tips=[
                    "Look for hidden hazards: children, parked vans, wet leaves, brake lights, and unclear intentions.",
                    "Hazard recognition often rewards the answer that creates time and space earliest.",
                ],
                common_mistakes=[
                    "Waiting for full proof of danger before reducing speed.",
                    "Looking only at the vehicle ahead instead of scanning deeper into the scene.",
                ],
                key_takeaways=[
                    "Hazard recognition is about anticipation, not surprise reactions.",
                    "Distance and visibility determine how much time you really have.",
                    "A small early response is often safer than a large late response.",
                ],
                sections=[
                    section(
                        title="Reading clues before the danger appears",
                        content=(
                            "Hazards rarely arrive without warning. A ball rolling from between parked cars, brake lights several vehicles ahead, a cyclist glancing over a shoulder, or fog thickening near water all tell you that the next few seconds may change quickly. Skilled drivers react to clues, not only to fully developed emergencies.\n\n"
                            "This approach makes driving feel calmer. If you release the accelerator early, widen your gaze, and cover the brake when the scene becomes uncertain, you reduce the need for harsh last-second braking. The exam often tests whether you can spot uncertainty and act before the road forces you to do so."
                        ),
                        examples=[
                            "A football near the kerb makes you slow down before any child enters the street.",
                            "A queue of brake lights on a motorway prompts you to create extra following distance immediately.",
                        ],
                        dutch_keywords=["anticiperen", "remweg", "reactietijd", "onzekerheid"],
                        callouts=[
                            ("tip", "If a scene gives you less information, lower your speed to buy time."),
                            (
                                "remember",
                                "The earliest safe response is often the smallest one: lift off, look wider, and prepare.",
                            ),
                        ],
                        illustration_hint="hazard-ball-road",
                    ),
                    section(
                        title="Distance, visibility, and appropriate response",
                        content=(
                            "Hazard recognition is not only about seeing the problem. It is also about selecting the right response. Sometimes lifting off the accelerator is enough. Sometimes you need firm braking. Sometimes the safest choice is to hold position and avoid a sudden steering action that could create a second conflict.\n\n"
                            "Weather and darkness make this skill even more important. In fog, rain, or glare, the distance you can see may be much shorter than the distance you need to stop. A safe driver constantly compares visible space, following distance, surface grip, and the possible actions of others."
                        ),
                        examples=[
                            "In thick fog, you reduce speed because the visible road is shorter than usual, even on a familiar route.",
                            "You avoid a sharp swerve around a small object if braking in lane is the safer option.",
                        ],
                        dutch_keywords=["mist", "volgafstand", "grip", "uitwijken"],
                        callouts=[
                            ("warning", "A sudden swerve can create a worse collision than the original hazard."),
                            (
                                "info",
                                "Good hazard recognition balances braking, steering, and space rather than using one response automatically.",
                            ),
                        ],
                        illustration_hint="fog-follow-distance",
                    ),
                ],
                questions=[
                    question(
                        "At 50 km/h, why is leaving at least about 25 metres or a good time gap useful?",
                        "A larger gap gives you more time to react and brake if the vehicle ahead slows unexpectedly.",
                        [
                            "It allows you to overtake faster",
                            "It creates reaction and braking space",
                            "It keeps the engine cooler",
                            "It is only for learner drivers",
                        ],
                        1,
                        difficulty=1,
                        question_type="hazard",
                    ),
                    question(
                        "Visibility drops to less than 50 metres in fog. Which rear light is especially important?",
                        "In very poor fog visibility, the rear fog light helps following traffic see you better.",
                        [
                            "Interior light",
                            "Rear fog light",
                            "Hazard lights only",
                            "Parking lights only",
                        ],
                        1,
                        difficulty=1,
                        question_type="multiple_choice",
                    ),
                    question(
                        "A ball rolls onto the road from between parked cars. What is the best hazard response?",
                        "A child may follow the ball, so immediate caution and speed reduction are necessary.",
                        [
                            "Accelerate past before anyone appears",
                            "Slow down immediately and prepare to stop",
                            "Steer hard into the opposite lane without checking",
                            "Ignore it if the road is dry",
                        ],
                        1,
                        difficulty=2,
                        question_type="hazard",
                    ),
                    question(
                        "Why are brake lights several vehicles ahead useful information?",
                        "They give an early clue that traffic is compressing further ahead than the car directly in front of you.",
                        [
                            "They mean the road is closed permanently",
                            "They warn of developing slowing traffic ahead",
                            "They give you priority to change lane",
                            "They only matter at night",
                        ],
                        1,
                        difficulty=1,
                        question_type="hazard",
                    ),
                    question(
                        "A warning sign for slippery road appears after rain and fallen leaves. What should you do?",
                        "The sign warns that grip may be reduced, so a lower speed and smoother inputs are safer.",
                        [
                            "Increase speed to clear the area quickly",
                            "Reduce speed and drive smoothly",
                            "Ignore it if your tyres are new",
                            "Use the horn to improve traction",
                        ],
                        1,
                        difficulty=2,
                        question_type="sign",
                        sign_hint="slippery-road",
                    ),
                    question(
                        "What is often safer than a sudden sharp swerve when a small obstacle appears?",
                        "If space and conditions allow, controlled braking in lane is often safer than a violent steering action.",
                        [
                            "Closing your eyes and holding the wheel",
                            "Controlled braking while keeping the vehicle stable",
                            "Accelerating toward the shoulder",
                            "Changing two lanes at once",
                        ],
                        1,
                        difficulty=2,
                        question_type="hazard",
                    ),
                    question(
                        "Why should you lower speed when information from the road scene becomes unclear?",
                        "Less information means more uncertainty, so you need extra time to observe and react.",
                        [
                            "Because uncertainty makes faster driving safer",
                            "Because lower speed buys time to understand the situation",
                            "Because unclear scenes cancel all signs",
                            "Because only trucks may continue then",
                        ],
                        1,
                        difficulty=1,
                        question_type="multiple_choice",
                    ),
                    question(
                        "You see a cyclist looking over one shoulder near parked cars. What might this mean?",
                        "The cyclist may be preparing to move out or turn, so you should anticipate a path change.",
                        [
                            "The cyclist is checking the weather only",
                            "The cyclist may soon change line or direction",
                            "The cyclist must stop immediately",
                            "The cyclist has lost balance completely",
                        ],
                        1,
                        difficulty=2,
                        question_type="hazard",
                    ),
                    question(
                        "A triangular sign with children warns you about what kind of developing risk?",
                        "It warns that children may be nearby and can move unpredictably.",
                        [
                            "A fuel station ahead",
                            "Possible children near or crossing the road",
                            "A bridge opening",
                            "An automatic tunnel door",
                        ],
                        1,
                        difficulty=1,
                        question_type="sign",
                        sign_hint="children-warning",
                    ),
                    question(
                        "Why is a two-second style following rule useful?",
                        "A time-based gap adapts better than guessing distance alone and helps at different speeds.",
                        [
                            "It guarantees no crash is possible",
                            "It helps maintain a practical minimum reaction gap",
                            "It only applies in tunnels",
                            "It removes the need to scan ahead",
                        ],
                        1,
                        difficulty=1,
                        question_type="multiple_choice",
                    ),
                    question(
                        "Night driving on an unfamiliar road feels comfortable until glare from oncoming traffic reduces your vision. What should change first?",
                        "When vision is reduced, speed should adapt before the road forces a sudden response.",
                        [
                            "Your speed should reduce",
                            "Your lane should widen",
                            "Your mirrors stop mattering",
                            "Your indicators should stay on permanently",
                        ],
                        0,
                        difficulty=2,
                        question_type="hazard",
                    ),
                    question(
                        "What is the main idea behind hazard recognition in theory training?",
                        "Hazard recognition teaches you to predict risk early and choose a measured safe response.",
                        [
                            "React only once the hazard is fully in front of you",
                            "Predict danger early and create time and space",
                            "Drive faster to spend less time near hazards",
                            "Ignore minor clues because they confuse you",
                        ],
                        1,
                        difficulty=1,
                        question_type="multiple_choice",
                    ),
                ],
            )
        ],
    ),
    topic(
        slug="safe-driving",
        title="Safe and Responsible Driving",
        summary="Study the decisions that keep you lawful, alert, sober, considerate, and ready for real-world traffic pressure.",
        dutch_terms=[
            {"term": "verantwoord rijden", "meaning": "responsible driving"},
            {"term": "alcoholpromillage", "meaning": "blood alcohol level"},
            {"term": "afleiding", "meaning": "distraction"},
            {"term": "blinde hoek", "meaning": "blind spot"},
        ],
        icon="bi-shield-check",
        color_theme="rgba(16,185,129,0.15)",
        difficulty_level="advanced",
        learning_objectives=[
            "Understand sober, attentive, and lawful driving behaviour.",
            "Apply a safe routine for lane changes and other complex actions.",
            "Recognise the impact of distraction, emotion, and fatigue.",
        ],
        exam_weight=5,
        order=12,
        lessons=[
            lesson(
                title="Good Judgement Behind the Wheel",
                summary="Connect law, responsibility, and defensive behaviour in everyday driving.",
                difficulty="hard",
                estimated_minutes=16,
                learning_objectives=[
                    "Recall important alcohol and fitness limits.",
                    "Describe a safe lane-change routine.",
                    "Recognise why distractions and emotions reduce driving quality.",
                ],
                exam_tips=[
                    "If an answer reduces distraction and increases observation, it is often the best one.",
                    "Theory questions about responsibility usually reward prevention, not excuses.",
                ],
                common_mistakes=[
                    "Believing short journeys make risky behaviour acceptable.",
                    "Changing lane after signalling without a final blind-spot check.",
                ],
                key_takeaways=[
                    "Stay sober, alert, and emotionally controlled.",
                    "Lane changes require mirrors, signal, and blind-spot checks in sequence.",
                    "Responsible driving means preventing danger before it reaches others.",
                ],
                sections=[
                    section(
                        title="Fitness, alcohol, and distraction",
                        content=(
                            "Safe driving starts before the engine does. Alcohol, drugs, strong emotion, fatigue, and phone distraction all reduce judgement and reaction time. Even when a driver believes they feel normal, their decisions may become slower, narrower, or more impulsive. That is why responsible driving means refusing to normalise small impairments.\n\n"
                            "In the Netherlands, alcohol limits exist for a reason: collision risk rises long before a driver feels completely unfit. Distraction works the same way. Looking away for a short moment, reading a message, or searching for an item in the car can remove the exact second you needed to notice a cyclist, brake light, or crossing pedestrian."
                        ),
                        examples=[
                            "You place the phone out of reach before the trip so you are not tempted to look down at a message.",
                            "You decline to drive after drinking because legal and safe driving both require a clear mind.",
                        ],
                        dutch_keywords=["alcohol", "afleiding", "vermoeidheid", "rijvaardigheid"],
                        callouts=[
                            ("warning", "Feeling 'mostly fine' is not the same as being fit to drive."),
                            ("remember", "Distraction steals time you cannot recover later with a quick reaction."),
                        ],
                        illustration_hint="phone-and-steering-wheel",
                    ),
                    section(
                        title="Deliberate and defensive actions",
                        content=(
                            "Responsible drivers act in a sequence. Before changing lane, they check mirrors, signal, judge the gap, check the blind spot, and then move smoothly. Before turning, they think about pedestrians and cyclists. Before overtaking, they ask whether waiting may be the safer choice. This method reduces rushed decisions.\n\n"
                            "Defensive driving also means refusing to copy bad behaviour. If another driver tailgates, pressures, or cuts in, your job is not to teach them a lesson. Your job is to protect space, avoid escalation, and keep the situation stable for everyone around you."
                        ),
                        examples=[
                            "On a motorway, you delay a lane change because a motorcycle is approaching quickly in the next lane.",
                            "You let an aggressive driver go instead of entering a contest for road space.",
                        ],
                        dutch_keywords=["spiegels", "richting aangeven", "dode hoek", "defensief rijden"],
                        callouts=[
                            ("tip", "A good routine saves you from relying on luck."),
                            ("info", "Defensive driving is active and alert, not slow or passive."),
                        ],
                        illustration_hint="lane-change-checks",
                    ),
                ],
                questions=[
                    question(
                        "What is the maximum blood alcohol level commonly allowed for experienced drivers in the Netherlands?",
                        "The commonly tested limit for experienced drivers is 0.5 promille.",
                        [
                            "0.1 promille",
                            "0.3 promille",
                            "0.5 promille",
                            "1.0 promille",
                        ],
                        2,
                        difficulty=1,
                        question_type="multiple_choice",
                    ),
                    question(
                        "Before changing lanes on a motorway, what is the safest order?",
                        "A safe routine is mirrors, signal, check the gap and blind spot, then move smoothly.",
                        [
                            "Signal, move, then check mirrors",
                            "Check mirrors, signal, check blind spot, then move when safe",
                            "Move first and correct later",
                            "Only look in the rear-view mirror",
                        ],
                        1,
                        difficulty=1,
                        question_type="scenario",
                    ),
                    question(
                        "Why is using a phone while driving dangerous even for a short glance?",
                        "A brief glance can remove your awareness during the exact moment a hazard develops.",
                        [
                            "Because the phone makes the steering wheel heavier",
                            "Because it steals attention and reaction time",
                            "Because it improves tunnel vision",
                            "Because it only affects parking speed",
                        ],
                        1,
                        difficulty=1,
                        question_type="multiple_choice",
                    ),
                    question(
                        "You had very little sleep but only plan a short drive to the shop. What is true?",
                        "Fatigue can affect any trip length because it reduces concentration and judgement.",
                        [
                            "Short trips are safe regardless of fatigue",
                            "Fatigue still makes you less fit to drive",
                            "Fatigue only matters above 100 km/h",
                            "Coffee guarantees safe driving",
                        ],
                        1,
                        difficulty=1,
                        question_type="hazard",
                    ),
                    question(
                        "A dashboard symbol shaped like a seatbelt reminds you to do what?",
                        "Seatbelt reminders reinforce a basic safety action before moving off.",
                        [
                            "Open a window",
                            "Fasten the seatbelt",
                            "Turn on fog lights",
                            "Change lane",
                        ],
                        1,
                        difficulty=1,
                        question_type="sign",
                        sign_hint="seatbelt-warning",
                    ),
                    question(
                        "Why is the blind-spot check still necessary after using mirrors?",
                        "Mirrors do not show every area beside the vehicle, especially close alongside.",
                        [
                            "Because mirrors are for decoration",
                            "Because some road users can still be hidden beside the vehicle",
                            "Because blind spots exist only in buses",
                            "Because the indicator blocks the mirrors",
                        ],
                        1,
                        difficulty=1,
                        question_type="multiple_choice",
                    ),
                    question(
                        "Another driver behaves aggressively behind you. What is the responsible response?",
                        "Avoid escalation and keep the situation stable rather than reacting emotionally.",
                        [
                            "Brake sharply to warn them",
                            "Stay calm and avoid escalating the conflict",
                            "Race away from them",
                            "Block their lane change on purpose",
                        ],
                        1,
                        difficulty=2,
                        question_type="scenario",
                    ),
                    question(
                        "Why is defensive driving considered responsible driving?",
                        "Defensive driving actively reduces risk by anticipating mistakes and keeping space.",
                        [
                            "Because it means always driving much slower than the limit",
                            "Because it helps prevent danger from developing",
                            "Because it gives you legal priority everywhere",
                            "Because it avoids using mirrors",
                        ],
                        1,
                        difficulty=1,
                        question_type="multiple_choice",
                    ),
                    question(
                        "You feel angry after an argument and get into the car immediately. What is the hazard?",
                        "Strong emotion can narrow attention and lead to rushed or aggressive decisions.",
                        [
                            "Emotion has no effect on driving",
                            "Emotion can reduce judgement and increase risk-taking",
                            "Anger improves reaction time",
                            "Only sadness affects driving",
                        ],
                        1,
                        difficulty=2,
                        question_type="hazard",
                    ),
                    question(
                        "A red warning symbol on the dashboard usually tells you what?",
                        "Red warning lights usually indicate a serious issue requiring immediate attention.",
                        [
                            "Everything is normal",
                            "A serious warning requiring prompt attention",
                            "A radio channel update",
                            "A recommended fuel grade",
                        ],
                        1,
                        difficulty=1,
                        question_type="sign",
                        sign_hint="dashboard-red-warning",
                    ),
                    question(
                        "What makes a lane change unsafe even if you have signalled?",
                        "Signalling does not remove the need for space, checks, and timing.",
                        [
                            "Signalling makes every gap safe",
                            "Moving without a safe gap or final check can still be dangerous",
                            "Lane changes are only unsafe in rain",
                            "Mirrors matter only after the move",
                        ],
                        1,
                        difficulty=2,
                        question_type="scenario",
                    ),
                    question(
                        "Why does responsible driving include considering the effect of your actions on others?",
                        "Driving safely means reducing risk for all road users, not only avoiding damage to yourself.",
                        [
                            "Because only others are responsible for traffic",
                            "Because your decisions influence the safety of everyone around you",
                            "Because pedestrians are outside the road system",
                            "Because responsibility ends once you signal",
                        ],
                        1,
                        difficulty=1,
                        question_type="multiple_choice",
                    ),
                ],
            )
        ],
    ),
    topic(
        slug="environmental-driving",
        title="Environmental Driving",
        summary="Learn eco-driving habits that reduce fuel use, wear, and emissions while keeping driving safe and smooth.",
        dutch_terms=[
            {"term": "zuinig rijden", "meaning": "economical or eco-driving"},
            {"term": "brandstofverbruik", "meaning": "fuel consumption"},
            {"term": "bandenspanning", "meaning": "tyre pressure"},
            {"term": "stationair draaien", "meaning": "idling"},
        ],
        icon="bi-leaf",
        color_theme="rgba(16,185,129,0.15)",
        difficulty_level="advanced",
        learning_objectives=[
            "Connect smooth driving with lower fuel use and emissions.",
            "Recognise maintenance factors that affect efficiency.",
            "Use eco-driving without compromising safety.",
        ],
        exam_weight=4,
        order=13,
        lessons=[
            lesson(
                title="Driving Smoothly and Efficiently",
                summary="Discover how anticipation and good vehicle care support cleaner, calmer driving.",
                difficulty="hard",
                estimated_minutes=14,
                learning_objectives=[
                    "Explain the purpose of eco-driving.",
                    "Use anticipation to avoid unnecessary braking and acceleration.",
                    "Recognise how tyre pressure and idling affect efficiency.",
                ],
                exam_tips=[
                    "Eco-driving answers should still be safe. Never choose fuel saving over control or visibility.",
                    "Smoothness, anticipation, and correct maintenance are recurring themes.",
                ],
                common_mistakes=[
                    "Confusing eco-driving with driving too slowly for the situation.",
                    "Ignoring tyre pressure even though it affects both safety and fuel use.",
                ],
                key_takeaways=[
                    "Look ahead and avoid unnecessary speed changes.",
                    "Maintain correct tyre pressure and vehicle condition.",
                    "Eco-driving supports comfort and safety when used properly.",
                ],
                sections=[
                    section(
                        title="Smooth inputs and anticipation",
                        content=(
                            "Environmental driving is based on anticipation. If you look further ahead, you can often release the accelerator earlier and avoid unnecessary heavy braking. Smooth acceleration, timely gear changes, and steady speed reduce fuel use, emissions, and mechanical wear. This style also makes the ride more comfortable for passengers and easier to read for other road users.\n\n"
                            "Eco-driving does not mean blocking traffic or ignoring conditions. It means avoiding waste. For example, instead of accelerating hard toward a red light and braking at the last moment, an efficient driver recognises the situation early and rolls down in a controlled way. The safety benefit is just as valuable as the environmental one."
                        ),
                        examples=[
                            "You notice a red traffic light ahead and ease off early instead of driving fast until the stop line.",
                            "You keep a steady gap on a flowing road so you do not need repeated harsh acceleration and braking.",
                        ],
                        dutch_keywords=["anticiperen", "gelijkmatige snelheid", "brandstof", "remmen"],
                        callouts=[
                            ("tip", "Looking further ahead often saves both fuel and stress."),
                            ("remember", "The greenest journey is still one that remains fully safe and legal."),
                        ],
                        illustration_hint="eco-driving-traffic-light",
                    ),
                    section(
                        title="Vehicle condition and avoiding waste",
                        content=(
                            "Efficiency is also affected by the condition of the vehicle. Under-inflated tyres increase rolling resistance, which makes the engine work harder. Unnecessary weight in the car, open windows at higher speed, and a poorly maintained engine can also increase fuel use. Good maintenance supports both safety and environmental performance.\n\n"
                            "Idling is another common source of waste. If you know you will be stationary for a meaningful time and conditions allow, avoiding unnecessary engine running can reduce emissions. The exact habit depends on the vehicle and situation, but the principle remains simple: do not burn fuel when it serves no useful driving purpose."
                        ),
                        examples=[
                            "You remove heavy unused items from the boot instead of carrying them for weeks.",
                            "You check tyre pressure regularly because efficiency and grip both matter.",
                        ],
                        dutch_keywords=["bandenspanning", "stationair", "onderhoud", "weerstand"],
                        callouts=[
                            (
                                "info",
                                "Correct tyre pressure helps with braking, handling, and fuel economy at the same time.",
                            ),
                            (
                                "warning",
                                "Do not switch attention from the road to eco-driving displays when the traffic situation is complex.",
                            ),
                        ],
                        illustration_hint="tyre-pressure-and-leaf",
                    ),
                ],
                questions=[
                    question(
                        "What is the main aim of eco-driving?",
                        "Eco-driving aims to reduce fuel use and emissions through smooth, efficient driving habits.",
                        [
                            "To make every journey longer",
                            "To reduce fuel consumption and emissions",
                            "To avoid using mirrors",
                            "To drive below all speed limits",
                        ],
                        1,
                        difficulty=1,
                        question_type="multiple_choice",
                    ),
                    question(
                        "Why can looking far ahead reduce fuel use?",
                        "It helps you avoid unnecessary acceleration and harsh braking by planning earlier.",
                        [
                            "Because distant vision makes the engine quieter",
                            "Because anticipation helps you drive more smoothly",
                            "Because signs are optional then",
                            "Because it removes the need for gears",
                        ],
                        1,
                        difficulty=1,
                        question_type="multiple_choice",
                    ),
                    question(
                        "A traffic light ahead turns red. What is an eco-friendly and safe response?",
                        "Releasing the accelerator early and slowing smoothly avoids wasteful acceleration toward a stop.",
                        [
                            "Accelerate and brake hard at the line",
                            "Ease off early and slow smoothly",
                            "Switch off all lights and continue",
                            "Move into another lane without checking",
                        ],
                        1,
                        difficulty=1,
                        question_type="scenario",
                    ),
                    question(
                        "Why does incorrect tyre pressure matter for environmental driving?",
                        "Low tyre pressure increases rolling resistance and can also affect safety.",
                        [
                            "It only changes the colour of the tyres",
                            "It can increase fuel use and reduce safety",
                            "It improves grip in every case",
                            "It only matters for racing cars",
                        ],
                        1,
                        difficulty=1,
                        question_type="multiple_choice",
                    ),
                    question(
                        "A dashboard leaf or efficiency symbol usually encourages what kind of driving style?",
                        "Such symbols generally encourage economical, smooth driving habits.",
                        [
                            "Aggressive acceleration",
                            "Economical, smooth driving",
                            "Driving without headlights",
                            "Ignoring maintenance",
                        ],
                        1,
                        difficulty=1,
                        question_type="sign",
                        sign_hint="eco-leaf-dashboard",
                    ),
                    question(
                        "What is the benefit of keeping a steady speed where appropriate?",
                        "Steady speed reduces unnecessary acceleration and braking, which saves fuel and supports comfort.",
                        [
                            "It increases tyre wear intentionally",
                            "It can reduce fuel use and make driving smoother",
                            "It removes the need to observe the road",
                            "It only matters downhill",
                        ],
                        1,
                        difficulty=1,
                        question_type="multiple_choice",
                    ),
                    question(
                        "You carry several heavy items in the car for weeks even though you do not need them. Why is that inefficient?",
                        "Extra weight can increase the energy needed to move the vehicle.",
                        [
                            "Weight has no effect on efficiency",
                            "Extra weight can increase fuel consumption",
                            "Heavy items always improve handling",
                            "It only matters on snowy roads",
                        ],
                        1,
                        difficulty=1,
                        question_type="scenario",
                    ),
                    question(
                        "Why should eco-driving never replace safe driving?",
                        "Saving fuel is not worth reduced control, poor visibility, or risky decisions.",
                        [
                            "Because eco-driving is illegal",
                            "Because safety remains the first priority",
                            "Because fuel saving only applies to trucks",
                            "Because signs disappear during eco-driving",
                        ],
                        1,
                        difficulty=1,
                        question_type="hazard",
                    ),
                    question(
                        "What does unnecessary idling do?",
                        "It uses fuel and creates emissions without helping the vehicle move.",
                        [
                            "It improves the tyres permanently",
                            "It wastes fuel and adds emissions",
                            "It shortens stopping distance",
                            "It cools the brakes instantly",
                        ],
                        1,
                        difficulty=1,
                        question_type="multiple_choice",
                    ),
                    question(
                        "A warning light about tyre pressure deserves attention for which two reasons?",
                        "Tyre pressure matters for both safety and efficiency.",
                        [
                            "Comfort and radio quality",
                            "Safety and fuel efficiency",
                            "Paint colour and resale only",
                            "Navigation and seat heating",
                        ],
                        1,
                        difficulty=2,
                        question_type="sign",
                        sign_hint="tyre-pressure-warning",
                    ),
                    question(
                        "Traffic ahead is slowing repeatedly. What eco-driving habit can help?",
                        "Leaving a good gap lets you ease off gradually instead of braking and accelerating sharply over and over.",
                        [
                            "Drive close so others cannot enter the gap",
                            "Leave a smoother gap and anticipate changes",
                            "Use the horn to keep traffic moving",
                            "Change lanes every few seconds",
                        ],
                        1,
                        difficulty=2,
                        question_type="scenario",
                    ),
                    question(
                        "Why is regular vehicle maintenance part of environmental driving?",
                        "A well-maintained vehicle generally runs more efficiently and with fewer avoidable emissions.",
                        [
                            "Because maintenance removes the need for careful driving",
                            "Because good condition supports efficient operation",
                            "Because maintenance increases idling",
                            "Because only old cars need maintenance",
                        ],
                        1,
                        difficulty=1,
                        question_type="multiple_choice",
                    ),
                ],
            )
        ],
    ),
    topic(
        slug="vehicle-knowledge",
        title="Vehicle Knowledge",
        summary="Understand the basic technical checks and warning signs that support safe, legal driving.",
        dutch_terms=[
            {"term": "profiel", "meaning": "tyre tread"},
            {"term": "waarschuwingslampje", "meaning": "warning light"},
            {"term": "oliepeil", "meaning": "oil level"},
            {"term": "bandenspanning", "meaning": "tyre pressure"},
        ],
        icon="bi-wrench-adjustable",
        color_theme="rgba(107,114,128,0.15)",
        difficulty_level="advanced",
        learning_objectives=[
            "Perform basic pre-drive safety checks.",
            "Recognise common dashboard warnings and tyre rules.",
            "Link vehicle condition to safe road use.",
        ],
        exam_weight=5,
        order=14,
        lessons=[
            lesson(
                title="Knowing Your Vehicle",
                summary="Focus on the simple technical facts every driver should know before using a car on public roads.",
                difficulty="hard",
                estimated_minutes=16,
                learning_objectives=[
                    "Recall minimum tyre tread depth and basic maintenance duties.",
                    "Interpret common warning-light colours and symbols.",
                    "Explain why visibility, brakes, and tyres matter every day.",
                ],
                exam_tips=[
                    "Vehicle questions often connect a small technical fault to a larger safety consequence.",
                    "Think beyond the part itself: ask what road risk follows if it is ignored.",
                ],
                common_mistakes=[
                    "Treating yellow warning lights as decorative rather than meaningful.",
                    "Waiting for obvious failure instead of acting on early signs of unsafe condition.",
                ],
                key_takeaways=[
                    "Basic checks before a trip can prevent larger hazards later.",
                    "Tyres, lights, fluids, and warning lamps all matter.",
                    "A vehicle that moves is not automatically a vehicle that is safe to drive.",
                ],
                sections=[
                    section(
                        title="Tyres, visibility, and basic checks",
                        content=(
                            "Vehicle knowledge begins with the parts that touch the road and support your view of it. Tyres need enough tread and correct pressure to provide grip, stable braking, and predictable handling. Windows, mirrors, wipers, and lights all help you see and be seen. When one of these is neglected, the risk appears first in poor weather or unexpected situations.\n\n"
                            "A short pre-drive check does not need to be complicated. Look at the tyres, clear the windows, make sure lights work, and notice whether anything feels unusual. These simple habits reduce the chance that a small issue becomes a dangerous surprise during the journey."
                        ),
                        examples=[
                            "You notice one tyre looks low before a trip and check it instead of assuming it will be fine.",
                            "Before driving in rain, you confirm that the wipers clear the screen effectively.",
                        ],
                        dutch_keywords=["banden", "profiel", "ruitenwissers", "verlichting"],
                        callouts=[
                            ("remember", "Your tyres are the only contact points between the car and the road."),
                            (
                                "tip",
                                "A two-minute check before departure is easier than solving a preventable problem on the road.",
                            ),
                        ],
                        illustration_hint="tyres-lights-check",
                    ),
                    section(
                        title="Warning lights and responding early",
                        content=(
                            "Dashboard warning lights help you notice problems before they become breakdowns or safety failures. In general, red warnings suggest an urgent issue, while yellow or amber warnings indicate something that needs attention soon. The exact meaning depends on the symbol, but the principle is the same: warning lights should lead to action, not to guesswork.\n\n"
                            "Good vehicle knowledge also means knowing your limits. If you are unsure about a warning, you should check the handbook or get reliable help instead of continuing blindly. A fault involving brakes, steering, engine temperature, or oil pressure can become serious very quickly."
                        ),
                        examples=[
                            "A tyre-pressure warning leads you to inspect the tyres before taking a fast road journey.",
                            "A red engine temperature warning tells you to stop safely and investigate rather than driving on.",
                        ],
                        dutch_keywords=["dashboard", "rood lampje", "geel lampje", "olie"],
                        callouts=[
                            (
                                "warning",
                                "A warning light is part of the safety system, not an inconvenience to ignore.",
                            ),
                            (
                                "info",
                                "Knowing the difference between urgent and soon-to-be-checked warnings helps you react properly.",
                            ),
                        ],
                        illustration_hint="dashboard-warning-cluster",
                    ),
                ],
                questions=[
                    question(
                        "What is the minimum tyre tread depth commonly required for a car tyre?",
                        "A minimum tread depth of 1.6 mm is commonly required.",
                        [
                            "0.8 mm",
                            "1.2 mm",
                            "1.6 mm",
                            "3.0 mm",
                        ],
                        2,
                        difficulty=1,
                        question_type="multiple_choice",
                    ),
                    question(
                        "What does a yellow dashboard warning light usually tell you?",
                        "A yellow or amber warning light usually indicates a fault or condition that needs attention soon.",
                        [
                            "Everything is operating perfectly",
                            "A condition that needs attention soon",
                            "The engine is extra powerful",
                            "You may ignore all maintenance",
                        ],
                        1,
                        difficulty=1,
                        question_type="sign",
                        sign_hint="dashboard-yellow-warning",
                    ),
                    question(
                        "Why is correct tyre pressure important?",
                        "Correct tyre pressure supports grip, braking, stability, and efficiency.",
                        [
                            "Only for paint protection",
                            "For grip, braking, and efficient rolling",
                            "Only for radio reception",
                            "Because it changes the registration number",
                        ],
                        1,
                        difficulty=1,
                        question_type="multiple_choice",
                    ),
                    question(
                        "Before driving in heavy rain, which equipment deserves a quick check?",
                        "Wipers, lights, and tyres are especially important when visibility and grip are reduced.",
                        [
                            "Only the horn",
                            "Wipers, lights, and tyres",
                            "Only the glove box",
                            "Only the rear seats",
                        ],
                        1,
                        difficulty=1,
                        question_type="scenario",
                    ),
                    question(
                        "A red oil-pressure warning appears while driving. What is the safest general response?",
                        "A red oil warning may indicate a serious engine lubrication problem and deserves urgent attention.",
                        [
                            "Ignore it until the next service",
                            "Stop safely and investigate promptly",
                            "Drive faster to clear the engine",
                            "Switch on the interior light",
                        ],
                        1,
                        difficulty=2,
                        question_type="sign",
                        sign_hint="oil-pressure-warning",
                    ),
                    question(
                        "Why do worn tyres increase risk on wet roads?",
                        "Less tread can reduce water dispersion and grip, increasing stopping distance and loss-of-control risk.",
                        [
                            "They make the car louder only",
                            "They can reduce wet grip and increase stopping distance",
                            "They improve cornering automatically",
                            "They only matter in summer",
                        ],
                        1,
                        difficulty=2,
                        question_type="hazard",
                    ),
                    question(
                        "What is the value of a short pre-drive walk-around check?",
                        "It helps you spot simple faults like low tyres, blocked lights, or damage before they become dangerous on the road.",
                        [
                            "It replaces all future servicing",
                            "It helps spot simple safety issues early",
                            "It is only for long holidays",
                            "It is required only after sunset",
                        ],
                        1,
                        difficulty=1,
                        question_type="multiple_choice",
                    ),
                    question(
                        "A tyre-pressure warning comes on before a motorway trip. What should you do?",
                        "High-speed driving with a tyre issue increases risk, so it should be checked before continuing confidently.",
                        [
                            "Ignore it because the tyres look round",
                            "Check and correct the tyre issue before relying on the vehicle",
                            "Only lower the radio volume",
                            "Drive in the left lane instead",
                        ],
                        1,
                        difficulty=2,
                        question_type="scenario",
                    ),
                    question(
                        "Why is clear glass all around the vehicle important?",
                        "Visibility in all relevant directions is essential for safe observation and manoeuvring.",
                        [
                            "Because side windows are decorative",
                            "Because safe driving depends on being able to see all around",
                            "Because mirrors replace windows entirely",
                            "Because it helps tyre wear",
                        ],
                        1,
                        difficulty=1,
                        question_type="multiple_choice",
                    ),
                    question(
                        "A battery symbol on the dashboard is best treated as what kind of information?",
                        "It is a warning that the charging system may need attention.",
                        [
                            "A music setting",
                            "A warning about the electrical charging system",
                            "A sign that your fuel is full",
                            "A seat adjustment reminder",
                        ],
                        1,
                        difficulty=2,
                        question_type="sign",
                        sign_hint="battery-warning",
                    ),
                    question(
                        "One headlight is not working before a night journey. Why is that a problem?",
                        "Lighting faults reduce how well you can see and how well others can judge your vehicle.",
                        [
                            "Because only police can drive at night with one light",
                            "Because it reduces seeing and being seen",
                            "Because it affects tyre tread depth",
                            "Because it changes the speed limit",
                        ],
                        1,
                        difficulty=1,
                        question_type="hazard",
                    ),
                    question(
                        "What is the best attitude toward a warning light you do not recognise?",
                        "Unknown warnings should be checked rather than ignored, because they may relate to safety-critical systems.",
                        [
                            "Ignore it if the car still moves",
                            "Check what it means before trusting the vehicle fully",
                            "Cover it with tape",
                            "Ask another driver to guess",
                        ],
                        1,
                        difficulty=1,
                        question_type="multiple_choice",
                    ),
                ],
            )
        ],
    ),
]


class Command(BaseCommand):
    help = "Seed Dutch driving theory content"

    def add_arguments(self, parser):
        parser.add_argument("--clear", action="store_true", help="Clear all data before seeding")

    @transaction.atomic
    def handle(self, *args, **options):
        from apps.driving_theory.models import (
            DrivingLesson,
            DrivingLessonSection,
            DrivingQuestion,
            DrivingQuestionOption,
            DrivingTopic,
        )

        if options["clear"]:
            DrivingTopic.objects.all().delete()
            self.stdout.write("Cleared all driving theory data.")

        topics_data = TOPICS

        total_topics = 0
        total_lessons = 0
        total_questions = 0

        for topic_data in topics_data:
            topic_obj, _ = DrivingTopic.objects.update_or_create(
                slug=topic_data["slug"],
                defaults={k: v for k, v in topic_data.items() if k not in {"slug", "lessons"}},
            )

            for lesson_data in topic_data.get("lessons", []):
                lesson_obj, _ = DrivingLesson.objects.update_or_create(
                    topic=topic_obj,
                    title=lesson_data["title"],
                    defaults={k: v for k, v in lesson_data.items() if k not in {"title", "sections", "questions"}},
                )
                total_lessons += 1

                DrivingLessonSection.objects.filter(lesson=lesson_obj).delete()
                for index, section_data in enumerate(lesson_data.get("sections", [])):
                    DrivingLessonSection.objects.create(lesson=lesson_obj, order=index, **section_data)

                desired_texts = [item["question_text"] for item in lesson_data.get("questions", [])]
                stale_questions = DrivingQuestion.objects.filter(topic=topic_obj).exclude(
                    question_text__in=desired_texts
                )
                for stale_question in stale_questions:
                    if stale_question.mocktestattempt_set.exists() or stale_question.mocktestanswer_set.exists():
                        stale_question.is_active = False
                        stale_question.lesson = None
                        stale_question.save(update_fields=["is_active", "lesson"])
                    else:
                        stale_question.delete()

                for question_data in lesson_data.get("questions", []):
                    options_data = question_data["options"]
                    question_defaults = {k: v for k, v in question_data.items() if k != "options"}
                    question_obj, _ = DrivingQuestion.objects.update_or_create(
                        topic=topic_obj,
                        question_text=question_data["question_text"],
                        defaults={"lesson": lesson_obj, **question_defaults},
                    )
                    question_obj.options.all().delete()
                    for option_index, option_data in enumerate(options_data):
                        DrivingQuestionOption.objects.create(question=question_obj, order=option_index, **option_data)
                    total_questions += 1

            self.stdout.write(f"  Seeded topic: {topic_obj.title}")
            total_topics += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"\nSeeding complete: {total_topics} topics, {total_lessons} lessons, {total_questions} questions.\n"
                "GuideWisey is not affiliated with or endorsed by the CBR.\n"
                "All content is original and for educational purposes only."
            )
        )
