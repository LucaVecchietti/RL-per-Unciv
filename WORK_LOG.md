# WORK_LOG.md — Diario sessioni

> Aggiornare **obbligatoriamente** alla fine di ogni sessione con Claude Code.
> Non sovrascrivere le sessioni precedenti — appendere sempre in cima.

---

## [2026-05-03] — Sessione 21

### Obiettivo sessione
Implementare File 16 — `src/utils/ruleset_reader.py` + `tests/test_ruleset_reader.py`.

### File modificati
- `src/utils/ruleset_reader.py` (creato)
- `tests/test_ruleset_reader.py` (creato)
- `WORK_LOG.md` (questo aggiornamento)

### Fatto
- `ConstructionInfo` dataclass: `name`, `required_tech: Optional[str]`, `is_unit: bool`
- `_load_jsonc(jar, path)`: strip commenti `//` e `/* */`, trailing commas → `json.loads`
- `get_ancient_classical_techs(jar_path)`: legge Techs.json (era blocks), filtra era Ancient + Classical
- `load_early_game_constructions(jar_path)`: filtra edifici (no wonders, no national wonders, no civ-unique, era constraint) + unità (unitType whitelist `{Sword, Scout, Civilian}`, no Great*, no civ-unique); ordine alfabetico edifici poi unità
- 10 test richiesti dalla spec — tutti con mock JAR in-memory (no dipendenza da JAR reale)

### Test
- [x] 74/74 test verdi: `python -m pytest tests/ -v`
- [x] 10/10 test `test_ruleset_reader.py` passano

### TODO prossima sessione
1. Implementare File 17 (`src/envs/unciv_env.py` — dynamic masking basato su tech + built_buildings, action space invariato Discrete(11))
2. Poi File 18 (expanded action space Discrete(~19), obs (~57,), 9 flag edifici)
3. Riavviare training dopo File 18 (checkpoint incompatibili con nuovo obs shape)

---

## [2026-05-02] — Sessione 20

### Obiettivo sessione
Pianificazione Fase 2.2 — scrittura spec files per i prossimi 3 step implementativi.

### File modificati
- `md_file_x_claude_code/16_fase2_2a_ruleset_reader.md` (creato)
- `md_file_x_claude_code/17_fase2_2b_dynamic_masking.md` (creato)
- `md_file_x_claude_code/18_fase2_2c_expanded_actions.md` (creato)
- `WORK_LOG.md` (questo aggiornamento)

### Fatto
- Verificato parsing ruleset dal JAR (JSONC con commenti + trailing commas)
- Path confermati: `jsons/Civ V - Vanilla/Buildings.json`, `Units.json`, `Techs.json`
- Identificati 9 edifici + 5 unità rilevanti Ancient+Classical
- Definita strategia: ACTION_MAP generato a runtime dal JAR, no hardcoding
- Split in 3 step per alleggerire ogni sessione:
  - **16**: `ruleset_reader.py` — lettura JAR, filtro era, dataclass `ConstructionInfo`
  - **17**: masking dinamico — `action_masks()` basato su tech + built_buildings (action space invariato)
  - **18**: action space espanso — Discrete(~19), obs (~57,), 9 flag edifici

### Test
- N/A — sessione documentazione

### TODO prossima sessione
1. Implementare File 16 (`src/utils/ruleset_reader.py` + `tests/test_ruleset_reader.py`)
2. Poi File 17 (dynamic masking)
3. Poi File 18 (expanded actions + obs)
4. Riavviare training dopo File 18 (checkpoint incompatibili con nuovo obs shape)

---

## [2026-05-02] — Sessione 19

### Obiettivo sessione
Fix bug scoperti a training avviato: metriche mancanti e ActionDistributionCallback stale.

### File modificati
- `src/utils/callbacks.py` (modificato — aggiunti `techs_mean`/`population_mean`, fix ActionDistribution 7→11 azioni)
- `src/envs/unciv_env.py` (modificato — aggiunti `n_techs` e `population` all'info dict)
- `tests/test_callbacks.py` (modificato — assert `(7,)` → `(11,)`)
- `WORK_LOG.md` (questo aggiornamento)

### Fatto
- `unciv/techs_mean` e `unciv/population_mean`: erano nella spec `06_monitoring.md` ma mai implementati in `callbacks.py` né nell'info dict di `unciv_env.py`
- `ActionDistributionCallback`: `_action_counts` array era `(7,)` e scartava azioni 7-10 (`MOVE_*`) — aggiornato a `(11,)` con nomi completi
- Fix applicati a training in corso — attivi al prossimo run

### Test
- [x] 64/64 test verdi

### TODO prossima sessione
- Monitorare training in corso (MaskablePPO_4)
- Verificare che al prossimo run compaiano `unciv/techs_mean`, `unciv/population_mean`, `unciv/action_MOVE_*`

---

## [2026-05-02] — Sessione 18

### Obiettivo sessione
Eliminare bottleneck JVM: ~5s/turno per spawn nuovo processo → training impraticabile
(~5.7 ore per primo log). Fix: modalità server JVM persistente.

### File modificati
- `unciv/Unciv/desktop/src/com/unciv/app/desktop/DesktopLauncher.kt` (modificato — aggiunto `--server` mode)
- `src/utils/headless.py` (riscritto — `subprocess.Popen` + persistent process + `close()`)
- `src/envs/unciv_env.py` (modificato — `close()` ora chiama `headless.close()`)
- `tests/test_headless.py` (riscritto — mock `subprocess.Popen`, 13 test inclusi `close` e `reuse_process`)
- `unciv/Unciv.jar` (ricompilato — include `--server` mode)
- `ARCHITECTURE.md` (modificato — sezione headless.py aggiornata, diagramma flusso)
- `WORK_LOG.md` (questo aggiornamento)

### Fatto

**Problema root cause:**
- Ogni `advance_turn()` lanciava `subprocess.run([java, -jar, Unciv.jar, --advance-turn, ...])` → ~5s JVM startup
- Con `n_envs=4`, `n_steps=1024`: 4096 advance_turn prima del primo log SB3 → ~5.7 ore

**Soluzione: modalità `--server` in DesktopLauncher.kt**
- JVM avvia `HeadlessApplication`, carica rulesets, stampa `READY\n` su stdout
- Poi entra in loop su stdin: comandi `advance <path>` o `quit`
- Per `advance`: chiama `nextTurn()`, salva JSON, stampa `ok <turn>\n`
- `System.out.flush()` esplicito dopo ogni risposta
- Due `CountDownLatch`: `initLatch` (segnala dopo READY), `doneLatch` (segnala dopo quit)
- Main thread: aspetta `initLatch` → aspetta `doneLatch` → `exitProcess(0)`

**Refactoring `src/utils/headless.py`**
- `subprocess.Popen` con `stdin/stdout/stderr=PIPE, text=True, bufsize=1`
- `_ensure_running()`: avvia processo se morto o None, legge `READY` con timeout
- `_readline_timeout(stream, t)`: thread daemon + `t.join(timeout)` per timeout su `readline()`
- `advance_turn()`: `stdin.write(f"advance {path}\n")`, `stdin.flush()`, legge risposta
- `close()`: `stdin.write("quit\n")`, `wait(5)`, terminate su fallback
- Lock threading per thread-safety (safety net, DummyVecEnv è single-thread)

**Costo atteso per turno:** ~50ms vs ~5s (stima −99% overhead headless)

**Verifica smoke-test:**
```
echo "advance saves/template_game.json\nquit" | java -jar unciv/Unciv.jar --server
→ READY
→ ok 5
```

### Test
- [x] 63/63 test verdi: `python -m pytest tests/ -v`
- [x] `test_headless.py`: 13 test (inclusi `test_close_sends_quit`, `test_reuse_process_across_calls`, `test_advance_turn_timeout`)

### TODO prossima sessione
1. **Avviare training:** `.venv\Scripts\python train.py`
2. **Verificare velocità:** primo log SB3 dovrebbe arrivare entro ~5 minuti (non 5.7 ore)
3. **Monitorare TensorBoard:** `tensorboard --logdir logs`
   - `unciv/action_MOVE_*` deve salire entro 50k step
   - `ep_rew_mean` target > 5.0 entro 500k step
4. **Se training crash:** controllare stderr JVM process (headless_timeout troppo basso?)


---

## [2026-05-02] — Sessione 17

### Obiettivo sessione
Aggiornare documentazione (ARCHITECTURE.md, COMMANDS.md, CLAUDE.md) allo stato Fase 2.1.

### File modificati
- `ARCHITECTURE.md` (modificato — riscritto per Fase 2.1)
- `COMMANDS.md` (modificato — aggiornato per Fase 2.1)
- `CLAUDE.md` (modificato — fix contratto stale UncivSimulator → UncivHeadless)
- `WORK_LOG.md` (questo aggiornamento)

### Fatto

**ARCHITECTURE.md:**
- Diagramma visione d'insieme: `PPO` → `MaskablePPO`, aggiunto Unciv fork JAR
- Flusso step: per-entity rotation completo (city step → unit step → advance turn)
- Obs layout aggiornato: `(7,)` → `(52,)` con tutti i 52 campi documentati
- Spazi Gymnasium: `Discrete(7)/(7,)` → `Discrete(11)/(52,)` + `action_masks()` doc
- Componenti: aggiornate tutte le firme e contratti, aggiunto `headless.py`, `_apply_movement`, `_get_obs`, `action_masks`
- Reward: aggiunta componente #7 exploration (`+explored_delta * 0.3`)
- `train.py` section: `MaskablePPO` + `ActionMasker` + `MaskableEvalCallback`, n_steps 1024
- File su disco: `unciv_mppo_*`, `fase2_1_final_model.zip`, `MaskablePPO_1/`
- Dipendenze: aggiunto `sb3_contrib`, rimosso `simulator.py` da dipendenze training
- Metriche TensorBoard: aggiornate con `unciv/action_Warrior` e `unciv/action_MOVE_*`

**COMMANDS.md:**
- Verifica save file: obs shape `(7,)` → `(52,)`
- Training: checkpoint names `unciv_ppo_*` → `unciv_mppo_*`, warning compatibilità
- Nuova sezione: diagnostica masking (`env.env_method("action_masks")`)
- Test: aggiunto `test_headless.py`
- Struttura output: `unciv_mppo_*`, `fase2_1_final_model.zip`, `MaskablePPO_1/`
- Tabella config: `n_steps` 2048→1024, `total_timesteps` 1M→500k, aggiunto `ent_coef`, `reward.exploration`, `unciv.java_path`, `unciv.headless_timeout`

**CLAUDE.md:**
- Fix contratto critico: `UncivSimulator in _advance_turn` → `UncivHeadless in _advance_turn`

### Test
- N/A — sessione documentazione, nessuna modifica al codice

### TODO prossima sessione
1. **Avviare training Fase 2.1:** `.venv\Scripts\python train.py`
2. **Monitorare TensorBoard:** `tensorboard --logdir logs`
   - `unciv/action_MOVE_*` deve salire entro 50k step
   - `unciv/action_Warrior` deve salire
   - `ep_rew_mean` target > 5.0 entro 500k step
3. **Se ep_rew_mean > 5.0** → Fase 2.1 completata → procedere Fase 2.2

---

## [2026-05-02] — Sessione 16

### Obiettivo sessione
File 15 — Migrare `train.py` ed `evaluate.py` da `PPO` a `MaskablePPO` (sb3-contrib).

### File modificati
- `train.py` (modificato — `MaskablePPO`, `ActionMasker`, `MaskableEvalCallback`, checkpoint prefix `unciv_mppo`)
- `evaluate.py` (modificato — `MaskablePPO`, `env.action_masks()` + `action_masks=masks` in `predict`)
- `WORK_LOG.md` (questo aggiornamento)

### Fatto

**Installazione:**
- `sb3-contrib 2.8.0` installato nel venv

**train.py:**
- Import: `MaskablePPO` da `sb3_contrib`, `ActionMasker`, `MaskableEvalCallback`
- `make_env`: aggiunto `ActionMasker(env, lambda e: e.action_masks())` tra `UncivEnv` e `Monitor`
- `train()`: `MaskablePPO(...)` invece di `PPO(...)`, checkpoint prefix `unciv_mppo`
- `EvalCallback` → `MaskableEvalCallback` (stessa firma, gestisce masks in eval)
- Modello finale salvato come `fase2_1_final_model.zip`

**evaluate.py:**
- `MaskablePPO.load(model_path)` invece di `PPO.load`
- Loop valutazione: `masks = env.action_masks()` + `model.predict(obs, action_masks=masks)`

**Verifica masking a runtime:**
- `env.env_method("action_masks")` su `DummyVecEnv([Monitor(ActionMasker(UncivEnv))])` → masks corrette
- City step: `[True]*7 + [False]*4` ✓

### Test
- [x] 60/60 test verdi: `python -m pytest tests/ -v` (nessuna modifica ai test necessaria)
- `test_train_module_imports` e `test_evaluate_module_imports` verdi senza modifiche

### TODO prossima sessione
1. **Avviare training Fase 2.1:** `python train.py`
2. **Monitorare TensorBoard:** `tensorboard --logdir logs`
   - `unciv/action_MOVE_*` deve salire entro 50k step (conferma masking funzionante)
   - `unciv/action_Warrior` deve salire (agente costruisce warrior)
   - `ep_rew_mean` target > 5.0 entro 500k step
3. **Se masking non funziona** (action_MOVE sempre 0): diagnostica con script verifica in File 15
4. **Se ep_rew_mean > 5.0** e warrior costruito regolarmente → Fase 2.1 completata → procedere Fase 2.2

---

## [2026-05-02] — Sessione 15

### Obiettivo sessione
Implementare File 10 — Fase 2.1: unità + movimento (action space Discrete(11), obs (52,), per-entity rotation, MaskablePPO action_masks).

### File modificati
- `requirements.txt` (modificato — aggiunto `sb3-contrib>=2.0.0`)
- `config/default_config.yaml` (modificato — aggiunta sezione `reward.exploration: 0.3`)
- `CLAUDE.md` (modificato — contratti: obs `(48,)`→`(52,)`, azioni `7`→`11`)
- `src/parsers/state_parser.py` (modificato — `to_observation_vector` esteso a `(52,)` con param `selected_unit`)
- `tests/test_parser.py` (modificato — shape assert `(48,)` → `(52,)`)
- `src/envs/unciv_env.py` (riscritto — `Discrete(11)`, per-entity rotation, `action_masks()`, `_apply_movement()`, `_advance_game_turn()`, `_get_obs()`)
- `tests/test_env.py` (riscritto — shape `(52,)`, n=11, +6 nuovi test per rotation e masks)
- `src/utils/reward.py` (modificato — aggiunto `exploration: 0.3` weight + componente reward #7)
- `tests/test_reward.py` (modificato — aggiunto `test_exploration_reward`)
- `WORK_LOG.md` (questo aggiornamento)

### Fatto

**state_parser.py:**
- `to_observation_vector` accetta `selected_unit: Optional[UnitState] = None`
- Aggiunge campi `[48-51]`: sel_x, sel_y, sel_movement (normalizzato /2.0), tiles_explored_ratio
- Shape `(48,)` → `(52,)`, assert aggiornato

**unciv_env.py — Fase 2.1:**
- `ACTION_MAP` esteso: azioni 7-10 = MOVE_NORTH/SOUTH/EAST/WEST
- `observation_space` shape `(52,)`, `action_space = Discrete(11)`
- `action_masks()`: azioni 0-6 valide in city step, 6+7-10 valide in unit step
- Per-entity rotation in `step()`:
  - City step: applica costruzione → se warriors con MP>0 → transition to unit step (reward=0) o advance turn
  - Unit step: applica movimento → se altri warriors → resto unit step (reward=0) o advance turn
  - `_buffered_city_action` traccia azione città per reward calculation
- `_advance_game_turn()`: metodo privato che concentra advance_turn + parse + reward + info
- `_get_obs()`: seleziona `selected_unit` da `_pending_warriors[_unit_rotation_index]` se in unit step
- `_apply_movement()`: sposta warrior nel JSON (tile swap su tileList)
- `_apply_action()`: guard `if action >= 7: return` per sicurezza

**reward.py:**
- `REWARD_WEIGHTS["exploration"] = 0.3`
- Componente #7: `explored_delta * weights["exploration"]` se `> 0`

### Test
- [x] 60/60 test verdi: `python -m pytest tests/ -v`
- Nuovi test: `test_action_masks_city_step`, `test_action_masks_unit_step`, `test_per_entity_rotation_transitions_to_unit_step`, `test_per_entity_rotation_advances_turn_after_warrior`, `test_obs_contains_selected_unit_coords`, `test_exploration_reward`

### TODO prossima sessione
1. **Installare sb3-contrib:** `pip install sb3-contrib>=2.0.0`
2. **Aggiornare train.py:** sostituire `PPO` con `MaskablePPO` da `sb3_contrib`, passare `action_masks` a `predict` e al training
3. **Test training Fase 2.1:** `python train.py` — verificare nessun crash, monitorare `ep_rew_mean` e `unciv/exploration`
4. **Criterio successo Fase 2.1:** agente costruisce ≥1 Warrior entro turno 50, esplora >30% mappa, `ep_rew_mean > 5.0`
5. **Se training stabile:** procedere a Fase 2.2 (multi-città, Settler, FoundCity)

---

## [2026-05-02] — Sessione 14

### Obiettivo sessione
Implementare File 09 — obs space reale `(48,)` da JSON save Unciv.

### File modificati
- `src/parsers/state_parser.py` (riscritto — obs vector `(48,)`, parsing reale da JSON)
- `src/envs/unciv_env.py` (modificato — `observation_space` shape `(7,)` → `(48,)`)
- `tests/test_parser.py` (modificato — MOCK_SAVE formato reale, assert `(7,)` → `(48,)`)
- `tests/test_env.py` (modificato — assert `(7,)` → `(48,)` in `test_spaces` e `test_step_output_shape`)
- `CLAUDE.md` (modificato — contratto obs vector `(7,)` → `(48,)`)
- `WORK_LOG.md` (questo aggiornamento)

### Fatto

**state_parser.py completo riscrittura:**
- Aggiunto `_TECH_COSTS` e `_CONSTRUCTION_COSTS` per normalizzazione costi
- `UnitState` dataclass: name, x, y, movement_points, health
- `CityState` aggiornato: +food_stored, food_threshold, production_stored, current_construction_cost, tiles_worked, x, y
- `GameState` aggiornato: +units, tiles_explored, total_tiles, science_per_turn, culture_per_turn, current_tech_progress, current_tech_cost, n_known_civs, at_war, gold_per_turn
- `_parse_stats_history()`: regex `r'([A-Z])(-?\d+)'` su stringa compressa `S44N1C2P5H8...`
- `_parse_units()`: scan tileList per owner==player_civ
- `_extract_game_state()`: usa `techsInProgress` per current_tech, `statsHistory` per happiness/science/culture, `proximity` per n_known_civs
- `_parse_city()`: usa `constructionQueue[0]`, `inProgressConstructions`, `population.population`, `workedTiles`, `location`
- `to_observation_vector()`: vettore `(48,)` float32 — Global(6)+City1(16)+Tech(8)+Units(8)+City2(8)+Diplomacy(2)

**Adattamenti da ispezione JSON reale:**
- `statsForNextTurn` non esiste → `statsHistory` con parsing regex
- `tech.currentTechnology` non esiste → `next(iter(techsInProgress), None)`
- `cityConstructions.currentConstruction` non esiste → `constructionQueue[0]`
- `cityStats` sempre vuoto → stats/turno default 0.0 (calcolati a runtime)
- Popolazione: `population.population` default 1 se assente (Unciv non salva se =1)

### Test
- [x] 54/54 test verdi: `python -m pytest tests/ -v`

### TODO prossima sessione
1. **File 10 — Training reale:** avviare `python train.py` con Unciv headless vero
2. Verificare che `to_observation_vector` funzioni su save file reale (stampare obs da save esistente)
3. Eventuale tuning reward function basato su segnali reali

---

## [2026-05-02] — Sessione 13

### Obiettivo sessione
Implementare File 08 — Fork Unciv + headless CLI `--advance-turn`.

### File modificati
- `unciv/Unciv/desktop/src/com/unciv/app/desktop/DesktopLauncher.kt` (modificato — aggiunto ramo `--advance-turn` con HeadlessApplication + CountDownLatch)
- `unciv/Unciv/build.gradle.kts` (modificato — aggiunto `gdx-backend-headless` a dipendenze desktop)
- `unciv/Unciv/gradle/wrapper/gradle-wrapper.properties` (modificato — Gradle 8.11.1 → 8.14)
- `unciv/Unciv/desktop/build/libs/Unciv.jar` (non in git — JAR custom buildato)
- `unciv/Unciv.jar` (non in git — copia JAR custom per uso Python)
- `src/utils/headless.py` (modificato — java_path configurabile, args corretti `--advance-turn --save-file`)
- `src/envs/unciv_env.py` (modificato — passa java_path a UncivHeadless, timeout default 60s)
- `config/default_config.yaml` (modificato — aggiunto java_path, headless_timeout: 60)
- `WORK_LOG.md` (questo aggiornamento)

### Fatto

**Kotlin fork di Unciv:**
- Aggiunto ramo `--advance-turn --save-file <path>` in `DesktopLauncher.main()`
- Usa `HeadlessApplication` (non consoleMode) per leggere jsons da dentro il JAR
- `CountDownLatch` sincronizza main thread con HeadlessApplication thread
- `UncivFiles.gameInfoFromString()` + `gameInfo.nextTurn()` + `UncivFiles.gameInfoToString()` — tutto companion object
- Output: `TURN_ADVANCED:<n>` su stdout, exit code 0 su successo

**Problemi risolti:**
- Gradle 8.11.1 + JDK 25 → `IllegalArgumentException: 25.0.3` in Kotlin parser
  - Fix: installato JDK 21 via winget (`EclipseAdoptium.Temurin.21.JDK`)
  - Build con JDK 21, runtime con JDK 25 (entrambi funzionano)
  - Gradle upgradato a 8.14 (non necessario ma rimasto)
- `MissingModsException: Civ V - Gods & Kings` — consoleMode usa filesystem, non JAR
  - Fix: HeadlessApplication inizializza `Gdx.files` → `loadRulesets(consoleMode=false)` legge da JAR
  - Aggiunto `gdx-backend-headless` alle dipendenze desktop
- HeadlessApplication non-blocking → `exitProcess(0)` killava processo prima di `create()`
  - Fix: `CountDownLatch(1)` — main thread attende `create()` poi chiama `exitProcess`

**Test manuale:**
- Turno 1 → 2 → 3 verificati manualmente con `TURN_ADVANCED:X` su stdout
- Exit code 0

**Python:**
- `headless.py`: `java_path` configurabile, subprocess args corretti
- `unciv_env.py`: legge `java_path` da config, default `"java"`
- `config.yaml`: `java_path` = percorso JDK 25

### Test
- [x] 54 test Python verdi: `python -m pytest tests/ -v`
- [x] Test manuale headless: `TURN_ADVANCED:2`, `TURN_ADVANCED:3`

### TODO prossima sessione
1. **Implementare File 09 (obs (48,)):** aggiornare `state_parser.py` per leggere campi reali dal save JSON
   - Step 1: stampare chiavi JSON da save file reale per trovare path corretti
   - Step 2-12: aggiornare parser, env, test
2. **Aggiornare contratti CLAUDE.md:** obs shape `(7,)` → `(48,)` quando File 09 completato
3. **Test training con Unciv reale:** `python train.py` — verificare nessun crash, reward cresce

---

## [2026-05-02] — Sessione 12

### Obiettivo sessione
Verifica headless Unciv + pivot architettura verso agente competitivo + riscrittura spec 08-10.

### File modificati
- `md_file_x_claude_code/08_headless_integration.md` (riscritto — piano fork Unciv con CLI --advance-turn)
- `md_file_x_claude_code/09_real_obs_space.md` (creato — obs (48,) reale da save Unciv)
- `md_file_x_claude_code/09_unit_movement.md` (deprecato — sostituito da 09_real_obs_space)
- `md_file_x_claude_code/10_competitive_roadmap.md` (creato — roadmap fasi 2.1→2.2→3→4→play)
- `WORK_LOG.md` (questo aggiornamento)

### Fatto

**Scoperta critica — headless non funziona come previsto:**
- `java -jar Unciv.jar headless` avvia server multiplayer, non advance-turn
- Flag `--save-file --advance-turn` non esistono in Unciv ufficiale
- Verificato manualmente: il processo si avvia ma rimane in attesa (server mode)
- Unico progetto RL esistente (CivAgent) usa multiplayer HTTP — troppo lento per training

**Decisione architetturale:**
- Obiettivo finale: agente competitivo contro umani in partite multiplayer reali
- Soluzione: fork Unciv (open source Kotlin), aggiungere CLI --advance-turn in DesktopLauncher.kt
- Training: Unciv fork headless (~1k step/min, meccaniche reali)
- Play mode: HTTP server Python riceve richieste da Unciv multiplayer

**Spec riscritte:**
- File 08: fork Unciv — clone → leggi sorgente → scrivi Kotlin → build → test
- File 09: obs (48,) reale — tile yields, unit positions, tech progress, diplomazia
- File 10: roadmap completa — Fasi 2.1 (unità), 2.2 (multi-città), 3.0 (combat), 4.0 (self-play), Play (HTTP)

### Problemi incontrati
- Java non in PATH della sandbox PowerShell — usare percorso completo `C:\Program Files\Eclipse Adoptium\jdk-25.0.3.9-hotspot\bin\java.exe`
- `headless.py` implementato in Sessione 11 usa API che non esistono — da aggiornare quando fork pronto

### Test
- N/A — sessione di diagnostica e pianificazione, nessuna modifica al codice

### TODO prossima sessione
1. **Clonare Unciv:** `git clone https://github.com/yairm210/Unciv.git unciv-src`
2. **Leggere DesktopLauncher.kt** — trovare API esatte: `loadGameFromFile`, `nextTurn`, `saveGame`
3. **Scrivere Kotlin** per ramo `--advance-turn` in DesktopLauncher.kt
4. **Build custom JAR:** `.\gradlew desktop:dist` (prima build ~10-15 min)
5. **Test manuale:** `java -jar unciv\Unciv.jar --advance-turn --save-file saves\template_game.json`
6. **Aggiornare headless.py:** aggiungere `java_path` configurabile
7. **Aggiornare config.yaml:** aggiungere `java_path` e `headless_timeout: 60`

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
