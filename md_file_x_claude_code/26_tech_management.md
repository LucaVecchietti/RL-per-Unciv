# File 26 — Tech management: scelta esplicita della tecnologia da ricercare

## Obiettivo

Dare all'agente RL il **controllo esplicito** della tecnologia da ricercare (oggi scelta
dall'auto-picker alfabetico), **sbloccare l'intero tech tree** del ruleset Civ V Vanilla
(74 tech anziché ~21 di Ancient+Classical) ed **esporre l'era corrente** nell'observation
vector. Risolve anche un bug latente sulla lettura della tech corrente dal save.

## ⚠️ Prerequisito

- **File 23.1 (reward rework) implementato e validato**: il dense signal
  `tech_progress: 0.5` è la base su cui poggia questa fase, perché compensa la sparsità
  del reward `tech_researched: 3.0` alla luce dell'espansione del tech tree.
- **Runtime validato** (eval reward stabile su Run #22, 500k step): senza una baseline
  verde, l'introduzione di 74 nuove azioni rischia di mascherare regressioni di reward
  shaping già esistenti.
- Nessun File 24/25 strettamente richiesto: **File 26 è indipendente** dagli altri rami
  della Fase 2 e può essere implementato in qualsiasi ordine rispetto a `buildroad` e
  `city_population`.

---

## Stato attuale

- **L'agente NON sceglie tech**: in `src/envs/unciv_env.py:222-273` non esiste alcuna
  azione `RESEARCH_*`. La scelta è interamente delegata al motore.
- **Auto-picker alfabetico** in `src/envs/unciv_env.py:452-500` (`_advance_tech`): seleziona
  la prima tech disponibile per ordine alfabetico tra quelle caricate da
  `src/utils/ruleset_reader.py:64-75` (`load_tech_prereqs`, filtrato da `_TARGET_ERAS`).
- **Tech tree limitato**: `_TARGET_ERAS` in `ruleset_reader.py:24` include solo
  `{"Ancient", "Classical"}` → ~21 tech disponibili contro le 74 totali del ruleset
  (`unciv/Unciv/android/assets/jsons/Civ V - Vanilla/Techs.json`).
- **Plateau osservato**: Run #22 mostra `techs_mean = 18` in 155 turni, perché:
  - filtro `_TARGET_ERAS` esclude Medieval+
  - l'auto-pick alfabetico non ottimizza il path (es. preferisce `Animal Husbandry` a
    `Pottery` solo per ordine lessicografico)
- **Bug latente** in `src/parsers/state_parser.py:174`: `current_tech` viene letto come
  `next(iter(techsInProgress.keys()))`, ma `techsInProgress` è una `HashMap` Java →
  ordine **non garantito**. La fonte autoritativa è `techsToResearch[0]` (vedi
  `TechManager.kt:129-131` nel sorgente Unciv, `TechManager.currentTechnologyName()`).

---

## Design

### Scelta utente confermata: sblocco di TUTTE le 74 tech del ruleset

> **Scelta confermata dall'utente: sbloccare tutte le 74 tech del ruleset Civ V Vanilla**,
> sovrascrivendo la raccomandazione di `rl-trainer` di limitarsi ad Ancient+Classical
> (~21 tech). Razionale utente: dare massima flessibilità all'agente, anche se in 155
> turni vedrà ~25 tech effettive. Le rimanenti ~49 azioni `RESEARCH_*` avranno mask=0
> quasi sempre (impatto: spazio azioni grande ma masking efficiente lato Python evita
> degenerazione esplorazione).

### Spazio azioni

- Aggiungere **74 azioni `RESEARCH_<tech>`**, una per tech del ruleset, ordine alfabetico
  stabile (indici riproducibili tra run).
- Action space totale post-File-26 isolato: `Discrete(23) → Discrete(97)`.

### Masking

- Vincolo `canBeResearched` ricostruito lato Python (no round-trip headless per step):
  `tech ∉ techs_researched AND prereqs ⊆ techs_researched`.
- Caricare prereqs di **tutte** le ere tramite nuova funzione
  `load_all_tech_prereqs(jar_path) -> dict[str, set[str]]` in `ruleset_reader.py`.
- Costo masking: `O(74)` per research step, trascurabile.

### Sub-step "research" nella rotation

- Nuovo `_step_type = "research"`, **eseguito una sola volta per turno**.
- Ordine confermato: city steps → **research step** → unit steps → advance.
- Azioni disponibili nel research step: 74 `RESEARCH_*` + `skip`.
- Maschera: solo tech con `canBeResearched=True`. `skip` sempre disponibile.

### Default fallback (safety net)

- Se l'agente sceglie `skip` nel research step → mantenere l'**auto-pick alfabetico
  esistente** (`_advance_tech` linee 474-477 invariate).
- Garantisce backward compatibility e robustezza nei casi in cui tutte le tech utili
  hanno mask=0 o l'agente non ha ancora imparato la dinamica.

### Obs vector: `era_one_hot`

- **5 dimensioni one-hot** per era corrente: Ancient / Classical / Medieval /
  Renaissance / Industrial.
- Era derivata da `TechManager.era` (riferimento sorgente: `TechManager.kt:480-507`,
  computata dal `column!!.era` dell'ultima tech ricercata).
- Posizione: **in coda** al vettore. Shape `(61,) → (66,)`.

### Reward shaping

- **Invariato**. Decisione utente esplicita: **NO `tech_speed_bonus`**.
- `tech_researched: 3.0` (`reward.py:10`) mantenuto come reward sparso al completamento.
- `tech_progress: 0.5` di File 23.1 continua a fornire il dense signal sul progresso.
- Razionale anti-bias: la vittoria scientifica è irraggiungibile in 155 turni (richiede
  tech tree completo + Apollo + Mars colony), quindi il rischio di degenerazione su una
  policy "research-only" è nullo in Fase 2.

### Bug fix `current_tech`

- In `src/parsers/state_parser.py:174`:
  - **Prima**: `next(iter(techsInProgress.keys()))` — non deterministico, può saltare la
    tech corretta se non ha ancora ricevuto scienza
  - **Dopo**: `techsToResearch[0] if techsToResearch else None` — fonte autoritativa,
    consistente con `TechManager.currentTechnologyName()`

---

## Implementazione

### `unciv/Unciv/desktop/src/com/unciv/app/desktop/DesktopLauncher.kt`

Aggiungere blocchi `else if` (pattern di `improve`/`foundcity`):

```kotlin
// settech <path> <techName>
// → valida canBeResearched, calcola getRequiredTechsToDestination,
//   civInfo.tech.techsToResearch = ArrayList(path.map { it.name })
//   civInfo.tech.updateResearchProgress(); scrive save
// → "ok settech <techName>" | "illegal not_researchable" | "error <msg>"

// listtechs <path>
// → ritorna le tech con canBeResearched=true (escluse isResearched)
// → "techs <name1> <name2> ..." | "error <msg>"

// techinfo <path> <techName>  (opzionale, utility debug)
// → "tech <name> cost=<n> era=<eraName> prereqs=<a,b,c>"
```

**Ricompilare il JAR** dopo le modifiche.

### `src/utils/headless.py`

- `set_tech(save_path, tech_name) -> dict`: invia `settech <path> <name>`. Aggiungere
  prefisso `"ok settech "` a `_RESPONSE_PREFIXES`.
- `list_techs(save_path) -> list[str]`: invia `listtechs <path>`. Aggiungere prefisso
  `"techs "`.
- `tech_info(save_path, tech_name) -> dict` (opzionale).

### `src/utils/ruleset_reader.py`

- `load_all_tech_prereqs(jar_path) -> dict[str, set[str]]`: parsa `Techs.json` **senza**
  filtro `_TARGET_ERAS`, ritorna mappa tech → set prereqs per tutte le 74 tech.
- Mantenere `load_tech_prereqs` esistente (alias usato dall'auto-picker) ma esporre flag
  opzionale `all_eras=True`.
- `load_tech_eras(jar_path) -> dict[str, str]`: ritorna mappa tech → era (parsata da
  `column.era` in `Techs.json`).

### `src/envs/unciv_env.py`

- In `__init__`: caricare `load_all_tech_prereqs(jar_path)` e `load_tech_eras(jar_path)`.
- In `ACTION_MAP` / `_ACTION_NAMES`: aggiungere 74 azioni `RESEARCH_<tech>` (ordine
  alfabetico stabile). Aggiornare `self._research_action_map` (indice azione → tech_name).
- Aggiungere `_step_type = "research"` e gestirlo in rotation.
- `action_masks`: in research step, calcolare maschera basata su `canBeResearched` locale
  (prereqs ⊆ techs_researched AND tech ∉ techs_researched). `skip` sempre `True`.
- `step`: branch research → `_apply_research(action)` che chiama
  `headless.set_tech(save, tech_name)`. `skip` → no-op (fallback auto-pick interviene in
  `_advance_tech`).
- `_advance_tech`: **invariato** (resta come safety net).

### `src/parsers/state_parser.py`

- **Fix `current_tech`** (riga 174 e dintorni): leggere da
  `tech.get('techsToResearch', [])[0]` invece di iterare la HashMap.
- Aggiungere `GameState.current_era: str = "Ancient"` (parsato da `TechManager.era` o
  ricostruito dall'ultima tech ricercata via `load_tech_eras`).
- `to_observation_vector`: appendere 5 valori `era_one_hot` (Ancient/Classical/Medieval/
  Renaissance/Industrial) → shape `(61,) → (66,)`. Aggiornare assert finale
  `len(obs) == 66`.

### `src/utils/callbacks.py` (`UncivMetricsCallback`)

- Log `unciv/current_era_mean` (0=Ancient, 1=Classical, …, 4=Industrial — ordinale
  numerico per facilità di visualizzazione TB).
- Aggiungere `unciv/action_RESEARCH_<tech>` in `_ACTION_NAMES` per le 74 nuove azioni
  (espande il log ma è informativo).
- Aggiungere `unciv/tech_action_attempted_mean`, `_succeeded_mean`.

### `src/utils/reward.py`

- **Invariato**. Nessun nuovo peso.

### `CLAUDE.md`

Aggiornare tabella contratti:
- Dimensione obs vector: `(61,)` → `(66,)`
- Numero azioni: `Discrete(23)` → `Discrete(97)` (cumulato con File 24/25 sarà maggiore)
- Aggiungere riga "Tech research" → `settech / listtechs` in `headless.py` ↔ `unciv_env.py`

---

## Contratti che cambiano

| Contratto | Prima | Dopo (post-File-26 isolato) |
|---|---|---|
| Obs vector | `(61,)` | `(66,)` |
| Action space | `Discrete(23)` | `Discrete(97)` |
| Headless commands | improve, foundcity, … | + `settech`, `listtechs`, `techinfo` |
| `current_tech` source | `techsInProgress.keys()` iter | `techsToResearch[0]` |
| Tech tree scope | Ancient + Classical (~21) | tutte le ere (74) |

> ⚠️ Aggiornare la tabella in `CLAUDE.md` al momento dell'implementazione.

---

## Test richiesti

### `tests/test_headless.py`
- `test_settech_success`
- `test_settech_illegal_not_researchable` (tech con prereqs mancanti)
- `test_settech_unknown_tech`
- `test_listtechs_parses_response` (mock di `techs A B C` → `["A","B","C"]`)
- `test_listtechs_empty`

### `tests/test_env.py`
- `test_action_space_size_after_research` — assert `env.action_space.n == 97` (isolato)
- `test_research_step_appears_in_rotation` — verificare nuovo step_type
- `test_research_masking_prereqs_satisfied` — solo tech con prereqs soddisfatti hanno
  mask=True
- `test_research_skip_falls_back_to_auto_pick` — skip mantiene auto-picker
- `test_research_action_calls_headless` — `set_tech` invocato col tech_name corretto

### `tests/test_parser.py`
- `test_current_tech_from_techsToResearch_first` — bug fix verificato
- `test_obs_shape_with_era_one_hot` — assert `obs.shape == (66,)`
- `test_era_one_hot_ancient` / `_classical` / `_medieval` / `_renaissance` / `_industrial`

### `tests/test_ruleset_reader.py`
- `test_load_all_tech_prereqs_includes_74` — `len == 74`
- `test_load_tech_eras` — Agriculture → `"Ancient"`, Industrialization → `"Industrial"`

### Smoke JAR
- Save con player India al turno 1 → `listtechs` → contiene Agriculture, Pottery, ecc.
  (tech con prereqs vuoti).
- `settech save Mathematics` → save aggiornato con `techsToResearch=[The Wheel,
  Mathematics]` (path automatico).

---

## Criteri di accettazione

- Suite test verde (132 esistenti + ~15 nuovi).
- Smoke JAR riuscito.
- Training di validazione 50k step:
  - `techs_mean ≥ 22` (era 18 in Run #22, ora con scelta esplicita + dense reward)
  - `current_era_mean ≥ 1.5` (almeno alcuni episodi raggiungono Classical/Medieval)
  - distribuzione `action_RESEARCH_*` non degenere su 1-2 tech
  - `ep_rew_mean` non crollato rispetto alla baseline
- **Failure mode**: se `techs_mean < 18` (regressione vs Run #22) → rollback,
  ripristinare auto-picker come comportamento principale e investigare prima di
  reintrodurre la scelta esplicita.

---

## Rischi / open questions

| Rischio | Mitigazione |
|---|---|
| **Sparsità masking**: 74 azioni con mask attivo solo per ~5-10 alla volta può rallentare l'esplorazione PPO | Monitorare `entropy_loss` e `clip_fraction` in TB; se entropia collassa, ridurre temporaneamente lo scope o aumentare `ent_coef` |
| **Cumulativo con altri file**: File 26 isolato → `Discrete(97)`, ma combinato con File 23 (+~12 BUILD), File 24 (+1 BUILD_ROAD), File 25 (+26 SET_FOCUS/WORK_TILE) → `Discrete(136+)` | Verificare scalabilità PPO; valutare policy network più ampia (`net_arch` esteso) |
| **Auto-pick fallback subottimale**: l'estensione del tech pool a 74 tech significa che il fallback alfabetico ora pesca tra tutte le ere | Documentato come "fallback subottimale by design"; l'agente è incentivato a scegliere esplicitamente via dense reward |
| **`era_one_hot` derivata**: `TechManager.era` non è serializzato come stringa diretta nel save (vedi `TechManager.kt:480-507`) | Ricostruire da `techsResearched` + `load_tech_eras`. Alternativa: parsing diretto da `civ.tech.era` se esposto nel JSON — verificare in implementazione |
| **Bug fix `current_tech`**: piccolo rischio regressione su test esistenti di `state_parser` che si appoggiano al comportamento corrente | Eseguire l'intera suite parser prima del merge; se necessario aggiornare assert dei test legacy |

---

## Fuori scope (estensioni future)

- **Vittoria scientifica**: richiede tech tree completo + Apollo Program + Mars colony →
  Fase 4.
- **Tech trading** con altre civ → Fase 4.
- **Tech speed bonus / strategic tech tier**: scartato in Fase 2 (vedi razionale
  `Design > Reward shaping`).
- **Espansione `max_turns` oltre 155** per permettere di raggiungere tech avanzate:
  fuori scope, da valutare con utente in fase futura.
