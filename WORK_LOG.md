# WORK_LOG.md — Diario sessioni

> Aggiornare **obbligatoriamente** alla fine di ogni sessione con Claude Code.
> Non sovrascrivere le sessioni precedenti — appendere sempre in cima.

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
