from __future__ import annotations

import re
import unicodedata

CATEGORY_ALIASES = {
    "guitar": 1,
    "guitars": 1,
    "electric guitar": 1,
    "electric guitars": 1,
    "guitarra": 1,
    "guitarras": 1,
    "bass": 2,
    "basses": 2,
    "bass guitar": 2,
    "bass guitars": 2,
    "electric bass": 2,
    "electric basses": 2,
    "electric bass guitar": 2,
    "electric bass guitars": 2,
    "acoustic bass": 2,
    "acoustic basses": 2,
    "double bass": 2,
    "upright bass": 2,
    "baixo": 2,
    "baixos": 2,
    "drum": 3,
    "drums": 3,
    "bateria": 3,
    "baterias": 3,
    "percussion": 3,
    "keyboard": 4,
    "keyboards": 4,
    "piano": 4,
    "pianos": 4,
    "teclado": 4,
    "teclados": 4,
    "synthesizer": 4,
    "synthesizers": 4,
    "acoustic guitar": 5,
    "acoustic guitars": 5,
    "classical guitar": 5,
    "classical guitars": 5,
    "violao": 5,
    "violoes": 5,
    "woodwind": 6,
    "woodwinds": 6,
    "flute": 6,
    "flutes": 6,
    "saxophone": 6,
    "saxophones": 6,
    "clarinet": 6,
    "clarinets": 6,
    "brass": 7,
    "trumpet": 7,
    "trumpets": 7,
    "trombone": 7,
    "trombones": 7,
    "orchestral strings": 8,
    "violin": 8,
    "violins": 8,
    "cello": 8,
    "cellos": 8,
    "ukulele": 9,
    "ukuleles": 9,
}

CATALOG_QUERY_SYNONYMS = {
    "acoustic guitars": "violão",
    "acoustic guitar": "violão",
    "classical guitars": "violão",
    "classical guitar": "violão",
    "electric guitars": "guitarra",
    "electric guitar": "guitarra",
    "guitars": "guitarra violão",
    "guitar": "guitarra violão",
    "bass guitars": "baixo",
    "bass guitar": "baixo",
    "electric bass guitars": "baixo",
    "electric bass guitar": "baixo",
    "electric basses": "baixo",
    "electric bass": "baixo",
    "acoustic basses": "baixo",
    "acoustic bass": "baixo",
    "double bass": "baixo",
    "upright bass": "baixo",
    "basses": "baixo",
    "bass": "baixo",
    "drums": "bateria",
    "drum": "bateria",
    "percussion": "bateria percussão",
    "keyboards": "teclado",
    "keyboard": "teclado",
    "pianos": "piano teclado",
    "piano": "piano teclado",
    "synthesizers": "sintetizador teclado",
    "synthesizer": "sintetizador teclado",
    "ukuleles": "ukulele",
    "ukulele": "ukulele",
    "violins": "violino",
    "violin": "violino",
    "cellos": "violoncelo",
    "cello": "violoncelo",
    "flutes": "flauta",
    "flute": "flauta",
    "saxophones": "saxofone",
    "saxophone": "saxofone",
    "trumpets": "trompete",
    "trumpet": "trompete",
    "trombones": "trombone",
    "trombone": "trombone",
}

POLICY_QUERY_SYNONYMS = {
    "change of mind": "arrependimento devolução",
    "return policy": "devolução arrependimento",
    "returns": "devolução troca reembolso",
    "return": "devolução troca reembolso",
    "refund": "reembolso devolução",
    "withdrawal": "arrependimento devolução",
    "exchanges": "troca trocas",
    "exchange": "troca trocas",
    "warranty": "garantia",
    "shipping": "frete entrega",
    "delivery": "entrega frete",
    "freight": "frete",
    "payment": "pagamento",
    "payments": "pagamento",
    "installments": "parcelamento parcelas",
    "installment": "parcelamento parcelas",
    "promotions": "promoção promoções desconto",
    "promotion": "promoção promoções desconto",
    "discount": "desconto promoção",
    "hours": "horário funcionamento",
    "opening": "horário funcionamento",
    "open": "horário funcionamento",
    "privacy": "privacidade dados",
    "accessories": "acessórios cordas palhetas cabos cases pedais amplificadores",
    "accessory": "acessórios cordas palhetas cabos cases pedais amplificadores",
    "strings": "cordas acessórios",
    "picks": "palhetas acessórios",
    "cables": "cabos acessórios",
    "cases": "cases acessórios",
    "pedals": "pedais acessórios",
    "amplifiers": "amplificadores acessórios",
    "defect": "defeito",
    "defective": "defeito",
    "preference": "preferência",
    "tracking": "rastreamento",
    "address": "endereço",
    "contact": "contato",
    "tone": "tom voz",
    "voice": "tom voz",
}


def normalize_text(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text or "")
    return "".join(char for char in decomposed if not unicodedata.combining(char)).casefold().strip()


def _expand(query: str, mapping: dict[str, str]) -> str:
    normalized = normalize_text(query)
    additions: list[str] = []
    for phrase in sorted(mapping, key=len, reverse=True):
        pattern = rf"\b{re.escape(phrase)}\b"
        if re.search(pattern, normalized):
            additions.append(mapping[phrase])
            normalized = re.sub(pattern, " ", normalized)
    if not additions:
        return query
    return f"{query} {' '.join(additions)}"


def expand_catalog_query(query: str) -> str:
    return _expand(query, CATALOG_QUERY_SYNONYMS)


def expand_policy_query(query: str) -> str:
    return _expand(query, POLICY_QUERY_SYNONYMS)


def resolve_category_id(category: str) -> int | None:
    return CATEGORY_ALIASES.get(normalize_text(category))


def resolve_query_category_ids(query: str) -> set[int] | None:
    normalized = normalize_text(query)
    matches: list[tuple[int, int, int, str]] = []
    for phrase, category_id in CATEGORY_ALIASES.items():
        pattern = rf"\b{re.escape(phrase)}\b"
        for match in re.finditer(pattern, normalized):
            matches.append((match.start(), match.end(), category_id, phrase))
    if not matches:
        return None

    selected: list[tuple[int, int, int, str]] = []
    occupied: list[tuple[int, int]] = []
    for start, end, category_id, phrase in sorted(
        matches, key=lambda item: (-(item[1] - item[0]), item[0])
    ):
        if any(not (end <= used_start or start >= used_end) for used_start, used_end in occupied):
            continue
        occupied.append((start, end))
        selected.append((start, end, category_id, phrase))

    category_ids: set[int] = set()
    for _, _, category_id, phrase in selected:
        if category_id == 1 and phrase in {"guitar", "guitars"}:
            category_ids.update({1, 5})
        else:
            category_ids.add(category_id)
    return category_ids or None
