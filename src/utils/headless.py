import subprocess
import shutil
from pathlib import Path


class UncivHeadless:
    """
    Gestisce l'esecuzione di Unciv in modalità headless.
    Isola tutta la logica subprocess in un unico modulo testabile.
    """

    def __init__(self, jar_path: str, timeout: int = 60, java_path: str = "java") -> None:
        self.jar_path = Path(jar_path)
        self.timeout = timeout
        self.java_path = java_path
        self._validate_jar()

    def _validate_jar(self) -> None:
        """Verifica che il JAR esista prima di procedere."""
        if not self.jar_path.exists():
            raise FileNotFoundError(
                f"Unciv.jar non trovato in: {self.jar_path}\n"
                f"Scaricalo da: https://github.com/yairm210/Unciv/releases/latest"
            )

    def advance_turn(self, save_path: Path) -> None:
        """
        Avanza di un turno eseguendo Unciv headless sul save file indicato.

        Args:
            save_path: Path al file JSON di salvataggio da aggiornare.

        Raises:
            FileNotFoundError: Se save_path non esiste.
            TimeoutError: Se il turno supera self.timeout secondi.
            RuntimeError: Se Unciv headless termina con errore.
        """
        save_path = Path(save_path)
        if not save_path.exists():
            raise FileNotFoundError(f"Save file non trovato: {save_path}")

        try:
            result = subprocess.run(
                [
                    self.java_path, "-jar", str(self.jar_path),
                    "--advance-turn",
                    "--save-file", str(save_path),
                ],
                capture_output=True,
                text=True,
                timeout=self.timeout,
            )
        except subprocess.TimeoutExpired:
            raise TimeoutError(
                f"Unciv headless timeout dopo {self.timeout}s "
                f"su file: {save_path}"
            )

        if result.returncode != 0 or "ERROR:" in result.stderr:
            raise RuntimeError(
                f"Unciv headless fallito (returncode={result.returncode})\n"
                f"stdout: {result.stdout[:500]}\n"
                f"stderr: {result.stderr[:500]}"
            )

    def start_new_game(self, template_path: Path, dest_path: Path) -> None:
        """
        Crea una nuova partita copiando il template.

        Args:
            template_path: Save file template da copiare.
            dest_path: Destinazione del nuovo save file.

        Raises:
            FileNotFoundError: Se template_path non esiste.
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
        """Controlla se Java e Unciv.jar sono disponibili."""
        try:
            result = subprocess.run(
                [self.java_path, "-version"],
                capture_output=True,
                timeout=5,
            )
            return result.returncode == 0 and self.jar_path.exists()
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False
