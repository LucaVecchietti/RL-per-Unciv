import pytest
import subprocess
import threading
from unittest.mock import patch, MagicMock
from pathlib import Path
from src.utils.headless import UncivHeadless


@pytest.fixture
def headless(tmp_path):
    """Headless con JAR fittizio (file esistente ma non reale)."""
    jar = tmp_path / "Unciv.jar"
    jar.write_bytes(b"fake jar")
    return UncivHeadless(jar_path=str(jar), timeout=5)


def _make_popen_mock(responses: list[str]) -> MagicMock:
    """
    Create a mock Popen that returns READY on startup then the given responses.
    Each string in responses is returned as a full line (newline appended).
    """
    all_lines = ["READY\n"] + [r + "\n" for r in responses]
    line_iter = iter(all_lines)

    mock_proc = MagicMock()
    mock_proc.poll.return_value = None  # process alive
    mock_proc.stdout.readline.side_effect = lambda: next(line_iter, "")
    mock_proc.stdin = MagicMock()
    mock_proc.stderr.read.return_value = ""
    return mock_proc


def test_jar_not_found_raises():
    with pytest.raises(FileNotFoundError):
        UncivHeadless(jar_path="/nonexistent/Unciv.jar")


def test_advance_turn_save_not_found(headless, tmp_path):
    with pytest.raises(FileNotFoundError):
        headless.advance_turn(tmp_path / "missing.json")


def test_advance_turn_success(headless, tmp_path):
    save = tmp_path / "game.json"
    save.write_text('{"turns": 2}')

    mock_proc = _make_popen_mock(["ok 3"])
    with patch("subprocess.Popen", return_value=mock_proc):
        headless.advance_turn(save)
    mock_proc.stdin.write.assert_called()
    mock_proc.stdin.flush.assert_called()


def test_advance_turn_failure(headless, tmp_path):
    save = tmp_path / "game.json"
    save.write_text('{"turns": 2}')

    mock_proc = _make_popen_mock(["error something went wrong"])
    with patch("subprocess.Popen", return_value=mock_proc):
        with pytest.raises(RuntimeError):
            headless.advance_turn(save)


def test_advance_turn_timeout(headless, tmp_path):
    save = tmp_path / "game.json"
    save.write_text('{"turns": 2}')

    # Short-timeout headless instance
    headless_fast = UncivHeadless(jar_path=str(headless.jar_path), timeout=1)

    call_count = [0]

    def slow_readline():
        call_count[0] += 1
        if call_count[0] == 1:
            return "READY\n"
        threading.Event().wait()  # block forever → simulates timeout
        return ""

    mock_proc = MagicMock()
    mock_proc.poll.return_value = None
    mock_proc.stdout.readline.side_effect = slow_readline
    mock_proc.stdin = MagicMock()
    mock_proc.stderr.read.return_value = ""

    with patch("subprocess.Popen", return_value=mock_proc):
        with pytest.raises(TimeoutError):
            headless_fast.advance_turn(save)


def test_start_new_game(headless, tmp_path):
    template = tmp_path / "template.json"
    template.write_text('{"turns": 2}')
    dest = tmp_path / "current_game_0.json"

    headless.start_new_game(template, dest)
    assert dest.exists()
    assert dest.read_text() == template.read_text()


def test_start_new_game_no_template(headless, tmp_path):
    with pytest.raises(FileNotFoundError):
        headless.start_new_game(tmp_path / "missing.json", tmp_path / "dest.json")


def test_is_available_false_no_jar(tmp_path):
    jar = tmp_path / "fake.jar"
    with pytest.raises(FileNotFoundError):
        UncivHeadless(jar_path=str(jar))


def test_is_available_true(headless):
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        assert headless.is_available() is True


def test_is_available_java_not_found(headless):
    with patch("subprocess.run", side_effect=FileNotFoundError):
        assert headless.is_available() is False


def test_close_sends_quit(headless):
    mock_proc = MagicMock()
    mock_proc.poll.return_value = None
    headless._process = mock_proc

    headless.close()

    mock_proc.stdin.write.assert_called_with("quit\n")
    assert headless._process is None


def test_close_noop_when_no_process(headless):
    headless._process = None
    headless.close()  # must not raise


def test_advance_turn_skips_log_lines_before_ready(headless, tmp_path):
    """JVM may print log lines before READY — must skip them and still succeed."""
    save = tmp_path / "game.json"
    save.write_text('{"turns": 2}')

    all_lines = iter([
        "[HeadlessApplication] Creating UncivFiles...\n",
        "Loaded 2 rulesets in 257ms\n",
        "READY\n",
        "ok 3\n",
    ])
    mock_proc = MagicMock()
    mock_proc.poll.return_value = None
    mock_proc.stdout.readline.side_effect = lambda: next(all_lines, "")
    mock_proc.stdin = MagicMock()
    mock_proc.stderr.read.return_value = ""

    with patch("subprocess.Popen", return_value=mock_proc):
        headless.advance_turn(save)


def test_move_unit_success(headless, tmp_path):
    save = tmp_path / "game.json"
    save.write_text('{"turns": 2}')
    mock_proc = _make_popen_mock(["moved 14 1 -1 1.0"])
    with patch("subprocess.Popen", return_value=mock_proc):
        result = headless.move_unit(save, 14, 2)
    assert result["success"] is True
    assert result["x"] == 1
    assert result["y"] == -1
    assert result["movement_left"] == 1.0


def test_move_unit_illegal(headless, tmp_path):
    save = tmp_path / "game.json"
    save.write_text('{"turns": 2}')
    mock_proc = _make_popen_mock(["illegal cannot_move"])
    with patch("subprocess.Popen", return_value=mock_proc):
        result = headless.move_unit(save, 14, 2)
    assert result["success"] is False


def test_legal_moves_parsed(headless, tmp_path):
    save = tmp_path / "game.json"
    save.write_text('{"turns": 2}')
    mock_proc = _make_popen_mock(["legal 2 6 10"])
    with patch("subprocess.Popen", return_value=mock_proc):
        clocks = headless.legal_moves(save, 14)
    assert clocks == [2, 6, 10]


def test_legal_moves_empty(headless, tmp_path):
    save = tmp_path / "game.json"
    save.write_text('{"turns": 2}')
    mock_proc = _make_popen_mock(["legal "])
    with patch("subprocess.Popen", return_value=mock_proc):
        clocks = headless.legal_moves(save, 14)
    assert clocks == []


def test_found_city_success(headless, tmp_path):
    save = tmp_path / "game.json"
    save.write_text('{"turns": 2}')
    mock_proc = _make_popen_mock(["founded 3 6"])
    with patch("subprocess.Popen", return_value=mock_proc):
        result = headless.found_city(save, 41)
    assert result["success"] is True
    assert result["x"] == 3
    assert result["y"] == 6


def test_found_city_illegal(headless, tmp_path):
    save = tmp_path / "game.json"
    save.write_text('{"turns": 2}')
    mock_proc = _make_popen_mock(["illegal cannot_settle"])
    with patch("subprocess.Popen", return_value=mock_proc):
        result = headless.found_city(save, 41)
    assert result["success"] is False


def test_advance_turn_skips_log_noise_in_response(headless, tmp_path):
    """Una riga di log del JVM intercalata prima di 'ok' va ignorata."""
    save = tmp_path / "game.json"
    save.write_text('{"turns": 2}')
    noise = "2026-05-24T17:24:01Z [threadpool-daemon-0] [SoundPlayer$Preloader] Preload UncivSound(promote)"
    mock_proc = _make_popen_mock([noise, "ok 3"])
    with patch("subprocess.Popen", return_value=mock_proc):
        headless.advance_turn(save)  # non deve sollevare


def test_move_unit_skips_log_noise(headless, tmp_path):
    save = tmp_path / "game.json"
    save.write_text('{"turns": 2}')
    noise = "2026-05-24T17:24:01Z [SoundPlayer$Preloader] Preload UncivSound(promote)"
    mock_proc = _make_popen_mock([noise, "moved 14 1 -1 1.0"])
    with patch("subprocess.Popen", return_value=mock_proc):
        result = headless.move_unit(save, 14, 2)
    assert result["success"] is True
    assert result["x"] == 1


def test_reuse_process_across_calls(headless, tmp_path):
    """JVM process started once and reused for multiple advance_turn calls."""
    save = tmp_path / "game.json"
    save.write_text('{"turns": 2}')

    mock_proc = _make_popen_mock(["ok 3", "ok 4"])

    with patch("subprocess.Popen", return_value=mock_proc) as mock_popen:
        headless.advance_turn(save)
        headless.advance_turn(save)
        mock_popen.assert_called_once()


def test_build_improvement_success(headless, tmp_path):
    save = tmp_path / "game.json"
    save.write_text('{"turns": 2}')
    mock_proc = _make_popen_mock(["improving Farm 7"])
    with patch("subprocess.Popen", return_value=mock_proc):
        result = headless.build_improvement(save, 12)
    assert result["success"] is True
    assert result["improvement"] == "Farm"
    assert result["turns"] == 7


def test_build_improvement_illegal(headless, tmp_path):
    save = tmp_path / "game.json"
    save.write_text('{"turns": 2}')
    mock_proc = _make_popen_mock(["illegal cannot_build"])
    with patch("subprocess.Popen", return_value=mock_proc):
        result = headless.build_improvement(save, 12)
    assert result["success"] is False
    assert "cannot_build" in result["reason"]


def test_build_improvement_skips_log_noise(headless, tmp_path):
    """Una riga di log JVM prima di 'improving ...' va ignorata, non scambiata per timeout."""
    save = tmp_path / "game.json"
    save.write_text('{"turns": 2}')
    noise = "2026-05-24T17:24:01Z [SoundPlayer$Preloader] Preload UncivSound(promote)"
    mock_proc = _make_popen_mock([noise, "improving Farm 7"])
    with patch("subprocess.Popen", return_value=mock_proc):
        result = headless.build_improvement(save, 12)
    assert result["success"] is True
    assert result["improvement"] == "Farm"


def test_build_improvement_multi_word_name(headless, tmp_path):
    """Nomi miglioramenti multi-token (es. 'Oil well') vanno parsati come stringa intera."""
    save = tmp_path / "game.json"
    save.write_text('{"turns": 2}')
    mock_proc = _make_popen_mock(["improving Oil well 5"])
    with patch("subprocess.Popen", return_value=mock_proc):
        result = headless.build_improvement(save, 12)
    assert result["success"] is True
    assert result["improvement"] == "Oil well"
    assert result["turns"] == 5


def test_build_improvement_multi_word_three_tokens(headless, tmp_path):
    """Robustezza: nome a 3 token (es. 'Trading Post Foo')."""
    save = tmp_path / "game.json"
    save.write_text('{"turns": 2}')
    mock_proc = _make_popen_mock(["improving Trading Post Foo 12"])
    with patch("subprocess.Popen", return_value=mock_proc):
        result = headless.build_improvement(save, 12)
    assert result["success"] is True
    assert result["improvement"] == "Trading Post Foo"
    assert result["turns"] == 12


def test_build_improvement_malformed_no_turns(headless, tmp_path):
    """Risposta 'improving Farm' senza turni: non deve crashare."""
    save = tmp_path / "game.json"
    save.write_text('{"turns": 2}')
    mock_proc = _make_popen_mock(["improving Farm"])
    with patch("subprocess.Popen", return_value=mock_proc):
        result = headless.build_improvement(save, 12)
    assert result["success"] is False
    assert "malformata" in result["reason"]


# --- File 24 — wrapper build_road --------------------------------------------


def test_build_road_success(headless, tmp_path):
    """Risposta 'improving Road <turns>' → success con improvement=Road e turns int."""
    save = tmp_path / "game.json"
    save.write_text('{"turns": 2}')
    mock_proc = _make_popen_mock(["improving Road 7"])
    with patch("subprocess.Popen", return_value=mock_proc):
        result = headless.build_road(save, 12)
    assert result["success"] is True
    assert result["improvement"] == "Road"
    assert result["turns"] == 7


def test_build_road_illegal_cannot_build(headless, tmp_path):
    """Risposta 'illegal cannot_build' → success=False con reason che contiene cannot_build."""
    save = tmp_path / "game.json"
    save.write_text('{"turns": 2}')
    mock_proc = _make_popen_mock(["illegal cannot_build"])
    with patch("subprocess.Popen", return_value=mock_proc):
        result = headless.build_road(save, 12)
    assert result["success"] is False
    assert "cannot_build" in result["reason"]


def test_build_road_no_unit(headless, tmp_path):
    """Risposta 'error no_unit' → success=False (unità non trovata)."""
    save = tmp_path / "game.json"
    save.write_text('{"turns": 2}')
    mock_proc = _make_popen_mock(["error no_unit"])
    with patch("subprocess.Popen", return_value=mock_proc):
        result = headless.build_road(save, 999)
    assert result["success"] is False


def test_build_road_skips_log_noise(headless, tmp_path):
    """Una riga di log JVM prima di 'improving Road ...' va ignorata."""
    save = tmp_path / "game.json"
    save.write_text('{"turns": 2}')
    noise = "2026-05-24T17:24:01Z [SoundPlayer$Preloader] Preload UncivSound(promote)"
    mock_proc = _make_popen_mock([noise, "improving Road 5"])
    with patch("subprocess.Popen", return_value=mock_proc):
        result = headless.build_road(save, 12)
    assert result["success"] is True
    assert result["improvement"] == "Road"
    assert result["turns"] == 5
