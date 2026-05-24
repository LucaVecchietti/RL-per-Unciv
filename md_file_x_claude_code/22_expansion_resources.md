# File 22 — Fase C: Espansione multi-città + risorse

## Obiettivo

Rendere l'agente capace di **espandersi** (fondare nuove città con i Settler) e di
**cercare/sfruttare le risorse** (riconoscerle nell'obs, fondare vicino, collegarle con i
Worker). Scope completo C1+C2+C3, ma implementato in tre sotto-step indipendentemente
testabili per isolare i bug.

**Prerequisiti:** Fase A (File 20) e Fase B (File 21) completate e validate.

> ⚠️ Questa fase cambia **obs shape** e **action space**. I checkpoint precedenti diventano
> incompatibili (atteso). Aggiornare la tabella contratti in `CLAUDE.md`.

---

## Meccanica reale delle risorse (verificata su sorgente)

Una risorsa Strategica/Luxury è "posseduta" (entra in `detailedCivResources`) **solo se**:
1. hai la tech `resource.revealedBy` (`TechManager.isResearched`),
2. il tile è nel **territorio** di una tua città,
3. ci costruisci sopra il **miglioramento** giusto con un **Worker**.

Quindi fondare vicino a una risorsa NON basta: serve il loop Worker. Per questo C è divisa
in: C1 (espansione), C2 (risorse nell'obs + reward di posizionamento, senza Worker),
C3 (Worker + risorse connesse reali).

### API verificate
- **FoundCity**: `unit.civ.addCity(tile.position, unit)` poi `unit.destroy()`.
  Guard: `tile.canBeSettled(unit.civ)` (acqua/impassabile + distanza minima `minimalCityDistance`),
  e `unit.hasMovement()`. (Da `UnitActionsFromUniques.getFoundCityAction` + `Civilization.addCity`.)
- **Worker**: `tile.startWorkingOnImprovement(ruleset.tileImprovements[name], civInfo, unit)`;
  check `unit.canBuildImprovement(improvement, tile)`. Completa in `turnsToImprovement`.
- **Risorse**: tile-level `resource` (nome), `resourceAmount`, `resource.resourceType`
  (Strategic/Luxury/Bonus); visibilità via `resource.revealedBy` → `tech.isResearched`.
- **Multi-città**: `civ.cities` (lista), ogni city ha `cityConstructions`, `tiles`, `population`.

---

## C1 — FoundCity + architettura multi-città

### C1.1 Kotlin — comando `foundcity` (`DesktopLauncher.kt`)
```
foundcity <path> <unitId>
```
Logica: carica gameInfo → player civ → `unit = civ.units.getUnitById(id)` →
`tile = unit.currentTile` → se non ha unique `FoundCity`: `error not_settler` →
se `!unit.hasMovement() || !tile.canBeSettled(civ)`: `illegal` →
`civ.addCity(tile.position, unit); unit.destroy()` → salva → `founded <x> <y>`.
(Usare `addCity` + `destroy` direttamente: NON usare la closure di `getFoundCityAction`,
che dipende dalla GUI.) **Ricompilare il JAR.**

### C1.2 `headless.py`
`found_city(save_path, unit_id) -> dict` (success / reason), come `move_unit`.

### C1.3 Rotation multi-città (`unciv_env.py`)
Estendere la per-entity rotation a:
`per ogni città (city step) → per ogni unità (unit step) → advance turn`.
- `_pending_cities` = tutte le città del player; ogni city step sceglie la costruzione per
  **quella** città (l'obs indica la città selezionata).
- `_pending_units` (da Fase B) include i Settler: nuova azione **FoundCity** valida solo se
  l'unità selezionata è un Settler su tile `canBeSettled`.
- `_apply_action` scrive nella coda della **città selezionata**, non sempre `cities[0]`.

### C1.4 Obs redesign per N città variabili
Sostituire gli slot fissi City1(19)+City2(10) con:
- **aggregato civ**: n_cities, somma pop, somma produzione, somma edifici, ecc.
- **blocco città selezionata** (full, ~19) — analogo al blocco "unità selezionata".
- (Le città non selezionate sono riassunte dall'aggregato.)

> La shape dell'obs cambia. Definire il layout esatto in implementazione e aggiornare
> `to_observation_vector`, l'assert di shape, `observation_space`, i test e CLAUDE.md.

### C1.5 Reward multi-città (`reward.py`)
- Pop growth ed edifici: sommare su **tutte** le città, non solo `cities[0]`.
- Nuovo bonus **FoundCity**: reward positiva quando `len(curr.cities) > len(prev.cities)`
  (peso configurabile in `config`, es. `reward.found_city`).

### Validazione C1
`cities_mean > 1` durante il training; il Settler viene usato per fondare (non solo costruito).

---

## C2 — Risorse nell'obs + reward di posizionamento

### C2.1 Parser (`state_parser.py`)
- Parsare i tile-resource: per ogni tile esplorato/visibile, `resource`, `resourceType`,
  e se `revealedBy` è soddisfatta dalle tech del player.
- Nuovi campi `GameState`: es. `visible_resources: list[(x,y,name,type)]` (solo monitoring/obs,
  non obs vector grezzo).

### C2.2 Obs — risorse locali
- **Patch locale** attorno all'entità selezionata (Settler/città): conteggio risorse
  Strategic/Luxury entro raggio R, gated dalle tech. Serve all'agente per *scegliere dove fondare*.
- Eventuale conteggio globale per tipo (cosa ti manca).

> Anche questo modifica la shape obs (oltre a C1). Consolidare le due modifiche di shape in
> un unico redesign per non cambiare il contratto due volte.

### C2.3 Reward di posizionamento (`reward.py`)
- Bonus quando una **nuova città** include nel territorio (`city.tiles`) un tile-risorsa
  Strategic/Luxury non ancora presente nel territorio delle altre città.
- Non richiede Worker → imparabile subito dopo C1.

### Validazione C2
Le città fondate tendono a includere tile-risorsa (rispetto a un baseline casuale);
`tiles_with_resource_in_territory_mean` cresce.

---

## C3 — Worker + miglioramenti → risorse connesse reali

### C3.1 Kotlin — comando `improve` (`DesktopLauncher.kt`)
```
improve <path> <unitId> <improvementName>
```
Logica: unità Worker → `improvement = ruleset.tileImprovements[name]` →
se `unit.canBuildImprovement(improvement, tile)`: `tile.startWorkingOnImprovement(...)` →
salva → `improving <name> <turns>`, altrimenti `illegal`. **Ricompilare il JAR.**

### C3.2 `headless.py`
`build_improvement(save_path, unit_id, improvement_name) -> dict`.

### C3.3 Azioni Worker (`unciv_env.py`)
Aggiungere azioni di miglioramento per i Worker. Due opzioni (decidere in implementazione):
- **(A) auto-improve**: una sola azione "costruisci il miglioramento consigliato per il tile"
  (lascia scegliere il tipo al motore/euristica). Action space minimo, più semplice da imparare.
- **(B) set esplicito**: BUILD_FARM / BUILD_MINE / BUILD_PLANTATION / BUILD_ROAD … più controllo,
  action space più grande, masking per validità.
Raccomandazione: partire con **(A)**, poi valutare (B).

### C3.4 Reward risorse connesse (`reward.py`)
- Bonus quando `detailedCivResources` acquisisce una nuova risorsa Strategic/Luxury
  (ora finalmente popolato grazie ai miglioramenti). Riusa il parsing risorse del File 19.

### ⚠️ Rischio da validare per primo in C3
Verificare che Unciv headless **processi i miglioramenti del Worker** per il player civ in
`nextTurn()` (la produzione città SÌ, la ricerca NO → patch manuale). Se i miglioramenti non
vengono processati, servirà un accumulo manuale come `_advance_tech`. Test: accodare un Farm,
avanzare N turni, verificare che `improvement` compaia sul tile.

### Validazione C3
`strategic_res_count_mean > 0` / `luxury_res_count_mean > 0` (risorse realmente connesse);
i Worker costruiscono miglioramenti (`improvements_built_mean > 0`).

---

## File da modificare (complessivo)

- `unciv/.../DesktopLauncher.kt` (`foundcity`, `improve`) + **ricompilare JAR**
- `src/utils/headless.py` (`found_city`, `build_improvement`)
- `src/parsers/state_parser.py` (tile-resources, visibilità tech, obs redesign N città + risorse)
- `src/envs/unciv_env.py` (rotation multi-città, azioni FoundCity/improve, obs, action space)
- `src/utils/reward.py` (reward multi-città, FoundCity, posizionamento risorse, risorse connesse)
- `src/utils/callbacks.py` (metriche: città fondate, risorse in territorio, risorse connesse, migliorie)
- `config/default_config.yaml` (pesi reward: `found_city`, `resource_placement`, `resource_connected`)
- `CLAUDE.md` (contratti: obs shape e action space aggiornati)
- test: `test_headless.py`, `test_env.py`, `test_parser.py`, `test_reward.py`, `test_callbacks.py`

---

## Contratti che cambiano

- **Obs shape**: da `(57,)` a un nuovo valore (redesign multi-città + risorse) — da fissare in C1/C2.
- **Action space**: da `Discrete(21)` (post-Fase B) a `Discrete(21 + 1 FoundCity + N_improve)`.
- Aggiornare la tabella contratti in `CLAUDE.md` e tutti i test di shape/azioni.

---

## Note implementative

- Implementare **nell'ordine C1 → C2 → C3**, validando ciascuno prima del successivo: ogni
  sotto-step è imparabile da solo e isola i bug.
- Consolidare le due modifiche di shape obs (C1 città selezionata + C2 risorse) in **un unico**
  redesign per non rompere il contratto due volte.
- Il loop risorse reale (C3) dipende dal fatto che i miglioramenti Worker siano processati in
  headless: validarlo per primo, prima di costruirci sopra la reward.
- Tutto delegato al motore (FoundCity, improvement) come per il movimento (Fase B): niente
  reimplementazione delle regole in Python.
