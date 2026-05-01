# 07 — Unciv Setup e Integrazione

## Obiettivo
Installare Unciv, generare il save file template per la Fase 1 e preparare
l'infrastruttura per l'integrazione headless nelle fasi successive.

---

## Prerequisiti di sistema

```bash
# Verifica Java installato (richiesto JDK 11+)
java -version

# Se non installato:
# Ubuntu/Debian
sudo apt install openjdk-17-jdk

# macOS (con Homebrew)
brew install openjdk@17

# Windows → scarica da https://adoptium.net
```

---

## Fase 1 — Setup manuale (adesso)

### Step 1 — Scarica Unciv

```bash
# Crea cartella dedicata fuori dalla repo Python
mkdir ~/unciv && cd ~/unciv

# Scarica l'ultima release
wget https://github.com/yairm210/Unciv/releases/latest/download/Unciv.jar

# Avvia
java -jar Unciv.jar
```

In alternativa scarica `Unciv.jar` manualmente da:
[github.com/yairm210/Unciv/releases/latest](https://github.com/yairm210/Unciv/releases/latest)

---

### Step 2 — Crea la partita template

Avvia Unciv e crea una nuova partita con **esattamente** queste impostazioni:

| Impostazione | Valore | Perché |
|---|---|---|
| Civiltà | **Romans** | Corrisponde al valore hardcoded nel parser |
| Mappa | **Tiny** | Stato JSON più piccolo, parsing più veloce |
| Difficoltà | **Chieftain** | Minima resistenza AI, focus sull'agente |
| Avversari AI | **0** | Nessuna variabile esterna nella Fase 1 |
| Seed mappa | **qualsiasi fisso** (es. `42`) | Riproducibilità tra run |

---

### Step 3 — Genera il save file

1. Fai esattamente **2 turni** nella partita
2. Salva la partita con il nome `template`
3. Trova il file salvato:

```
Linux:   ~/.local/share/Unciv/saves/template
Windows: %APPDATA%\Roaming\Unciv\saves\template
macOS:   ~/Library/Application Support/Unciv/saves/template
```

4. Copialo nella repo:

```bash
# Linux
cp ~/.local/share/Unciv/saves/template /path/to/unciv-rl-agent/saves/template_game.json

# Windows (PowerShell)
Copy-Item "$env:APPDATA\Roaming\Unciv\saves\template" ".\saves\template_game.json"

# macOS
cp ~/Library/Application\ Support/Unciv/saves/template ./saves/template_game.json
```

> ⚠️ Unciv salva i file senza estensione o come `.gz` a seconda della versione.
> Se il file è binario/compresso, il parser lo gestisce già (vedi `02_unciv_state_parser.md`).

---

### Step 4 — Verifica il save file

```bash
# Dalla root del progetto
python - << 'EOF'
from src.parsers.state_parser import UncivStateParser

parser = UncivStateParser(player_civ="Romans")
state = parser.parse("saves/template_game.json")

print(f"✅ Save file valido")
print(f"   Turno:        {state.turn}")
print(f"   Oro:          {state.gold}")
print(f"   Happiness:    {state.happiness}")
print(f"   Città:        {len(state.cities)}")
print(f"   Tecnologie:   {len(state.techs_researched)}")

obs = parser.to_observation_vector(state)
print(f"   Obs vector:   shape={obs.shape}, dtype={obs.dtype}")
print(f"   Valori:       {obs}")
EOF
```

Output atteso:
```
✅ Save file valido
   Turno:        2
   Oro:          50.0
   Happiness:    9.0
   Città:        1
   Tecnologie:   1
   Obs vector:   shape=(7,), dtype=float32
   Valori:       [0.004 0.05 0.45 0.1 0.012 0.15 0.05]
```

---

## Fase 2+ — Integrazione headless (training automatico)

Quando si passa al training reale, Unciv deve girare senza interfaccia grafica,
controllato da Python via `subprocess`.

### Modalità headless di Unciv

```bash
# Avvia Unciv in modalità headless (nessuna finestra)
java -jar Unciv.jar headless
```

> ⚠️ La modalità headless di Unciv è ancora in sviluppo attivo.
> Verificare lo stato corrente su: https://github.com/yairm210/Unciv/issues

### Struttura di integrazione Python → Unciv

```
Python (unciv_env.py)
    │
    ├─ scrive azione → saves/current_game_{rank}.json
    │
    ├─ subprocess.run(["java", "-jar", "Unciv.jar", "headless", "--advance-turn"])
    │
    └─ legge nuovo stato ← saves/current_game_{rank}.json
```

### Implementazione `_advance_turn()` per Fase 2

Sostituire lo stub in `unciv_env.py`:

```python
import subprocess
import time
from pathlib import Path

def _advance_turn(self):
    """
    Fase 2+: avanza il turno via Unciv headless.
    Sostituisce lo stub JSON della Fase 1.
    """
    result = subprocess.run(
        [
            "java", "-jar", str(self.unciv_jar_path),
            "headless",
            "--save-file", str(self.save_path),
            "--advance-turn"
        ],
        capture_output=True,
        text=True,
        timeout=30  # secondi — evita hang infiniti
    )

    if result.returncode != 0:
        raise RuntimeError(
            f"Unciv headless fallito (returncode {result.returncode})\n"
            f"stderr: {result.stderr}"
        )
```

Aggiungere in `config/default_config.yaml`:

```yaml
unciv:
  jar_path: "~/unciv/Unciv.jar"    # path al JAR
  headless_timeout: 30              # secondi max per turno
  saves_prefix: "current_game"      # prefisso save files paralleli
```

---

## Gestione save files paralleli (n_envs > 1)

Con `n_envs=4` servono 4 save files separati per evitare race conditions:

```
saves/
├── template_game.json      # template originale (read-only)
├── current_game_0.json     # env rank 0
├── current_game_1.json     # env rank 1
├── current_game_2.json     # env rank 2
└── current_game_3.json     # env rank 3
```

Aggiornare `UncivEnv.__init__()`:

```python
def __init__(self, config_path: str = "config/default_config.yaml",
             env_rank: int = 0, render_mode=None):
    ...
    self.save_path = (
        Path(self.config["paths"]["unciv_saves"])
        / f"current_game_{env_rank}.json"
    )
```

E aggiornare la factory in `train.py`:

```python
def make_env(config_path: str, rank: int):
    def _init():
        env = UncivEnv(config_path=config_path, env_rank=rank)
        return Monitor(env)
    return _init

env = make_vec_env(
    [make_env(config_path, rank=i) for i in range(tc["n_envs"])],
    n_envs=tc["n_envs"],
)
```

---

## Checklist setup completo

```
Fase 1 (adesso):
[ ] Java 11+ installato e verificato
[ ] Unciv.jar scaricato e avviabile
[ ] Partita template creata con le impostazioni corrette
[ ] saves/template_game.json presente nella repo
[ ] Script di verifica eseguito senza errori

Fase 2+ (quando si inizia il training reale):
[ ] Unciv headless testato manualmente
[ ] _advance_turn() aggiornato con subprocess
[ ] config/default_config.yaml aggiornato con sezione unciv:
[ ] Gestione save files paralleli implementata
[ ] Test di integrazione end-to-end scritto
```

---

## Note per Claude Code
- Il path `Unciv.jar` deve venire da `config/default_config.yaml`, mai hardcoded
- I save files `current_game_N.json` sono ignorati da `.gitignore` — solo `template_game.json` va committato
- In Fase 1 `_advance_turn()` è uno stub JSON — non implementare ancora subprocess
- Se Unciv headless non è disponibile nella versione scaricata, aprire una issue sul repo Unciv e usare lo stub JSON finché non viene rilasciato
