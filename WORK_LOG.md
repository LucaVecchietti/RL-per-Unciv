# WORK_LOG.md — Diario sessioni

> Aggiornare **obbligatoriamente** alla fine di ogni sessione con Claude Code.
> Non sovrascrivere le sessioni precedenti — appendere sempre in cima.

---

## [2026-05-31] — Sessione 44 — Pianificazione File 26 (tech management)

### Obiettivo sessione
Pianificare File 26: dare all'agente il controllo esplicito della scelta tech invece di lasciarla all'auto-picker alfabetico, sbloccare tutto il tech tree (74 tech), aggiungere `era_one_hot` in obs.

### Metodo (skill `/team plan`)
Discovery in parallelo `unciv-engine` + `rl-trainer` per:
1. Verificare ipotesi utente "cap 18 nel masking".
2. Inventario API Unciv per scelta tech.
3. Proporre design RL + reward shaping (utente ha delegato la decisione reward).

### Risultati discovery

**Ipotesi utente "cap 18 nel masking" — FALSA**.
- Non esiste azione `RESEARCH_<tech>` nell'env (`unciv_env.py:222-273`).
- Tech tree ruleset Civ V Vanilla = **74 tech** totali.
- Plateau a ~18 è **naturale**: `ruleset_reader.load_tech_prereqs` filtra solo Ancient+Classical (~21 tech) via `_TARGET_ERAS`, e l'auto-picker alfabetico in `unciv_env.py:452-500` completa ~18 di queste in 155 turni con mono-città.

**Bug latente scoperto** (`state_parser.py:174`): `current_tech` letto da `next(iter(techsInProgress))` ma `techsInProgress` è una `HashMap` Java → ordine non garantito. Fonte autoritativa: `techsToResearch[0]` (`TechManager.kt:129-131`). Fix incluso in File 26.

**API Unciv** (`unciv-engine`):
- Scelta tech via `civInfo.tech.techsToResearch.add(name)` + `updateResearchProgress()`.
- Pattern UI usa `getRequiredTechsToDestination` per path automatico dei prereq.
- Validazione: `canBeResearched(name)` in `TechManager.kt:176-183`.

### Scelte confermate dall'utente

1. **Scope tech: TUTTE le 74** (utente ha confermato la sua intuizione originale, sovrascrivendo la raccomandazione `rl-trainer` di limitarsi a Ancient+Classical). Razionale utente: massima flessibilità anche se in 155 turni l'agente ne vede ~25.
2. **Reward shaping: invariato** (no `tech_speed_bonus`). `tech_researched: 3.0` sparso + `tech_progress: 0.5` denso (File 23.1) sufficienti. Vittoria scientifica irraggiungibile in 155 turni → no rischio bias.
3. **Obs: `era_one_hot` +5 dim** → contratto `(61,) → (66,)`. Cambio CLAUDE.md richiesto.
4. **Fix bug `current_tech` incluso nel File 26**.

### File modificati
- `md_file_x_claude_code/26_tech_management.md` (creato — 278 righe)

### Design (sintesi)
- 74 azioni `RESEARCH_<tech>` discrete (ordine alfabetico)
- Action space: `Discrete(23) → Discrete(97)` (isolato)
- Masking via prereqs locali Python (no round-trip headless)
- Nuovo sub-step "research" dopo city steps, prima di unit steps
- Skip → fallback all'auto-picker esistente (safety net)
- 3 comandi server Kotlin: `settech`, `listtechs`, `techinfo`
- `load_all_tech_prereqs` (senza filtro era) + `load_tech_eras`
- Obs `era_one_hot` per Ancient/Classical/Medieval/Renaissance/Industrial
- Reward invariato

### Contratti che cambiano
- Obs vector: `(61,) → (66,)`
- Action space: `Discrete(23) → Discrete(97)` isolato (cumulato con File 23/24/25 → `Discrete(136+)`)
- Nuovi comandi headless: `settech`, `listtechs`, `techinfo`
- **CLAUDE.md tabella contratti** da aggiornare in fase implementazione.

### Test
N/A — sessione di pianificazione (no codice).

### Note / rischi
- **Sparsità masking**: 74 azioni con mask attivo per ~5-10 alla volta. Da monitorare `entropy_loss`/`clip_fraction` in TB.
- **Cumulativo action space**: combinato con File 23/24/25 può superare 130 azioni. Possibile bisogno di policy network più ampia.
- **Auto-pick fallback** ora pesca da tutte le 74 tech (era 21) — comportamento subottimale by design ma stabile.

### Ordine di implementazione aggiornato
1. File 23.1 (reward rework)
2. File 23 (Worker completo, Opzione B)
3. File 24 (buildroad)
4. File 25 (popolazione città)
5. **File 26 (tech management)**

### TODO prossima sessione
1. Implementare File 23.1 via `/team implement` (prossimo in coda).
2. File 26 può essere implementato anche prima di File 23/24/25 (è indipendente dagli altri — vedi sezione Prerequisito della spec).

---

## [2026-05-31] — Sessione 43 — Validazione Run #22 + Pianificazione File 23.1 (reward rework)

### Obiettivo sessione
1. Validare il Run #22 (500k step, ~2h45) come prerequisito per File 23.
2. Pianificare File 23.1 (reward rework) prima di implementare File 23, per correggere `cities_founded` calante osservato nel Run #22.

### Validazione Run #22
- 500k step completati, **nessun crash**.
- `eval/mean_reward`: 166.14 (50k) → 175.73 (500k), peak **176.00 a 450k**. Trend monotonamente crescente, +10 punti in 10 eval.
- `improvements_built_mean`: 0 (Run #20) → 5-15 stabile.
- `connected_resources_mean`: 0-1 sporadico (era 0 stabile).
- `fps`: 50 stabile (era 18-39 in Run #20).
- `units_stuck_mean`: oscilla 4-100 (era esploso a 275 in Run #20).
- `gold_mean`: passa da -210 a +400/+700 (cash flow risolto).
- `action_Worker`: 0.014 → 0.04 (3×), `moved_worker_mean`: 94 → 950 (10×).
- `action_Idle`: 0.22 → 0.11 (agente più attivo).

**Anomalie osservate** (non bloccanti, ma motivano File 23.1):
1. **`cities_founded_mean` cala** 2 → 0-1; `action_FoundCity` 0.05 → 0.002. L'agente DE-impara a fondare città — diagnosi: `found_city: 5.0` è one-shot, no gradiente per espansione continua.
2. **`techs_mean = 18` costante** — l'agente non sceglie tech attivamente, nessun reward su accumulo.
3. **`connected_resources_mean` resta basso** (~0-1) — Worker fa improve di vario tipo, raramente connettenti.

Prerequisito File 23 dichiarato in `23_worker_full_improvements.md` SODDISFATTO.

### File modificati
- `md_file_x_claude_code/23.1_reward_rework.md` (creato — 252 righe)

### Metodo (skill `/team plan`)
Discovery focalizzata su `rl-trainer` (le direttive utente sono già concrete; engine, tests, docs non coinvolti in design). `rl-trainer` ha analizzato `reward.py`, metriche Run #22, e prodotto un piano in 7 sezioni (A-G). Sintesi presentata all'utente con 3 scelte chiave via AskUserQuestion. Tutte le opzioni "Recommended" confermate.

### Scelte confermate (File 23.1)

**A. Direttive utente (literal)**:
- `resource_connected` differenziato per tipo: Bonus +3, Strategic +4, Luxury +5.
- 5 stats accumulate uniformi: `science/gold/culture/happiness/faith_accumulated = 0.25 × max(0, delta)` turn-per-turn.
- Delta clippato a 0 sui cali (non penalizziamo fluttuazioni transitorie).
- `faith_accumulated` armato ma inerte (faith_per_turn non ancora nel parser).

**B. Diagnosi cities_founded calante**:
- `found_city: 5.0 → 3.0` (riduzione varianza one-shot).
- `cities_alive_bonus: 0.05` per turno per città oltre la prima (continuum, gradiente denso).

**C. Proposte aggiuntive rl-trainer**:
- `tech_progress: 0.5` su delta normalizzato `progress/cost` (sblocca techs_mean=18).
- `units_stuck_penalty: 0.02` per unità stuck.
- `happiness_bonus: 0.05` se `happiness > 5` (cap, comportamento meno risk-averse).
- `building_diversity: 0.5` una tantum per ogni edificio nuovo nel set globale.

**Feature flag**: tutti i pesi vanno in `config/default_config.yaml`, ablation via `peso = 0.0` senza PR multiple.

### Ordine di implementazione aggiornato
1. **File 23.1** (reward rework) — prossimo
2. File 23 (Worker completo, Opzione B)
3. File 24 (buildroad)
4. File 25 (popolazione città)

### Test
N/A — sessione di pianificazione (no codice).

### Note / contratti
- **Contratti CLAUDE.md invariati**: obs `(61,)`, action `Discrete(23)`. File 23.1 tocca solo logica reward + GameState fields (non obs).
- Nessun rebuild JAR (modifiche solo Python).
- Criteri di accettazione 50k step: `ep_rew_mean ∈ [180, 250]`, `connected_resources_mean ≥ 1.5`, `techs_mean ≥ 20`, `cities_founded_mean ≥ 1.5`, `action_FoundCity ≥ 0.005`.

### TODO prossima sessione
1. Implementare File 23.1 via `/team implement` (engine non coinvolto, principalmente rl-trainer + tests-engineer).
2. Run di validazione 50k step dopo implementazione per verificare criteri di accettazione.
3. Se ok → procedere con File 23 (Worker completo).

---

## [2026-05-30] — Sessione 42 — Pianificazione File 24 + File 25

### Obiettivo sessione
Pianificare due nuovi file di spec mentre il training di validazione (post-fix Sessione 40+41) gira:
- **File 24** — comando `buildroad` + reward rete commerciale città↔capitale
- **File 25** — gestione popolazione città (focus + worked tiles fine)

### File modificati
- `md_file_x_claude_code/24_buildroad.md` (creato — 143 righe)
- `md_file_x_claude_code/25_city_population.md` (creato — 163 righe, poi corretto a 8 focus invece di 6)

### Metodo
Skill `/team plan` (prima invocazione dopo creazione Sessione 41). Discovery in parallelo dei 4 sub-agenti, ognuno con brief specifico per entrambi i file:
- `unciv-engine`: inventario tecnico Kotlin (API, campi save serializzati vs @Transient, comandi server proposti). Vedi `CivInfoTransientCache.kt:46`, `City.kt:158` (proxy serializzabile `connectedToCapitalStatus`), `CityPopulationManager.kt:158-215` (`autoAssignPopulation`).
- `rl-trainer`: proposte obs/action/masking/reward/metriche. Reward event-based per File 24, invariata per File 25.
- `tests-engineer`: lista test richiesti per ciascun file (headless + env + parser + reward + smoke).
- `docs-keeper`: convenzioni di formato (allineate a File 22/23), stato CLAUDE.md, numerazione (24, 25 senza gap).

### Scelte confermate dall'utente
**File 24**:
- Comando server: **`buildroad <path> <unitId>`** dedicato (non estensione di `improve`)
- Reward: **solo `city_connected_to_capital = 4.0` event-based** (no reward denso su road_built)
- Obs: +3 globali → `(61,) → (64,)`
- Action: +1 `BUILD_ROAD`

**File 25**:
- Granularità: **Focus + worktile fine (entrambi)** — controllo a due livelli
- **8 azioni `SET_FOCUS_*`** allineate alla UI Unciv (Food/Production/Gold/Science/Culture/Faith/GoldGrowth/ProductionGrowth — esclusi Default e Manuale meta-modi, e Happiness che non è tra gli 8 focus UI). Correzione applicata dopo due round di feedback utente: prima "le azioni di focus sono 8 non 6", poi "non esclude science".
- +18 azioni `WORK_TILE_<clock>` toggle, disponibili solo se `cityAIFocus = Manual`
- Action space: `Discrete(24+N) → Discrete(50+N)` (post File 24)
- Obs MVP: `(64,) → (82,)` (focus_one_hot + free_pop per 2 città). Estensione: `(82,) → (100,)` (worked_tile_mask città selezionata).
- Reward: **invariata** (segnale indiretto via metriche esistenti)

**Ordine implementazione**: 24 prima di 25.

### Test
N/A — sessione di pianificazione (no codice).

### Note / dipendenze
- File 24 era già citato come fuori scope esplicito in `23_worker_full_improvements.md:121-122`.
- File 25 è scope nuovo, non precedentemente tracciato (segnalato nella spec).
- Entrambi richiedono **rebuild JAR** (nuovi comandi Kotlin).
- Limite noto File 24: `City.connectedToCapitalStatus` viene aggiornato a `startTurn` successivo (non istantaneo dopo `buildroad`) — reward arriva 1 turno dopo.
- Decisione di disabilitazione AI cittadina File 25: implicita lato motore (`worktile` imposta `cityAIFocus=Manual`). Le 8 `SET_FOCUS_*` riattivano `autoAssignPopulation` con priorità diversa.

### TODO prossima sessione
1. Aspettare metriche training corrente (post-fix Sessione 40+41). Atteso: `improvements_built_mean > 0`, `connected_resources_mean` in crescita, `units_stuck_mean` in calo.
2. Se stabile per ≥100k step → **implementare File 23** (Worker completo, Opzione B) con `/team implement`.
3. Dopo File 23 stabile → implementare File 24 (`buildroad`).
4. Dopo File 24 stabile → implementare File 25 (popolazione città).

---

## [2026-05-30] — Sessione 41

### Obiettivo sessione
1. Creare una skill `/team` che orchestra i 4 sub-agenti project-scoped in due modalità (`implement` / `plan`).
2. Fixare un crash del training emerso al primo `improve` reale dopo il fix di Sessione 40: `ValueError: invalid literal for int() with base 10: 'well'` su risposta JVM `improving Oil well 5`.

### File modificati
- `.claude/skills/team/SKILL.md` (creato — skill `/team` con modalità `implement <task>` e `plan`, tabella routing agenti/dominio, regole anti-deriva, contesto progetto)
- `src/utils/headless.py` (modificato — `build_improvement` parsa nomi multi-token: `parts[-1]=turni`, `parts[1:-1]=nome` con `" ".join`; aggiunti guardrail su risposte malformate)
- `tests/test_headless.py` (modificato — 3 nuovi test: nome multi-word a 2 token, multi-word a 3 token, risposta malformata)

### Root cause del crash
`DesktopLauncher.kt:217` stampa `println("improving ${improvement.name} ${tile.turnsToImprovement}")`. Quando `improvement.name` contiene spazi (es. "Oil well"), la risposta è `improving Oil well 5` e il vecchio parsing `parts[2]` prendeva "well" invece dei turni. Fix puramente lato Python (no rebuild JAR): l'ultimo token è sempre il numero, il nome è tutto quello in mezzo.

### Test
- [x] 132/132 verdi: `.venv\Scripts\python -m pytest tests/ -q` (129 + 3 nuovi)

### Note / impatti
- Il training crashava al primo improve reale di un'unità su tile-risorsa con miglioramento multi-word (probabilmente "Oil well" su tile Oil). Ora il parser lo gestisce.
- La skill `/team` sarà invocabile dalla prossima sessione (Claude Code carica le skill all'avvio).

### TODO prossima sessione
1. **Rilanciare il training** (nessun rebuild JAR — solo Python). Stesse metriche di Sessione 40 da monitorare:
   - `improvements_built_mean > 0` fin dalle prime iter
   - `connected_resources_mean` in crescita
   - `units_stuck_mean` in calo da 275
   - `ep_rew_mean` finalmente in salita
2. Se stabile per ≥100k step → procedere col **File 23 (Worker completo, Opzione B)**.
3. Provare la skill `/team plan` per scrivere il File 24 quando il training sarà stabile.

---

## [2026-05-30] — Sessione 40

### Obiettivo sessione
Trovare e fixare il root cause del "hang" del comando `improve`. Nel training #20 (500k step, ~3h30) `improvements_built_mean=0` per **tutto** il training, `units_stuck_mean` esploso 23 → 275, `connected_resources_mean` 0.75 → 0.

### Root cause (trovato da sub-agent `unciv-engine`)
**Non era un hang nel motore Kotlin**. Il server JVM eseguiva `improve` correttamente, scriveva il save, e stampava `improving <name> <turns>` su stdout. Il bug era lato Python: `src/utils/headless.py:66` definiva `_RESPONSE_PREFIXES = ("ok ", "error", "moved ", "illegal", "legal", "founded ")` — **mancava `"improving "`**. `_read_protocol_response` quindi scartava la risposta valida come "riga di log", continuava a leggere, finiva in timeout 5s, ritornava `"error timeout"` e uccideva la JVM.

Effetto a catena:
- ogni Improve marcata fallita → reward 0 → `improvements_built_mean=0`
- JVM killata → riavviata su save fresco → progresso C2/C3 perso → `connected_resources_mean → 0`
- Worker dopo "improve fallita" restava a lavorare nel save scritto (la Kotlin l'aveva applicata!) ma Python lo contava come no-op → `units_stuck_mean` cresceva linearmente

### File modificati
- `src/utils/headless.py` (modificato — aggiunto `"improving "` a `_RESPONSE_PREFIXES`)
- `tests/test_headless.py` (modificato — 3 nuovi test: `test_build_improvement_success`, `test_build_improvement_illegal`, `test_build_improvement_skips_log_noise`)

### Test
- [x] 129/129 verdi: `.venv\Scripts\python -m pytest tests/ -q` (126 + 3 nuovi)

### Metodo usato
- Sub-agent `unciv-engine`: analisi del comando `improve` in DesktopLauncher.kt:193-226, mappatura di tutte le chiamate interne (tutte sincrone, niente animazioni/popup/I/O bloccante), confronto con `_RESPONSE_PREFIXES`. Ha isolato il bug in ~5 minuti con confidenza ~95%.
- Sub-agent `rl-trainer`: piano repro indipendente (cattura save su timeout in `Temp/improve_repro/`). Confermato il mismatch tra prefisso emesso lato Kotlin e prefissi accettati lato Python.
- Approccio in parallelo ha confermato il root cause da due angolazioni indipendenti senza falsi positivi.

### Note / impatti attesi nel prossimo training
- `improvements_built_mean` dovrebbe salire > 0 fin dalle prime iterazioni (il masking di Sessione 39 garantisce che Improve venga emessa solo su tile-risorsa non connessa).
- `connected_resources_mean` dovrebbe crescere stabilmente.
- `units_stuck_mean` dovrebbe scendere (Worker non più "fantasma" che lavora senza che Python lo sappia).
- `fps` invariato o leggermente migliore (un Improve riuscito costa <1s vs i 5s del timeout).
- Reward dovrebbe iniziare a salire grazie al bonus `resource_connected: 3.0`.

### TODO prossima sessione
1. **Rilanciare il training** (nessun rebuild JAR necessario — modifiche solo Python). Confronto atteso con run #20:
   - `improvements_built_mean`: 0 → > 0 (atteso almeno qualche unità per episodio)
   - `connected_resources_mean`: 0 → trend crescente
   - `units_stuck_mean`: 275 → in calo
   - `ep_rew_mean`: 170 → trend crescente (presumibilmente)
2. Se stabile per ≥100k step e improvements_built > 0 → procedere col **File 23 (Worker completo, Opzione B)**: comando Kotlin `improve <nome>`, action space dinamica `BUILD_<improvement>` da ruleset.
3. Se ancora qualcosa va storto, riprendere la cattura repro proposta da `rl-trainer` (salvare save in `Temp/improve_repro/` sui fallimenti residui).

---

## [2026-05-26] — Sessione 39

### Obiettivo sessione
Sbloccare il training, in stallo da ~1 giorno (~0 fps): ogni `improve` falliva silenziosamente per timeout 60s, gli stalli si accumulavano e collassavano il throughput.

### Evidenza dai log utente
- `action_Improve` cresce da 0.0035 (iter 3) a 0.0095 (iter 8) — l'agente ha imparato a usarla.
- `improvements_built_mean = 0` in TUTTE le iter → ogni improve fallisce (no-op da resilienza Sessione 37).
- iter 10 → 11: `time_elapsed` +66338s per 4096 step (~16s/step). iter 11 → 12: +69791s. Praticamente bloccato.
- `units_stuck_mean: 30-40` → anche `legal_moves` probabilmente in timeout su qualche unità.

### File modificati
- `src/utils/headless.py` (modificato — timeout differenziato: `action_timeout` per comandi-unità, `timeout` per startup/advance; `_read_protocol_response(timeout=…)` accetta override; `_send_command` passa `self.action_timeout`)
- `config/default_config.yaml` (modificato — `headless_action_timeout: 5`, mentre `headless_timeout: 60` resta per READY e advance)
- `src/envs/unciv_env.py` (modificato — legge `headless_action_timeout`, lo passa a `UncivHeadless`; masking Improve attivo solo se la risorsa NON è già connessa)
- `src/parsers/state_parser.py` (modificato — esporta `GameState.resource_connected_tiles: set` per il masking RL-side)
- `tests/test_env.py` (modificato — nuovo test `test_improve_mask_off_when_resource_already_connected`)

### Fatto
Tentato di delegare a `unciv-engine` + `rl-trainer` (i due agenti creati nella Sessione 38) ma non sono ancora caricati nella sessione attiva (vengono registrati all'avvio di una nuova sessione Claude Code). Ho fatto io il lavoro inline applicando esattamente i fix che avrei delegato.

- **Engine fix — timeout differenziato**: prima qualunque comando hang costava 60s. Ora i comandi-unità (move/legalmoves/foundcity/improve) hanno timeout **5s** (default `headless_action_timeout` da config). advance resta a 60s (può essere genuinamente lento su save grandi); READY resta a 60s (startup JVM). Atteso: **6–12× riduzione del costo per hang**.
- **RL mitigation — masking Improve più stretto**: prima Improve era valido su qualunque tile-risorsa Strategic/Luxury. Ora è valido solo su una risorsa **non ancora connessa** (la tile non ha già il miglioramento connettente). Riduce drasticamente i tentativi inutili: una volta connessa, il Worker non riprova; se è già connessa quando ci arriva sopra (es. AI o stato pregresso), non spreca azioni.
- Esposta `GameState.resource_connected_tiles` (set di posizioni connesse) per il masking. Il parser lo calcola insieme a `connected_strategic/luxury` (logica condivisa).

### Test
- [x] 126/126 test verdi: `.venv\Scripts\python -m pytest tests/ -q` (125 + 1 nuovo)
- Test esistenti su timeout (`test_advance_turn_timeout`) restano validi: usano `timeout=1s` sull'instanza, advance legge `self.timeout` (60s di default ma 1s nel test) → comportamento invariato.

### Note / rischi
- Il root cause Kotlin del hang improve non è ancora isolato; questi fix lo **contengono** (5s no-op invece di 60s) e ne **riducono la frequenza** (mask più stretto). Quando arriveremo al File 23 (Worker completo, Opzione B), rivedremo `improve` con più strumenti.
- Se in training reale ci sono comandi advance che superano 30-60s su save molto grandi, valutare di alzare `headless_timeout`.

### TODO prossima sessione
1. Rilanciare il training (nessun rebuild JAR necessario — modifiche solo Python). Monitorare:
   - `fps` ora dovrebbe essere ≥ a quanto era prima dello stallo (idealmente più alto perché le mosse falliranno più velocemente).
   - `improvements_built_mean > 0` quando un improve riesce.
   - `units_stuck_mean` dovrebbe scendere (i timeout su legal_moves costano meno).
2. Se stabile per ≥50k step → procedere col File 23 (Opzione B).
3. Gli agenti project-scoped saranno disponibili dalla prossima sessione (`unciv-engine`, `rl-trainer`, `docs-keeper`, `tests-engineer`).

---

## [2026-05-26] — Sessione 38

### Obiettivo sessione
Creare un team di sub-agenti project-scoped per ripartire il lavoro sul progetto.

### File modificati
- `.claude/agents/unciv-engine.md` (creato — fork Kotlin + headless + JAR + parsing campi save + ruleset)
- `.claude/agents/rl-trainer.md` (creato — env + reward + masking + costruzione obs + callbacks + training)
- `.claude/agents/docs-keeper.md` (creato — WORK_LOG + CLAUDE.md + spec)
- `.claude/agents/tests-engineer.md` (creato — pytest, mock headless, shape asserts, TDD, diagnosi)

### Fatto
- Definiti 4 sub-agenti con scope chiari e regole di handoff. Confini:
  - `state_parser.py`: engine possiede il parsing dei campi del save, rl-trainer possiede `to_observation_vector`.
  - `headless.py`: i wrapper Python li scrive engine quando aggiunge un comando server; rl-trainer li chiama.
  - Test: tutti gli agenti coordinano con tests-engineer per i test del proprio dominio.
- Proposta su miglioramenti del team: la 4-agent setup è adatta alla scala attuale; un eventuale `experiments-runner` ha senso solo da Fase 3+ in poi (training multipli per tuning).

### Test
- N/A — sessione di configurazione (non tocca codice di produzione).

### TODO prossima sessione
1. Continuare la validazione runtime di C1+C2+C3 (training riavviato col fix di Sessione 37) — controllare metriche e fps.
2. Se stabile → implementare File 23 (Worker completo, Opzione B).

---

## [2026-05-24] — Sessione 37

### Obiettivo sessione
Fix crash training su azione Improve: `TimeoutError: JVM server timeout/EOF dopo 60s`.

### Problema
Durante il training di validazione, l'azione `Improve` su un caso specifico di tile/risorsa manda il server JVM in timeout/EOF (blocco o morte) → `_read_protocol_response` solleva e il training crasha. Lo smoke C3 funzionava solo sul caso craftato (Iron/Hills); su un Worker reale (Wheat→Farm) funziona, quindi il crash è su un caso non riprodotto facilmente.

### File modificati
- `src/utils/headless.py` (modificato — `_send_command` cattura `TimeoutError` e restituisce `"error timeout"`: l'azione-unità diventa no-op invece di crashare; la JVM, già terminata, viene riavviata al comando successivo da `_ensure_running`)
- `src/envs/unciv_env.py` (modificato — `Improve` mascherata solo per Worker **su un tile-risorsa** Strategic/Luxury → meno chiamate improve, meno probabilità del caso che crasha)
- `tests/test_env.py` (modificato — test masking improve su/fuori risorsa)

### Fatto
- **Resilienza**: un timeout/morte JVM su move/found/improve/legalmoves ora è un no-op (no crash training); `advance` invariato (la JVM morta viene comunque riavviata al prossimo `_ensure_running`).
- **Masking più stretto**: l'agente può fare `Improve` solo quando il Worker è su un tile-risorsa (coerente con C3 = connettere strategiche/luxury; i miglioramenti generici sono scope File 23/Opzione B).
- Nessun rebuild JAR: modifiche solo Python (comando Kotlin `improve` invariato).

### Test
- [x] 125/125 test verdi: `.venv\Scripts\python -m pytest tests/ -q`

### Note / rischi
- Il caso esatto che blocca `improve` nel motore non è stato isolato (difficile da riprodurre); è contenuto (no-op) ma se un tile-risorsa lo triggera deterministicamente costa ~60s di stallo per occorrenza. Da rivedere quando si implementa il File 23 (gestione miglioramenti più robusta).

### TODO prossima sessione
1. Ripetere il **training di validazione** C1+C2+C3 (ora senza crash su Improve); monitorare `fps` (eventuali stalli da timeout) e le metriche C1/C2/C3.
2. Se stabile → implementare File 23 (Opzione B). Valutare timeout headless più basso se gli stalli sono frequenti.

---

## [2026-05-24] — Sessione 36

### Obiettivo sessione
Pianificare il "Worker completo" (miglioramenti generali oltre la connessione risorse).

### File modificati
- `md_file_x_claude_code/23_worker_full_improvements.md` (creato — spec)

### Fatto
- Scritta la spec File 23. Risposta alla domanda dell'utente: attualmente il Worker costruisce **solo** il miglioramento che connette la risorsa sul suo tile (C3), non miglioramenti di resa generici, rimozione feature o strade.
- **Scelta utente: Opzione B** — set di azioni esplicite `BUILD_<improvement>` (un'azione per tipo, masking dinamico via nuovo comando `legalimprovements`), action space `23 → 22 + N`. Opzione A (auto-improve delegato al motore) scartata.
- File 23 aggiornato come guida d'implementazione dell'Opzione B (ruleset_reader `load_buildable_improvements`, Kotlin `improve <name>` + `legalimprovements`, headless, env, test, contratto). Strade/rete commerciale e improvement da Grande Personaggio lasciati fuori scope.
- **Prerequisito messo nero su bianco: training di validazione di C1+C2+C3 PRIMA di implementare il File 23.**

### Test
- N/A — sessione di pianificazione.

### TODO prossima sessione
1. **(Prioritario) Training di validazione C1+C2+C3** (obs 61, action 23): no crash, `cities_founded_mean>0`, `territory_resources_mean` cresce, `improvements_built_mean>0`, `connected_resources_mean>0`, fps ok.
2. Solo dopo: implementare File 23 (Opzione B — azioni esplicite Worker).

---

## [2026-05-24] — Sessione 35

### Obiettivo sessione
Implementare la Fase C3 (File 22): Worker + miglioramenti → risorse connesse + reward.

### File modificati
- `unciv/Unciv/desktop/src/com/unciv/app/desktop/DesktopLauncher.kt` (comando `improve`; fork gitignored → solo locale)
- `unciv/Unciv.jar` (ricompilato — NON in git)
- `src/utils/ruleset_reader.py` (modificato — `load_resource_improvements`)
- `src/utils/headless.py` (modificato — `build_improvement`)
- `src/parsers/state_parser.py` (modificato — `resource_improvements` nel parser; `GameState.connected_strategic/luxury`; conteggio risorse connesse nel territorio)
- `src/envs/unciv_env.py` (modificato — azione `Improve` (action 22→23), masking Worker, `_apply_improve`, carica resource_improvements, contatore improvements_built, info dict)
- `src/utils/reward.py` (modificato — peso `resource_connected`, bonus su delta risorse connesse)
- `config/default_config.yaml` (modificato — `reward.resource_connected: 3.0`)
- `src/utils/callbacks.py` (modificato — 23 azioni; `connected_resources_mean`, `improvements_built_mean`)
- `CLAUDE.md` (modificato — contratto azioni 22→23)
- `tests/test_ruleset_reader.py`, `tests/test_parser.py`, `tests/test_env.py`, `tests/test_reward.py`, `tests/test_callbacks.py`

### Fatto
- **Kotlin `improve <path> <id>`**: costruisce il miglioramento che connette la risorsa sul tile del Worker (`ruleset.tileResources[tile.resource].improvement`) via `startWorkingOnImprovement`.
- **env**: azione `Improve` (mascherata solo per Worker in unit step); `_apply_improve` via headless; contatore `improvements_built`.
- **parser**: una risorsa è "connessa" se nel territorio di una città **e** il tile ha il miglioramento giusto costruito; `connected_strategic/luxury` in `GameState`.
- **reward**: bonus `resource_connected` (3.0) sul delta di risorse connesse.

### Findings importanti (validati con smoke sul JAR)
- ✅ **Headless PROCESSA i miglioramenti del Worker del player**: smoke → `improving Mine 5`, dopo gli advance il tile ha `improvement: Mine` (rischio risolto, a differenza della scienza che andava accumulata a mano).
- ⚠️ **`detailedCivResources` è `@Transient`** (Civilization.kt:103) → **non serializzato nel save** → leggerlo dà sempre vuoto (per questo `strategic/luxury_res_count` del File 19 erano sempre 0, NON per mancanza di connessione). Workaround: uso un **proxy serializzabile** (risorsa in territorio + miglioramento connettente costruito).

### Test / validazione
- [x] 124/124 test verdi: `.venv\Scripts\python -m pytest tests/ -q`
- [x] Smoke end-to-end sul JAR: Worker su Iron(+Hills) in capitale → `improve` → Mine costruito → parser reale `connected_strategic == 1`.

### Note / rischi
- Action space 23 → checkpoint precedenti incompatibili (ripartire da zero).
- Le metriche `strategic_res_count_mean`/`luxury_res_count_mean` (File 19, da `detailedCivResources`) restano sempre 0 (transient non serializzato): usare invece `connected_resources_mean` / `territory_resources_mean`.
- Il Worker deve essere SUL tile-risorsa per costruire il miglioramento: l'agente impara muovi-worker (Fase B) → improve, guidato dall'obs risorse (C2).

### TODO prossima sessione
1. Riavviare training (obs 61, action 23) e verificare: `improvements_built_mean > 0`, `connected_resources_mean > 0`, niente crash.
2. Eventuale tuning reward (bilanciare found_city / resource_placement / resource_connected) e tech-gating risorse.
3. Eliminare gli script scratch in `Temp/`. Valutare di rimuovere il parsing morto di `detailedCivResources` (File 19).

---

## [2026-05-24] — Sessione 34

### Obiettivo sessione
Implementare la Fase C2 (File 22): risorse nell'obs + reward di posizionamento.

### File modificati
- `src/utils/ruleset_reader.py` (modificato — `load_resource_types(jar)` da `TileResources.json`)
- `src/parsers/state_parser.py` (modificato — `resource_types` nel parser; `GameState.resource_tiles`; `CityState.territory_strategic/luxury`; obs +4 feature (57→61); helper `_hex_distance`)
- `src/envs/unciv_env.py` (modificato — carica `resource_types` dal jar, `observation_space` (61,))
- `src/utils/reward.py` (modificato — peso `resource_placement`, bonus su delta tile-risorsa in territorio)
- `config/default_config.yaml` (modificato — `reward.resource_placement: 2.0`)
- `src/utils/callbacks.py` (modificato — `territory_resources_mean`)
- `CLAUDE.md` (modificato — contratto obs (57,)→(61,))
- `tests/test_ruleset_reader.py`, `tests/test_parser.py`, `tests/test_env.py`, `tests/test_reward.py` (test nuovi/adattati)

### Fatto
- **ruleset_reader**: `load_resource_types` mappa nome→tipo (Strategic/Luxury/Bonus) dal ruleset (il save NON contiene `resourceType` per tile).
- **parser**: costruisce `resource_tiles {(x,y): tipo}` (solo Strategic/Luxury) dai tile; conta le risorse nel territorio di ogni città (match `city.tiles` ↔ posizioni risorsa); obs +4 feature in coda: risorse Strategic/Luxury nel territorio della città selezionata + entro raggio 3 dall'unità selezionata.
- **reward**: bonus `resource_placement` quando cresce il totale di tile-risorsa catturate nei territori (premia fondare su/vicino a risorse).
- **Decisioni**: niente tech-gating in questa iterazione (conto tutte le Strategic/Luxury — segnale più chiaro); feature aggiunte in coda così gli indici obs esistenti non cambiano.

### Test
- [x] 119/119 test verdi: `.venv\Scripts\python -m pytest tests/ -q` (115 + 4 nuovi C2)
- Nessun rebuild JAR: C2 è solo Python (legge `TileResources.json` già nel jar).

### Note / rischi
- Obs (61,) → checkpoint precedenti incompatibili (ripartire da zero).
- Tech-gating delle risorse (visibilità per `revealedBy`) non implementato: l'agente "vede" tutte le risorse. Raffinamento futuro.
- `detailedCivResources` resta vuoto senza Worker/miglioramenti → `strategic/luxury_res_count` (risorse *connesse*) restano 0 fino a C3; il nuovo `territory_resources` invece misura le risorse nel territorio (a prescindere dalla connessione).

### TODO prossima sessione
1. Riavviare training (obs 61) e verificare: `territory_resources_mean` cresce, le città tendono a includere risorse, niente crash (fix headless Sessione 33).
2. **Fase C3**: Worker + miglioramenti → risorse connesse reali (`detailedCivResources`) → reward sulle risorse connesse. Richiede comando Kotlin `improve` + rebuild JAR; validare prima che i miglioramenti Worker siano processati in headless.
3. Eliminare gli script scratch in `Temp/`.

---

## [2026-05-24] — Sessione 33

### Obiettivo sessione
Fix crash training: log asincroni del JVM su stdout rompono il protocollo headless.

### Problema
Durante il training: `RuntimeError: Risposta JVM inattesa: '...[SoundPlayer$Preloader] Preload UncivSound(fileName=promote)'`. Un thread daemon del gioco (SoundPlayer) scriveva un log su **stdout** proprio mentre Python leggeva la risposta a `advance` → la riga di log veniva scambiata per risposta del protocollo. Race non deterministica, più frequente ora che ci sono combattimenti (suono `promote`).

### File modificati
- `src/utils/headless.py` (modificato — `_read_protocol_response()` salta le righe non-protocollo; `advance_turn` e `_send_command` lo usano; helper `_terminate_process`)
- `unciv/Unciv/desktop/src/com/unciv/app/desktop/DesktopLauncher.kt` (modificato — nel branch `--server`, `Log.backend` reindirizzato su **stderr**; fork gitignored → solo locale)
- `unciv/Unciv.jar` (ricompilato — NON in git)
- `tests/test_headless.py` (modificato — 2 test: skip rumore log in advance e move)

### Fatto
- **Python (rete di sicurezza)**: il lettore di risposta ora ignora qualsiasi riga che non inizi con un prefisso valido (`ok `/`error`/`moved `/`illegal`/`legal`/`founded `), saltando i log del JVM intercalati.
- **Kotlin (fix alla sorgente)**: `Log.backend` impostato su un backend che scrive su `System.err`, così lo stdout resta pulito per il protocollo. (`SoundPlayer` e gli altri `Log.debug` ora vanno su stderr.)

### Test
- [x] 115/115 test verdi (113 + 2 nuovi skip-noise)
- [x] Smoke JAR: dopo `READY` lo stdout contiene solo `ok 89`/`ok 90` (nessun log); i log su stderr.

### TODO prossima sessione
1. Riavviare training col nuovo JAR e verificare che non si ripresenti il crash (girare oltre i ~90k step dove prima si rompeva).
2. Poi Fase C2 (risorse nell'obs) e C3 (Worker/miglioramenti).

---

## [2026-05-24] — Sessione 32

### Obiettivo sessione
Implementare la Fase C1 (File 22): espansione multi-città (FoundCity + rotation per-città).

### File modificati
- `unciv/Unciv/desktop/src/com/unciv/app/desktop/DesktopLauncher.kt` (comando `foundcity`; fork gitignored → solo locale)
- `unciv/Unciv.jar` (ricompilato — NON in git)
- `src/utils/headless.py` (`found_city`)
- `src/parsers/state_parser.py` (param `selected_city`; Città1 obs = città selezionata)
- `src/envs/unciv_env.py` (rotation per-città, azione FoundCity, action space 21→22, masking Settler, `_apply_found_city`, contatore cities_founded)
- `src/utils/reward.py` (pop/edifici sommati su tutte le città + bonus `found_city`)
- `config/default_config.yaml` (`reward.found_city: 5.0`)
- `src/utils/callbacks.py` (22 azioni + `cities_founded_mean`)
- `CLAUDE.md` (contratto azioni 21→22)
- `tests/test_headless.py`, `tests/test_env.py`, `tests/test_parser.py`, `tests/test_reward.py`, `tests/test_callbacks.py`

### Fatto
- **Kotlin**: comando `foundcity <path> <id>` → `getUnitById` + `hasUnique(FoundCity)` + `canBeSettled` + `civ.addCity` + `unit.destroy`. JAR ricompilato (JDK 21).
- **headless.py**: `found_city` → dict success/x/y/reason.
- **env**: per-entity rotation estesa a **città** (ogni città sceglie la costruzione) poi unità; obs Città1 = città selezionata (shape (57,) invariata); `Discrete(21)→Discrete(22)` (+FoundCity); FoundCity mascherata solo per Settler; `_apply_action(city_index)`.
- **reward**: popolazione ed edifici sommati su **tutte** le città; bonus `found_city` quando il numero di città cresce.
- **Scelte utente**: scope solo C1; rotation per-città; training fermato per smoke pulito.

### Test
- [x] 113/113 test verdi: `.venv\Scripts\python -m pytest tests/ -q`
- [x] Smoke JAR (training fermato): `error not_settler` (Worker), `illegal cannot_settle` (Settler troppo vicino), **`founded -1 -9` → India 2 città ['Delhi','Mumbai']** (success path validato).

### Problemi incontrati / diagnosi
- Lungo falso allarme sul success-path di `foundcity`: sembrava non produrre output. **Root cause: il mio harness di smoke** — `Set-Content` prependeva un **BOM** alla prima riga del file comandi, così quando `foundcity` era il primo comando diventava `?foundcity…` e `startsWith("foundcity ")` falliva. Con un comando "esca" prima, `foundcity` funziona perfettamente (founded + 2 città). Il codice non aveva bug.
- Cache Gradle ambigua durante i rebuild → usato `--rerun-tasks` per ricompilazioni pulite.
- `catch(Exception)` → `catch(Throwable)` nel branch foundcity (più robusto: un eventuale Error a runtime diventa `error …` invece di rompere il loop comandi silenziosamente).

### Note / rischi
- Action space 22 → checkpoint precedenti incompatibili (ripartire da zero).
- Una città fondata aggiunge il Palace ai builtBuildings → piccolo doppio conteggio con `building_complete` oltre al bonus `found_city` (trascurabile).
- C1 non include ancora le risorse nell'obs né i Worker/miglioramenti (Fase C2/C3).

### TODO prossima sessione
1. **Validare a runtime** (riavviare training col nuovo JAR): `cities_mean > 1`, `cities_founded_mean > 0`, `moved_settler_mean > 0`, `fps` accettabile.
2. Se ok → **Fase C2** (risorse nell'obs + reward di posizionamento), poi **C3** (Worker/miglioramenti → risorse connesse).
3. Eliminare gli script scratch in `Temp/`.

---

## [2026-05-24] — Sessione 31

### Obiettivo sessione
Implementare la Fase B (File 21): rework movimento delegato al motore Unciv.

### File modificati
- `unciv/Unciv/desktop/src/com/unciv/app/desktop/DesktopLauncher.kt` (modificato — comandi `move`/`legalmoves` nel server `--server`; il fork `unciv/Unciv/` è gitignored → modifica solo locale)
- `unciv/Unciv.jar` (ricompilato — NON in git)
- `src/utils/headless.py` (modificato — `_send_command`, `move_unit`, `legal_moves`)
- `src/parsers/state_parser.py` (modificato — `UnitState.id`, `GameState.map_radius`, normalizzazione coordinate hex radius-based)
- `src/envs/unciv_env.py` (modificato — rotation su tutte le unità con MP>0, 6 direzioni hex, action space 19→21, masking unit-step via `legal_moves`, `_apply_movement` via headless, metriche movimento)
- `src/utils/callbacks.py` (modificato — `_ACTION_NAMES` a 21, metriche movimento)
- `CLAUDE.md` (modificato — contratto azioni 19→21)
- `tests/test_headless.py`, `tests/test_env.py`, `tests/test_parser.py`, `tests/test_callbacks.py` (modificati — nuovi test + adattati a 21 azioni / coord hex / masking via legal_moves)

### Fatto
- **Kotlin**: `move <path> <id> <clock>` → `getUnitById` + vicino via `getNeighborTileClockPosition` + `canMoveTo`/`moveToTile` (costo terreno reale), salva; `legalmoves <path> <id>` → direzioni hex legali. Ricompilato `Unciv.jar` (`gradlew desktop:dist`, JDK 21, BUILD SUCCESSFUL).
- **headless.py**: `move_unit` → dict {success,x,y,movement_left}; `legal_moves` → lista clock.
- **parser**: unità con `id`; coordinate normalizzate via raggio mappa (gestisce hex negativo, prima `x/width` sbagliato); `map_radius` in `GameState`.
- **env**: per-entity rotation estesa a **tutte** le unità (militari + civili) con MP>0; azioni movimento = 6 direzioni hex (clock 2/4/6/8/10/12); `Discrete(19)→Discrete(21)`; masking unit-step **preciso** (interroga `legal_moves`); movimento via `headless.move_unit`. Metriche movimento per-episodio (attempted/succeeded/illegal, move_cost, moved_<tipo>, units_stuck, legal_moves_available, new_tiles_per_move).
- **Scelte utente**: masking preciso (`legalmoves`), build JAR eseguita in sessione.

### Test
- [x] 106/106 test verdi: `.venv\Scripts\python -m pytest tests/ -v`
- [x] Smoke test JAR: `moved 110 2 6 1.0` (Worker civile mosso, costo 2→1.0), `legal 4 8`/`legal 2 4 8`, `illegal cannot_move` (rifiuto corretto)

### Problemi incontrati
- venv/Java non nel PATH della sessione tool → usato path esplicito JDK 21 (`C:\Program Files\Eclipse Adoptium\jdk-21.0.11.10-hotspot`).
- Primo smoke test con id obsoleti (`no_unit`): il training in esecuzione riscrive `current_game_*.json` di continuo → usato uno snapshot copiato in `Temp/` con id validi.

### Note / rischi
- Il masking preciso aggiunge ~1 round-trip `legalmoves` per unit-step + 1 `move` → con molte unità il training potrebbe rallentare. Da monitorare (`fps`); eventualmente passare a masking semplice.
- Movimento: una azione = una casella (un vicino), il movimento residuo non viene riusato nello stesso turno (semplificazione).
- Action space 21 → checkpoint precedenti incompatibili (ripartire da zero, comunque necessario dopo Fase A).

### TODO prossima sessione
1. **Validare a runtime** (riavviare training con nuovo JAR): `move_cost_mean ≠ 1` (costo terreno), `moved_settler/scout/worker_mean > 0`, `moves_illegal_mean` basso, `fps` accettabile.
2. Se ok → **Fase C (File 22)**: espansione multi-città + risorse.
3. Eliminare gli script scratch in `Temp/`.

---

## [2026-05-24] — Sessione 30

### Obiettivo sessione
Implementare la Fase A (File 20): fix costruzione + decodifica `statsHistory`.

### File modificati
- `src/envs/unciv_env.py` (modificato — `_apply_action` scrive `constructionQueue`; `culture_per_turn` come delta di `stored_culture`)
- `src/parsers/state_parser.py` (modificato — `_STATS_LETTERS`, `production_per_turn`←P, `food_per_turn`←C su città principale, `gold_per_turn`=0, `culture_per_turn`=0 nel parser, campo `stored_culture`; rimosso `_parse_culture_per_turn`)
- `tests/test_env.py` (modificato — test `_apply_action` scrive `constructionQueue`)
- `tests/test_parser.py` (modificato — 5 test decodifica statsHistory + `stored_culture`)

### Fatto
- **A1**: `_apply_action` ora scrive `constructionQueue=[name]` + `inProgressConstructions` (setdefault) + `currentConstructionIsUserSet=True`, e rimuove il vecchio `currentConstruction`. Sblocca la costruzione (prima l'agente non costruiva nulla).
- **A2**: corretta la decodifica di `statsHistory` (è `CivRankingHistory`): `production_per_turn`←`P`, `food_per_turn`←`C` (Growth) assegnati alla città principale; `gold_per_turn`=0 (era `N`=popolazione); `culture_per_turn` reale via delta di `policies.storedCulture` calcolato in `unciv_env` (opzione b scelta dall'utente). Aggiunta costante documentativa `_STATS_LETTERS`.

### Test
- [x] 100/100 test verdi: `.venv\Scripts\python -m pytest tests/ -v` (94 + 6 nuovi)

### Validazione a runtime (confermata dai log del training dell'utente)
- `built_monument/granary/barracks/colosseum/walls_mean` ≈ 1 (prima 0) ✅
- `trained_warrior/scout/settler/spearman_mean` 3–10 (prima 0, solo worker=1) ✅
- `culture_per_turn_mean` ≈ 3, `ep_total_culture_mean` ≈ 420 (prima ~0.1 / 22, era cibo) ✅
- `population` 12, `city_territory` 16, `science_per_turn` 15 (in crescita)

### Osservazioni (non bug — feature delle fasi successive)
- `gold_mean` cala: l'agente paga il mantenimento delle molte unità prodotte (prima non costruiva nulla → oro accumulato a ~1660).
- Settler costruiti (2–4) ma inutilizzabili finché manca FoundCity (Fase C); `cities_mean` resta 1.
- `strategic/luxury_res_count` restano 0 (servono Worker + miglioramenti → Fase C).
- `built_courthouse/stable/temple` = 0 (tech/prereq non soddisfatti o non scelti).

### TODO prossima sessione
1. **Fase B (File 21)** — rework movimento delegato al motore (comando headless `move`, 6 direzioni hex, tutte le unità, costo terreno, action space 19→21)
2. Poi Fase C (File 22 — espansione + risorse)
3. Eliminare gli script scratch in `Temp/` quando non servono più

---

## [2026-05-24] — Sessione 29

### Obiettivo sessione
Ricreare il venv, far ripartire il training, investigare l'anomalia `built_*=0`, pianificare i prossimi step (Fasi A/B/C).

### File modificati
- `config/default_config.yaml` (modificato — `java_path` da percorso JDK fisso a `"java"` su PATH)
- `md_file_x_claude_code/20_fix_construction_and_stats.md` (creato — spec Fase A)
- `md_file_x_claude_code/21_movement_rework.md` (creato — spec Fase B)
- `md_file_x_claude_code/22_expansion_resources.md` (creato — spec Fase C)
- `Temp/` (creato — script scratch di ispezione save, NON in git)

### Fatto
- **venv ricreato**: il `.venv` era costruito su un'altra macchina (`pyvenv.cfg` → utente "Luca Vecchietti", Python 3.13 assente qui). Ricreato con **Python 3.14.5**, reinstallato `requirements.txt` (torch 2.12.0, sb3-contrib 2.8.0, gymnasium 1.2.3, numpy 2.4.6, tensorboard 2.20.0). Ora `sb3_contrib` presente.
- **Java mancante** (rimosso con la pulizia macchina): `config.java_path` portato a `"java"`; l'utente reinstalla JDK 21 via winget.
- **Anomalia `built_*=0` / `trained_*=0` diagnosticata** (NON ancora fixata, solo pianificata):
  - Costruzione: `_apply_action` scrive `cityConstructions.currentConstruction` (campo INESISTENTE); Unciv usa `constructionQueue[0]` (`CityConstructions.kt:74`). La scelta dell'agente non arriva mai al motore → non costruisce nulla.
  - `statsHistory` decodificato con lettere sbagliate: è `CivRankingHistory` (punteggi classifica). Da `RankingType.kt`: C=Growth(cibo/turno), N=Population, P=Production, G=Gold totale, H=Happiness, W=Technologies, A=Culture(policy), S=Score. Quindi `culture_per_turn` leggeva il cibo, `gold_per_turn` la popolazione.
- **Audit completo dei campi** scrittura/lettura Python vs nomi reali Unciv: corretti gold/population/builtBuildings/constructionQueue(read)/tech/diplomacy/proximity/units; errati `_apply_action`, `culture_per_turn`, `gold_per_turn`, normalizzazione coordinate hex (`x/width`), risorse (`detailedCivResources` vuoto → usare tile-level).
- **Verifica sorgente Kotlin** per il piano movimento (6 vicini hex da `HexMath.clockPositionToHexcoordMap`; API `UnitMovement.moveToTile/canMoveTo/getDistanceToTiles`; `MapUnit.id`, `civ.units.getUnitById`, `tileMap.getIfTileExistsOrNull`, `Tile.neighbors` con world-wrap; protocollo `--server`) e per la Fase C (`Civilization.addCity` + `unit.destroy`, `Tile.canBeSettled`, `Tile.startWorkingOnImprovement`, `resource.revealedBy` → `tech.isResearched`).
- **3 file di pianificazione creati** (Fasi A/B/C) con diagnosi, modifiche file-per-file, test e validazione.

### Problemi incontrati
- venv inutilizzabile (ABI cp313 vs Python 3.14) → ricreato.
- Java assente → training non partiva (`WinError 2` su Popen JVM); risolto reinstallando JDK + `java_path: "java"`.

### Test
- [x] 94/94 test verdi (suite eseguita a inizio sessione dopo ricreazione venv)
- Investigazione e pianificazione: nessuna modifica al codice di produzione (i fix sono pianificati nei File 20-22, non ancora implementati)

### TODO prossima sessione
1. **Implementare Fase A (File 20)**: fix `_apply_action` (`constructionQueue`) + decodifica `statsHistory` corretta + test; validare `built_*_mean > 0`
2. Poi Fase B (File 21 — rework movimento) e Fase C (File 22 — espansione + risorse)
3. Eliminare gli script scratch in `Temp/` quando non servono più

---

## [2026-05-24] — Sessione 28

### Obiettivo sessione
Implementare File 19 — Extended Metrics Logging (TODO Sessione 27).

### File modificati
- `CLAUDE.md` (modificato — Stack tecnico: venv obbligatorio `.venv`; Regola sviluppo 8 "zero debiti a fine sessione"; chiusura sessione aggiornata)
- `src/parsers/state_parser.py` (modificato — nuovi campi GameState + parsing risorse/territorio/scienza)
- `src/envs/unciv_env.py` (modificato — contatori per-episodio + info dict esteso + `_accumulate_episode_metrics` + `_count_by_name`)
- `src/utils/callbacks.py` (modificato — nuove metriche TensorBoard in `_on_rollout_end`)
- `tests/test_parser.py` (modificato — 6 nuovi test)
- `tests/test_env.py` (modificato — 4 nuovi test)
- `.venv/` (ricreato — non in git)

### Fatto
- **Decisione approccio "Ibrido"** sui 3 campi in conflitto (la spec li elencava come nuovi ma esistevano già con sorgenti diverse):
  - `science_per_turn` allineato a `tech.scienceOfLast8Turns[-1]` (coerente con `_advance_tech`, e con la spec)
  - `tiles_explored` invariato dalla sorgente reale `tileList[].exploredBy` (la spec proponeva `civ.exploredTiles`, che rischia di non esistere nei save reali → regressione silenziosa evitata)
  - `culture_per_turn` estratto in helper `_parse_culture_per_turn()` mantenendo `statsHistory` chiave `C`
- **state_parser.py**: 3 nuovi campi `GameState` (`city_territory_tiles`, `strategic_resources`, `luxury_resources`); parsing `detailedCivResources` (Strategic/Luxury); `city_territory_tiles = sum(len(c.tiles))`
- **unciv_env.py**: contatori `_ep_total_gold/science/culture`, `_ep_buildings_built`, `_ep_units_built` in `__init__` e `reset()`; accumulo in nuovo `_accumulate_episode_metrics()` (gold solo incrementi, delta edifici/unità); `info` dict esteso con 11 nuove chiavi; helper module-level `_count_by_name()`
- **callbacks.py**: `logger.record()` per metriche per-turno, totali episodio, costruzioni/unità per tipo, conteggio risorse
- Nessuna modifica a obs shape `(57,)` o action space `Discrete(19)` — checkpoint compatibili

### Problemi incontrati
- **venv rotto**: il progetto è stato copiato da un'altra macchina (`pyvenv.cfg` puntava a `C:\Users\Luca Vecchietti\...Python313`, inesistente qui). Su questa macchina è disponibile solo **Python 3.14.5** (3.13 rimosso). Le dipendenze cp313 nel venv non erano importabili sotto 3.14 (mismatch ABI).
- **Fix**: ricreato `.venv` con Python 3.14.5 e reinstallato `requirements.txt`. Installati tra gli altri: torch 2.12.0, stable-baselines3 2.8.0, sb3-contrib 2.8.0, gymnasium 1.2.3, numpy 2.4.6, tensorboard 2.20.0. Ora `sb3_contrib` è presente → i 4 test prima skippati passano.

### Test
- [x] 94/94 test verdi: `.venv\Scripts\python -m pytest tests/ -v` (45.65s)
- [x] 84 test pre-esistenti (inclusi 4 prima skippati per sb3_contrib mancante) + 10 nuovi File 19

### TODO prossima sessione
1. Riavviare training e verificare che le nuove metriche compaiano in TensorBoard (`unciv/tiles_explored_mean`, `unciv/science_per_turn_mean`, `unciv/built_*_mean`, `unciv/trained_*_mean`, `unciv/strategic_res_count_mean`, ecc.)
2. Verificare su save reale che `detailedCivResources` e `city.tiles` siano popolati (popolano `strategic/luxury_resources` e `city_territory_tiles`)
3. Valutare se usare le nuove metriche per estendere la reward function (Fase 3)

---

## [2026-05-03] — Sessione 27

### Obiettivo sessione
Scrivere spec File 19 — Extended Metrics Logging.

### File modificati
- `md_file_x_claude_code/19_extended_metrics_logging.md` (creato — spec metriche estese)

### Fatto
- Spec completa: parsing nuovi campi `GameState` (tiles esplorate, territorio città, scienza/cultura per turno, risorse strategiche/luxury), contatori delta per-episodio in `UncivEnv`, logging in `callbacks.py`
- Nessuna modifica a obs shape o action space — checkpoint compatibili

### TODO prossima sessione
1. Implementare File 19: modificare `state_parser.py`, `unciv_env.py`, `callbacks.py`, test

---

## [2026-05-03] — Sessione 26

### Obiettivo sessione
Fix crash `TypeError: 'NoneType' object is not iterable` in `state_parser.py`.

### File modificati
- `src/parsers/state_parser.py` (modificato — riga 127: `tech.get('techsInProgress', {})` → `tech.get('techsInProgress') or {}`)

### Fatto
- Root cause: `_advance_tech()` scrive `techsInProgress = None` quando nessuna tech disponibile; `dict.get(key, default)` restituisce `None` (non il default) se chiave presente con valore `None`; `iter(None)` → crash
- Fix one-liner: `or {}` fallback gestisce esplicitamente il null JSON

### Test
- [x] 80/84 test verdi (4 falliscono per `sb3_contrib` non installato — pre-esistente, non correlato)

### TODO prossima sessione
1. Restart training e verificare `techs_mean` > 5
2. Monitorare se tech chain (Agriculture → Pottery → Writing...) funziona correttamente

---

## [2026-05-03] — Sessione 25

### Obiettivo sessione
Fix bug persistente: `techs_mean: 2` anche con `_ensure_tech_queued`. Root cause: Unciv headless NON accumula scienza per il civ player in `nextTurn()` (solo AI civs).

### File modificati
- `src/envs/unciv_env.py` (modificato — `_ensure_tech_queued` rimossa; `_advance_tech` aggiunta; chiamata spostata DOPO `_advance_turn`; import `_TECH_COSTS` da state_parser)
- `tests/test_env.py` (modificato — rimossi 2 test `_ensure_tech_queued`; aggiunti `test_advance_tech_accumulates_science` e `test_advance_tech_completes_tech`)
- `WORK_LOG.md` (questo aggiornamento)

### Fatto
- Diagnosticato: `techsInProgress: {"Animal Husbandry": 0}` invariato su 9 turni consecutivi → Unciv non processa ricerca per player civ in headless server mode
- `_advance_tech()` legge `scienceOfLast8Turns[-1]` (calcolato da Unciv correttamente) e accumula manualmente in `techsInProgress`
- Quando scienza accumulata >= costo tech: tech aggiunta a `techsResearched`, prossima tech selezionata con overflow scienza
- Chiamata DOPO `_advance_turn` per leggere scienza del turno appena processato

### Test
- [x] 84/84 test verdi

### TODO prossima sessione
1. Verificare che `techs_mean` salga >5 nel training
2. Monitorare se `_TECH_COSTS` approssimazione è abbastanza precisa

---

## [2026-05-03] — Sessione 24

### Obiettivo sessione
Fix bug: tech research non veniva aggiornata durante training → `techs_mean: 2` dopo 155 turni.

### File modificati
- `src/utils/ruleset_reader.py` (modificato — aggiunta `load_tech_prereqs()`)
- `src/envs/unciv_env.py` (modificato — import `load_tech_prereqs`, `self._tech_prereqs` in `__init__`, metodo `_ensure_tech_queued()`, chiamata in `_advance_game_turn()`)
- `tests/test_env.py` (modificato — 2 nuovi test per `_ensure_tech_queued`)
- `WORK_LOG.md` (questo aggiornamento)

### Fatto
- Diagnosticato: `currentTechResearch: None` nel save → Unciv non ricercava nulla, scienza sprecata
- `load_tech_prereqs(jar_path)` → `{tech_name: [prereq_names]}` per era Ancient+Classical
- `_ensure_tech_queued()` auto-seleziona prima tech disponibile (prereq soddisfatti) se coda vuota
- Chiamata in `_advance_game_turn()` prima di `_advance_turn()`

### Test
- [x] 84/84 test verdi

### TODO prossima sessione
1. Verificare che `techs_mean` salga durante training (target: >5 in 150 turni)
2. Installare `sb3_contrib` su sistema se necessario per training headless

---

## [2026-05-03] — Sessione 23

### Obiettivo sessione
Implementare File 18 — expanded action space (Discrete(19), obs (57,), 9 flag edifici); correggere bug in `reward.py` e `callbacks.py`.

### File modificati
- `src/utils/ruleset_reader.py` (modificato — fix `_TARGET_ERAS` da `{"Ancient","Classical"}` a forma multi-era; aggiunti `uniqueTo` filter per edifici e unità; aggiunti "Lighthouse" a `_BUILDING_EXCLUDE`, "Swordsman" a `_UNIT_MISC_EXCLUDE`)
- `src/parsers/state_parser.py` (modificato — `_TRACKED_BUILDINGS` da 6 a 9 flag; `_city_obs()` da 16→19 elementi; city 2 da 8→10 elementi; obs assert (52,)→(57,))
- `src/envs/unciv_env.py` (modificato — ACTION_MAP dinamico da JAR in `__init__`; obs space (57,); action space `Discrete(len(ACTION_MAP))`; `_skip_idx`/`_move_start_idx` calcolati; `_compute_reward` passa `skip_action_idx=self._skip_idx`)
- `src/utils/reward.py` (modificato — aggiunto parametro `skip_action_idx: int = 6`; fix body `if action == 6:` → `if action == skip_action_idx:`)
- `src/utils/callbacks.py` (modificato — `_ACTION_NAMES` da 11 a 19 voci; docstring aggiornata)
- `tests/test_env.py` (riscritto — shape (52,)→(57,), action count 11→19; `_setup_masking` ricostruisce ACTION_MAP deterministicamente; `_get_idx` helper; indici dinamici con `env._skip_idx`/`env._move_start_idx`; unit coord obs indices 48→53)
- `tests/test_parser.py` (modificato — shape assert (52,)→(57,))
- `tests/test_callbacks.py` (modificato — shape assert (11,)→(19,))
- `CLAUDE.md` (modificato — contratti: obs (52,)→(57,), azioni 11→19)
- `WORK_LOG.md` (questo aggiornamento)

### Fatto
- ACTION_MAP ora dinamico (caricato da JAR in `__init__`): 9 edifici + 5 unità + skip + 4 MOVE_* = 19 azioni
- Obs espanso (52,)→(57,): 3 flag edifici extra in city1, gold/t + tiles_worked in city2
- Bug fix `reward.py`: idle penalty ora usa `skip_action_idx` parametro, non hardcoded `6`
- Bug fix `callbacks.py`: `_ACTION_NAMES` aggiornato a 19 voci per Fase 2.2c
- Bug fix `ruleset_reader.py`: era names ("Ancient era" vs "Ancient"), uniqueTo filter, Lighthouse/Swordsman exclude

### Problemi risolti
- `_TARGET_ERAS` era `{"Ancient","Classical"}` ma il JAR usa `"Ancient era"` e `"Classical era"` → produceva solo 1 costruzione (Monument). Fix: supportare entrambi i formati.
- `test_ruleset_reader.py` usa mock data con "Ancient" → soluzione: `_TARGET_ERAS` ora contiene entrambe le varianti.
- Test env shapes e indici hardcoded → aggiornati con helper `_get_idx` e `env._skip_idx`/`env._move_start_idx`.

### Test
- [x] 78/82 test verdi: `python -m pytest tests/ -v`
- [x] 4 failure pre-esistenti in `test_training.py` (ModuleNotFoundError: `sb3_contrib` non installato)
- [x] 17/17 test `test_env.py` passano
- [x] 10/10 test `test_ruleset_reader.py` passano

### TODO prossima sessione
1. Installare `sb3_contrib` (o fixare test_training.py per ambiente privo di sb3_contrib)
2. Riavviare training con nuovo obs/action space — checkpoint precedenti incompatibili
3. Aggiornare `ARCHITECTURE.md` con nuovo obs layout (57,) e action space (19)

---

## [2026-05-03] — Sessione 22

### Obiettivo sessione
Implementare File 17 — dynamic action masking in `unciv_env.py`.

### File modificati
- `src/envs/unciv_env.py` (modificato — import `load_early_game_constructions`, `_prereq_map`/`_unit_names`/`_building_names` in `__init__`, `action_masks()` riscritto)
- `tests/test_env.py` (modificato — `test_action_masks_city_step` aggiornato, `_setup_masking` helper aggiunto, 8 nuovi test masking)
- `WORK_LOG.md` (questo aggiornamento)

### Fatto
- `action_masks()` ora maschera dinamicamente per city step:
  - Guard per `_current_state=None` → solo skip True
  - Per ogni azione: verifica `requiredTech` in `state.techs_researched`
  - Edifici: blocca se già costruiti (`built_buildings`)
  - Unità: solo check tech
  - `MOVE_*` sempre False in city step
  - Skip sempre True — invariante anti-deadlock garantito
- `_prereq_map` caricato una volta in `__init__` da `load_early_game_constructions(jar_path)`
- `state_parser.py`: nessuna modifica — `built_buildings` già parsato da `builtBuildings`

### Test
- [x] 82/82 test verdi: `python -m pytest tests/ -v`
- [x] 16/16 test `test_env.py` passano (8 nuovi masking test)

### TODO prossima sessione
1. Implementare File 18 — expanded action space (Discrete(~19), obs (~57,), 9 flag edifici)
2. Riavviare training dopo File 18 (checkpoint incompatibili con nuovo obs shape)

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
