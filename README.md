# RL-per-Unciv

Agente di Reinforcement Learning che impara a giocare a **Unciv** — clone open-source di Civilization V — tramite PPO e self-play.

L'agente interagisce con il gioco leggendo e scrivendo i file di salvataggio JSON di Unciv, senza modificare il codice del gioco.

---

## Stack tecnico

| Componente | Tecnologia |
|---|---|
| Algoritmo RL | PPO (Proximal Policy Optimization) |
| Framework RL | Stable-Baselines3 v2+ |
| Ambiente | Gymnasium (API standard) |
| Monitoring | TensorBoard |
| Linguaggio | Python 3.11+ |
| Config | YAML (unica fonte di verità) |

---

## Architettura

```
saves/template_game.json          # Save file Unciv (input)
         │
         ▼
src/parsers/state_parser.py       # JSON → vettore numpy (7,) float32
         │
         ▼
src/envs/unciv_env.py             # Ambiente Gymnasium custom
         │
         ▼
src/utils/reward.py               # Reward function (pura, densa)
         │
         ▼
train.py  ──►  PPO (SB3)  ──►  models/checkpoints/
         │
         ▼
src/utils/callbacks.py            # Metriche custom su TensorBoard
```

### Spazio delle azioni — Fase 1

| Azione | Effetto |
|---|---|
| 0 | Costruisci Monument |
| 1 | Costruisci Granary |
| 2 | Costruisci Library |
| 3 | Costruisci Barracks |
| 4 | Costruisci Settler |
| 5 | Costruisci Warrior |
| 6 | Fine turno |

### Osservazione

Vettore `(7,)` float32 normalizzato in `[0, 1]`:
```
[turn/500, gold/1000, happiness/20, n_cities/10, n_techs/80, population/20, n_buildings/20]
```

### Reward function

```
reward = crescita_popolazione + edifici_completati + tecnologie_scoperte
       + gestione_oro - penalty_happiness_negativa - penalty_idle
```

---

## Installazione

**Prerequisiti:** Python 3.11+, Java 11+ (per Unciv)

```powershell
git clone https://github.com/LucaVecchietti/RL-per-Unciv.git
cd RL-per-Unciv

python -m venv .venv
.venv\Scripts\Activate.ps1

pip install -r requirements.txt
python tests/test_installation.py
```

---

## Quick start

**1. Prepara il save file Unciv**

Avvia Unciv, crea una partita con civilta **India**, mappa **Tiny**, difficolta **Chieftain**, 0 avversari AI. Fai 2 turni, salva come `template`, poi:

```powershell
Copy-Item "$env:APPDATA\Roaming\Unciv\saves\template" ".\saves\template_game.json"
python _verify.py
```

**2. Avvia il training**

```powershell
python train.py
```

**3. Monitora i progressi**

```powershell
# In un secondo terminale
tensorboard --logdir logs
# Apri http://localhost:6006
```

**4. Valuta il modello**

```powershell
python evaluate.py --model models/checkpoints/best/best_model.zip
```

---

## Struttura del progetto

```
RL-per-Unciv/
├── src/
│   ├── envs/unciv_env.py         # Ambiente Gymnasium
│   ├── agents/ppo_agent.py       # Agente PPO
│   ├── parsers/state_parser.py   # Parser JSON Unciv
│   └── utils/
│       ├── reward.py             # Reward function
│       ├── callbacks.py          # Callback TensorBoard
│       ├── reward_logger.py      # Debug reward breakdown
│       └── analyze_run.py        # Analisi run offline
├── config/default_config.yaml    # Iperparametri
├── tests/                        # 29 test (pytest)
├── saves/                        # Save files Unciv
├── models/checkpoints/           # Modelli salvati
├── logs/                         # Log TensorBoard
├── train.py                      # Entry point training
├── evaluate.py                   # Valutazione modello
├── COMMANDS.md                   # Tutti i comandi
└── WORK_LOG.md                   # Diario sessioni di sviluppo
```

---

## Fasi di sviluppo

- [x] **Fase 1** — Gestione singola citta (produzione, tech, oro, happiness)
- [ ] **Fase 2** — Espansione (settler, esplorazione mappa)
- [ ] **Fase 3** — Combattimento (unita militari)
- [ ] **Fase 4** — Diplomazia e vittoria completa

---

## Test

```powershell
python -m pytest tests/ -v
# 29 test — parser, ambiente, reward, callback, training
```

---

## Configurazione

Tutti i parametri sono in `config/default_config.yaml` — nessun valore hardcoded nel codice.
Vedi `COMMANDS.md` per la tabella completa degli iperparametri.
