#!/usr/bin/env python3
"""Детерминиран брояч на нарушенията на правилата за прост български.

Брои механичните нарушения, които регулярен израз може да хване: дължина на
изречението, забранени модални думи, минало неопределено време, страдателен
залог със „съм“ и „бъда“, деепричастия, причастни обороти след запетая, точка
и запетая, тирета между твърдения, съкращения („т.е.“, „напр.“), слоп и
канцеларщина, отглаголни съществителни вместо глагол, условие след командата,
верига от „на“ и смяна на синоними.

Граница: това е проход с регулярни изрази, а не граматичен анализатор. Той
пропуска нарушения (няма проверка за част на речта и за членуване) и може да
сгреши границите на изреченията в необичаен Markdown. Числата от него са
сравними между два текста от една и съща версия. Те не са оценка за
съответствие.

Употреба:
  python3 bg_lint.py --type procedural file.md
  cat text.md | python3 bg_lint.py --type descriptive -
  python3 bg_lint.py --type reply file.md
  python3 bg_lint.py --self-test
"""
import json
import pathlib
import re
import sys
from collections import Counter

W = r"[^\W\d_]"  # буква (кирилица или латиница)


def word(pattern):
    """Цяла дума или фраза: без буква отляво и отдясно."""
    return r"(?<!\w)(?:" + pattern + r")(?!\w)"


BANNED_MODALS = re.compile(word(
    r"би|бих|бихме|бихте|биха|следва\s+да|евентуалн\w*|вероятно|"
    r"възможно\s+е\s+да|препоръчително\s+е"), re.I)

# Минало неопределено: спомагателно „съм“ + минало деятелно причастие на -л.
PERFECT = re.compile(
    r"(?<!\w)(?:съм|си|е|сме|сте|са)\s+(?:бил[аои]?\s+)?(\w+[аяиеъ]л[аои]?)(?!\w)", re.I)
# Съществителни и прилагателни на -л, които не са причастия.
NOT_PARTICIPLE = {
    "материал", "сигнал", "канал", "терминал", "портал", "интервал", "потенциал",
    "капитал", "персонал", "журнал", "идеал", "финал", "локал", "стил", "профил",
    "модел", "панел", "тунел", "кернел", "пиксел", "хотел", "цял", "цяла", "цяло",
    "бял", "бяла", "бяло", "мил", "мила", "мило", "инал", "оригинал", "минимал",
    "спектрал", "дял", "дела", "цел", "цели", "цела", "числа", "мисъл", "смисъл",
    "правило", "правила", "сила", "крило", "масло", "дело", "село", "тяло", "стрела", "мебел",
}

PASSIVE = re.compile(word(
    r"(?:бъде|бъдат|бъдем|бъдете|бе|беше|бяха|бил|била|било|били)\s+"
    r"\w+(?:[аяеи]н|[аяеи]т)(?:[аои]|ия|ият|ата|ото|ите)?"), re.I)

GERUND = re.compile(word(r"\w{3,}[аеяиу]йки"), re.I)

PARTICIPLE_CLAUSE = re.compile(r",\s*(\w+(?:ащ|ящ|ещ)(?:[аои]|ия|ият|ата|ото|ите)?)(?!\w)", re.I)
# Нечленувано причастие в началото на изречението, после допълнение и запетая: „Засягащ въпроса за таксите, докладът…“.
LEADING_CLAUSE = re.compile(r"(?:^|(?<=[.!?:]\s))[ \t]*(\w+(?:ащ|ящ|ещ)[аои]?)\s[^,.!?\n]{1,80},", re.M)
NOT_CLAUSE = re.compile(r"^(следващ|подходящ|настоящ|предходящ|предстоящ|съществуващ|текущ|действащ|защото|нещо|още|общ|вещ|мощ|помощ|пещ)", re.I)

ABBREV = re.compile(
    r"(?<!\w)(т\.\s?е\.|напр\.|и\s+т\.\s?н\.?|и\s+др\.|т\.\s?нар\.|e\.g\.|i\.e\.|etc\.?)(?=[\s,)]|$)", re.I)

# Глагол и отглаголно съществително вместо един глагол (наръчникът на ЕК, съвет 6).
NOMINAL = re.compile(word(
    r"(?:извършван|провеждан|осъществяван|вземан|изготвян|предприеман)\w*\s+на|"
    r"(?:прав|направ|провед|провежд|изготв|изготвя|вз[еи]м|предприем)\w*\s+"
    r"(?:преглед|оценка|анализ|разследване|решение|смяна|промяна|избор|опит)\w*|"
    r"(?:дад|дав)\w*\s+препоръка\w*"), re.I)

SLOP_CORE = r"просто|лесно|елементарно|безпроблемно"
SLOP_TSV = pathlib.Path(__file__).resolve().parent / "slop.tsv"


def slop_pattern():
    """Обединение на основния списък и evals/slop.tsv (регулярен израз, пример, заместител)."""
    terms = [SLOP_CORE]
    if SLOP_TSV.exists():
        for line in SLOP_TSV.read_text(encoding="utf-8").splitlines():
            if not line.strip() or line.startswith("#"):
                continue
            term = line.split("\t")[0].strip()
            if term:
                terms.append(term)
    return re.compile(word("|".join(terms)), re.I)


SLOP = slop_pattern()

# Само „ако“: „когато“ в описателен текст обикновено описва поведение, а не условие.
TRAILING_COND = re.compile(r"\sако\s", re.I)

DASH = re.compile(r"—|(?<!\d)–(?!\d)|(?<= )--(?= )|(?<=[^\s\d]{2}) - (?=[^\s\d]{2})")

NOUN_CHAIN = re.compile(
    r"(?<!\w)на\s+(?:[^\s.!?;:]+\s+){1,3}?на\s+(?:[^\s.!?;:]+\s+){1,3}?на(?!\w)", re.I)

ROTATION_SETS = [
    # Правило 8 засяга глагола в инструкцията („проверете“). Съществителното „проверка“ е термин и остава.
    ("провери-увери", [
        ("провер", r"провер(?:ете|ите|и|явайте|явай)"), ("верифиц", r"верифицир(?:айте|ате|ай)"),
        ("валидир", r"валидир(?:айте|ате|ай)"), ("потвърд", r"потвърд(?:ете|ите|и)"),
        ("удостовер", r"удостовер(?:ете|ите|и)"),
        ("увер", r"увер(?:ете|и|явам|явайте|яват|ява)\s+се"),
    ]),
    ("конфигурация-настройки", [
        ("конфигурац", r"конфигурац\w*"), ("конфиг", r"конфиг(?!у)\w*"), ("настройк", r"настройк\w*"),
    ]),
]
ROTATION_RX = [(name, [(key, re.compile(word(rx), re.I)) for key, rx in members]) for name, members in ROTATION_SETS]

LIMITS = {"procedural": 20, "descriptive": 25}


LINT_OFF = re.compile(r"<!--\s*bg-lint off\s*-->.*?(<!--\s*bg-lint on\s*-->|\Z)", re.S)


def blank(m):
    """Заменя съвпадението с толкова нови редове, колкото има в него. Номерата на редовете остават верни."""
    return "\n" * m.group(0).count("\n")


def strip_code(text):
    text = re.sub(r"\A---\n.*?\n---\n", blank, text, flags=re.S)  # YAML frontmatter
    text = LINT_OFF.sub(blank, text)  # нарочно лоши примери и списъци със забранени думи
    text = re.sub(r"<!--.*?-->", blank, text, flags=re.S)
    text = re.sub(r"</(p|th|td|li|tr|div|h[1-6])>", ". ", text, flags=re.I)  # края на HTML блок е края на изречение
    text = re.sub(r"</?[a-zA-Z][^>\n]*>", " ", text)
    text = re.sub(r"^[ \t]*>[ \t]?", "", text, flags=re.M)  # цитираният блок се проверява като обикновен текст
    # Цитатът и кодът са една дума (правило 8.6). Препинателният знак след тях не е отделна дума.
    text = re.sub(r"„[^“\n]{0,300}“", " QUOTE", text)
    text = re.sub(r"```.*?```", blank, text, flags=re.S)
    text = re.sub(r"`[^`\n]+`", " CODESPAN", text)
    text = re.sub(r"^#+\s.*$", " ", text, flags=re.M)  # заглавията са изключени (8.6)
    text = re.sub(r"https?://\S+", " URL ", text)
    # [ \t] вместо \s: шаблонът не трябва да поглъща новите редове, иначе номерата на редовете се разминават.
    text = re.sub(r"^[ \t]*\|[ \t:|-]+\|[ \t]*$", " ", text, flags=re.M)  # разделител в таблица
    text = re.sub(r"^[ \t]*\|(.*)\|[ \t]*$",
                  lambda m: ". ".join(c.strip() for c in m.group(1).split("|") if c.strip()) + ". ",
                  text, flags=re.M)  # всяка клетка е отделна единица
    return text


def sentences(text):
    # Всеки елемент от списък става отделно изречение.
    text = re.sub(r"^\s*([-*]|\d+\.)\s+(.*?)([.!?:])?\s*$",
                  lambda m: m.group(2) + (m.group(3) or ".") + " ", text, flags=re.M)
    parts = re.split(r"(?<=[.!?:])\s+", text)
    return [p.strip() for p in parts if len(p.strip().split()) >= 2]


def trailing_condition(s):
    m = TRAILING_COND.search(s)
    if not m or re.search(r"освен\s+ако", s[max(0, m.start() - 8):m.end()], re.I):
        return False
    # Условие след заглавие или празен ред е условие отпред, а не отзад.
    line_start = s.rfind("\n", 0, m.start()) + 1
    return m.start() - line_start >= 4 and not re.match(r"^ако\b", s, re.I)


def lint_detail(text, text_type):
    """Всяко нарушение с намерения текст и номера на реда.

    strip_code() запазва всеки нов ред, затова номерът на реда в изчистения
    текст е и номерът на реда в оригиналния текст.
    """
    body = strip_code(text)
    limit = LIMITS[text_type]
    hits = []

    def line_of(pos):
        return body.count("\n", 0, pos) + 1

    def add(category, m, snippet=None, group=0):
        hits.append({"category": category, "text": (snippet or m.group(group)).strip(), "line": line_of(m.start())})

    def add_sentence(category, sentence, start):
        text_out = sentence if len(sentence) <= 80 else sentence[:80] + "…"
        hits.append({"category": category, "text": text_out, "line": line_of(start)})

    pos = 0
    for s in sentences(body):
        found = body.find(s, pos)
        pos = found if found != -1 else pos
        if len(s.split()) > limit:
            add_sentence("sentence_over_limit", s, pos)
        if trailing_condition(s):
            add_sentence("trailing_condition", s, pos)
        pos += max(len(s), 1)

    for m in BANNED_MODALS.finditer(body):
        add("banned_modal", m)
    for m in PERFECT.finditer(body):
        if m.group(1).lower() not in NOT_PARTICIPLE:
            add("perfect_tense", m)
    for m in PASSIVE.finditer(body):
        add("passive_voice", m)
    for m in GERUND.finditer(body):
        add("gerund", m)
    for m in PARTICIPLE_CLAUSE.finditer(body):
        if not NOT_CLAUSE.match(m.group(1)):
            add("participle_clause", m, group=1)
    for m in LEADING_CLAUSE.finditer(body):
        if not NOT_CLAUSE.match(m.group(1)):
            hits.append({"category": "participle_clause", "text": m.group(1), "line": line_of(m.start(1))})
    for m in re.finditer(";", body):
        add("semicolon", m)
    for m in DASH.finditer(body):
        add("em_dash", m)
    for m in ABBREV.finditer(body):
        add("abbreviation", m)
    for m in SLOP.finditer(body):
        add("slop_word", m)
    for m in NOMINAL.finditer(body):
        add("nominalization", m)
    for m in NOUN_CHAIN.finditer(body):
        add("noun_chain", m)
    for name, members in ROTATION_RX:
        first = []
        for key, rx in members:
            m = rx.search(body)
            if m:
                first.append((m.start(), key, m))
        for _, key, m in sorted(first)[1:]:
            add("synonym_rotation", m, f"{m.group(0)} ({name})")

    return sorted(hits, key=lambda h: h["line"])


CATEGORIES = (
    "sentence_over_limit", "trailing_condition", "banned_modal", "perfect_tense", "passive_voice",
    "gerund", "participle_clause", "semicolon", "em_dash", "abbreviation", "slop_word", "nominalization", "noun_chain",
    "synonym_rotation",
)


def lint(text, text_type):
    body = strip_code(text)
    lengths = [len(s.split()) for s in sentences(body)]
    found = Counter(h["category"] for h in lint_detail(text, text_type))
    counts = {c: found.get(c, 0) for c in CATEGORIES}
    words = max(1, len(body.split()))
    total = sum(counts.values())
    return {
        "type": text_type,
        "words": words,
        "sentences": len(lengths),
        "mean_sentence_words": round(sum(lengths) / max(1, len(lengths)), 1),
        "longest_sentence_words": max(lengths, default=0),
        "violations": counts,
        "violations_total": total,
        "violations_per_100w": round(100.0 * total / words, 2),
    }


BOLD = re.compile(r"\*\*[^*\n]+\*\*")
HEADER = re.compile(r"^#{1,6}\s", re.M)
BULLET = re.compile(r"^\s*([-*+]|\d+[.)])\s", re.M)


def reader_check(text):
    """Какво вижда читателят в отговор в чата."""
    text = text.replace("\r\n", "\n")
    prose = re.sub(r"```.*?```", " ", text, flags=re.S)
    prose = re.sub(r"`[^`\n]+`", " CODESPAN ", prose)
    prose_no_md = re.sub(r"^\s*(#{1,6}\s|[-*+]\s|\d+[.)]\s|\|)", "", prose, flags=re.M)
    prose_no_md = re.sub(r"^\s*[\s:|-]+$", "", prose_no_md, flags=re.M)
    sents = [p for p in re.split(r"(?<=[.!?])[\"'“)\]]*\s+|\n+", prose_no_md) if len(p.strip().split()) >= 2]
    counts = {
        "sentences": len(sents),
        "em_dash": len(DASH.findall(prose)),
        "bold_spans": len(BOLD.findall(prose)),
        "headers": len(HEADER.findall(prose)),
        "bullets": len(BULLET.findall(prose)),
    }
    words = max(1, len(prose_no_md.split()))
    visible = counts["em_dash"] + counts["bold_spans"] + counts["headers"] + counts["bullets"]
    return {"type": "reply", "words": words, "counts": counts, "visible_total": visible}


def cyrillic_share(text):
    """Делът на кирилските букви сред всички букви. Хуковете пропускат текст, който не е на български."""
    letters = re.findall(W, strip_code(text))
    if not letters:
        return 0.0
    return sum(1 for ch in letters if "Ѐ" <= ch <= "ӿ") / len(letters)


SLOP_FIXTURE = """Използвайки нашия надежден механизъм за повторни опити, неуспешните качвания се повтарят автоматично, осигурявайки цялостта на данните през целия процес, който е бил проектиран от самото начало да се справя безпроблемно дори с най-сложните прекъсвания на мрежата.
Би трябвало да проверите данните си за достъп; също така прегледайте настройките, напр. времето за изчакване в конфигурацията. Свържете се с поддръжката, ако проблемът продължи."""

CLEAN_FIXTURE = """Системата повтаря неуспешното качване автоматично. Така данните остават верни.

Ако грешките продължат, уверете се, че паролата ви е вярна. Ако проблемът остане, пишете на поддръжката."""

TABLE_FIXTURE = """\
| Колона А | Колона Б | Колона В |
|----------|----------|----------|
| Клетка едно, която е много дълга и има много думи | Клетка две, която също е дълга | Клетка три |
| Още данни в тази клетка | И още данни тук | И още повече тук |
"""

LIST_FIXTURE = """\
Има следните елементи:

- Първият елемент няма точка в края на реда си
- Вторият елемент няма точка в края на реда си
- Третият елемент няма точка в края на реда си

Изречение в проза след списъка.
"""

# Само първите три тирета са тирета между твърдения.
DASH_FIXTURE = """Внедряването не успя — дискът беше пълен.
Качването не успя -- токенът изтече.
Опитът не успя – портът беше затворен.
Не използвайте --force в продукционна среда.
Прозорецът е 5–10 минути, през сезона 2024–2025.
Използвайте по-новата версия на най-бързия сървър.
Използвайте флага `--config sqlpipe.yaml`.
"""

REPLY_FIXTURE = """**Да** – лошо е.

## Защо
- Закъснението расте.
- Потребителите чакат.

Уверете се сега. После увеличете капацитета."""


def self_test():
    slop = lint(SLOP_FIXTURE, "procedural")
    v = slop["violations"]
    clean = lint(CLEAN_FIXTURE, "procedural")
    assert v["sentence_over_limit"] >= 1, slop
    assert v["banned_modal"] >= 1, slop
    assert v["perfect_tense"] >= 1, slop
    assert v["passive_voice"] >= 1, slop
    assert v["gerund"] == 2, slop
    assert v["semicolon"] == 1, slop
    assert v["abbreviation"] == 1, slop
    assert v["slop_word"] >= 2, slop
    assert v["trailing_condition"] == 1, slop
    assert v["synonym_rotation"] >= 1, slop
    assert clean["violations_total"] == 0, clean
    dashes = lint(DASH_FIXTURE, "procedural")["violations"]
    assert dashes["em_dash"] == 3, dashes
    assert lint("Процесът, обработващ заявките, спря.", "descriptive")["violations"]["participle_clause"] == 1
    assert lint("Прочетете следващата стъпка, следващата е по-кратка.", "descriptive")["violations"]["participle_clause"] == 0
    assert lint("Това е модел на данни. Това е канал за събития.", "descriptive")["violations_total"] == 0
    assert lint("Сървърът беше рестартиран.", "descriptive")["violations"]["passive_voice"] == 1
    assert lint("Екипът е добавил индекс.", "descriptive")["violations"]["perfect_tense"] == 1
    assert lint("Стойността на времето за изчакване на пула на връзките е 30 s.", "descriptive")["violations"]["noun_chain"] == 1
    assert lint("Генерирайте SSH ключове. Надеждността на услугата е 99,9%.", "descriptive")["violations_total"] == 0
    assert lint("Има и други формати, т.е. CSV и JSON и т.н.", "descriptive")["violations"]["abbreviation"] == 2
    r = reader_check(REPLY_FIXTURE)["counts"]
    assert (r["sentences"], r["em_dash"], r["bold_spans"], r["headers"], r["bullets"]) == (5, 1, 1, 1, 2), r
    assert reader_check("Да. Лошо е, защото закъснението расте. Увеличете капацитета.")["visible_total"] == 0
    cell = lint("| Колона | Стойност |\n|---|---|\n| Би трябвало да рестартирате | да |\n", "descriptive")["violations"]
    assert cell["banned_modal"] == 1 and cell["sentence_over_limit"] == 0, cell
    assert lint(TABLE_FIXTURE, "descriptive")["violations"]["sentence_over_limit"] == 0
    assert lint(LIST_FIXTURE, "descriptive")["violations"]["sentence_over_limit"] == 0
    assert lint("дума " * 30, "descriptive")["violations"]["sentence_over_limit"] >= 1
    assert sentences("- Разхлабете болтовете.\n- После продължете") == ["Разхлабете болтовете.", "После продължете."]
    detail = lint_detail(SLOP_FIXTURE, "procedural")
    assert len(detail) == slop["violations_total"], (len(detail), slop["violations_total"])
    assert all(h["line"] >= 1 and h["text"] for h in detail), detail
    assert lint("Задайте порта, освен ако услугата вече работи.", "procedural")["violations"]["trailing_condition"] == 0
    assert lint("Пишете „би трябвало“ като „трябва“.", "descriptive")["violations_total"] == 0
    assert lint("---\nname: x\ndescription: " + "дума " * 40 + "\n---\nТекст.", "descriptive")["violations_total"] == 0
    assert lint("Това е правило за стила. Това е сила.", "descriptive")["violations_total"] == 0
    assert cyrillic_share(CLEAN_FIXTURE) > 0.9 and cyrillic_share("Run the migration.") == 0.0
    off = "Преди:\n\n<!-- bg-lint off -->\n> " + SLOP_FIXTURE + "\n<!-- bg-lint on -->\n\nСлед:\n\n> Би трябвало да спрете."
    off_hits = lint_detail(off, "procedural")
    assert [(h["category"], h["line"]) for h in off_hits] == [("banned_modal", 10)], off_hits
    assert lint("<!-- bg-lint off -->\n" + SLOP_FIXTURE, "procedural")["violations_total"] == 0
    assert lint("> ## Заглавие\n>\n> Рестартирайте услугата.", "procedural")["violations_total"] == 0
    assert lint("<table><tr><th>Без skill</th><th>Със skill</th></tr></table>\nТекст.", "descriptive")["violations_total"] == 0
    table_lines = lint_detail("Текст.\n\n| А | Б |\n|---|---|\n| едно | две |\n\nБи трябвало да спрете.", "descriptive")
    assert [h["line"] for h in table_lines] == [7], table_lines
    assert lint("Проверката мина. Уверете се, че портът е отворен.", "procedural")["violations_total"] == 0
    assert lint("Проверете порта. Уверете се, че портът е отворен.", "procedural")["violations"]["synonym_rotation"] == 1
    # Примерите от наръчника на ЕК „Как да пишем ясно“.
    assert lint("Този проект бе отхвърлен.", "descriptive")["violations"]["passive_voice"] == 1
    assert lint("Ще проведем разследване и ще вземем решение.", "descriptive")["violations"]["nominalization"] == 2
    assert lint("Извършването на оценка отне седмица.", "descriptive")["violations"]["nominalization"] == 1
    assert lint("Парламентът даде препоръка на държавите.", "descriptive")["violations"]["nominalization"] == 1
    assert lint("Засягащ въпроса за таксите, докладът е кратък.", "descriptive")["violations"]["participle_clause"] == 1
    assert lint("Следващата стъпка, която е кратка, е последна.", "descriptive")["violations_total"] == 0
    assert lint("Работещият процес, който спря, е стар.", "descriptive")["violations_total"] == 0
    assert lint("Определен брой кандидати подадоха заявки в съответствие с правилата.", "descriptive")["violations"]["slop_word"] == 2
    assert lint("Направете резервно копие. Прегледът мина.", "procedural")["violations_total"] == 0
    quotes = "Потърсете " + ", ".join(["„би“"] * 14) + "."
    assert lint(quotes, "descriptive")["violations"]["sentence_over_limit"] == 0
    print("self-test OK:", slop["violations_total"], "нарушения в текста със слоп, 0 в чистия текст")


USAGE = "usage: bg_lint.py [--type procedural|descriptive|reply] [--gate] [--detail] (FILE|-) | --self-test"


def main():
    args = sys.argv[1:]
    if "--self-test" in args:
        self_test()
        return 0
    gate = "--gate" in args
    if gate:
        args.remove("--gate")
    detail = "--detail" in args
    if detail:
        args.remove("--detail")
    text_type = "descriptive"
    if "--type" in args:
        i = args.index("--type")
        if i + 1 >= len(args):
            sys.exit("missing value after --type\n" + USAGE)
        text_type = args[i + 1]
        del args[i:i + 2]
    if text_type != "reply" and text_type not in LIMITS:
        sys.exit("unknown --type %r (expected procedural, descriptive or reply)\n%s" % (text_type, USAGE))
    if len(args) != 1:
        sys.exit(USAGE)
    src = args[0]
    if src == "-":
        text = sys.stdin.read()
    else:
        try:
            with open(src, encoding="utf-8") as fh:
                text = fh.read()
        except OSError as err:
            sys.exit(str(err))
    report = reader_check(text) if text_type == "reply" else lint(text, text_type)
    if text_type != "reply" and detail:
        report["hits"] = lint_detail(text, text_type)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    total = report["visible_total"] if text_type == "reply" else report["violations_total"]
    return 1 if gate and total else 0


if __name__ == "__main__":
    sys.exit(main())
