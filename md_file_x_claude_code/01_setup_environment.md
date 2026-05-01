# 01 — Setup Environment

## Obiettivo
Creare la struttura completa del progetto, installare le dipendenze e verificare che tutto funzioni prima di scrivere una riga di logica.

---

## Struttura cartelle da creare

```
unciv-rl-agent/
├── src/
│   ├── envs/               # Ambiente Gymnasium custom
│   │   ├── __init__.py
│   │   └── unciv_env.py
│   ├── agents/             # Logica dell'agente PPO
│   │   ├── __init__.py
│   │   └── ppo_agent.py
│   ├── parsers/            # Lettura/scrittura stato JSON di Unciv
│   │   ├── __init__.py
│   │   └── state_parser.py
│   └── utils/              # Funzioni di supporto
│       ├── __init__.py
│       └── helpers.py
├── config/
│   └── default_config.yaml # Iperparametri e configurazione
├── models/
│   └── checkpoints/        # Modelli salvati (ignorato da git)
├── logs/                   # Log TensorBoard (ignorato da git)
├── saves/                  # Save files Unciv (ignorato da git)
├── tests/
│   ├── test_env.py
│   └── test_parser.py
├── requirements.txt
├── README.md
└── train.py                # Entry point principale
```

---

## Comandi da eseguire

### 1. Crea la struttura cartelle
```bash
mkdir -p unciv-rl-agent/{src/{envs,agents,parsers,utils},config,models/checkpoints,logs,saves,tests}
cd unciv-rl-agent
touch src/{__init__.py,envs/__init__.py,agents/__init__.py,parsers/__init__.py,utils/__init__.py}
touch train.py
```

### 2. Crea e attiva l'ambiente virtuale
```bash
python -m venv .venv
# Linux/macOS
source .venv/bin/activate
# Windows
.venv\Scripts\activate
```

### 3. Installa le dipendenze
```bash
pip install stable-baselines3[extra] gymnasium pyyaml tensorboard numpy
pip freeze > requirements.txt
```

---

## Contenuto di `requirements.txt` atteso
```
stable-baselines3>=2.3.0
gymnasium>=0.29.0
pyyaml>=6.0
tensorboard>=2.16.0
numpy>=1.26.0
```

---

## Contenuto di `config/default_config.yaml`
```yaml
training:
  total_timesteps: 1_000_000
  n_envs: 4                  # Ambienti paralleli
  learning_rate: 0.0003
  n_steps: 2048              # Passi per update PPO
  batch_size: 64
  n_epochs: 10
  gamma: 0.99                # Discount factor
  clip_range: 0.2

environment:
  max_turns: 200             # Turni massimi per episodio (Fase 1)
  map_size: "tiny"           # tiny | small | standard
  victory_type: "science"    # Obiettivo iniziale semplificato

paths:
  save_dir: "models/checkpoints"
  log_dir: "logs"
  unciv_saves: "saves"
```

---

## Script di verifica installazione

Crea `tests/test_installation.py` con questo contenuto e poi eseguilo:

```python
def test_imports():
    import gymnasium
    import stable_baselines3
    import numpy
    import yaml
    import tensorboard
    print("✅ Tutte le dipendenze sono installate correttamente")
    print(f"  gymnasium:          {gymnasium.__version__}")
    print(f"  stable-baselines3:  {stable_baselines3.__version__}")
    print(f"  numpy:              {numpy.__version__}")

if __name__ == "__main__":
    test_imports()
```

```bash
python tests/test_installation.py
```

---

## Note per Claude Code
- Usa Python 3.11+
- Tutti i path sono relativi alla root del progetto `unciv-rl-agent/`
- Il file `config/default_config.yaml` è l'unica fonte di verità per gli iperparametri — nessun valore hardcoded nel codice
- Ogni modulo deve avere il suo `__init__.py` anche se vuoto
