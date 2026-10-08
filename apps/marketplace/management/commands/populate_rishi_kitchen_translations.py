from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.marketplace.models import Shop

PRODUCT_TRANSLATIONS = {
    "Besan Laddoo 500g": {
        "description": "Huisgemaakte besan-laddoo's, verpakking van 500 g. Bestel vooraf; alleen afhalen in 2724 HE Zoetermeer.",
    },
    "Carrot Achar 250 g": {
        "description": "Huisgemaakte vegetarische wortel achar van 250 g. Een friszuur gekruide smaakmaker bij dal, rijst of roti. Op bestelling bereid; alleen afhalen in 2724 HE Zoetermeer. Voorgesteld recept en allergeneninformatie moeten nog per batch worden bevestigd.",
        "ingredients": "Voorgesteld recept: wortel, citroensap, zonnebloemolie, mosterdzaad, venkelzaad, kurkuma, zout. Bevestig de werkelijke ingrediënten en bestelling vóór publicatie.",
        "allergens": "Voorgesteld: MOSTERD. Bevestig de ingrediënten van de leverancier en mogelijke kruisbesmetting in de keuken.",
    },
    "Eggless Chocolate Chip Cupcake": {
        "description": "Zachte, smeuïge en heerlijke eivrije vanillecupcakes met rijke chocoladestukjes. Vers gebakken voor een lichte, luchtige structuur. Heerlijk voor verjaardagen, feestjes, bij de thee of gewoon tussendoor.\n\nGeschikt voor: vegetariërs ✔️ Eivrij ✔️",
        "ingredients": "Tarwebloem\nSuiker\nMelk\nBoter of plantaardige olie\nChocoladestukjes\nBakpoeder\nZuiveringszout\nVanille-extract\nZout",
        "allergens": "Bevat:\n\nTarwe (gluten)\nMelk\nSoja (kan voorkomen in chocoladestukjes)",
    },
    "Ginger Achar 250 g": {
        "description": "Huisgemaakte vegetarische gember achar van 250 g. Een friszuur gekruide smaakmaker bij dal, rijst of roti. Op bestelling bereid; alleen afhalen in 2724 HE Zoetermeer. Voorgesteld recept en allergeneninformatie moeten nog per batch worden bevestigd.",
        "ingredients": "Voorgesteld recept: gember, citroensap, zonnebloemolie, mosterdzaad, kurkuma, zout. Bevestig de werkelijke ingrediënten en bestelling vóór publicatie.",
        "allergens": "Voorgesteld: MOSTERD. Bevestig de ingrediënten van de leverancier en mogelijke kruisbesmetting in de keuken.",
    },
    "Gulab Jamun": {
        "description": "Zachte, melkhoudende zoete balletjes in geurige suikersiroop.\n\nOngeveer 20 stuks",
        "ingredients": "Ingrediënten:\n\nTarwebloem (maida)\nMelkbestanddelen (melkpoeder)\nSuiker\nPlantaardig vet\nRijsmiddelen (E500, E341)\nKardemomaroma\n\nBewaren:\nKoel en droog bewaren, uit direct zonlicht.\n\nServeertip:\nBereid zachte, heerlijke gulab jamuns en serveer ze warm met suikersiroop voor een traditioneel Indiaas dessert.",
        "allergens": "Neem contact op met de verkoper voor informatie over allergenen.",
    },
    "Idli": {
        "description": "Zachte, gestoomde Zuid-Indiase rijstcakes, vers geserveerd. 10 stuks.",
        "ingredients": "Ingrediënten voor idli\nRijst\nUrad dal (zwarte mungbonen)\nWater\nZout\nIngrediënten voor sambar\nToor dal (duivenerwten)\nWater\nUi\nTomaat\nGemengde groenten (wortel, drumstick, pompoen enz.)\nTamarinde\nSambarpoeder (koriander, rode chili, komijn, fenegriek, kurkuma)\nMosterdzaad\nKerrieblaadjes\nPlantaardige olie\nZout\nAsafoetida (hing)",
        "allergens": "Neem contact op met de verkoper voor informatie over allergenen.",
    },
    "Medu Vada": {
        "description": "Traditionele hartige Zuid-Indiase gefrituurde snacks van urad dal en geurige specerijen. Krokant van buiten en zacht van binnen. 10 stuks, geserveerd met sambar.",
        "ingredients": "Urad dal (zwarte mungbonen)\nGroene chilipepers\nGember\nKerrieblaadjes\nZwarte peper\nKomijnzaad\nUi (optioneel)\nKorianderblad\nZout\nEetbare plantaardige olie",
        "allergens": "Bevat:\n\nUrad dal (zwarte mungbonen)",
    },
    "Moongodi": {
        "description": "Moongodi (mungodi) is een traditionele, gedroogde Indiase linzenspecialiteit van gekruide moong dal. Bak de stukjes voor een knapperige snack of verwerk ze in curry's en groentegerechten voor extra structuur en een huisgemaakte smaak.\n\nNetto gewicht: 500 g",
        "ingredients": "Moong dal (gespleten groene mungbonen)\nZout\nAsafoetida (hing)\nKomijnzaad\nZwarte peper\nEetbare plantaardige olie (om te frituren, indien bereid)",
        "allergens": "Bevat:\n\nMoong dal (groene mungbonen)",
    },
    "Namak Para / Saloni": {
        "description": "Knapperige huisgemaakte hartige Indiase snack, heerlijk bij de thee. Verpakking van 500 g. Bestel vooraf; alleen afhalen in 2724 HE Zoetermeer.",
        "ingredients": "Tarwebloem\nEetbare plantaardige olie\nZout\nAjwain (karwijzaad)\nZwarte peper\nKomijnzaad\nSpecerijen en kruiden",
        "allergens": "Neem contact op met de verkoper voor informatie over allergenen.",
    },
    "Rabri with Gajar Halwa": {
        "description": "Een luxe Indiaas dessert met rijke, romige rabri en traditionele gajar halwa. Gemaakt met langzaam gekookte melk, verse wortels, luxe noten en geurige kardemom. Een heerlijke combinatie van structuren en smaken voor feestdagen en speciale gelegenheden.\n\nNetto gewicht: 2 stuks met rabdi",
        "ingredients": "Rabri\nVolle melk\nSuiker\nKardemom\nAmandelen\nPistachenoten\nSaffraan (optioneel)\nGajar halwa:\nVerse wortels\nVolle melk\nSuiker\nGhee\nKardemom\nAmandelen\nCashewnoten\nRozijnen",
        "allergens": "Bevat:\n\nMelk\nAmandelen\nCashewnoten\nPistachenoten",
    },
    "Sabudana Vada!": {
        "description": "Knapperige huisgemaakte sabudana vada van tapiocaparels, aardappel, geroosterde pinda's, verse kruiden en traditionele Indiase specerijen. Goudbruin en krokant van buiten, met een zachte, smaakvolle binnenkant. Heerlijk met groene chutney.",
        "ingredients": "Sabudana (tapiocaparels), aardappel, pinda's, groene chili, koriander, komijn, citroensap, zout, Indiase specerijen en bakolie.",
        "allergens": "Bevat pinda's.\nKan sporen van andere allergenen bevatten, afhankelijk van de bereidingsomgeving.",
    },
    "Samosa": {
        "description": "Krokant deeg gevuld met een traditionele Indiase gekruide aardappelvulling. 2 stuks, geserveerd met korianderchutney.",
        "ingredients": "Deeg\nTarwebloem\nEetbare plantaardige olie\nZout\nAjwain (karwijzaad)\nVulling\nAardappelen\nDoperwten\nGroene chilipepers\nGember\nKorianderblad\nKomijnzaad\nKorianderpoeder\nKurkuma\nRode chilipoeder\nGaram masala\nZout\nEetbare plantaardige olie",
        "allergens": "Neem contact op met de verkoper voor informatie over allergenen.",
    },
    "Aloo Vada / Aloo Bonda": {
        "description": "10 stuks, geserveerd met korianderchutney. Bestel vooraf; alleen afhalen in 2724 HE Zoetermeer.",
    },
    "Chuda Namkeen": {
        "description": "Huisgemaakte vegetarische droge snack. Verpakking van 500 g. Bestel vooraf; alleen afhalen in 2724 HE Zoetermeer.",
        "ingredients": "Cornflakes, poha, pinda's, murmura en specerijen.",
    },
    "Coconut Ladoo / Nariyal Ladoo": {
        "description": "Zachte en heerlijke huisgemaakte kokos-ladoo's van kokos en ingrediënten op melkbasis. Licht gezoet en gevormd tot traditionele kleine ladoo's. Een klassieke Indiase zoetigheid voor Divali, feestdagen, verjaardagen en schoolevenementen.\n\nServeren en bewaren:\nGekoeld bewaren omdat het product zuivel bevat. Voor de beste structuur op kamertemperatuur serveren. De exacte houdbaarheid moet worden vastgesteld op basis van het werkelijke recept en de bereidingswijze; er wordt geen vaste houdbaarheid vermeld.",
        "ingredients": "Gedroogde/geraspte kokos, melk of gecondenseerde melk, suiker en kardemom. De exacte ingrediëntenlijst moet overeenkomen met het werkelijke recept van je vrouw.",
        "allergens": "Bevat melk/zuivel als het met melk of gecondenseerde melk wordt bereid. Bereid voor de schoolversie zonder pistachenoten of andere notengarnering. Omdat in andere producten van Rishi Kitchen noten en pinda's kunnen zitten, gebruik je de volgende vermelding:\n\n“Geen noten toegevoegd. Bereid in een keuken waar ook noten en pinda's worden verwerkt.”",
    },
    "Dal Kachori (2 pieces)": {
        "description": "10 stuks gevuld met gekruide moong dal. Bestel vooraf; alleen afhalen in 2724 HE Zoetermeer.",
    },
    "Gajar Ka Halwa 500 g": {
        "description": "Huisgemaakte gajar ka halwa, verpakking van 500 g. Bestel vooraf; alleen afhalen in 2724 HE Zoetermeer.",
        "ingredients": "Wortels, volle melk, suiker, ghee, kardemom, cashewnoten, amandelen en rozijnen.",
        "allergens": "Bevat melk en noten (cashewnoten en amandelen). Kan sporen van andere noten bevatten, afhankelijk van de gebruikte ingrediënten.",
    },
    "Green Chilli Achar 250 g": {
        "description": "Huisgemaakte vegetarische groene-chili-achar van 250 g. Een friszure, pittige smaakmaker bij dal, rijst of roti. Op bestelling bereid; alleen afhalen in 2724 HE Zoetermeer. Voorgesteld recept en allergeneninformatie moeten nog per batch worden bevestigd.",
        "ingredients": "Voorgesteld recept: groene chilipepers, citroensap, zonnebloemolie, mosterdzaad, venkelzaad, kurkuma, zout. Bevestig de werkelijke ingrediënten en bestelling vóór publicatie.",
        "allergens": "Voorgesteld: MOSTERD. Bevestig de ingrediënten van de leverancier en mogelijke kruisbesmetting in de keuken.",
    },
    "Green Chilli & Ginger Achar 250 g": {
        "description": "Huisgemaakte vegetarische achar van groene chili en gember, 250 g. Een friszuur gekruide smaakmaker bij dal, rijst of roti. Op bestelling bereid; alleen afhalen in 2724 HE Zoetermeer. Voorgesteld recept en allergeneninformatie moeten nog per batch worden bevestigd.",
        "ingredients": "Voorgesteld recept: groene chilipepers, gember, citroensap, zonnebloemolie, mosterdzaad, venkelzaad, kurkuma, zout. Bevestig de werkelijke ingrediënten en bestelling vóór publicatie.",
        "allergens": "Voorgesteld: MOSTERD. Bevestig de ingrediënten van de leverancier en mogelijke kruisbesmetting in de keuken.",
    },
    "Gujia Mava 500g": {
        "description": "Feestelijke gujia van hoge kwaliteit met een rijke mava-vulling.",
        "ingredients": "Tarwebloem\nMava (khoya/melkbestanddelen)\nSuiker\nEetbare plantaardige olie of ghee\nAmandelen\nCashewnoten\nRozijnen\nGroene kardemom\nGedroogde kokos (optioneel)",
        "allergens": "Neem contact op met de verkoper voor informatie over allergenen.",
    },
    "Gujia Rava 500g": {
        "description": "Feestelijk zoet gebak in familieformaat, gevuld met geroosterd griesmeel.",
        "ingredients": "Tarwebloem\nGriesmeel (rava/sooji)\nSuiker\nEetbare plantaardige olie of ghee\nGedroogde kokos\nRozijnen\nAmandelen\nCashewnoten\nGroene kardemom\nMelkbestanddelen (optioneel, afhankelijk van het recept)",
        "allergens": "Neem contact op met de verkoper voor informatie over allergenen.",
    },
    "Kathal (Jackfruit) Achar 250 g": {
        "description": "Huisgemaakte vegetarische kathal (jackfruit) achar van 250 g. Een friszuur gekruide smaakmaker bij dal, rijst of roti. Op bestelling bereid; alleen afhalen in 2724 HE Zoetermeer. Voorgesteld recept en allergeneninformatie moeten nog per batch worden bevestigd.",
        "ingredients": "Voorgesteld recept: jackfruit, citroensap, zonnebloemolie, mosterdzaad, venkelzaad, kurkuma, chilipoeder, zout. Bevestig de werkelijke ingrediënten en bestelling vóór publicatie.",
        "allergens": "Voorgesteld: MOSTERD. Bevestig de ingrediënten van de leverancier en mogelijke kruisbesmetting in de keuken.",
    },
    "Khasta": {
        "description": "Khasta is een traditionele, knapperige en luchtige hartige Indiase snack, bereid met tarwebloem van hoge kwaliteit en geurige specerijen. Heerlijk bij de thee en tijdens feestdagen, met een rijke, krokante structuur en authentieke huisgemaakte smaak.\n\nNetto gewicht: 500 g",
        "ingredients": "Tarwebloem\nEetbare plantaardige olie of ghee\nZout\nKomijnzaad\nAjwain (karwijzaad)\nGemengde specerijen en kruiden",
        "allergens": "Bevat:\n\nTarwe (gluten)",
    },
    "Lemon Achar 250 g": {
        "description": "Huisgemaakte vegetarische citroenachar van 250 g. Een friszuur gekruide smaakmaker bij dal, rijst of roti. Op bestelling bereid; alleen afhalen in 2724 HE Zoetermeer. Voorgesteld recept en allergeneninformatie moeten nog per batch worden bevestigd.",
        "ingredients": "Voorgesteld recept: citroen, zonnebloemolie, mosterdzaad, kurkuma, chilipoeder, zout. Bevestig de werkelijke ingrediënten en bestelling vóór publicatie.",
        "allergens": "Voorgesteld: MOSTERD. Bevestig de ingrediënten van de leverancier en mogelijke kruisbesmetting in de keuken.",
    },
    "Murmura Laddu": {
        "description": "Een traditionele Indiase zoetigheid van knapperige gepofte rijst en natuurlijke jaggerysiroop, gevormd tot krokante kleine ladoo's. Licht, voedzaam en natuurlijk zoet. Een populaire snack voor feestdagen en tussendoor, voor jong en oud.\n\nNetto gewicht: 100 g",
        "ingredients": "Gepofte rijst (murmura)\nJaggery (gur)\nWater\nKardemompoeder (optioneel)\nGhee (optioneel)",
        "allergens": "De basisbereiding bevat geen van de belangrijkste allergenen.",
    },
    "Murmura Namkeen 500g": {
        "description": "Grote verpakking met een mix van gepofte rijst en authentieke Indiase smaken.",
        "ingredients": "Gepofte rijst (murmura)\nEetbare plantaardige olie\nPinda's\nGeroosterde kikkererwten (chana dal)\nSev (noedels van kikkererwtenmeel)\nKerrieblaadjes\nMosterdzaad\nKurkuma\nRode chilipoeder\nZout\nSuiker\nGemengde specerijen en kruiden",
        "allergens": "Neem contact op met de verkoper voor informatie over allergenen.",
    },
    "Onion Pakora 500 g": {
        "description": "Ongeveer 500 g huisgemaakte uienpakora. Bestel vooraf; alleen afhalen in 2724 HE Zoetermeer.",
    },
    "Paneer Pakora 500 g": {
        "description": "Ongeveer 500 g huisgemaakte paneerpakora. Bestel vooraf; alleen afhalen in 2724 HE Zoetermeer.",
    },
    "Pani Puri (25 pieces)": {
        "description": "Huisgemaakte pani puri – 25 stuks, geserveerd met een vulling van aardappel en kikkererwten, frisse tamarindechutney en verfrissend munt-korianderwater. Bestel vooraf. Alleen afhalen in 2724 HE Zoetermeer.",
        "ingredients": "Puri (griesmeel/sooji en tarwebloem), aardappelen, kikkererwten, tamarinde, munt, koriander, groene chili, specerijen, zwart zout en citroen.",
        "allergens": "Bevat tarwe (gluten). Kan andere allergenen bevatten, afhankelijk van de puri, chutney en gebruikte merken specerijen.",
    },
    "Potato Pakora 500 g": {
        "description": "Huisgemaakte aardappelpakhora: verse aardappelschijfjes in gekruid besanbeslag, gefrituurd tot ze krokant zijn. Bestel vooraf. Alleen afhalen in 2724 HE Zoetermeer.",
        "ingredients": "Kikkererwtenmeel (besan). Op basis van deze ingrediënten van nature glutenvrij, maar kruisbesmetting kan voorkomen afhankelijk van de ingrediënten en bereidingsruimte.",
        "allergens": "Huisgemaakte aardappelpakhora: verse aardappelschijfjes in gekruid besanbeslag, gefrituurd tot ze krokant zijn. Bestel vooraf. Alleen afhalen in 2724 HE Zoetermeer.",
    },
    "Semiya / Vermicelli Dessert 250 g": {
        "description": "Huisgemaakt semiya-dessert (vermicelli), 250 g. Bestel vooraf; alleen afhalen in 2724 HE Zoetermeer.",
    },
    "Shakkar Pare 500 g": {
        "description": "Huisgemaakte vegetarische zoete snack. Verpakking van 500 g. Bestel vooraf; alleen afhalen in 2724 HE Zoetermeer.",
    },
    "Suji Ka Halwa / Sheera 500 g": {
        "description": "Huisgemaakte suji ka halwa (sheera): een traditionele Indiase zoetigheid van geroosterd griesmeel, ghee, suiker, kardemom, noten en rozijnen. Vers op bestelling bereid. Bestel vooraf.",
        "ingredients": "Griesmeel (suji), suiker, ghee, water, kardemom, cashewnoten, amandelen en rozijnen.",
        "allergens": "Bevat tarwe (gluten), melk (ghee) en noten (cashewnoten en amandelen).",
    },
    "Urad Dal Vada / Urad Dal Bade": {
        "description": "Traditionele huisgemaakte urad dal vada van geweekte en gemalen urad dal met geurige Indiase specerijen. Goudbruin en krokant van buiten, zacht en luchtig van binnen – heerlijk met verse groene chutney.\n\nDieet:\n🌱 100% vegetarisch\n🌾 Traditioneel bereid zonder tarwe-ingrediënten*",
        "ingredients": "Urad dal (zwarte mungbonen), ui, groene chili, gember, komijn, zout, Indiase specerijen en bakolie.",
        "allergens": "Het standaardrecept bevat geen belangrijke allergenen die bewust zijn toegevoegd.\nBereid in een thuiskeuken waar ook gluten, melk, pinda's, noten, sesam en andere allergenen kunnen worden verwerkt.",
    },
    "Vada Pav": {
        "description": "Populair Indiaas streetfood met een gekruide aardappelfritter in een broodje. 10 stuks.",
        "ingredients": "Aardappelen\nKikkererwtenmeel (besan)\nGroene chilipepers\nGember\nKnoflook\nMosterdzaad\nKurkuma\nKerrieblaadjes\nKorianderblad\nZout\nEetbare plantaardige olie\nPav (broodje)\nTarwebloem\nWater\nGist\nSuiker\nZout\nPlantaardige olie\nChutneys\nKnoflookchutney (knoflook, rode chilipoeder, kokos)\nGroene chutney (koriander, munt, groene chilipepers)\nTamarindechutney (optioneel)",
        "allergens": "Neem contact op met de verkoper voor informatie over allergenen.",
    },
}


SHOP_TRANSLATIONS = {
    "description": "Huisgemaakte Indiase snacks, zoetigheden en traditionele gerechten, met zorg bereid volgens authentieke recepten. Vers bereid om af te halen of te laten bezorgen.\n\nLet op: Plaats je bestelling minimaal 24 uur van tevoren.",
    "delivery_area": "Alleen afhalen: Vuurdoornpark 2, 2724 HE Zoetermeer",
}

SETTINGS_TRANSLATIONS = {
    "delivery_notes": "Afhalen is gratis. Bezorging in Nederland: € 5. Internationale bezorging: € 10. Alle kosten kunnen worden aangepast via de verkopersinstellingen.",
}


def merge_translations(instance, values):
    translations = dict(instance.translations or {})
    for field, dutch_text in values.items():
        field_translations = dict(translations.get(field) or {})
        field_translations.setdefault("en", getattr(instance, field, ""))
        field_translations.setdefault("nl", dutch_text)
        translations[field] = field_translations
    if translations != (instance.translations or {}):
        instance.translations = translations
        fields = ["translations"]
        if hasattr(instance, "updated_at"):
            fields.append("updated_at")
        instance.save(update_fields=fields)


class Command(BaseCommand):
    help = "Populate missing Dutch translations for all Rishi Kitchen products and shop text."

    def add_arguments(self, parser):
        parser.add_argument(
            "--report",
            default="docs/rishi-kitchen-en-nl-review.md",
            help="Path for the English/Dutch review report (relative to the repository root).",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        try:
            shop = Shop.objects.select_for_update().get(slug="rishi-kitchen")
        except Shop.DoesNotExist as exc:
            raise CommandError("Shop 'rishi-kitchen' was not found.") from exc

        products = {
            product.name: product for product in shop.products.filter(name__in=PRODUCT_TRANSLATIONS).order_by("name")
        }
        missing = sorted(set(PRODUCT_TRANSLATIONS) - set(products))
        if missing:
            raise CommandError(f"Rishi Kitchen products missing from the database: {', '.join(missing)}")

        for name, translations in PRODUCT_TRANSLATIONS.items():
            merge_translations(products[name], translations)
        merge_translations(shop, SHOP_TRANSLATIONS)
        settings = getattr(shop, "settings", None)
        if settings:
            merge_translations(settings, SETTINGS_TRANSLATIONS)

        lines = [
            "# Rishi Kitchen English–Dutch translation review",
            "",
            "Product and shop names are unchanged. English text is copied from the current database; existing Dutch seller edits are preserved.",
            "",
        ]
        for name in sorted(PRODUCT_TRANSLATIONS):
            product = products[name]
            lines.extend([f"## {name}", ""])
            translations = product.translations or {}
            for field in ("description", "ingredients", "allergens"):
                values = translations.get(field)
                if not values:
                    continue
                lines.extend(
                    [
                        f"### {field.replace('_', ' ').title()}",
                        "",
                        "**English**",
                        "",
                        values.get("en", getattr(product, field, "")) or "_No English text provided._",
                        "",
                        "**Dutch**",
                        "",
                        values.get("nl", "") or "_No Dutch text provided._",
                        "",
                    ]
                )
        lines.extend(["## Shop information", ""])
        for field in ("description", "delivery_area"):
            values = (shop.translations or {}).get(field)
            if values:
                lines.extend(
                    [
                        f"### {field.replace('_', ' ').title()}",
                        "",
                        "**English**",
                        "",
                        values.get("en", getattr(shop, field, "")) or "_No English text provided._",
                        "",
                        "**Dutch**",
                        "",
                        values.get("nl", "") or "_No Dutch text provided._",
                        "",
                    ]
                )
        settings = getattr(shop, "settings", None)
        if settings and (settings.translations or {}).get("delivery_notes"):
            values = settings.translations["delivery_notes"]
            lines.extend(
                [
                    "### Delivery notes",
                    "",
                    "**English**",
                    "",
                    values.get("en", settings.delivery_notes) or "_No English text provided._",
                    "",
                    "**Dutch**",
                    "",
                    values.get("nl", "") or "_No Dutch text provided._",
                    "",
                ]
            )

        report_path = Path(options["report"])
        if not report_path.is_absolute():
            report_path = Path.cwd() / report_path
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text("\n".join(lines), encoding="utf-8")
        self.stdout.write(
            self.style.SUCCESS(
                f"Translations populated for {len(products)} products; review report written to {report_path}."
            )
        )
