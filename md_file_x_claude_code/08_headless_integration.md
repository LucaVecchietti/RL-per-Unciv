# 08 — Headless Integration (Fase 2)

## Obiettivo
Sostituire gli stub JSON della Fase 1 con una vera integrazione con Unciv headless.
Dopo questa fase, il motore di gioco Unciv gira davvero ad ogni turno.

---

## Cos'è la modalità headless

Unciv può girare senza interfaccia grafica tramite il flag `headless`.
In questa modalità:
- Legge un save file JSON da disco
- Esegue un turno completo (crescita città, produzione, ricerca, AI avversari)
- Scrive il nuovo stato sul file JSON
- Si chiude

Il ciclo Python → Unciv → Python avviene ad ogni step dell'ambiente.

```
Python scrive azione → saves/current_game_0.json
         │
         ▼
java -jar Unciv.jar headless --save-file current_game_0.json
         │
         ▼
Unciv esegue turno → aggiorna current_game_0.json
         │
         ▼
Python legge nuovo stato → calcola reward
```

---

## Prerequisiti

```yaml
# Aggiungere a config/default_config.yaml
unciv:
  jar_path: "unciv/Unciv.jar"     # path relativo alla root del progetto
  headless_timeout: 30             # secondi max per turno
  saves_prefix: "current_game"     # prefisso save files paralleli
```

Scaricare Unciv.jar nella cartella `unciv/` nella root del progetto:
```
unciv-rl-agent/
└── unciv/
    └── Unciv.jar     ← da scaricare da GitHub releases
```

---

## Verifica headless manuale

Prima di integrare nel codice, verificare che headless funzioni:

```powershell
# Dalla root del progetto
java -jar unciv/Unciv.jar headless
```

Output atteso:
```
Unciv headless mode
Waiting for save file...
```

> ⚠️ Se headless non è ancora supportato nella versione scaricata,
> controllare: https://github.com/yairm210/Unciv/issues
> e usare lo stub JSON della Fase 1 finché non viene rilasciato.

---

## Implementazione: `src/utils/headless.py`

Nuovo modulo dedicato alla comunicazione con Unciv headless.

```python
import subprocess
import json
import shutil
from pathlib import Path
from typing import Optional


class UncivHeadless:
    """
    Gestisce l'esecuzione di Unciv in modalità headless.
    Isola tutta la logica subprocess in un unico modulo testabile.
    """

    def __init__(self, jar_path: str, timeout: int = 30) -> None:
        self.jar_path = Path(jar_path)
        self.timeout = timeout
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
            RuntimeError: Se Unciv headless fallisce o va in timeout.
            TimeoutError: Se il turno supera self.timeout secondi.
        """
        if not save_path.exists():
            raise FileNotFoundError(f"Save file non trovato: {save_path}")

        try:
            result = subprocess.run(
                [
                    "java", "-jar", str(self.jar_path),
                    "headless",
                    "--save-file", str(save_path),
                    "--advance-turn",
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

        if result.returncode != 0:
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
        """
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
                ["java", "-version"],
                capture_output=True,
                timeout=5,
            )
            return result.returncode == 0 and self.jar_path.exists()
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False
```

---

## Aggiornamento: `src/envs/unciv_env.py`

### Modifiche necessarie

**1. Aggiungere `env_rank` per save files paralleli**

```python
def __init__(
    self,
    config_path: str = "config/default_config.yaml",
    env_rank: int = 0,
    render_mode: Optional[str] = None,
) -> None:
    super().__init__()
    self.render_mode = render_mode
    self.env_rank = env_rank
    self.config = self._load_config(config_path)
    self.parser = UncivStateParser(player_civ="India")

    # Save file univoco per questo env (evita race conditions con n_envs > 1)
    saves_dir = Path(self.config["paths"]["unciv_saves"])
    prefix = self.config.get("unciv", {}).get("saves_prefix", "current_game")
    self.save_path = saves_dir / f"{prefix}_{env_rank}.json"
    self.template_path = saves_dir / "template_game.json"

    self.max_turns = self.config["environment"]["max_turns"]

    # Inizializza headless (Fase 2)
    unciv_cfg = self.config.get("unciv", {})
    jar_path = unciv_cfg.get("jar_path", "unciv/Unciv.jar")
    timeout = unciv_cfg.get("headless_timeout", 30)
    self.headless = UncivHeadless(jar_path=jar_path, timeout=timeout)

    # Spazi Gymnasium (invariati)
    self.observation_space = gym.spaces.Box(
        low=0.0, high=1.0, shape=(7,), dtype=np.float32
    )
    self.action_space = gym.spaces.Discrete(len(ACTION_MAP))

    self._current_state: Optional[GameState] = None
    self._prev_state: Optional[GameState] = None
    self._episode_steps = 0
```

**2. Aggiornare `_start_new_game`**

```python
def _start_new_game(self) -> None:
    """Crea una nuova partita copiando il template (Fase 1 e 2)."""
    self.headless.start_new_game(self.template_path, self.save_path)
```

**3. Aggiornare `_advance_turn`**

```python
def _advance_turn(self) -> None:
    """
    Fase 2: avanza il turno via Unciv headless.
    Sostituisce lo stub JSON della Fase 1.
    """
    self.headless.advance_turn(self.save_path)
```

**4. Import da aggiungere in cima al file**

```python
from src.utils.headless import UncivHeadless
```

---

## Aggiornamento: `train.py`

Aggiornare `make_env` per passare `env_rank`:

```python
def make_env(config_path: str, rank: int = 0):
    """Factory function per make_vec_env con env_rank per save files separati."""
    def _init():
        env = UncivEnv(config_path=config_path, env_rank=rank)
        return Monitor(env)
    return _init


def train(config_path: str = "config/default_config.yaml", resume: str = None) -> None:
    ...
    n_envs = tc["n_envs"]

    # Ogni env ha il suo save file: current_game_0.json, current_game_1.json ...
    env = make_vec_env(
        [make_env(config_path, rank=i) for i in range(n_envs)],
        n_envs=n_envs,
    )
    eval_env = make_vec_env([make_env(config_path, rank=n_envs)], n_envs=1)
    ...
```

> ⚠️ L'env di valutazione usa `rank=n_envs` (es. rank=4) per avere un save file
> separato anche dai 4 env di training.

---

## Test: `tests/test_headless.py`

```python
import pytest
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
    import subprocess
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
    # Non creare il file → jar non esiste
    with pytest.raises(FileNotFoundError):
        UncivHeadless(jar_path=str(jar))
```

---

## Checklist Fase 2

```
[ ] Unciv.jar scaricato in unciv/Unciv.jar
[ ] headless testato manualmente con java -jar unciv/Unciv.jar headless
[ ] config/default_config.yaml aggiornato con sezione unciv:
[ ] src/utils/headless.py creato
[ ] src/envs/unciv_env.py aggiornato (env_rank + UncivHeadless)
[ ] train.py aggiornato (make_env con rank)
[ ] tests/test_headless.py creato — tutti i test passano
[ ] python train.py avviato con headless reale
[ ] TensorBoard: ep_rew_mean cresce rispetto alla Fase 1
```

---

## Note per Claude Code
- `UncivHeadless` deve essere **mockabile nei test** — non chiamare subprocess direttamente in `unciv_env.py`
- Il `env_rank` dell'env di valutazione è sempre `n_envs` (non 0) — evita conflitti sui save files
- Se Unciv headless non è ancora disponibile: lasciare lo stub JSON della Fase 1 e saltare al file `09_expansion.md` per preparare l'observation space
- Loggare sempre il tempo medio per turno su TensorBoard (`unciv/turn_time_ms`) — se supera 5 secondi il training diventa impraticabile
