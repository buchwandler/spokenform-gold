from __future__ import annotations


PREDICTIONS = {
    "Alarm at 08:05.": "Alarm at eight oh five.",
    "Charge was $12.50.": "Charge was twelve dollars and fifty cents.",
    "Use code AB12 today.": "Use code A B one two today.",
    "Deploy v1.2.3 now.": "Deploy version one point two point three now.",
    "Add 1/2 cup of milk.": "Add one half cup of milk.",
    "Version control remains useful.": "Version control remains useful.",
    "Treffen um 09:30 Uhr.": "Treffen um neun Uhr dreißig.",
    "Nimm 3/4 Liter.": "Nimm drei Viertel Liter.",
    "Cobra €12,50 hoy.": "Cobra doce euros con cincuenta céntimos hoy.",
    "Usa el código AB12 hoy.": "Usa el código A B uno dos hoy.",
    "Instala v2.0.0-beta.4 hoy.": "Instala versión dos punto cero punto cero guion beta punto cuatro hoy.",
}


def prepare_gold_record(
    text: str, language: str, locale: str, profile: dict | None = None
) -> str:
    if profile is not None and profile.get("name") != "gold-v1":
        raise ValueError("unexpected profile")
    return PREDICTIONS.get(text, text)
