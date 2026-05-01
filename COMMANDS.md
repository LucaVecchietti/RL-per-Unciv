# COMMANDS.md — Riferimento comandi

## Setup iniziale

```powershell
# Crea e attiva ambiente virtuale
python -m venv .venv
.venv\Scripts\Activate.ps1

# Installa dipendenze
pip install -r requirements.txt

# Verifica installazione
python tests/test_installation.py
```

---

## Verifica save file Unciv

```powershell
# Prima di avviare il training, verifica che il template sia valido
python _verify.py
```

Output atteso:
```
Turno: 2, Citta: 1, Gold: 50.0
Obs: shape=(7,), dtype=float32
Valori: [...]
```

---

## Training

```powershell
# Training da zero (usa config/default_config.yaml)
python train.py

# Training con config personalizzata
python train.py --config config/mia_config.yaml

# Riprendere da checkpoint
python train.py --resume models/checkpoints/unciv_ppo_100000_steps.zip
```

---

## Valutazione

```powershell
# Valuta il miglior modello salvato (default: 10 episodi)
python evaluate.py

# Valuta modello specifico
python evaluate.py --model models/checkpoints/best/best_model.zip --episodes 20
```

---

## Monitoring

```powershell
# Avvia TensorBoard (secondo terminale, durante il training)
.venv\Scripts\python -m tensorboard --logdir logs\
# Poi apri: http://localhost:6006

# Analisi rapida senza TensorBoard (dopo almeno una valutazione)
python src/utils/analyze_run.py
```

---

## Test

```powershell
# Suite completa
python -m pytest tests/ -v

# Modulo specifico
python -m pytest tests/test_parser.py -v
python -m pytest tests/test_env.py -v
python -m pytest tests/test_reward.py -v
python -m pytest tests/test_callbacks.py -v
python -m pytest tests/test_training.py -v
```

---

## Struttura output training

```
models/checkpoints/
    unciv_ppo_10000_steps.zip     # Checkpoint automatici
    unciv_ppo_50000_steps.zip
    final_model.zip               # Modello finale
    best/
        best_model.zip            # Miglior reward media

logs/
    PPO_1/
        events.out.tfevents.*     # File TensorBoard
        evaluations.npz           # Dati valutazione (per analyze_run.py)
```

---

## Setup Unciv (prerequisito training reale)

```powershell
# 1. Verifica Java installato
java -version

# 2. Scarica Unciv.jar da:
#    https://github.com/yairm210/Unciv/releases/latest

# 3. Avvia Unciv, crea partita con:
#    - Civilta: India
#    - Mappa: Tiny
#    - Difficolta: Chieftain
#    - Avversari AI: 0
#    - Fai 2 turni, salva come "template"

# 4. Copia il save nella repo (Windows)
Copy-Item "$env:APPDATA\Roaming\Unciv\saves\template" ".\saves\template_game.json"

# 5. Verifica
python _verify.py
```

---

## Configurazione

Tutti gli iperparametri sono in `config/default_config.yaml`:

| Parametro | Default | Descrizione |
|---|---|---|
| `training.total_timesteps` | `1_000_000` | Step totali di training |
| `training.n_envs` | `4` | Ambienti paralleli |
| `training.learning_rate` | `0.0003` | Learning rate PPO |
| `training.n_steps` | `2048` | Step per update |
| `training.batch_size` | `64` | Mini-batch size |
| `environment.max_turns` | `200` | Turni massimi per episodio |
| `environment.map_size` | `tiny` | Dimensione mappa |
