# WORK_LOG.md — Diario sessioni

> Aggiornare **obbligatoriamente** alla fine di ogni sessione con Claude Code.
> Non sovrascrivere le sessioni precedenti — appendere sempre in cima.

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
