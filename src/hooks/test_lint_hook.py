import json, os, pathlib, subprocess, sys, tempfile
HERE = pathlib.Path(__file__).resolve().parent
HOOK = HERE / "lint_hook.py"
CLEAN = {"CLAUDE_CONFIG_DIR": "/nonexistent/claude-config", "SIMPLE_BULGARIAN_LINT_EXCLUDE": ""}
SLOP = "Би трябвало просто да използвате надеждния инструмент, правейки всичко безпроблемно.\n"

def run(event, env=None):
    r = subprocess.run([sys.executable, str(HOOK)], input=json.dumps(event), capture_output=True, text=True,
                       env={**os.environ, **CLEAN, **(env or {})})
    return r.returncode, r.stdout, r.stderr

def write_slop(directory, name="notes.md"):
    path = pathlib.Path(directory, name)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(SLOP, encoding="utf-8")
    return str(path)

def post(path, **event):
    return {"hook_event_name": "PostToolUse", "tool_name": "Write", "tool_input": {"file_path": path}, **event}

def test_post_tool_use_flags_a_slop_markdown_file():
    with tempfile.TemporaryDirectory() as d:
        code, out, err = run(post(write_slop(d)))
    assert code == 2 and "нарушения на правилата" in err, (code, err)

def test_post_tool_use_prints_the_offending_text_and_line_number():
    with tempfile.TemporaryDirectory() as d:
        path = pathlib.Path(d, "notes.md")
        path.write_text("# Заглавие\n\nБи трябвало да го прегледате. Екипът е добавил индекс.\n", encoding="utf-8")
        code, out, err = run(post(str(path)))
    assert code == 2, (code, err)
    assert "ред 3, banned_modal: Би" in err, err
    assert "ред 3, perfect_tense: е добавил" in err, err

def test_post_tool_use_ignores_clean_file_and_non_markdown():
    with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False) as f:
        f.write("Изпълнете миграцията. После рестартирайте услугата.\n"); path = f.name
    assert run({"hook_event_name": "PostToolUse", "tool_input": {"file_path": path}})[0] == 0
    assert run({"hook_event_name": "PostToolUse", "tool_input": {"file_path": "/tmp/x.py"}})[0] == 0

def test_post_tool_use_skips_the_claude_config_dir():
    with tempfile.TemporaryDirectory() as d:
        path = write_slop(pathlib.Path(d, "projects", "repo", "memory"), "MEMORY.md")
        assert run(post(path))[0] == 2, "a memory file outside any config dir still lints"
        assert run(post(path), env={"CLAUDE_CONFIG_DIR": d})[0] == 0

def test_post_tool_use_skips_a_dot_claude_directory():
    with tempfile.TemporaryDirectory() as d:
        assert run(post(write_slop(pathlib.Path(d, ".claude", "agent-memory", "reviewer"), "MEMORY.md")))[0] == 0

def test_post_tool_use_honours_the_exclude_globs():
    with tempfile.TemporaryDirectory() as d:
        path = write_slop(d)
        assert run(post(path))[0] == 2
        globs = os.pathsep.join(["~/no-such-file.md", f"{d}/*.md"])
        assert run(post(path), env={"SIMPLE_BULGARIAN_LINT_EXCLUDE": globs})[0] == 0

def test_post_tool_use_resolves_a_relative_path_against_the_event_cwd():
    with tempfile.TemporaryDirectory() as d:
        write_slop(d)
        assert run(post("notes.md", cwd=d))[0] == 2

def test_post_tool_use_lints_a_path_that_escapes_a_dot_claude_directory():
    with tempfile.TemporaryDirectory() as d:
        write_slop(d)
        pathlib.Path(d, ".claude").mkdir()
        assert run(post(str(pathlib.Path(d, ".claude", "..", "notes.md"))))[0] == 2

def test_post_tool_use_skips_a_symlink_into_a_dot_claude_directory():
    with tempfile.TemporaryDirectory() as d:
        link = pathlib.Path(d, "notes.md")
        link.symlink_to(write_slop(pathlib.Path(d, ".claude"), "MEMORY.md"))
        assert run(post(str(link)))[0] == 0

def test_post_tool_use_skips_a_symlinked_dot_claude_directory():
    with tempfile.TemporaryDirectory() as d:
        write_slop(pathlib.Path(d, "dotfiles"), "MEMORY.md")
        pathlib.Path(d, ".claude").symlink_to(pathlib.Path(d, "dotfiles"))
        assert run(post(str(pathlib.Path(d, ".claude", "MEMORY.md"))))[0] == 0

def test_post_tool_use_matches_a_glob_through_a_symlinked_directory():
    with tempfile.TemporaryDirectory() as d:
        write_slop(pathlib.Path(d, "store"))
        pathlib.Path(d, "notes").symlink_to(pathlib.Path(d, "store"))
        path = str(pathlib.Path(d, "notes", "notes.md"))
        assert run(post(path))[0] == 2
        assert run(post(path), env={"SIMPLE_BULGARIAN_LINT_EXCLUDE": f"{d}/notes/*"})[0] == 0

def test_stop_flags_slop_reply_and_never_blocks():
    long = "Чудесен въпрос! " + "Това е надеждно изречение. " * 7 + "Надявам се това да помогне!"
    code, out, err = run({"hook_event_name": "Stop", "last_assistant_message": long})
    assert code == 0 and "systemMessage" in out, (code, out)
    msg = json.loads(out)["systemMessage"]
    assert "встъпителна" in msg and "заключителна" in msg and "слоп" in msg, msg

def test_stop_does_not_count_sentences():
    """The reply register has no sentence cap since 2.1.0. Length alone is not a defect."""
    reply = " ".join(f"Стъпка {i} работи." for i in range(20))
    code, out, err = run({"hook_event_name": "Stop", "last_assistant_message": reply})
    assert code == 0 and out.strip() == "", (code, out)

def test_stop_is_silent_on_a_good_reply():
    code, out, err = run({"hook_event_name": "Stop", "last_assistant_message": "Компилацията не успя, защото дискът беше пълен. Освободете 2 GB и я изпълнете отново."})
    assert code == 0 and out.strip() == "", (code, out)

def test_post_tool_use_skips_an_english_file():
    with tempfile.TemporaryDirectory() as d:
        path = pathlib.Path(d, "README.md")
        path.write_text("You should simply leverage the robust tool; it has been done.\n", encoding="utf-8")
        assert run(post(str(path)))[0] == 0

def test_stop_ignores_an_english_reply():
    code, out, err = run({"hook_event_name": "Stop", "last_assistant_message": "**Great question!** It is robust — I hope this helps!"})
    assert code == 0 and out.strip() == "", (code, out)

def test_stop_flags_dash_and_bold():
    code, out, err = run({"hook_event_name": "Stop", "last_assistant_message": "**Да**, услугата спря – дискът е пълен."})
    msg = json.loads(out)["systemMessage"]
    assert "тире" in msg and "удебеляване" in msg, msg

def test_post_tool_use_skips_a_marked_bad_example():
    with tempfile.TemporaryDirectory() as d:
        path = pathlib.Path(d, "examples.md")
        path.write_text("Преди:\n\n<!-- bg-lint off -->\n> " + SLOP + "<!-- bg-lint on -->\n\nСлед:\n\n> Изпълнете миграцията.\n",
                        encoding="utf-8")
        assert run(post(str(path)))[0] == 0
        path.write_text(path.read_text(encoding="utf-8") + "\nБи трябвало да спрете.\n", encoding="utf-8")
        code, out, err = run(post(str(path)))
    assert code == 2 and "ред 11, banned_modal" in err, (code, err)

def test_garbage_stdin_exits_zero():
    r = subprocess.run([sys.executable, str(HOOK)], input="not json", capture_output=True, text=True)
    assert r.returncode == 0

if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn(); print("ok", name)
