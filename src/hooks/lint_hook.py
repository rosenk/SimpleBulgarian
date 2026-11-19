#!/usr/bin/env python3
"""Съветващи проверки на писането за hook-овете на Claude Code. Никога не блокират.

PostToolUse (Write|Edit на .md файл): проверява файла с evals/bg_lint.py.
Ако файлът има нарушения, извежда в stderr текста и номера на реда за всяко
попадение (до MAX_HOOK_HITS) и излиза с код 2, за да ги види моделът. Код 2
при PostToolUse е само съвет: инструментът вече е изпълнен. Файлове, които не
са на български (под MIN_CYRILLIC кирилица), се пропускат. Вътрешните файлове
на агента, например файловете с памет в конфигурационната директория на
Claude, също се пропускат. SIMPLE_BULGARIAN_LINT_EXCLUDE добавя още пътища.

Stop: чете `last_assistant_message`, проверява регистъра на отговора (без
удебеляване, без тирета, без слоп, без встъпления и заключителни фрази) и
връща systemMessage само ако отговорът го нарушава. Винаги излиза с код 0,
за да не зацикли сесията.
"""
import fnmatch
import json
import os
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(ROOT / "evals"))

MAX_HOOK_HITS = 12
MIN_CYRILLIC = 0.5
CLAUDE_DIR = ".claude"
EXCLUDE_VAR = "SIMPLE_BULGARIAN_LINT_EXCLUDE"
OPENERS = re.compile(
    r"^\s*(разбира се|естествено[,!]|чудесен въпрос|страхотен въпрос|отличен въпрос|"
    r"абсолютно (сте|си) прав|с удоволствие|абсолютно[,!])", re.I)
CLOSERS = re.compile(
    r"(надявам се,? (това|че това|да съм) (да )?(ви |ти )?(помог|е полезн)|"
    r"ако имате (още |други )?въпроси|ако имаш (още |други )?въпроси|не се колебайте|"
    r"(кажете|кажи|пишете|пиши) ми,? ако|успех!)", re.I)


def load_linter():
    try:
        import bg_lint  # noqa: WPS433
        return bg_lint
    except Exception:  # noqa: BLE001
        return None


def strip_code(text):
    text = re.sub(r"```.*?```", " ", text, flags=re.S)
    return re.sub(r"`[^`]*`", " ", text)


def absolute(path, cwd=None):
    """Прави пътя абсолютен. Hook-ът може да получи път спрямо директорията на сесията."""
    return pathlib.Path(cwd or ".", pathlib.Path(path).expanduser()).absolute()


def variants(path):
    """Пътят както е написан и пътят с разрешени символни връзки. Изключването важи и за двата."""
    return {pathlib.Path(os.path.normpath(path)), path.resolve()}


def excluded(target):
    """True за вътрешните Markdown файлове на агента и за пътищата, които потребителят изключва."""
    config_dirs = variants(absolute(os.environ.get("CLAUDE_CONFIG_DIR") or f"~/{CLAUDE_DIR}"))
    raw = os.environ.get(EXCLUDE_VAR, "").split(os.pathsep)
    patterns = [os.path.expanduser(p) for p in raw if p]
    for form in variants(target):
        if CLAUDE_DIR in form.parts or any(form.is_relative_to(d) for d in config_dirs):
            return True
        if any(fnmatch.fnmatch(str(form), p) for p in patterns):
            return True
    return False


def post_tool_use(event):
    path = (event.get("tool_input") or {}).get("file_path") or ""
    if not path.endswith(".md"):
        return 0
    target = absolute(path, event.get("cwd"))
    if excluded(target):
        return 0
    lint = load_linter()
    if lint is None:
        return 0
    try:
        text = target.read_text(encoding="utf-8")
    except OSError:
        return 0
    if lint.cyrillic_share(text) < MIN_CYRILLIC:
        return 0
    report = lint.lint(text, "descriptive")
    if not report["violations_total"]:
        return 0
    detail = lint.lint_detail(text, "descriptive")
    lines = [f"simple-bulgarian: {target.name} има {report['violations_total']} нарушения на правилата."]
    for h in detail[:MAX_HOOK_HITS]:
        lines.append(f"  ред {h['line']}, {h['category']}: {h['text']}")
    if len(detail) > MAX_HOOK_HITS:
        lines.append(f"  и още {len(detail) - MAX_HOOK_HITS} попадения.")
    lines.append("Поправете тези попадения във файла, който току-що записахте, и продължете.")
    sys.stderr.write("\n".join(lines) + "\n")
    return 2


def stop(event):
    reply = event.get("last_assistant_message") or ""
    lint = load_linter()
    if lint is None or lint.cyrillic_share(reply) < MIN_CYRILLIC:
        return 0
    problems = []
    c = lint.reader_check(reply)["counts"]
    for key, label in (("em_dash", "тире"), ("bold_spans", "удебеляване")):
        if c[key]:
            problems.append(f"{c[key]} × {label}")
    slop = lint.lint(strip_code(reply), "descriptive")["violations"].get("slop_word", 0)
    if slop:
        problems.append(f"{slop} × слоп или канцеларщина")
    if OPENERS.search(reply):
        problems.append("встъпителна фраза")
    if CLOSERS.search(reply):
        problems.append("заключителна фраза")
    if problems:
        print(json.dumps({"systemMessage": "simple-bulgarian, проверка на отговора: " + "; ".join(problems) + "."},
                         ensure_ascii=False))
    return 0


def main():
    try:
        event = json.load(sys.stdin)
    except Exception:  # noqa: BLE001
        return 0
    try:
        name = event.get("hook_event_name", "")
        if name == "PostToolUse":
            return post_tool_use(event)
        if name == "Stop":
            return stop(event)
    except Exception:  # noqa: BLE001  съветващ hook: сривът никога не блокира и не зацикля сесията
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
