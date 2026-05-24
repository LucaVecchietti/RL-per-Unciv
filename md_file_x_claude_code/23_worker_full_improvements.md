# File 23 — Worker completo: miglioramenti generali (Opzione B — azioni esplicite)

## Obiettivo

Estendere le capacità del Worker oltre la sola connessione delle risorse (Fase C3):
permettere di costruire **qualsiasi miglioramento rilevante** (Farm, Mine, Trading Post,
Lumber Mill, Camp, Pasture, Plantation, Quarry, Fishing Boats…), **rimuovere feature**
(Jungle/Forest/Marsh) e (estensione) costruire **strade**, dando il controllo all'agente.

> **Scelta confermata dall'utente: Opzione B — set di azioni esplicite** (un'azione per tipo di
> miglioramento), con masking dinamico di validità. L'Opzione A (auto-improve delegato al motore)
> è scartata: si vuole che sia l'agente a scegliere *cosa* costruire.

## ⚠️ Prerequisito: validazione a runtime PRIMA di implementare

Prima di questa fase va eseguito un **training di validazione di C1+C2+C3** (obs `(61,)`,
action `Discrete(23)`, JAR aggiornato) e verificato che:
- nessun crash (fix protocollo headless Sessione 33),
- `cities_founded_mean > 0`, `territory_resources_mean` cresce,
- `improvements_built_mean > 0`, `connected_resources_mean > 0`,
- `fps` accettabile (il masking preciso aggiunge round-trip).

Solo dopo questa conferma si implementa il File 23.

---

## Stato attuale (Fase C3)

`improve <path> <id>` (senza nome) costruisce SOLO il miglioramento che connette la risorsa sul
tile. Azione Python singola `Improve` (indice `_improve_idx`, action space 23), mascherata per i
Worker. Con l'Opzione B questa azione singola viene **sostituita** dal set `BUILD_<improvement>`.

---

## Design (Opzione B)

### Spazio azioni
- Rimuovere l'azione singola `Improve`.
- Aggiungere N azioni `BUILD_<improvement>` generate **dinamicamente dal ruleset** (no hardcoding,
  come per edifici/unità). `Discrete(23 - 1 + N)` = `Discrete(22 + N)`.
- Le azioni sono valide **solo in unit step, solo per Worker**, e mascherate per validità reale
  (vedi `legalimprovements`).

### Quali miglioramenti includere (filtro in `ruleset_reader`)
Leggere `jsons/Civ V - Vanilla/TileImprovements.json` e includere i miglioramenti "da Worker"
early/standard, **escludendo**:
- `City center`, `Barbarian encampment`, `Ancient ruins`, rovine/relitti;
- miglioramenti da Grande Personaggio (Academy, Citadel, Manufactory, Customs House, Holy Site…)
  — riconoscibili da `uniqueTo`/uniques o da `turnsToBuild` assente/0;
- ferrovie/strade SE si rimanda la rete commerciale (Road può essere incluso o lasciato a una
  fase strade dedicata — vedi Fuori scope);
- miglioramenti con `techRequired` oltre Classical (coerente con il resto del progetto).
Includere: Farm, Mine, Trading Post, Lumber Mill, Camp, Pasture, Plantation, Quarry,
Fishing Boats, e le rimozioni feature (`Remove Jungle/Forest/Marsh`) — l'elenco effettivo deriva
dal filtro, ordine alfabetico per indici stabili.

> Verificare in implementazione i campi reali di `TileImprovements.json` (es. `name`,
> `terrainsCanBeBuiltOn`, `techRequired`, `turnsToBuild`, `uniqueTo`, uniques) per il filtro.

---

## Implementazione

### `src/utils/ruleset_reader.py`
- `load_buildable_improvements(jar_path) -> list[str]`: nomi dei miglioramenti costruibili dal
  Worker (filtro sopra), ordine alfabetico. (Eventuale dataclass con `required_tech` se serve
  per il masking lato Python, ma la validità reale la dà il motore.)

### Kotlin — `DesktopLauncher.kt` (rebuild JAR)
- Cambiare `improve` per accettare il nome del miglioramento:
  `improve <path> <unitId> <improvementName>` →
  `imp = ruleset.tileImprovements[name]`; se `unit.canBuildImprovement(imp, tile)` →
  `tile.startWorkingOnImprovement(imp, civ, unit)` → `improving <name> <turns>`, altrimenti
  `illegal cannot_build`.
- Nuovo comando `legalimprovements <path> <unitId>` → `legalimp <name> <name> …`: i miglioramenti
  che il Worker può costruire sul tile corrente (iterare `ruleset.tileImprovements` filtrando con
  `unit.canBuildImprovement`). Usato per il masking preciso (come `legalmoves`).

### `src/utils/headless.py`
- `build_improvement(save, unit_id, improvement_name) -> dict` (estende la firma C3 con il nome).
- `legal_improvements(save, unit_id) -> list[str]`.

### `src/envs/unciv_env.py`
- ACTION_MAP: rimuovere `"Improve"`, aggiungere `BUILD_<imp>` (da `load_buildable_improvements`).
  Aggiornare `_skip_idx`/`_move_start_idx`/`_found_city_idx` e nuovo `_build_action_map`
  (indice azione → nome improvement).
- `action_masks` unit step: per i Worker, query `headless.legal_improvements`, mascherare i
  `BUILD_<imp>` legali (oltre a skip + direzioni legali). (Costo: +1 round-trip per Worker/step.)
- `step` unit branch: se l'azione è un `BUILD_<imp>` → `_apply_improve(action, unit)` che chiama
  `headless.build_improvement(save, id, nome)`. Contatore `improvements_built` invariato.
- `action_masks` city step: i `BUILD_<imp>` sempre `False`.

### `src/utils/reward.py` + `config`
- `connected_resources` (C3) invariato. Opzionale `improvement_built` (piccolo bonus diretto,
  es. 0.2) per incoraggiare l'attività; di default tenere solo la reward indiretta + connected.

### `CLAUDE.md`
- Aggiornare il contratto azioni `23` → `22 + N` (N = n. miglioramenti costruibili).

---

## Test richiesti

- `test_ruleset_reader`: `load_buildable_improvements` include Farm/Mine/Trading Post, esclude
  City center e improvement da Grande Personaggio.
- `test_headless`: `build_improvement` con nome (success/illegal); `legal_improvements` parsing.
- `test_env`: action space `22+N`; `BUILD_*` mascherati solo per Worker e solo se legali (mock
  `legal_improvements`); `_apply_improve(action, unit)` chiama headless col nome giusto.
- **Smoke JAR** (con comando "esca" per il BOM dell'harness):
  - Worker su Grassland → `legalimprovements` include Farm → `improve … Farm` → advance → tile
    ha `improvement: Farm` (il motore processa anche le rese, non solo le risorse).
  - Worker su tile risorsa → `improve … Mine` connette (C3 invariato).

## Validazione (runtime)

- L'agente costruisce vari miglioramenti (`improvements_built_mean` cresce anche senza risorse);
  resa città e `population_mean` migliorano; distribuzione azioni `BUILD_*` non degenere.

## Fuori scope (estensioni future)

- **Strade/ferrovie** + rete commerciale (città→capitale): comando `buildroad` + logica rete +
  reward su città connesse. Da fare in una fase dedicata.
- Miglioramenti da Grande Personaggio.
