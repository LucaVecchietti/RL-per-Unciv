# COMMANDS.md — Riferimento comandi

## Setup iniziale

```powershell
# Crea e attiva ambiente virtuale
python -m venv .venv
.venv\Scripts\Activate.ps1

# Installa dipendenze (include sb3-contrib per MaskablePPO)
pip install -r requirements.txt

# Verifica installazione
python -m pytest tests/test_installation.py -v
```

---

## Verifica save file Unciv

```powershell
# Verifica che il template sia leggibile dal parser
.venv\Scripts\python -c "
from src.parsers.state_parser import UncivStateParser
p = UncivStateParser()
s = p.parse('saves/template_game.json')
obs = p.to_observation_vector(s)
print(f'Turno: {s.turn}, Citta: {len(s.cities)}, Gold: {s.gold}')
print(f'Obs: shape={obs.shape}, dtype={obs.dtype}')
"
```

Output atteso:
```
Turno: 2, Citta: 1, Gold: 50.0
Obs: shape=(52,), dtype=float32
```

---

## Training

```powershell
# Training da zero (usa config/default_config.yaml)
.venv\Scripts\python train.py

# Training con config personalizzata
.venv\Scripts\python train.py --config config/mia_config.yaml

# Riprendere da checkpoint MaskablePPO
.venv\Scripts\python train.py --resume models/checkpoints/unciv_mppo_100000_steps.zip
```

> ⚠️ Checkpoint `unciv_ppo_*` (Fase 1.5) non compatibili con MaskablePPO.
> Usare solo checkpoint `unciv_mppo_*`.

---

## Valutazione

```powershell
# Valuta il miglior modello salvato (default: 10 episodi)
.venv\Scripts\python evaluate.py

# Valuta modello specifico
.venv\Scripts\python evaluate.py --model models/checkpoints/best/best_model.zip --episodes 20
```

---

## Monitoring

```powershell
# Avvia TensorBoard (secondo terminale, durante il training)
tensorboard --logdir logs
# Poi apri: http://localhost:6006

# Analisi rapida senza TensorBoard (dopo almeno una valutazione)
.venv\Scripts\python src/utils/analyze_run.py
```

---

## Diagnostica masking (Fase 2.1)

```powershell
# Verifica che action_masks() funzioni via DummyVecEnv
.venv\Scripts\python -c "
from stable_baselines3.common.vec_env import DummyVecEnv
from train import make_env
env = DummyVecEnv([make_env('config/default_config.yaml', rank=0)])
masks = env.env_method('action_masks')
print('masks:', masks)
print('city step ok:', all(masks[0][0:7]) and not any(masks[0][7:11]))
env.close()
"
```

Output atteso:
```
masks: [array([ True,  True,  True,  True,  True,  True,  True, False, False, False, False])]
city step ok: True
```

Se `city step ok: False` → `ActionMasker` non configurato correttamente in `make_env`.

---

## Diagnostica training

```powershell
# Analisi stato save file corrente (segnala anomalie)
.venv\Scripts\python src/utils/diagnose_run.py

# Analisi save file specifico
.venv\Scripts\python src/utils/diagnose_run.py saves/current_game_0.json

# Simulazione manuale 30 turni (verifica formule simulatore)
.venv\Scripts\python src/utils/diagnose_run.py sim
```

Output atteso `sim`:
```
 Turn |   Gold |  Happy |  Pop | Built                     | Techs
   17 |   67.0 |    9.0 |    3 | ['Monument']              | ['Agriculture', 'Pottery']
```

---

## Test

```powershell
# Suite completa
.venv\Scripts\python -m pytest tests/ -v

# Moduli specifici
.venv\Scripts\python -m pytest tests/test_parser.py -v
.venv\Scripts\python -m pytest tests/test_env.py -v
.venv\Scripts\python -m pytest tests/test_reward.py -v
.venv\Scripts\python -m pytest tests/test_callbacks.py -v
.venv\Scripts\python -m pytest tests/test_headless.py -v
.venv\Scripts\python -m pytest tests/test_training.py -v
```

---

## Unciv headless fork

```powershell
# Test manuale avanzamento turno (verifica JAR custom)
& "C:\Program Files\Eclipse Adoptium\jdk-25.0.3.9-hotspot\bin\java.exe" `
  -jar unciv\Unciv.jar `
  --advance-turn `
  --save-file saves\template_game.json

# Output atteso: TURN_ADVANCED:N (o "Turn advanced. New turn: N")
# Exit code atteso: 0
```

---

## Struttura output training

```
models/checkpoints/
    unciv_mppo_10000_steps.zip   # Checkpoint automatici (MaskablePPO)
    unciv_mppo_50000_steps.zip
    fase2_1_final_model.zip      # Modello finale sessione corrente
    best/
        best_model.zip           # Miglior reward media (MaskableEvalCallback)

logs/
    MaskablePPO_1/
        events.out.tfevents.*    # File TensorBoard
        evaluations.npz          # Dati valutazione (per analyze_run.py)
```

---

## Configurazione

Tutti gli iperparametri sono in `config/default_config.yaml`:

| Parametro | Default | Descrizione |
|---|---|---|
| `training.total_timesteps` | `500_000` | Step totali di training |
| `training.n_envs` | `4` | Ambienti paralleli |
| `training.learning_rate` | `0.0003` | Learning rate |
| `training.n_steps` | `1024` | Step per update (4×1024=4096 per batch) |
| `training.batch_size` | `64` | Mini-batch size |
| `training.ent_coef` | `0.01` | Entropia — aumentare a 0.05 se policy collassa |
| `environment.max_turns` | `150` | Turni massimi per episodio |
| `environment.map_size` | `tiny` | Dimensione mappa |
| `reward.exploration` | `0.3` | Reward per tile nuova esplorata |
| `unciv.java_path` | percorso JDK | Path java.exe per headless |
| `unciv.headless_timeout` | `60` | Secondi max per turno headless |
