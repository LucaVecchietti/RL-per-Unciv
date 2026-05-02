import subprocess
import shutil
import threading
import time
from pathlib import Path
from typing import Optional


class UncivHeadless:
    """
    Manages Unciv headless execution via a persistent JVM server process.

    One process per UncivHeadless instance (one per env_rank). The JVM starts
    once on the first advance_turn() call, then handles all subsequent calls
    via a stdin/stdout command protocol — eliminating ~5s JVM startup per turn.

    Protocol:
        Python → JVM:  "advance <path>\\n" | "quit\\n"
        JVM → Python:  "READY\\n" (on startup) | "ok <turn>\\n" | "error <msg>\\n"
    """

    def __init__(self, jar_path: str, timeout: int = 60, java_path: str = "java") -> None:
        self.jar_path = Path(jar_path)
        self.timeout = timeout
        self.java_path = java_path
        self._process: Optional[subprocess.Popen] = None
        self._lock = threading.Lock()
        self._validate_jar()

    def _validate_jar(self) -> None:
        """Verify JAR exists before proceeding."""
        if not self.jar_path.exists():
            raise FileNotFoundError(
                f"Unciv.jar non trovato in: {self.jar_path}\n"
                f"Scaricalo da: https://github.com/yairm210/Unciv/releases/latest"
            )

    def _readline_timeout(self, stream, timeout: int) -> Optional[str]:
        """Read one line from stream with timeout. Returns None on timeout."""
        result: list[Optional[str]] = [None]

        def _read() -> None:
            result[0] = stream.readline()

        t = threading.Thread(target=_read, daemon=True)
        t.start()
        t.join(timeout)
        return result[0]

    def _ensure_running(self) -> None:
        """Start persistent JVM server process if not running or dead."""
        if self._process is not None and self._process.poll() is None:
            return

        self._process = subprocess.Popen(
            [self.java_path, "-jar", str(self.jar_path), "--server"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        # JVM may print log lines to stdout before "READY" — skip them
        deadline = time.monotonic() + self.timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            line = self._readline_timeout(self._process.stdout, max(1.0, remaining))
            if line is None or line == "":
                break
            if line.strip() == "READY":
                return
        stderr_snippet = ""
        try:
            self._process.terminate()
            stderr_snippet = self._process.stderr.read(500)
        except Exception:
            pass
        self._process = None
        raise RuntimeError(
            f"JVM server non pronto: READY non ricevuto entro {self.timeout}s\n"
            f"stderr: {stderr_snippet}"
        )

    def advance_turn(self, save_path: Path) -> None:
        """
        Advance one game turn via the persistent JVM server process.

        Args:
            save_path: Path to the JSON save file to update in-place.

        Raises:
            FileNotFoundError: If save_path doesn't exist.
            TimeoutError: If JVM server doesn't respond within self.timeout seconds.
            RuntimeError: If JVM server reports an error or returns unexpected response.
        """
        save_path = Path(save_path)
        if not save_path.exists():
            raise FileNotFoundError(f"Save file non trovato: {save_path}")

        with self._lock:
            self._ensure_running()

            self._process.stdin.write(f"advance {save_path.as_posix()}\n")
            self._process.stdin.flush()

            response = self._readline_timeout(self._process.stdout, self.timeout)

            if response is None:
                try:
                    self._process.terminate()
                except Exception:
                    pass
                self._process = None
                raise TimeoutError(
                    f"JVM server timeout dopo {self.timeout}s su: {save_path}"
                )

            response = response.strip()
            if response.startswith("error "):
                raise RuntimeError(f"Unciv headless errore: {response[6:]}")
            if not response.startswith("ok "):
                raise RuntimeError(f"Risposta JVM inattesa: {response!r}")

    def start_new_game(self, template_path: Path, dest_path: Path) -> None:
        """
        Copy template to create a new game save.

        Args:
            template_path: Source template save file.
            dest_path: Destination for the new save file.

        Raises:
            FileNotFoundError: If template_path doesn't exist.
        """
        template_path = Path(template_path)
        dest_path = Path(dest_path)
        if not template_path.exists():
            raise FileNotFoundError(
                f"Template non trovato: {template_path}\n"
                "Genera una partita manuale con Unciv e copiala in saves/template_game.json"
            )
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(template_path, dest_path)

    def is_available(self) -> bool:
        """Check if Java and Unciv.jar are available."""
        try:
            result = subprocess.run(
                [self.java_path, "-version"],
                capture_output=True,
                timeout=5,
            )
            return result.returncode == 0 and self.jar_path.exists()
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False

    def close(self) -> None:
        """Shut down the persistent JVM server process gracefully."""
        if self._process is not None and self._process.poll() is None:
            try:
                self._process.stdin.write("quit\n")
                self._process.stdin.flush()
                self._process.wait(timeout=5)
            except Exception:
                try:
                    self._process.terminate()
                except Exception:
                    pass
        self._process = None
