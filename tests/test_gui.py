import tkinter as tk
from datetime import datetime
from pathlib import Path

import pytest

from src import gui
from src.gui import App, default_output_path, summarise
from src.pipeline import RunResult


def result(exceptions: int) -> RunResult:
    return RunResult(
        output_path=Path("/data/today/closeout_output_20261009_180507.xlsx"),
        rules_version="2026-10-09",
        closeout_rows=581,
        eligible_rows=289,
        summary_rows=18,
        pn_rows=13,
        ocbc_rows=5,
        exceptions=exceptions,
    )


def test_output_goes_next_to_the_closeout_file_under_a_fresh_name():
    path = default_output_path(Path("/data/today/close out.csv"), now=datetime(2026, 10, 9, 18, 5, 7))
    assert path == Path("/data/today/closeout_output_20261009_180507.xlsx")


def test_summary_reports_counts_and_where_the_file_is():
    text = summarise(result(exceptions=0))
    assert "Phillip Nova instructions: 13" in text
    assert "OCBC instructions: 5" in text
    assert "closeout_output_20261009_180507.xlsx" in text
    assert "Review" not in text


def test_summary_tells_the_user_to_review_exceptions_when_there_are_any():
    assert "Review the 'exceptions' sheet before sending anything." in summarise(result(exceptions=1))


@pytest.fixture
def app(monkeypatch):
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        pytest.skip(f"Tk cannot start: {exc}")
    root.withdraw()
    yield App(root, {"rules_version": "test"})
    root.destroy()


def test_prompt_asks_for_both_files_then_generates(app, monkeypatch):
    calls = []
    answers = iter(["/data/today/filled.csv", "/data/today/close out.csv"])

    def fake_ask(**kwargs):
        calls.append(kwargs)
        return next(answers)

    generated = []
    monkeypatch.setattr(gui.filedialog, "askopenfilename", fake_ask)
    monkeypatch.setattr(App, "generate", lambda self: generated.append(1))
    app.prompt_for_files()
    assert app.filled.get() == "/data/today/filled.csv"
    assert app.closeout.get() == "/data/today/close out.csv"
    assert generated == [1]
    assert calls[0]["title"] == gui.FILLED_TITLE
    assert calls[1]["title"] == gui.CLOSEOUT_TITLE
    assert calls[1]["initialdir"] == "/data/today"


def test_prompt_stops_if_the_first_dialog_is_cancelled(app, monkeypatch):
    generated = []
    monkeypatch.setattr(gui.filedialog, "askopenfilename", lambda **kw: "")
    monkeypatch.setattr(App, "generate", lambda self: generated.append(1))
    app.prompt_for_files()
    assert generated == []
    assert app.filled.get() == "" and "Browse" in app.status.get()


def test_prompt_stops_if_the_second_dialog_is_cancelled(app, monkeypatch):
    answers = iter(["/data/filled.csv", ""])
    generated = []
    monkeypatch.setattr(gui.filedialog, "askopenfilename", lambda **kw: next(answers))
    monkeypatch.setattr(App, "generate", lambda self: generated.append(1))
    app.prompt_for_files()
    assert generated == []
    assert app.filled.get() == "/data/filled.csv" and "Browse" in app.status.get()


@pytest.mark.parametrize("platform,expects_message", [("darwin", True), ("win32", False), ("linux", False)])
def test_dialog_message_is_passed_only_on_macos(app, monkeypatch, platform, expects_message):
    seen = {}
    monkeypatch.setattr(gui.filedialog, "askopenfilename", lambda **kw: seen.update(kw) or "")
    monkeypatch.setattr(gui.sys, "platform", platform)
    app.ask_file(gui.FILLED_TITLE)
    assert ("message" in seen) is expects_message
    if expects_message:
        assert seen["message"] == gui.FILLED_TITLE
