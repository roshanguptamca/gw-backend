"""Seed data + helper for BuddyScenario real-life practice scenarios.

Used by the `seed_buddy_scenarios` management command and available for
tests / fixtures that want a consistent baseline scenario catalog.
"""

from ..models import BuddyScenario

DUTCH_SCENARIOS = [
    {
        "title": "Gemeente Appointment",
        "slug": "nl-gemeente-appointment",
        "description": "Practice booking and attending an appointment at the local gemeente (municipality) office.",
        "category": "government",
        "level": "intermediate",
        "opening_message": "Goedemiddag! Waarmee kan ik u vandaag helpen bij de gemeente?",
        "expected_skills": ["formal register", "asking for documents", "appointment vocabulary"],
        "vocabulary_focus": ["afspraak", "identiteitsbewijs", "inschrijving", "loket"],
        "is_kids_safe": True,
    },
    {
        "title": "Doctor Visit",
        "slug": "nl-doctor-visit",
        "description": "Describe symptoms and understand advice during a visit to the huisarts (GP).",
        "category": "healthcare",
        "level": "intermediate",
        "opening_message": "Goedemorgen, wat zijn uw klachten vandaag?",
        "expected_skills": ["describing symptoms", "understanding medical advice"],
        "vocabulary_focus": ["klachten", "pijn", "recept", "afspraak"],
        "is_kids_safe": True,
    },
    {
        "title": "School / Teacher Conversation",
        "slug": "nl-school-teacher-conversation",
        "description": "Talk with your child's teacher about progress and school activities.",
        "category": "education",
        "level": "elementary",
        "opening_message": "Fijn dat u er bent. Zullen we het even hebben over de voortgang van uw kind?",
        "expected_skills": ["polite questions", "school vocabulary"],
        "vocabulary_focus": ["huiswerk", "rapport", "oudergesprek"],
        "is_kids_safe": True,
    },
    {
        "title": "Job Interview",
        "slug": "nl-job-interview",
        "description": "Practice answering common Dutch job interview questions.",
        "category": "work",
        "level": "upper_intermediate",
        "opening_message": "Vertel eens iets over uzelf en waarom u solliciteert naar deze functie.",
        "expected_skills": ["self-introduction", "formal vocabulary", "answering behavioral questions"],
        "vocabulary_focus": ["sollicitatie", "ervaring", "vaardigheden"],
        "is_kids_safe": True,
    },
    {
        "title": "Customer Support Call",
        "slug": "nl-customer-support-call",
        "description": "Handle a customer service call about a billing or delivery issue.",
        "category": "customer_service",
        "level": "intermediate",
        "opening_message": "Goedendag, u spreekt met de klantenservice. Waarmee kan ik u helpen?",
        "expected_skills": ["explaining a problem", "polite complaint phrasing"],
        "vocabulary_focus": ["klacht", "bestelling", "terugbetaling"],
        "is_kids_safe": True,
    },
    {
        "title": "Ordering Food",
        "slug": "nl-ordering-food",
        "description": "Order food and drinks at a Dutch restaurant or cafe.",
        "category": "food",
        "level": "beginner",
        "opening_message": "Welkom! Wat mag het zijn?",
        "expected_skills": ["ordering", "asking about menu items"],
        "vocabulary_focus": ["menukaart", "bestellen", "rekening"],
        "is_kids_safe": True,
    },
    {
        "title": "Supermarket Conversation",
        "slug": "nl-supermarket-conversation",
        "description": "Ask for help finding items and pay at a Dutch supermarket.",
        "category": "shopping",
        "level": "beginner",
        "opening_message": "Hallo, kan ik u ergens mee helpen in de winkel?",
        "expected_skills": ["asking where items are", "basic shopping phrases"],
        "vocabulary_focus": ["boodschappen", "kassa", "korting"],
        "is_kids_safe": True,
    },
    {
        "title": "Travel / Public Transport",
        "slug": "nl-travel-public-transport",
        "description": "Ask for directions and buy tickets for Dutch public transport.",
        "category": "travel",
        "level": "elementary",
        "opening_message": "Goedemiddag, waar wilt u vandaag naartoe reizen?",
        "expected_skills": ["asking directions", "buying tickets"],
        "vocabulary_focus": ["trein", "kaartje", "overstappen"],
        "is_kids_safe": True,
    },
    {
        "title": "CBR Driving Theory Explanation",
        "slug": "nl-cbr-driving-theory",
        "description": "Discuss and explain Dutch driving theory (CBR) concepts and rules.",
        "category": "driving",
        "level": "intermediate",
        "opening_message": "Zullen we een paar verkeersregels doornemen voor je CBR-theorie-examen?",
        "expected_skills": ["explaining rules", "traffic vocabulary"],
        "vocabulary_focus": ["voorrang", "verkeersbord", "rijbewijs"],
        "is_kids_safe": True,
    },
    {
        "title": "Work Standup Conversation",
        "slug": "nl-work-standup",
        "description": "Practice giving a short daily standup update at work in Dutch.",
        "category": "work",
        "level": "upper_intermediate",
        "opening_message": "Goedemorgen! Wat heb je gisteren gedaan en waar werk je vandaag aan?",
        "expected_skills": ["summarizing tasks", "workplace vocabulary"],
        "vocabulary_focus": ["taken", "deadline", "vergadering"],
        "is_kids_safe": True,
    },
]

ENGLISH_SCENARIOS = [
    {
        "title": "Job Interview",
        "slug": "en-job-interview",
        "description": "Practice answering common English job interview questions.",
        "category": "work",
        "level": "upper_intermediate",
        "opening_message": "Thanks for coming in. Can you tell me a bit about yourself?",
        "expected_skills": ["self-introduction", "answering behavioral questions"],
        "vocabulary_focus": ["experience", "strengths", "teamwork"],
        "is_kids_safe": True,
    },
    {
        "title": "Customer Support",
        "slug": "en-customer-support",
        "description": "Handle a customer service call about an order or billing issue.",
        "category": "customer_service",
        "level": "intermediate",
        "opening_message": "Hello, thanks for calling support. How can I help you today?",
        "expected_skills": ["explaining a problem", "polite complaint phrasing"],
        "vocabulary_focus": ["refund", "order", "complaint"],
        "is_kids_safe": True,
    },
    {
        "title": "Daily Small Talk",
        "slug": "en-daily-small-talk",
        "description": "Practice casual everyday small talk in English.",
        "category": "daily_life",
        "level": "beginner",
        "opening_message": "Hey! How's your day going so far?",
        "expected_skills": ["casual conversation", "asking follow-up questions"],
        "vocabulary_focus": ["weather", "weekend plans", "hobbies"],
        "is_kids_safe": True,
    },
    {
        "title": "Airport / Travel",
        "slug": "en-airport-travel",
        "description": "Check in, go through security, and board a flight.",
        "category": "travel",
        "level": "elementary",
        "opening_message": "Good morning! Can I see your passport and boarding pass, please?",
        "expected_skills": ["travel vocabulary", "answering security questions"],
        "vocabulary_focus": ["boarding pass", "luggage", "gate"],
        "is_kids_safe": True,
    },
    {
        "title": "Doctor Visit",
        "slug": "en-doctor-visit",
        "description": "Describe symptoms and understand advice during a doctor visit.",
        "category": "healthcare",
        "level": "intermediate",
        "opening_message": "Good morning, what brings you in today?",
        "expected_skills": ["describing symptoms", "understanding medical advice"],
        "vocabulary_focus": ["symptoms", "prescription", "appointment"],
        "is_kids_safe": True,
    },
    {
        "title": "School Conversation",
        "slug": "en-school-conversation",
        "description": "Talk with a teacher about school progress and activities.",
        "category": "education",
        "level": "elementary",
        "opening_message": "Thanks for coming in. Let's talk about how things are going at school.",
        "expected_skills": ["polite questions", "school vocabulary"],
        "vocabulary_focus": ["homework", "report card", "parent-teacher meeting"],
        "is_kids_safe": True,
    },
    {
        "title": "Business Meeting",
        "slug": "en-business-meeting",
        "description": "Participate in a business meeting discussing project updates.",
        "category": "business",
        "level": "upper_intermediate",
        "opening_message": "Let's get started. Can you walk us through the project status?",
        "expected_skills": ["summarizing updates", "business vocabulary"],
        "vocabulary_focus": ["deadline", "budget", "stakeholders"],
        "is_kids_safe": True,
    },
    {
        "title": "Presentation Practice",
        "slug": "en-presentation-practice",
        "description": "Practice delivering and defending a short presentation.",
        "category": "presentation",
        "level": "upper_intermediate",
        "opening_message": "Whenever you're ready, please begin your presentation.",
        "expected_skills": ["clear structure", "handling questions"],
        "vocabulary_focus": ["overview", "conclusion", "next steps"],
        "is_kids_safe": True,
    },
    {
        "title": "Restaurant Ordering",
        "slug": "en-restaurant-ordering",
        "description": "Order food and drinks at an English-speaking restaurant.",
        "category": "food",
        "level": "beginner",
        "opening_message": "Welcome! Are you ready to order, or do you need a few more minutes?",
        "expected_skills": ["ordering", "asking about menu items"],
        "vocabulary_focus": ["menu", "order", "bill"],
        "is_kids_safe": True,
    },
    {
        "title": "Complaint Handling",
        "slug": "en-complaint-handling",
        "description": "Practice making and resolving a polite complaint.",
        "category": "customer_service",
        "level": "intermediate",
        "opening_message": "I understand you have an issue with your order. Can you tell me what happened?",
        "expected_skills": ["polite complaint phrasing", "problem resolution"],
        "vocabulary_focus": ["complaint", "refund", "apology"],
        "is_kids_safe": True,
    },
]


def _system_prompt_for(scenario_data, language):
    lang_label = "Dutch" if language == "nl" else "English"
    return (
        f"You are role-playing a real-life {scenario_data['category']} scenario in {lang_label}. "
        f"Stay in character for: {scenario_data['title']}. "
        "Speak mainly in the target language, use practical everyday sentences, keep answers short, "
        "and ask only one question at a time. If corrections are needed, explain them briefly in the "
        "user's native language when helpful."
    )


def seed_scenarios():
    """Create or update the baseline Dutch and English scenario catalog. Idempotent."""
    created, updated = 0, 0
    for language, scenarios in (("nl", DUTCH_SCENARIOS), ("en", ENGLISH_SCENARIOS)):
        for data in scenarios:
            defaults = {
                "title": data["title"],
                "description": data["description"],
                "language": language,
                "category": data["category"],
                "level": data["level"],
                "system_prompt": _system_prompt_for(data, language),
                "opening_message": data["opening_message"],
                "expected_skills": data["expected_skills"],
                "vocabulary_focus": data["vocabulary_focus"],
                "is_kids_safe": data["is_kids_safe"],
                "is_active": True,
            }
            _obj, was_created = BuddyScenario.objects.update_or_create(slug=data["slug"], defaults=defaults)
            if was_created:
                created += 1
            else:
                updated += 1
    return created, updated
