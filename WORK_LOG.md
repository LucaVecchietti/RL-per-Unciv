# WORK_LOG.md — Diario sessioni

> Aggiornare **obbligatoriamente** alla fine di ogni sessione con Claude Code.
> Non sovrascrivere le sessioni precedenti — appendere sempre in cima.

---

## [2026-05-02] — Sessione 11

### Obiettivo sessione
Implementare File 08 — headless integration (Fase 2.0).

### File modificati
- `src/utils/headless.py` (creato — UncivHeadless: advance_turn, start_new_game, is_available)
- `tests/test_headless.py` (creato — 10 test TDD con mock subprocess)
- `src/envs/unciv_env.py` (modificato — import headless, __init__ con template_path + UncivHeadless, _start_new_game, _advance_turn)
- `config/default_config.yaml` (modificato — sezione unciv: jar_path, headless_timeout, saves_prefix)
- `WORK_LOG.md` (questo aggiornamento)

### Fatto
- Creato `UncivHeadless` con logica subprocess isolata e mockabile
- `_advance_turn` ora delega a `self.headless.advance_turn(self.save_path)`
- `_start_new_game` ora delega a `self.headless.start_new_game(template_path, save_path)`
- Rimosso `UncivSimulator` da `unciv_env.py` — non più usato
- `self.template_path` aggiunto in `__init__` da config `paths.unciv_saves`
- Tutte le costanti in config: `jar_path`, `headless_timeout`, `saves_prefix`
- Training Fase 1.5 analizzato: reward 34.5 → 37.5 a 500k step, modello salvato come `fase1_5_final_model.zip`

### Problemi incontrati
- Java non visibile dalla sandbox PowerShell (PATH limitato) — nessun impatto: user ha Java in PATH nel proprio terminale (`C:\ProgramData\Oracle\Java\javapath\java.exe`)
- `shutil` rimasto come import orfano dopo refactoring — rimosso

### Test
- [x] Tutti i test passano
- [x] Comando eseguito: `.venv\Scripts\python -m pytest tests/ -v`
- Output: `54 passed in 6.87s`

### TODO prossima sessione
1. **Verificare headless manuale:** `! java -jar unciv/Unciv.jar headless` dal terminale — verificare che Unciv supporti il flag e gli argomenti `--save-file --advance-turn`
2. Se headless funziona: avviare training con `python train.py` e monitorare TensorBoard
3. Se headless non supporta quegli argomenti: investigare API reale Unciv headless e aggiornare `headless.py`
4. Verificare che il template `saves/template_game.json` sia corretto per Unciv headless (potrebbe servire formato diverso dal template JSON per simulatore)
5. Quando training headless stabile: procedere a File 09 (Fase 2.1 — unit movement)

---

## [2026-05-01] — Sessione 10

### Obiettivo sessione
Pianificazione Fase 2.0 e 2.1 + aggiornamento spec file 08-10.

### File modificati
- `md_file_x_claude_code/08_headless_integration.md` (modificato — scope Fase 2.0, DummyVecEnv, nota env_rank già fatto)
- `md_file_x_claude_code/09_unit_movement.md` (creato — piano completo Fase 2.1)
- `md_file_x_claude_code/09_expansion_DEPRECATED.md` (rinominato — vecchio file 09 deprecato)
- `md_file_x_claude_code/10_obs_space_migration.md` (modificato — shapes (10,), azioni 11, MaskablePPO)
- `WORK_LOG.md` (questo aggiornamento)

### Fatto

**Discussione architetturale Fase 2:**
- Problema multi-action: in Unciv per turno ci sono N decisioni indipendenti
- Soluzione scelta: **per-entity rotation** — sistema cicla entità (città, poi ogni warrior), agente vede una entità alla volta, action space resta `Discrete(K)`
- Scartato Multi-Discrete: spazio esplode, PPO soffre

**Piano Fase 2.0 (headless integration):**
- Scope minimo: stessa action space `Discrete(7)`, stessa obs `(7,)` float32
- Solo `_advance_turn` cambia: `UncivSimulator.advance_turn()` → `UncivHeadless.advance_turn()`
- Criterio successo: training gira con Unciv reale, ep_rew_mean comparabile a Fase 1.5

**Piano Fase 2.1 (unit movement):**
- N Warriors illimitati, build-first (agente costruisce Warrior prima di muoverlo)
- Per-entity rotation: city step → warrior_0 step → warrior_1 step → turno avanza
- Action space: `Discrete(11)` — 0-6 costruzione/idle, 7-10 movimento N/S/E/W
- Observation: `(10,)` — aggiunge n_warriors, selected_warrior_x/y, tiles_explored
- Action masking: `MaskablePPO` da `sb3-contrib` — movimento valido solo se warrior esiste con MP > 0
- Reward exploration: +0.3 per tile nuova esplorata
- Movimento: 1 tile/turno, solo Warrior (no Horseman per ora)
- Criterio successo: ≥1 Warrior entro turno 50, >30% mappa esplorata, sopravvive 200 turni

**Spec file aggiornati:**
- File 08: scope Fase 2.0 chiarito, DummyVecEnv corretto
- File 09: riscrittura completa (ex "expansion" → "unit_movement")
- File 10: shapes aggiornate (12,)→(10,), azioni 9→11, step MaskablePPO aggiunto

**Nota:** durante sessione il training Fase 1.5 ha girato in background — checkpoint fino a 110k step presenti in `models/checkpoints/`.

### Problemi incontrati
- Nessuno

### Test
- N/A — sessione di pianificazione e documentazione, nessuna modifica al codice

### TODO prossima sessione
1. **Controllare risultati training Fase 1.5:** aprire TensorBoard (`tensorboard --logdir logs`), verificare `ep_rew_mean` a 110k step
2. Se `ep_rew_mean > 0.0` e crescente → continuare training fino a 500k
3. Se `ep_rew_mean` piatta → `python src/utils/diagnose_run.py sim` per diagnostica
4. Se `action_Idle > 70%` → aumentare `ent_coef` da 0.01 a 0.05
5. Quando `ep_rew_mean > 1.0` → salvare `fase1_5_final.zip` e aprire File 08 (headless)
6. **Prossima fase implementativa:** File 08 (`08_headless_integration.md`) — prerequisito: Java installato e Unciv.jar scaricato

---

## [2026-05-01] — Sessione 9

### Obiettivo sessione
Diagnostica training (File 13) + aggiornamento docs (File 14).

### File modificati
- `src/utils/diagnose_run.py` (creato — diagnosi save file + simulazione 30 turni)
- `config/default_config.yaml` (modificato — ent_coef 0.01, n_steps 1024, max_turns 150, total_timesteps 500k)
- `train.py` (modificato — ent_coef letto da config, passato a PPO)
- `COMMANDS.md` (modificato — sezione Diagnostica con comandi diagnose_run.py)
- `WORK_LOG.md` (questo aggiornamento)

### Fatto
- Creato `diagnose_run.py` con due modalità: analisi save file reale (warning automatici) e simulazione 30 turni manuale
- Fix import per esecuzione come script (`sys.path.insert` con path root progetto)
- Simulazione 30 turni verificata: Monument completa turno 17, pop cresce, tech avanza — simulatore corretto
- Config Fase 1.5 applicata: n_steps 2048→1024, max_turns 200→150, total_timesteps 1M→500k, ent_coef 0.01 aggiunto
- `train.py` legge `ent_coef` con `tc.get("ent_coef", 0.0)` — backward compatible

### Problemi incontrati
- `python src/utils/diagnose_run.py sim` → `ModuleNotFoundError: No module named 'src'` — fix: aggiunto `sys.path.insert(0, ...)` in cima al file

### Test
- [x] Tutti i test passano
- [x] Comando eseguito: `.venv/Scripts/python -m pytest tests/ -v`
- Output: `44 passed in 2.62s`

### Fix post-sessione
- `train.py`: `make_vec_env(lista, n_envs)` → `DummyVecEnv(lista)` — SB3 non accetta lista di callable come `env_id` in `make_vec_env`. Fix: import `DummyVecEnv` e uso diretto. Commit `75c3519`.

### TODO prossima sessione
1. **Rilanciare training:** `python train.py` (interrompere run precedente se attivo)
2. Monitorare con TensorBoard: `tensorboard --logdir logs`
3. Target 100k step: `ep_rew_mean > 0.0`
4. Target 500k step: `ep_rew_mean > 2.0`
5. Se reward piatta dopo 200k → `python src/utils/diagnose_run.py sim`
6. Se action_Idle > 70% → aumentare `ent_coef` da 0.01 a 0.05 in config
7. Quando `ep_rew_mean > 1.0` → salvare `fase1_5_final.zip` e aprire File 08

---

## [2026-05-01] — Sessione 8

### Obiettivo sessione
Implementare Fase 1.5: micro-simulatore Python (File 11) + fix race condition env_rank (File 12).

### File modificati
- `src/utils/simulator.py` (creato — UncivSimulator: produzione, popolazione, scienza, oro, happiness)
- `tests/test_simulator.py` (creato — 14 test TDD)
- `src/envs/unciv_env.py` (modificato — import UncivSimulator, self.simulator, _advance_turn reale, env_rank)
- `train.py` (modificato — make_env con rank, env/eval_env con save file separati)
- `tests/test_env.py` (modificato — fixture env_rank=0 esplicito + test race condition)
- `CLAUDE.md` (modificato — Fase 1.5 completata, struttura utils, contratti aggiornati)
- `WORK_LOG.md` (questo aggiornamento)

### Fatto
- Implementato `UncivSimulator` con formule Unciv: produzione (3+pop-1 prod/turn), crescita popolazione (food threshold), scienza (Library bonus), oro (1/città/turn), happiness (9.0 base + Monument - pop penalty)
- Fix race condition: ogni env ora usa `current_game_{rank}.json` separato
- `train.py`: eval env usa `rank=n_envs` (es. rank=4 per n_envs=4)
- 14 nuovi test simulatore + 1 test race condition — tutti passano
- Suite totale: **44 test passati**

### Problemi incontrati
- Nessuno — spec File 11 e 12 corrette e coerenti con codebase esistente

### Test
- [x] Tutti i test passano
- [x] Comando eseguito: `.venv/Scripts/python -m pytest tests/ -v`
- Output: `44 passed in 4.13s`

### TODO prossima sessione
1. Creare `src/utils/diagnose_run.py` (File 13) — diagnostica save file e simulazione 30 turni
2. Rilanciare training con simulatore: `python train.py` — interrompere run precedente
3. Monitorare `ep_rew_mean` — deve superare 0.0 entro 100k step, 2.0 entro 500k
4. Se reward piatta dopo 200k step → `python src/utils/diagnose_run.py sim`
5. Quando `ep_rew_mean > 1.0` → salvare `fase1_5_final.zip` e aprire File 08

---

## [2026-05-01] — Sessione 7

### Obiettivo sessione
Verifica save file Unciv, primo training reale, fix documentazione.

### File modificati
- `CLAUDE.md` (modificato — civilizzazione Romans → India nella tabella contratti)
- `src/parsers/state_parser.py` (modificato — default player_civ Romans → India)
- `src/envs/unciv_env.py` (modificato — Romans → India in 2 punti)
- `tests/test_parser.py` (modificato — Romans → India ovunque)
- `tests/test_env.py` (modificato — Romans → India)
- `tests/test_reward.py` (modificato — Romans → India)
- `COMMANDS.md` (creato — riferimento completo tutti i comandi)
- `README.md` (modificato — descrizione completa per repo GitHub)
- `_verify.py` (creato — script verifica save file, non in git)

### Fatto
- Rinominata civilizzazione da `"Romans"` a `"India"` in tutti i file .py (9 occorrenze) e CLAUDE.md — 29 test passano ancora
- Creato `saves/template_game.json` manualmente via Unciv (partita India, Tiny, Chieftain, 0 AI, 2 turni)
- Verificato save file valido con `_verify.py` — obs vector `shape=(7,)` corretto
- Avviato primo training reale `python train.py` — nessun errore
- Avviato TensorBoard con `tensorboard --logdir logs` — metriche custom `unciv/` visibili
- Fix comando TensorBoard in COMMANDS.md e README.md (`tensorboard --logdir logs`, non `python -m tensorboard`)

### Problemi incontrati
- `python -m tensorboard` non funziona → usare `tensorboard --logdir logs` direttamente
- PowerShell heredoc (`<< 'EOF'`) non supportato → usato `-c` su singola riga o file `_verify.py`

### Test
- [x] Tutti i test passano
- [x] Comando eseguito: `.venv/Scripts/python -m pytest tests/ -v`
- Output: `29 passed in 2.74s`

### Stato training al momento della chiusura sessione
```
iterations: 2 | total_timesteps: 16384 | fps: ~38
ep_rew_mean: -1.11 (normale, agente esplora casualmente)
action_*: distribuzione uniforme ~14% ciascuna (esplorazione)
happiness_mean: 0, gold_mean: 3
```

### TODO prossima sessione
1. Controllare `ep_rew_mean` — deve salire verso valori positivi
2. Se reward piatta dopo 200k+ step → analizzare con `python src/utils/analyze_run.py`
3. Se agente converge su azione singola → aumentare `ent_coef` in config
4. Eventuale Fase 2: espansione con Settler e gestione save files paralleli (`env_rank`)

---

## [2026-05-01] — Sessione 6

### Obiettivo sessione
Implementare monitoring TensorBoard (`06_monitoring.md`). Setup Unciv headless (`07_unciv_setup.md`) = solo step manuali, nessun codice.

### File modificati
- `tests/test_callbacks.py` (creato — 10 test)
- `src/utils/callbacks.py` (creato — `UncivMetricsCallback`, `ActionDistributionCallback`)
- `src/utils/analyze_run.py` (creato — `analyze_evaluations`)
- `train.py` (modificato — aggiunto `metrics_cb` e `action_cb` a `CallbackList`)

### Fatto
- Scritti 10 test prima dell'implementazione (TDD)
- Implementato `UncivMetricsCallback`: logga gold/happiness/cities/turns per rollout
- Implementato `ActionDistributionCallback`: logga frequenza azioni ogni 10k step
- Implementato `analyze_evaluations`: legge `evaluations.npz` da EvalCallback senza TensorBoard
- `train.py` aggiornato con i 4 callback (checkpoint, eval, metrics, action)
- Bug trovato e corretto nei test: `num_timesteps` è plain attr in SB3 2.8.0 (non property)

### Problemi incontrati
- `logger`, `training_env` e `num_timesteps` sembravano property, ma solo `logger` e `training_env` delegano a `model`; `num_timesteps` è plain attribute → risolto settando `cb.num_timesteps` direttamente

### Test
- [x] Tutti i test passano
- [x] Comando eseguito: `.venv/Scripts/python -m pytest tests/ -v`
- Output: `29 passed in 2.57s`

### TODO prossima sessione
1. **Azione manuale richiesta:** seguire `07_unciv_setup.md` per installare Unciv e generare `saves/template_game.json`
2. Dopo aver creato il template: testare `python -m pytest tests/ -v` + avviare training reale con `python train.py`

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
