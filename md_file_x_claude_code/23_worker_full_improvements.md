# File 23 — Worker completo: miglioramenti generali

## Obiettivo

Estendere l'azione `Improve` del Worker oltre la sola connessione delle risorse (Fase C3):
permettere di costruire **miglioramenti di resa** (Farm, Mine, Trading Post, Lumber Mill, Camp…)
e di **rimuovere feature** (Jungle/Forest/Marsh) anche su tile **senza** risorsa, così le città
crescono e producono di più.

**Stato attuale (Fase C3):** `improve <path> <id>` costruisce SOLO il miglioramento che connette
la risorsa sul tile (`ruleset.tileResources[tile.resource].improvement`). Su tile senza risorsa
risponde `illegal no_resource_improvement`. Niente scelta tra miglioramenti, niente rimozione
feature, niente strade.

**Prerequisiti:** Fase C (File 22) completata. Movimento Worker (Fase B) funzionante.

---

## Decisione di design (da confermare con l'utente)

### Opzione A — Auto-improve generalizzato (CONSIGLIATA)
Una sola azione `Improve` (già esistente, **action space invariato a 23**): il motore sceglie
il **miglior miglioramento** per il tile del Worker (risorsa o resa o rimozione feature).
- L'agente sceglie comunque **quale tile** (via movimento) e **quando** migliorare; il *cosa* lo
  decide il motore (come per movimento/FoundCity, delegati al motore).
- Pro: nessun cambio di contratto, semplice, coerente col resto del progetto, sfrutta la logica
  del gioco (gestisce anche rimozione feature). Con: l'agente non sceglie il *tipo* di miglioramento.

### Opzione B — Set di azioni esplicite
Azioni separate: `BUILD_FARM`, `BUILD_MINE`, `BUILD_TRADING_POST`, `BUILD_ROAD`,
`REMOVE_JUNGLE`, … con masking per validità (`unit.canBuildImprovement`).
- Pro: controllo totale dell'agente. Con: **action space cresce molto**, masking complesso,
  apprendimento più difficile, checkpoint da rifare.

> Raccomandazione: **Opzione A**. Mantiene `Discrete(23)`, massimo riuso del motore.
> L'Opzione B si può aggiungere in un secondo momento se serve controllo fine.

---

## Implementazione (Opzione A)

### Kotlin — generalizzare il comando `improve` (`DesktopLauncher.kt`)
Oggi il ramo `improve` cerca solo `tile.resource`. Generalizzarlo a:
1. Se il tile ha una risorsa con miglioramento connettente costruibile → costruisci quello
   (comportamento attuale, prioritario).
2. Altrimenti scegli il **miglior miglioramento** per il tile.

Per il punto 2, due strade (verificare in implementazione):
- **(a)** `WorkerAutomation.chooseImprovement(unit, tile, localUniqueCache)` → `TileImprovement?`
  (vedi `WorkerAutomation.kt:305`). Se `private`, rendere accessibile nel fork (o usare
  `automateWorkerAction` — sconsigliato perché muove anche l'unità).
- **(b)** Euristica semplice: iterare `gameInfo.ruleset.tileImprovements.values`, filtrare con
  `unit.canBuildImprovement(imp, tile)`, escludere strade, scegliere per resa (es. il primo
  valido o quello con `improvementStats` migliore per il tile).

Output: `improving <name> <turns>` | `illegal nothing_to_improve` | `error <msg>`.
**Ricompilare il JAR.**

### Python
- `headless.build_improvement` (Fase C3): **invariato** (il comando resta `improve <path> <id>`).
- `unciv_env.action_masks` (unit step): `Improve` valido per i Worker — **invariato**. (Già
  abilitato solo per `name == "Worker"`.) Opzionale: abilitare solo se esiste un miglioramento
  costruibile (richiederebbe una query extra → lasciare semplice, illegale gestito come no-op).
- `_apply_improve`: invariato (incrementa `improvements_built`).

### Reward (opzionale)
- Le migliorie di resa sono già premiate **indirettamente** (più cibo/produzione → crescita pop
  ed edifici completati, già in reward). Valutare un piccolo bonus diretto `improvement_built`
  (es. 0.2) per incoraggiare l'attività del Worker, da bilanciare per non incentivare improving
  inutile. Default: **nessun bonus diretto** (si parte con la reward indiretta).

### Obs (opzionale)
- Per aiutare l'agente a capire quando il Worker è su un tile migliorabile, si può aggiungere
  1 feature: "tile dell'unità selezionata è migliorabile (no improvement, lavorabile)". Cambia
  la shape (61→62). **Opzionale**: valutare solo se il training mostra che il Worker non impara
  a migliorare senza questo segnale.

---

## File da modificare

- `unciv/.../DesktopLauncher.kt` (generalizzare `improve`) + **ricompilare JAR**
- (eventuale) `src/utils/reward.py` + `config` se si aggiunge `improvement_built`
- (eventuale) `src/parsers/state_parser.py` + `unciv_env.py` se si aggiunge la feature obs
- `tests/` (test del nuovo comportamento), `CLAUDE.md` (se cambiano contratti)

> Se si sceglie l'Opzione A senza reward/obs extra: l'**unica** modifica è il Kotlin + rebuild
> JAR; nessun cambio di contratto Python.

---

## Test richiesti

- **Smoke JAR** (come per C3, con comando "esca" per il BOM dell'harness):
  - Worker su tile **senza risorsa** ma migliorabile (es. Grassland) → `improve` → `improving Farm N`;
    advance → tile ha `improvement` (verifica che il motore processi anche le migliorie di resa).
  - Worker su tile **con feature** (Jungle) → `improve` → costruisce/rimuove come da motore.
  - Worker su tile **risorsa** → comportamento C3 invariato (connette la risorsa).
- **Python**: se si aggiunge reward/obs, relativi unit test; altrimenti i test C3 restano validi
  (il comando Python non cambia firma).

---

## Validazione (runtime)

- `improvements_built_mean` cresce anche in partite senza molte risorse (il Worker migliora resa).
- Resa città (food/produzione per turno) e `population_mean` migliorano rispetto a C3.

---

## Fuori scope (estensioni future)

- **Strade/ferrovie** e rete commerciale (connessione città → capitale): sotto-sistema a parte
  (comando `buildroad`, logica di rete, reward su città connesse).
- **Opzione B** (azioni esplicite per tipo di miglioramento) se serve controllo fine dell'agente.
- **Automazione completa** del Worker (`automateWorkerAction`): toglie agency all'agente RL,
  utile solo come baseline/confronto.
