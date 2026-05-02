import pytest
import subprocess
from unittest.mock import patch, MagicMock
from pathlib import Path
from src.utils.headless import UncivHeadless


@pytest.fixture
def headless(tmp_path):
    """Headless con JAR fittizio (file esistente ma non reale)."""
    jar = tmp_path / "Unciv.jar"
    jar.write_bytes(b"fake jar")
    return UncivHeadless(jar_path=str(jar), timeout=5)


def test_jar_not_found_raises():
    with pytest.raises(FileNotFoundError):
        UncivHeadless(jar_path="/nonexistent/Unciv.jar")


def test_advance_turn_save_not_found(headless, tmp_path):
    with pytest.raises(FileNotFoundError):
        headless.advance_turn(tmp_path / "missing.json")


def test_advance_turn_success(headless, tmp_path):
    save = tmp_path / "game.json"
    save.write_text('{"turns": 2}')

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        headless.advance_turn(save)
        mock_run.assert_called_once()


def test_advance_turn_failure(headless, tmp_path):
    save = tmp_path / "game.json"
    save.write_text('{"turns": 2}')

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="error")
        with pytest.raises(RuntimeError):
            headless.advance_turn(save)


def test_advance_turn_timeout(headless, tmp_path):
    save = tmp_path / "game.json"
    save.write_text('{"turns": 2}')

    with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("java", 5)):
        with pytest.raises(TimeoutError):
            headless.advance_turn(save)


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
