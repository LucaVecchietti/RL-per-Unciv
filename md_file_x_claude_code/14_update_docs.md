# 14 — Aggiornamenti CLAUDE.md e WORK_LOG per Fase 1.5

## Obiettivo
Mantenere la documentazione sincronizzata. Eseguire **per ultimo**,
dopo che tutti i test passano e il training è avviato.

---

## Aggiornamenti CLAUDE.md

### 1. Sezione "Fasi di sviluppo"

```markdown
## Fasi di sviluppo
- [x] **Fase 1** — Gestione singola città (produzione, tech, oro, happiness)
- [x] **Fase 1.5** — Micro-simulatore Python (reward reali, training rapido)
- [ ] **Fase 2** — Unciv Headless + espansione (File 08-10)
- [ ] **Fase 3** — Combattimento
- [ ] **Fase 4** — Diplomazia + vittoria completa
```

### 2. Sezione "Struttura del progetto" — aggiungere in `utils/`

```
├── simulator.py         # NUOVO: micro-simulatore turno Unciv (Fase 1.5)
└── diagnose_run.py      # NUOVO: diagnostica training e save file
```

### 3. Tabella "Contratti critici" — aggiungere righe

```markdown
| Simulatore attivo     | `UncivSimulator` in `_advance_turn`        | `simulator.py` ↔ `unciv_env.py` |
| Save file per env     | `current_game_{rank}.json`                 | `unciv_env.py` ↔ `train.py`     |
```

### 4. Aggiungere sezione "Stato training"

```markdown
## Stato training corrente

| Run | Timesteps | ep_rew_mean | Note |
|---|---|---|---|
| Fase 1 (stub JSON) | ~50k | ~-1.1 | Nessun segnale reale |
| Fase 1.5 (simulatore) | in corso | TBD | Reward da simulazione Python |

> Aggiornare dopo ogni run significativo.
```

---

## Template WORK_LOG — Sessione 8

```markdown
## [2026-05-XX] — Sessione 8

### Obiettivo sessione
Implementare Fase 1.5: micro-simulatore Python + fix race condition env_rank.

### File modificati
- `src/utils/simulator.py` (creato)
- `src/utils/diagnose_run.py` (creato)
- `src/envs/unciv_env.py` (modificato — import, self.simulator, _advance_turn, env_rank)
- `train.py` (modificato — make_env con rank)
- `tests/test_simulator.py` (creato)
- `tests/test_env.py` (modificato — env_rank fixture + test race condition)
- `CLAUDE.md` (modificato)
- `WORK_LOG.md` (questo aggiornamento)

### Fatto
- Implementato UncivSimulator: produzione, popolazione, scienza, oro, happiness
- Fix race condition: ogni env usa current_game_{rank}.json
- Tutti i test passano (29 + N nuovi)
- Training rilanciato con simulatore

### Problemi incontrati
- [compilare durante la sessione]

### Test
- [ ] Tutti i test passano
- Comando: `.venv\Scripts\python -m pytest tests/ -v`
- Output: [incollare]

### Stato training
```
iterations: X | total_timesteps: X | fps: ~X
ep_rew_mean: X
```

### TODO prossima sessione
1. Monitorare ep_rew_mean — deve superare 0 entro 100k step
2. Se dopo 200k step reward piatta → python src/utils/diagnose_run.py sim
3. Quando ep_rew_mean > 1.0 → salvare fase1_5_final.zip e aprire file 08
```

---

## Note per Claude Code
- Compilare il WORK_LOG con i dati reali della sessione
- I file `md_file_x_claude_code/` sono spec storiche — non modificarli
- La sezione "Stato training" in CLAUDE.md va aggiornata nei run futuri
