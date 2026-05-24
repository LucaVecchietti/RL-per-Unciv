# File 21 — Fase B: Rework del movimento (delegato al motore)

## Obiettivo

Sostituire il movimento "fatto a mano" in Python — sbagliato su griglia esagonale, a
costo fisso, solo per i Warrior — con un movimento **delegato al motore Unciv** via il
fork headless. Risultato: tutte le unità (militari e civili) si muovono rispettando
costo del terreno, adiacenza hex, world-wrap, passabilità e legalità, calcolati dal gioco.

**Prerequisiti:** Fase A (File 20) completata e validata.

---

## Diagnosi (verificata su sorgente Kotlin + save reali)

Movimento attuale (`unciv_env.py::_apply_movement` + `_MOVE_DELTA`):
- **4 direzioni cartesiane** `(±1,0),(0,±1)` → su hex i vicini reali sono **6**.
- **costo fisso −1.0**, ignora il terreno.
- **solo `militaryUnit`** e **solo Warrior** (`_pending_warriors` filtra `name=="Warrior"`).
- tile-swap manuale nel JSON, senza passare dal motore.

### Fatti verificati nel sorgente
- **6 vicini hex** (`HexMath.clockPositionToHexcoordMap`), offset `(x,y)` per ora di orologio:
  | Ora | Offset |
  |---|---|
  | 12 | (+1, +1) |
  | 2  | (0, +1) |
  | 4  | (−1, 0) |
  | 6  | (−1, −1) |
  | 8  | (0, −1) |
  | 10 | (+1, 0) |
- Coordinate hex centrate sull'origine, **valori negativi normali**, `worldWrap=true`, `radius=10`.
  Il save **omette `position`/`x`/`y` quando 0**.
- **API movimento** (`UnitMovement.kt`, su `unit.movement`):
  - `moveToTile(tile)` — muove applicando costo terreno reale, pathing, ZoC, mosse parziali.
  - `canMoveTo(tile)` / `canReachInCurrentTurn(tile)` — legalità / raggiungibilità nel turno.
  - `getDistanceToTiles()` — destinazioni raggiungibili nel turno con costo.
- **Indirizzamento**:
  - `MapUnit.id: Int` (nel save: `id:14`, `id:29`).
  - `civ.units.getUnitById(id): MapUnit?`.
  - `tileMap.getIfTileExistsOrNull(x,y): Tile?`.
  - `Tile.neighbors` — i 6 vicini, **gestisce già il world-wrap**.
- **Protocollo `--server`** (`DesktopLauncher.kt`): oggi solo `advance <path>` e `quit`.
  Ogni comando ricarica il save da file, opera, rissalva (stateless per comando).
  `gameInfoFromString` imposta i transients (lo conferma il funzionamento di `nextTurn()`).

---

## B1 — Kotlin: comando `move` nel server (`DesktopLauncher.kt`)

Nel loop `--server`, aggiungere un ramo `move`:
```
move <path> <unitId> <clock>     // clock ∈ {2,4,6,8,10,12}
```
Logica:
1. `file.readText` → `gameInfo = UncivFiles.gameInfoFromString(...)`.
2. `civ = gameInfo.getCivilization("India")` (o il player civ).
3. `unit = civ.units.getUnitById(unitId)` → se null: stampare `error no_unit`.
4. destinazione = vicino di `unit.currentTile` corrispondente al `clock`
   (usare `Tile.neighbors` + `HexMath` per mappare clock→vicino; il wrap è già gestito).
5. se `unit.movement.canMoveTo(dest)` (o reachable): `unit.movement.moveToTile(dest)`,
   salvare il file, stampare `moved <unitId> <x> <y> <currentMovement>`.
   altrimenti stampare `illegal`.
6. `System.out.flush()`.

Opzionale ma consigliato: comando `legalmoves <path> <unitId>` → stampa le direzioni
legali (per masking preciso lato Python).

**Build:** ricompilare `Unciv.jar` con JDK 21 (`gradlew desktop:dist`), copiarlo in `unciv/Unciv.jar`.

---

## B2 — `src/utils/headless.py`

Aggiungere `move_unit(save_path, unit_id, clock) -> dict` che:
- scrive `move <path> <id> <clock>\n` sullo stdin del processo persistente,
- legge la risposta (`moved ...` / `illegal` / `error ...`),
- restituisce esito strutturato `{success, x, y, movement_left}` o `{success: False, reason}`.
Riusa la stessa infrastruttura di `advance_turn` (lock, `_ensure_running`, timeout).

---

## B3 — `src/parsers/state_parser.py`

- `UnitState`: aggiungere `id: int` (parsato da `militaryUnit.id` / `civilianUnit.id`).
- **Fix normalizzazione coordinate** nell'obs: oggi `x / width` è errato per hex con coord
  negative. Usare il raggio mappa: es. `(x / radius)` clampato in `[-1, 1]`, idem `y`.
  Serve esporre `map_radius` in `GameState` (da `mapParameters.mapSize.radius`).

---

## B4 — `src/envs/unciv_env.py`

- **Rotation su tutte le unità**: `_pending_units` = tutte le unità del player con
  `currentMovement > 0` (militari **e** civili), non solo Warrior.
- **Azioni movimento = 6 direzioni hex** (clock 2/4/6/8/10/12) + skip.
  ⚠️ **L'action space cambia**: `Discrete(19)` → `Discrete(21)`
  (9 edifici + 5 unità + skip + **6** direzioni). Aggiornare:
  - `ACTION_MAP` (sostituire i 4 `MOVE_*` con 6 `MOVE_CLOCK_2/4/6/8/10/12` o nomi direzione hex),
  - `observation_space` invariato `(57,)`,
  - contratto in `CLAUDE.md` (azioni 19 → 21).
- `_apply_movement`: chiamare `self.headless.move_unit(save_path, unit.id, clock)` invece del
  tile-swap manuale; rimuovere `_MOVE_DELTA`/swap.
- `action_masks()` unit-step: abilitare solo le direzioni legali (da `legalmoves`, o tutte+esito).

---

## B5 — `src/utils/callbacks.py`

Nuove metriche (accumulate nell'`info` dict di `unciv_env`, loggate in `_on_rollout_end`):
- `moves_attempted_mean`, `moves_succeeded_mean`, `moves_illegal_mean`
- `move_cost_mean` (punti movimento consumati per mossa — verifica costo terreno ≠ 1)
- `moved_warrior_mean`, `moved_scout_mean`, `moved_settler_mean`, `moved_worker_mean`
- `units_stuck_mean` (unità con movimento>0 ma nessuna mossa legale)
- `legal_moves_available_mean`
- `new_tiles_per_move_mean` (tiles nuove esplorate / mosse)

Aggiornare `ActionDistributionCallback._ACTION_NAMES` alle 21 azioni (6 direzioni).

---

## File da modificare

- `unciv/.../DesktopLauncher.kt` (B1: comando `move`/`legalmoves`) + **ricompilare JAR**
- `src/utils/headless.py` (B2: `move_unit`)
- `src/parsers/state_parser.py` (B3: `UnitState.id`, `map_radius`, fix coord)
- `src/envs/unciv_env.py` (B4: rotation tutte le unità, 6 direzioni, action space 21, `_apply_movement`)
- `src/utils/callbacks.py` (B5: metriche movimento + 21 azioni)
- `CLAUDE.md` (contratto azioni 19 → 21)
- `tests/test_headless.py`, `tests/test_env.py`, `tests/test_parser.py`, `tests/test_callbacks.py`

---

## Test richiesti

```python
# test_headless.py
test_move_unit_success()        # risposta "moved 14 1 -1 1.0" → dict parsato
test_move_unit_illegal()         # risposta "illegal" → success False

# test_parser.py
test_unitstate_has_id()          # id parsato da militaryUnit/civilianUnit
test_coord_normalization_negative()  # coord negative → obs in [-1,1], non fuori range

# test_env.py
test_rotation_includes_civilian_units()   # Settler/Worker entrano nella rotation
test_action_space_is_21()
test_unit_step_six_directions_masked()
test_apply_movement_calls_headless()       # mock move_unit chiamato con id+clock

# test_callbacks.py
test_movement_metrics_logged()
```

---

## Validazione (criterio di chiusura Fase B)

Run con metriche movimento:
- `move_cost_mean ≠ 1.0` costante → conferma costo terreno reale.
- `moved_settler_mean`, `moved_scout_mean`, `moved_worker_mean > 0` → tutte le unità si muovono.
- `moves_illegal_mean` basso → direzioni/masking corretti.
- `tiles_explored_mean` continua a salire (esplorazione efficace su hex corretto).

---

## Note implementative

- Preferire il movimento per **direzione/clock** (vicino) e lasciare il world-wrap al motore
  (`Tile.neighbors`), invece di calcolare le coordinate destinazione in Python.
- `moveToTile` gestisce mosse parziali e costo: una singola azione può consumare 1, 2 o più
  punti a seconda del terreno; va bene — è il comportamento reale.
- L'action space a 21 rende i checkpoint precedenti incompatibili → ripartire da zero (già
  necessario dopo la Fase A).
- Le unità civili (Settler/Worker) ora si muovono ma **non hanno ancora azioni speciali**
  (fondare città / costruire miglioramenti): quello è scope Fase C.
