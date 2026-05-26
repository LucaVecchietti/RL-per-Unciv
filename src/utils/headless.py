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
        Python → JVM:  "advance <path>\\n" | "move <path> <id> <clock>\\n"
                       | "legalmoves <path> <id>\\n" | "foundcity <path> <id>\\n"
                       | "improve <path> <id>\\n" | "quit\\n"
        JVM → Python:  "READY\\n" (on startup) | "ok <turn>\\n"
                       | "moved <id> <x> <y> <movement>\\n" | "legal <clock>...\\n"
                       | "founded <x> <y>\\n" | "improving <name> <turns>\\n"
                       | "illegal <reason>\\n" | "error <msg>\\n"
    """

    def __init__(
        self,
        jar_path: str,
        timeout: int = 60,
        java_path: str = "java",
        action_timeout: int = 5,
    ) -> None:
        self.jar_path = Path(jar_path)
        # timeout = startup (READY) + advance: comandi che possono essere genuinamente lenti
        self.timeout = timeout
        # action_timeout = comandi-unità (move/found/improve/legalmoves): normale <1s, oltre = hang quasi certo
        self.action_timeout = action_timeout
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

    # Prefissi delle risposte valide del protocollo. Tutto il resto su stdout
    # (log del JVM, es. SoundPlayer$Preloader) va ignorato.
    _RESPONSE_PREFIXES = ("ok ", "error", "moved ", "illegal", "legal", "founded ")

    def _terminate_process(self) -> None:
        """Termina il processo JVM e azzera il riferimento."""
        try:
            self._process.terminate()
        except Exception:
            pass
        self._process = None

    def _read_protocol_response(self, timeout: Optional[float] = None) -> str:
        """
        Legge righe da stdout finché non arriva una risposta del protocollo,
        saltando le righe di log asincrone del JVM (es. SoundPlayer$Preloader).

        `timeout` override (in secondi). Se None, usa `self.timeout` (default).
        """
        eff_timeout = timeout if timeout is not None else self.timeout
        deadline = time.monotonic() + eff_timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                self._terminate_process()
                raise TimeoutError(f"JVM server timeout dopo {eff_timeout}s")
            line = self._readline_timeout(self._process.stdout, max(0.5, remaining))
            if line is None or line == "":
                self._terminate_process()
                raise TimeoutError(f"JVM server timeout/EOF dopo {eff_timeout}s")
            stripped = line.strip()
            if stripped.startswith(self._RESPONSE_PREFIXES):
                return stripped
            # riga di log del JVM → ignora e continua a leggere

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

            response = self._read_protocol_response()
            if response.startswith("error"):
                raise RuntimeError(f"Unciv headless errore: {response}")
            if not response.startswith("ok "):
                raise RuntimeError(f"Risposta JVM inattesa: {response!r}")

    def _send_command(self, command: str) -> str:
        """Invia un comando al server JVM persistente e restituisce la risposta (stripped)."""
        with self._lock:
            self._ensure_running()
            self._process.stdin.write(command + "\n")
            self._process.stdin.flush()
            try:
                # comandi-unità (move/legalmoves/foundcity/improve/build_improvement): timeout corto
                return self._read_protocol_response(timeout=self.action_timeout)
            except TimeoutError:
                # JVM bloccata o morta su questo comando: è già stata terminata
                # (verrà riavviata al prossimo comando). Restituisce un esito di errore
                # così il chiamante tratta l'azione come no-op → il training non crasha.
                return "error timeout"

    def move_unit(self, save_path: Path, unit_id: int, clock: int) -> dict:
        """
        Muove un'unità di una casella nella direzione `clock` (2,4,6,8,10,12) via il server.

        Args:
            save_path: file di salvataggio da aggiornare in-place.
            unit_id: id dell'unità (campo `id` nel JSON).
            clock: direzione esagonale (ora di orologio).

        Returns:
            dict: {"success": True, "x", "y", "movement_left"} se riuscito,
                  altrimenti {"success": False, "reason": ...}.
        """
        save_path = Path(save_path)
        response = self._send_command(f"move {save_path.as_posix()} {unit_id} {clock}")
        if response.startswith("moved "):
            parts = response.split()
            return {
                "success": True,
                "x": int(parts[2]),
                "y": int(parts[3]),
                "movement_left": float(parts[4]),
            }
        if response.startswith("illegal"):
            return {"success": False, "reason": response}
        if response.startswith("error "):
            return {"success": False, "reason": response[6:]}
        return {"success": False, "reason": f"risposta inattesa: {response!r}"}

    def legal_moves(self, save_path: Path, unit_id: int) -> list[int]:
        """Restituisce le direzioni (clock) legali per l'unità, lista vuota se nessuna/errore."""
        save_path = Path(save_path)
        response = self._send_command(f"legalmoves {save_path.as_posix()} {unit_id}")
        if response.startswith("legal"):
            return [int(c) for c in response.split()[1:]]
        return []

    def build_improvement(self, save_path: Path, unit_id: int) -> dict:
        """
        Fa costruire al Worker il miglioramento che connette la risorsa sul suo tile.

        Returns:
            dict: {"success": True, "improvement", "turns"} se avviato,
                  altrimenti {"success": False, "reason": ...}.
        """
        save_path = Path(save_path)
        response = self._send_command(f"improve {save_path.as_posix()} {unit_id}")
        if response.startswith("improving "):
            parts = response.split()
            return {"success": True, "improvement": parts[1], "turns": int(parts[2])}
        return {"success": False, "reason": response}

    def found_city(self, save_path: Path, unit_id: int) -> dict:
        """
        Fonda una città con il Settler indicato (consuma l'unità).

        Returns:
            dict: {"success": True, "x", "y"} se fondata,
                  altrimenti {"success": False, "reason": ...}.
        """
        save_path = Path(save_path)
        response = self._send_command(f"foundcity {save_path.as_posix()} {unit_id}")
        if response.startswith("founded "):
            parts = response.split()
            return {"success": True, "x": int(parts[1]), "y": int(parts[2])}
        return {"success": False, "reason": response}

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
