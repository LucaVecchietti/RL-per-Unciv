# File 24 — Comando buildroad + reward rete commerciale

## Obiettivo

Estendere il Worker con la capacita' di **costruire strade** (Road) e introdurre una reward
**event-based** per ogni citta' che diventa **connessa alla capitale** via rete commerciale.
Niente reward denso per "road costruita": il segnale ha senso solo se la strada effettivamente
chiude un percorso verso la capitale.

## ⚠️ Prerequisito

Validare a runtime **File 23** (Worker completo, azioni `BUILD_<imp>` esplicite) **prima** di
implementare File 24:
- `improvements_built_mean > 0` stabile per **≥ 100k step**,
- distribuzione `BUILD_<imp>` **non degenere** (non solo Farm),
- nessuna regressione su `connected_resources_mean`,
- `fps` accettabile dopo il masking preciso introdotto da File 23.

Solo dopo questa conferma si implementa il File 24.

---

## Stato attuale

Dopo File 23, il Worker puo' costruire **qualsiasi improvement del ruleset early/standard**
**eccetto Road/Railroad**, esclusi dal filtro in `load_buildable_improvements` perche' non sono
"improvement risorsa/yield". Le strade in Unciv vengono attualmente costruite solo dalla AI
nativa su unita' non controllate dall'agente.

Nessuna nozione di **"citta' connessa al trade network"** in obs o reward. Il flag esiste a
livello save (`City.connectedToCapitalStatus`) ma non e' parsato.

---

## Design

### Scelte confermate dall'utente

- **Comando server dedicato `buildroad <path> <unitId>`**, NON estensione di `improve`. Pulizia
  di scope: `improve` resta per i miglioramenti-risorsa/yield, `buildroad` per strade.
- **Reward solo event-based** `city_connected_to_capital = 4.0` (delta tra `prev` e `curr`,
  clamp ≥ 0). **Niente reward denso `road_built`**: evita reward hacking (spam Road su tile
  scollegati).

### Meccanica reale (verificata su sorgente)

- Road e' un improvement gia' definito in `TileImprovements.json:107-132`
  (`techRequired: "The Wheel"`, `turnsToBuild: 4`).
- API motore identica agli altri improvement:
  ```kotlin
  tile.startWorkingOnImprovement(ruleset.tileImprovements["Road"], civ, unit)
  ```
- Stato strada serializzato a livello tile: `Tile.roadStatus: RoadStatus = None|Road|Railroad`
  (`Tile.kt:80`).
- Connessione citta'↔capitale: `CivInfoTransientCache.citiesConnectedToCapitalToMediums` e'
  `@Transient` (non serializzato), MA esiste **proxy serializzabile** `City.connectedToCapitalStatus: Boolean`
  (`City.kt:158`). Pattern identico al fix `detailedCivResources` di Sessione 35.

### Limite noto (da documentare)

`connectedToCapitalStatus` e' aggiornato a `startTurn` successivo (`CivInfoTransientCache.kt:299-301`),
non immediatamente dopo il `buildroad`. **Il reward arriva 1 turno dopo** il completamento della
strada. Accettato: il delta event-based si applica comunque al primo turno in cui il flag passa
da `False` a `True`.

---

## Implementazione

### `unciv/Unciv/desktop/src/com/unciv/app/desktop/DesktopLauncher.kt`

Aggiungere blocco `else if (trimmed.startsWith("buildroad "))` modellato sull'handler `improve`
(`DesktopLauncher.kt:193-226`). Pseudo-codice:

```kotlin
// buildroad <path> <unitId> → costruisce Road sul tile corrente
// Riusa: ruleset.tileImprovements["Road"], unit.canBuildImprovement(imp, tile),
//        tile.startWorkingOnImprovement(imp, civ, unit)
// Risposte: "improving Road <turns>" | "illegal cannot_build" | "error <msg>"
```

La risposta `improving Road <turns>` riusa **lo stesso prefisso** di `improve`, quindi e' gia'
compatibile con il parser headless esistente (post-Sessione 41). **Ricompilare il JAR.**

### `src/utils/headless.py`

- Nuovo metodo `build_road(save_path, unit_id) -> dict` che invia `buildroad <path> <id>`.
- Factor-out una helper privata `_parse_improving_response(response)` chiamata sia da
  `build_improvement` sia da `build_road`. Stessa shape di ritorno
  (`{"ok": bool, "improvement": str, "turns": int}`).

### `src/envs/unciv_env.py`

- Nuova azione singola `BUILD_ROAD` → action space cresce di **+1** (sopra il valore post-File-23).
- Masking unit step: `True` solo se
  - `unit.name == "Worker"`, AND
  - tile corrente con `roadStatus == None` (richiede campo nuovo del parser).
- Tech-gate "The Wheel": **opzionale lato Python**, puo' essere lasciato al motore che ritorna
  `illegal cannot_build` (consistente con la filosofia di delega del File 23).
- Handler `_apply_build_road(unit)` → chiama `headless.build_road(save, id)`.

### `src/parsers/state_parser.py`

- Nuovi campi `GameState`:
  - `tiles_with_road: set[(x,y)]` da `Tile.roadStatus != None`,
  - `cities_connected_to_capital: int` (count) da `City.connectedToCapitalStatus` per ogni citta'
    del player.
- **`to_observation_vector`**: appendere **3 feature globali** → shape passa da `(61,) → (64,)`:
  - `[61]` `connected_cities_ratio` = citta' non-capitale connesse / totale non-capitali (clip 0..1),
  - `[62]` `roads_built_count` normalizzato `/50.0`,
  - `[63]` `selected_unit_on_road` = `1.0` se Worker selezionato sta su tile con road, `0.0` altrimenti.

### `src/utils/reward.py` + `config/default_config.yaml`

- Nuovo peso `city_connected_to_capital: 4.0`.
- Delta event-based:
  ```python
  reward += weight * max(0, curr.cities_connected_to_capital - prev.cities_connected_to_capital)
  ```
- Commento nel codice: **"il reward arriva al turno SUCCESSIVO al buildroad effettivo, causa
  update transient cache di Unciv"**.

### `src/utils/callbacks.py` (`UncivMetricsCallback`)

- `unciv/roads_built_mean` (delta per-episodio),
- `unciv/cities_connected_mean` (count finale),
- `unciv/road_actions_attempted_mean`, `unciv/road_actions_succeeded_mean`,
- `unciv/action_BUILD_ROAD` in `_ACTION_NAMES`.

---

## Contratti che cambiano

- **Obs vector**: `(61,) → (64,)` (assumendo File 24 implementato isolato sopra obs attuale).
- **Action space**: `Discrete(23 + N) → Discrete(24 + N)` (post File 23, `N` = miglioramenti).
- **Nuovo comando headless**: `buildroad`.

> ⚠️ Aggiornare la **tabella contratti** in `CLAUDE.md` quando si implementa.

---

## Test richiesti

### `tests/test_headless.py`
- `test_build_road_success`
- `test_build_road_illegal_no_worker`
- `test_build_road_illegal_already_present`
- `test_build_road_parsing_response`
- `test_build_road_skips_log_noise`

### `tests/test_env.py`
- `test_action_space_size_after_road`
- `test_build_road_masking_only_worker`
- `test_build_road_masking_off_if_road_present`
- `test_build_road_calls_headless`

### `tests/test_parser.py`
- `test_obs_includes_trade_network_features` (shape `(64,)`)
- `test_tiles_with_road_parsed`

### `tests/test_reward.py`
- `test_reward_city_connected_delta_event_based`
- `test_reward_no_double_count` (delta non si ripaga se `cities_connected_to_capital` invariato)

### Smoke JAR
- Worker su Plains adiacente a due citta' → `buildroad` ripetuto sui tile del percorso →
  advance N turni → save mostra `roadStatus: Road` sui tile attraversati → flag
  `connectedToCapitalStatus = true` sulla seconda citta' dopo `advance`.

---

## Criteri di accettazione

- **132+5 test verdi**.
- **Smoke JAR riuscito** (manuale).
- **Training di validazione su 50k step** con `roads_built_mean > 0` e almeno un episodio con
  `cities_connected_mean > 1`.

---

## Rischi / open questions

- **Sparsita' del segnale**: il delay di 1 turno tra `buildroad` e flag connesso puo' rendere il
  reward troppo raro. Mitigazione: monitorare ratio `roads_built_mean / cities_connected_mean`
  — se molto basso (es. > 50:1), passare a reward `road_built = 0.1` denso come **fallback**.
- **Stato iniziale falso negativo**: `connectedToCapitalStatus` potrebbe essere gia' `False`
  all'inizio per errori di calcolo iniziali della transient cache. Verificare su save di test
  prima di calcolare delta.

---

## Fuori scope (estensioni future)

- **Railroad** (post-medieval, tech `Railroads` non raggiungibile nelle ~150 turn della Fase 2).
- **Pillage road** (richiede combattimento, Fase 3).
- **Trade route diplomatici** tra civ diverse (Fase 4).
