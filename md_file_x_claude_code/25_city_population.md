# File 25 — Gestione popolazione citta' (focus + worked tiles)

## Obiettivo

Dare all'agente il controllo della **popolazione delle citta'**, sia a livello "focus strategico"
(priorita' Food / Production / Gold / Science / Culture / Faith / GoldGrowth / ProductionGrowth
— gli 8 focus esposti dalla UI di Unciv) sia a livello fine ("lavora questo tile specifico"),
invece di lasciare la "AI cittadina" di Unciv decidere tutto autonomamente.

## ⚠️ Prerequisito

Validare a runtime **File 23 + File 24** stabili prima di implementare File 25:
- `improvements_built_mean > 0`,
- `cities_connected_mean ≥ 0.5` (almeno qualche citta' mediamente connessa),
- distribuzione azioni non degenere,
- nessuna regressione su `ep_rew_mean`.

---

## Stato attuale

Le citta' di Unciv riassegnano automaticamente i cittadini ai tile via `autoAssignPopulation()`
(`CityPopulationManager.kt:158-215`), chiamata ad ogni `addPopulation()` e ad ogni `startTurn`.
**Nessuna azione dell'agente** influisce su quali tile vengono lavorati o sul focus. Le citta'
girano in `cityAIFocus = NoFocus` per default.

---

## Design

### Scelta confermata dall'utente

**Focus + worktile fine (entrambi)** — controllo a due livelli, masking complesso ma massima
espressivita'. L'agente impara sia decisioni strategiche (focus) sia tattiche (assegnazioni
specifiche).

### Azioni aggiunte

1. **8 azioni `SET_FOCUS_*`**: `Food, Production, Gold, Science, Culture, Faith, GoldGrowth,
   ProductionGrowth`. Allineate ai **8 focus** mostrati nella UI di Unciv ("Focus cittadini" nella
   City Screen — accanto ai meta-modi "Default" e "Manuale"). Sempre disponibili nello **step
   citta'**. Nota: `NoFocus` (Default) non e' un'azione esplicita — qualunque `SET_FOCUS_*`
   riabilita di per se' `autoAssignPopulation`. `Manual` viene impostato implicitamente da
   `worktile` (vedi sotto). `HappinessFocus` esiste nell'enum `CityFocus.kt` ma non e' tra gli 8
   focus mostrati in UI Unciv → escluso anche qui per coerenza.
2. **~18 azioni `WORK_TILE_<n>`** (toggle): clock-direction city-relative.
   - clock 1..6 a distanza 1 → 6 tile,
   - clock 1..12 a distanza 2 → 12 tile.
   - Totale ~18. Disponibili solo se `city.cityAIFocus == "Manual"`.
   - Toggle: se tile **lavorato** → libera; se **non lavorato** → lavora (solo se
     `freePopulation > 0`).
3. (Opzionale, fase successiva) `SET_MANUAL_SPECIALISTS` per disabilitare auto-assegnazione
   specialisti.

### Disabilitazione AI cittadina

Per usare `WORK_TILE` serve `city.cityAIFocus = CityFocus.Manual`. **Decisione confermata:
implicito** — il comando server `worktile` setta `cityAIFocus = Manual` se non gia' impostato, e
disabilita di fatto `autoAssignPopulation` per quella citta'. L'agente puo' tornare al focus
strategico con `SET_FOCUS_*` (che riabilita `autoAssign`).

### Reward

**Invariata**. Segnale indiretto via metriche esistenti: `population_growth`, `tech_researched`,
`gold_accumulation` (vedi `reward.py:REWARD_WEIGHTS`). Scelta esplicita dell'utente per evitare
reward hacking (cambio focus a ogni turno per +reward).

---

## Implementazione

### `unciv/Unciv/desktop/src/com/unciv/app/desktop/DesktopLauncher.kt`

Nuovi comandi, modellati sul template `improve`/`foundcity`:

```kotlin
// setfocus <path> <cityId> <focusName>
//   → city.setCityFocus(CityFocus.valueOf(focusName)); city.reassignPopulation()
//   → "ok focus <focusName>" | "illegal unknown_focus" | "error <msg>"

// worktile <path> <cityId> <x> <y>   (toggle)
//   → se tile in city.workedTiles: city.population.stopWorkingTile(pos)
//   → altrimenti se freePopulation > 0: assegna manualmente
//   → setta cityAIFocus = Manual implicitamente
//   → "ok worked <x> <y>" | "ok unworked <x> <y>" | "illegal cannot_work"

// listcitizen <path> <cityId>
//   → "citizen <focus> <pop> [<x>,<y>] [<x>,<y>] ..."
//   → utility per debug e test
```

**Ricompilare il JAR.**

### `src/utils/headless.py`

- `set_city_focus(save, city_id, focus) -> dict`
- `work_tile(save, city_id, x, y) -> dict`
- `list_citizen(save, city_id) -> dict`
- Aggiungere prefissi protocollo `"ok worked "`, `"ok unworked "`, `"ok focus "`, `"citizen "`
  a `_RESPONSE_PREFIXES`.

### `src/envs/unciv_env.py`

- Aggiungere 8 azioni `SET_FOCUS_*` + 18 azioni `WORK_TILE_<clock_distance>` (city-relative).
- **Mapping clock-direction → (dx, dy) hex city-relative** documentato come tabella nella spec
  implementativa; verificare coincidenza con il sistema hex usato dalle azioni `MOVE_*`
  esistenti in `_ACTION_NAMES`.
- Masking:
  - `SET_FOCUS_*` sempre disponibili nello step **citta'**,
  - `WORK_TILE_*` mascherate `True` solo se `city.cityAIFocus == "Manual"` AND tile in
    `city.getWorkableTiles()` AND entro distanza territorio.
- Nuovi handler `_apply_set_focus(action, city)`, `_apply_work_tile(action, city)`.

### `src/parsers/state_parser.py`

Nuovi campi su `CityState`:
- `focus: str` (da `cityAIFocus`),
- `worked_tiles_positions: set[(x,y)]` (da `City.workedTiles`),
- `locked_tiles_positions: set[(x,y)]`,
- `free_population: int` (derivato: `population - len(workedTiles) - specialists`).

**`to_observation_vector`**:
- per la **citta' selezionata**: 8 valori `focus_one_hot` + 1 valore `free_population_norm`
  (`/5.0`) + 18 valori `worked_tile_mask` (clock-relativo, `1.0` se lavorato, `0.0` altrimenti),
- per la **citta' 2** (riassunto, se esposta): solo 8 valori `focus_one_hot` + 1 `free_population_norm`.

**Stima shape totale**:
- MVP solo `focus_one_hot + free_pop` per le 2 citta' esposte: `+18` → `(64,) → (82,)` se File 24
  implementato, altrimenti `(61,) → (79,)`.
- Estensione con `worked_tile_mask` per citta' selezionata: `+18` → `(82,) → (100,)`.

**Raccomandazione**: implementare in **due sotto-step**:
1. prima solo `focus_one_hot + free_pop`,
2. poi `worked_tile_mask` (richiede mapping clock-direction verificato).

Numeri finali da raffinare in implementazione (sono cambiati i conteggi rispetto alla stima
iniziale di pianificazione — vedi sezione "Rischi").

### `src/utils/reward.py`

**Invariato**. Nessun nuovo peso.

### `src/utils/callbacks.py`

- `unciv/focus_food_ratio_mean`, `_production`, `_gold`, `_science`, `_culture`, `_faith`,
  `_gold_growth`, `_production_growth`, `_none`, `_manual` (frazione citta' con quel focus a
  fine episodio),
- `unciv/focus_changes_mean` (anti-thrashing detection),
- `unciv/worktile_actions_attempted_mean`, `_succeeded_mean`,
- `unciv/action_SET_FOCUS_*`, `unciv/action_WORK_TILE_*` in `_ACTION_NAMES`.

---

## Contratti che cambiano

- **Obs vector**:
  - MVP (solo focus + free_pop): `(64,) → (82,)` (post File 24),
  - estensione (con worked_tile_mask): `(82,) → (100,)`.
- **Action space**: `Discrete(24 + N) → Discrete(50 + N)` (8 `SET_FOCUS_*` + 18 `WORK_TILE_*`).
- **Nuovi comandi headless**: `setfocus`, `worktile`, `listcitizen`.

> ⚠️ Aggiornare la **tabella contratti** in `CLAUDE.md` quando si implementa.

---

## Test richiesti

### `tests/test_headless.py`
- `test_setfocus_success`
- `test_setfocus_illegal_unknown_focus`
- `test_worktile_toggle_assign`
- `test_worktile_toggle_release`
- `test_worktile_illegal_no_free_pop`
- `test_worktile_implies_manual_focus`
- `test_listcitizen_parses_worked_tiles`

### `tests/test_env.py`
- `test_action_space_size_after_citizens`
- `test_setfocus_masked_only_city_step`
- `test_worktile_masked_only_if_manual_focus`
- `test_focus_change_calls_headless`

### `tests/test_parser.py`
- `test_city_state_focus_field`
- `test_city_state_worked_tiles_positions`
- `test_obs_shape_with_focus_features`

### `tests/test_reward.py`
- Nessun nuovo test reward (peso invariato).

### Smoke JAR
- Citta' con `NoFocus` → `setfocus Food` → advance → `worked_tiles` shift verso tile a food alto,
- `worktile (x,y)` → save mostra `cityAIFocus = Manual` + `(x,y)` in `workedTiles`.

---

## Criteri di accettazione

- **~132 + 10 test verdi**.
- **Smoke JAR riuscito**.
- **Training di validazione 50k step** con:
  - `focus_changes_mean` ragionevole (1-5 per episodio, non spam),
  - almeno **2 focus diversi** rappresentati nella distribuzione.

---

## Rischi / open questions

- **Spazio azioni grande** (`50 + N`): rallenta esplorazione PPO. Monitorare `fps` e
  `ep_rew_mean` post-implementazione.
- **Mapping clock-direction city-relative ai tile reali**: richiede verifica che gli offset
  coincidano con il sistema hex usato dalle azioni `MOVE_*` esistenti. Da validare in
  implementazione (test parser + smoke).
- **`autoAssignPopulation` implicita**: chiamata da `addPopulation()` puo' sovrascrivere scelte
  fini se non in Manual. Verificare con smoke che dopo `worktile` la scelta sopravviva al
  successivo `addPopulation`.
- **Conteggio finale obs shape**: la stima parte dalle ipotesi MVP/esteso indicate sopra; il
  numero esatto va fissato dopo aver verificato quali citta' vengono effettivamente esposte
  (selezionata vs citta' 2 vs aggregato).

---

## Fuori scope (estensioni future)

- **Acquisto tile** (gold spending).
- **Acquisto edifici con gold** (rush production).
- **Annex / raze citta' conquistate** (richiede combattimento, Fase 3).
- **Production focus su miglioramenti specifici** (legato a File 23, gia' coperto).
- **Faith focus** (fuori scope tech early Classical).
