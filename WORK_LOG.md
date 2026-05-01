# WORK_LOG.md — Diario sessioni

> Aggiornare **obbligatoriamente** alla fine di ogni sessione con Claude Code.
> Non sovrascrivere le sessioni precedenti — appendere sempre in cima.

---

## [2026-05-01] — Sessione 5

### Obiettivo sessione
Implementare `train.py` ed `evaluate.py` seguendo `05_ppo_training.md`.

### File modificati
- `tests/test_training.py` (creato — 4 test)
- `train.py` (modificato — implementazione completa)
- `evaluate.py` (creato — script valutazione)
- `src/agents/ppo_agent.py` (invariato — spec non definisce contenuto)

### Fatto
- Implementato `train()`: PPO con make_vec_env, CheckpointCallback, EvalCallback, resume da checkpoint
- Implementato `make_env()`: factory con Monitor wrapper (obbligatorio per EvalCallback)
- Implementato `load_config()`: lettura YAML
- Creato `evaluate.py`: valutazione N episodi con modello caricato
- Test: import check + `load_config` + `make_env` callable

### Problemi incontrati
- Nessuno

### Test
- [x] Tutti i test passano
- [x] Comando eseguito: `.venv/Scripts/python -m pytest tests/ -v`
- Output: `19 passed in 2.58s`

### TODO prossima sessione
1. Implementare monitoring TensorBoard (spec in `06_monitoring.md`)
2. Setup Unciv headless (spec in `07_unciv_setup.md`)

---

## [2026-05-01] — Sessione 4

### Obiettivo sessione
Implementare `src/utils/reward.py` e collegarlo a `unciv_env.py`.

### File modificati
- `tests/test_reward.py` (creato — 10 test)
- `src/utils/reward.py` (modificato — implementazione completa)
- `src/utils/reward_logger.py` (creato — verbose breakdown, richiesto da spec)
- `src/envs/unciv_env.py` (modificato — integrazione reward + terminal reward)

### Fatto
- Scritti 10 test prima dell'implementazione (TDD)
- Implementato `compute_reward` (pura, no side effects): 6 componenti (pop, edifici, tech, oro, happiness, idle)
- Implementato `compute_terminal_reward`: survival_bonus + progress_bonus
- Implementato `compute_reward_verbose` in `reward_logger.py` con breakdown per componente
- `unciv_env.py`: sostituito stub → `compute_reward`; aggiunto `compute_terminal_reward` su `terminated=True` (non su `truncated`)

### Problemi incontrati
- Nessuno

### Test
- [x] Tutti i test passano
- [x] Comando eseguito: `.venv/Scripts/python -m pytest tests/ -v`
- Output: `15 passed in 2.50s`

### TODO prossima sessione
1. Implementare `src/agents/ppo_agent.py` e `train.py` (spec in `05_ppo_training.md`)

---

## [2026-05-01] — Sessione 3

### Obiettivo sessione
Implementare `src/envs/unciv_env.py` e `tests/test_env.py`.

### File modificati
- `tests/test_env.py` (modificato — test reali da stub)
- `src/envs/unciv_env.py` (modificato — implementazione completa)

### Fatto
- Scritti test prima dell'implementazione (TDD)
- Implementato `UncivEnv(gym.Env)` con: `reset()`, `step()`, `render()`, `close()`
- `observation_space`: Box `(7,)` float32 — contratto rispettato con `state_parser.py`
- `action_space`: Discrete(7) — mappa `ACTION_MAP` 0-6
- Stub espliciti per `_start_new_game`, `_apply_action`, `_advance_turn`, `_compute_reward`
- `_is_terminated()` termina se `happiness < -10`

### Problemi incontrati
- Nessuno

### Test
- [x] Tutti i test passano
- [x] Comando eseguito: `.venv/Scripts/python -m pytest tests/ -v`
- Output: `5 passed in 2.45s`

### TODO prossima sessione
1. Implementare `src/utils/reward.py` (spec in `04_reward_function.md`)
2. Collegare `_compute_reward` in `unciv_env.py` al modulo reward

---

## [2026-05-01] — Sessione 2

### Obiettivo sessione
Implementare `src/parsers/state_parser.py` e `tests/test_parser.py`.

### File modificati
- `tests/test_parser.py` (modificato — test reali da stub)
- `src/parsers/state_parser.py` (modificato — implementazione completa)

### Fatto
- Scritti test prima dell'implementazione (TDD)
- Implementati `CityState`, `GameState` dataclass
- Implementato `UncivStateParser` con: `load()` (JSON + gzip), `parse()`, `to_observation_vector()`
- Vettore osservazione shape `(7,)` float32 — contratto con `unciv_env.py`
- Gestito caso `cities = []` (turno 1 senza città)

### Problemi incontrati
- Nessuno

### Test
- [x] Tutti i test passano
- [x] Comando eseguito: `.venv/Scripts/python -m pytest tests/ -v`
- Output: `3 passed in 2.66s`

### TODO prossima sessione
1. Implementare `src/envs/unciv_env.py` (spec in `03_gymnasium_env.md`)
2. Scrivere `tests/test_env.py` prima dell'implementazione

---

## [2026-05-01] — Sessione 1

### Obiettivo sessione
Setup ambiente completo: struttura cartelle, venv, dipendenze, verifica installazione.

### File modificati
- `src/__init__.py` (creato)
- `src/envs/__init__.py` (creato)
- `src/envs/unciv_env.py` (creato — stub)
- `src/agents/__init__.py` (creato)
- `src/agents/ppo_agent.py` (creato — stub)
- `src/parsers/__init__.py` (creato)
- `src/parsers/state_parser.py` (creato — stub)
- `src/utils/__init__.py` (creato)
- `src/utils/helpers.py` (creato — stub)
- `config/default_config.yaml` (creato)
- `requirements.txt` (creato)
- `train.py` (creato — stub)
- `tests/test_installation.py` (creato)
- `tests/test_env.py` (creato — stub)
- `tests/test_parser.py` (creato — stub)
- `.venv/` (creato — non in git)

### Fatto
- Creata struttura cartelle completa (`src/`, `config/`, `models/checkpoints/`, `logs/`, `saves/`, `tests/`)
- Creato venv Python 3.13.7 in `.venv/`
- Installato: stable-baselines3 2.8.0, gymnasium 1.2.3, numpy 2.4.4, tensorboard 2.20.0, pyyaml 6.0.3, pytest 9.0.3
- Tutti gli `__init__.py` creati (moduli importabili)
- `config/default_config.yaml` creato con iperparametri da spec

### Problemi incontrati
- pytest non in requirements.txt originale → aggiunto

### Test
- [x] Tutti i test passano
- [x] Comando eseguito: `.venv/Scripts/python -m pytest tests/ -v`
- Output: `1 passed in 2.46s`

### TODO prossima sessione
1. Implementare `src/parsers/state_parser.py` (spec in `02_unciv_state_parser.md`)
2. Scrivere `tests/test_parser.py` prima dell'implementazione

---

## [TEMPLATE — copiare per ogni nuova sessione]

```
## [YYYY-MM-DD] — Sessione N

### Obiettivo sessione
(cosa si voleva fare)

### File modificati
- path/al/file.py (creato | modificato | eliminato)

### Fatto
- 

### Problemi incontrati
- 

### Test
- [ ] Tutti i test passano
- [ ] Comando eseguito: `python -m pytest tests/ -v`
- Output rilevante:

### TODO prossima sessione
1. 
2. 
```

---

## [2024-01-01] — Sessione 0 (setup iniziale)

### Obiettivo sessione
Setup repository e file di configurazione progetto.

### File modificati
- `CLAUDE.md` (creato)
- `WORK_LOG.md` (creato)
- `.claudeignore` (creato)
- `.gitignore` (creato)
- `config/default_config.yaml` (creato)

### Fatto
- Definita architettura completa del progetto
- Scelto stack: PPO + Stable-Baselines3 + Gymnasium
- Creati file di configurazione repo

### Problemi incontrati
- Nessuno

### Test
- [ ] Tutti i test passano
- Nessun test ancora (da implementare dalla Sessione 1)

### TODO prossima sessione
1. Creare struttura cartelle (`src/`, `tests/`, ecc.)
2. Installare dipendenze e verificare con `tests/test_installation.py`
3. Implementare `src/parsers/state_parser.py` (spec in `02_unciv_state_parser.md`)
