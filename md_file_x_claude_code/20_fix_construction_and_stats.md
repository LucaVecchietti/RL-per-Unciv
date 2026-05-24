# File 20 — Fase A: Fix costruzione + decodifica statsHistory

## Obiettivo

Sbloccare l'apprendimento mono-città, oggi di fatto rotto: l'agente sceglie cosa
costruire ma **non costruisce mai nulla**, e diversi campi `GameState` derivati da
`statsHistory` sono mappati alla statistica sbagliata.

Queste sono correzioni piccole e mirate, da fare **prima** del rework movimento
(File 21), perché senza di esse la reward su edifici è cieca e parte dell'obs è errata.

**Prerequisiti:** nessuno. Non cambia obs shape `(57,)` né action space `(19)`.

---

## Diagnosi (verificata su sorgente Kotlin + save reali)

### Bug 1 — `_apply_action` scrive un campo inesistente
`unciv_env.py::_apply_action` scrive:
```python
civ["cities"][0]["cityConstructions"]["currentConstruction"] = name
```
Ma `CityConstructions.kt` non ha alcun campo `currentConstruction`:
- `currentConstructionName() = if (constructionQueue.isEmpty()) "" else constructionQueue.first()` (linea 74) → la costruzione corrente è **`constructionQueue[0]`**.
- la produzione si accumula in `inProgressConstructions: HashMap<String,Int>` (linea 83).

Conseguenza (confermata sui save): a turn 63 `builtBuildings` è ancora solo `['Palace']`,
`constructionQueue: None`, produzione persa in `productionOverflow`. L'unico Worker mai
prodotto è quello pre-accodato nel `template_game.json`.

### Bug 2 — `statsHistory` decodificato con lettere sbagliate
`statsHistory` è `CivRankingHistory` (punteggi di classifica, **non** rese per turno).
Mappa reale delle lettere (da `RankingType.kt`, campo `idForSerialization`):

| Lettera | RankingType | Significato |
|---|---|---|
| S | Score | punteggio totale |
| N | Population | popolazione |
| C | Growth | **cibo/turno** (`statsForNextTurn.food`) |
| P | Production | **produzione/turno** |
| G | Gold | oro **totale** |
| T | Territory | n. tile |
| F | Force | potenza militare |
| H | Happiness | felicità |
| W | Technologies | n. tech ricercate |
| A | Culture | n. policy adottate |

Errori attuali nel parser:
- `culture_per_turn = stats['C']/10` → `C` è il **cibo/turno**, non la cultura. Doppio errore.
- `gold_per_turn = stats['N']/10` → `N` è la **popolazione**, non oro/turno.
- `happiness = stats['H']` → corretto (fortunatamente).
- `science_per_turn` → già corretto nel File 19 (legge `scienceOfLast8Turns[-1]`).
- `production_per_turn` / `food_per_turn` → hardcoded `0.0`, ma disponibili in `P` e `C`.

---

## A1 — Fix `_apply_action` (`src/envs/unciv_env.py`)

Sostituire la scrittura di `currentConstruction` con la coda reale:
```python
cc = civ["cities"][0]["cityConstructions"]
cc["constructionQueue"] = [name]
cc.setdefault("inProgressConstructions", {})   # non perdere produzione accumulata
cc["currentConstructionIsUserSet"] = True       # impedisce override dell'AI
cc.pop("currentConstruction", None)             # rimuovi campo legacy se presente
```
Mantenere il guard esistente (no-op per skip e `MOVE_*`).

---

## A2 — Fix decodifica statsHistory (`src/parsers/state_parser.py`)

Aggiungere una costante esplicita di mappatura (documenta l'intento):
```python
# statsHistory = CivRankingHistory (RankingType.idForSerialization)
_STATS_LETTERS = {
    'S': 'score', 'N': 'population', 'C': 'food_per_turn', 'P': 'production_per_turn',
    'G': 'gold_total', 'T': 'territory', 'F': 'force', 'H': 'happiness',
    'W': 'n_techs', 'A': 'n_policies',
}
```

In `_extract_game_state()`:
- `happiness = float(stats.get('H', 8))` — invariato (corretto).
- **`gold_per_turn`**: NON usare `N`. Calcolare a runtime come ΔG tra turni (in `unciv_env`, come già si fa per `_ep_total_gold`) oppure lasciare `0.0`. Rimuovere `stats['N']/10`.
- **`culture_per_turn`**: NON usare `C`. Sorgente reale = delta di `policies.storedCulture` tra turni (calcolato in `unciv_env`); in parser default `0.0`. Rimuovere `stats['C']/10`.
- **`production_per_turn`** (City): popolare da `P` (statsHistory) — è produzione/turno della civ; per ora assegnabile alla città principale come stima.
- **`food_per_turn`** (City): popolare da `C` (Growth = cibo/turno).

> Nota: `statsHistory` è a livello civ, non città. Per Fase A va bene assegnare `P`/`C`
> alla città principale come stima (mono-città). Con multi-città servirà una fonte per-città.

`_parse_culture_per_turn()` (File 19): cambiare sorgente a `policies.storedCulture` delta,
oppure rimuoverlo e gestire la cultura/turno come delta in `unciv_env` (coerente con gold).
Decidere in fase di implementazione; in entrambi i casi **non** leggere più `C` come cultura.

---

## File da modificare

- `src/envs/unciv_env.py` (A1: `_apply_action`; A2: eventuale calcolo delta gold/cultura)
- `src/parsers/state_parser.py` (A2: mappa statsHistory, fix culture/gold/production/food)
- `tests/test_env.py` (test `_apply_action` scrive `constructionQueue`)
- `tests/test_parser.py` (test decodifica statsHistory corretta)

---

## Test richiesti

```python
# test_env.py
test_apply_action_sets_construction_queue()
    # _apply_action(Granary) → cc["constructionQueue"] == ["Granary"],
    # currentConstructionIsUserSet True, niente chiave "currentConstruction"

# test_parser.py
test_statshistory_happiness_from_H()        # H6 → happiness 6
test_statshistory_food_per_turn_from_C()    # C4 → food_per_turn 4 (non cultura)
test_statshistory_production_from_P()        # P7 → production_per_turn 7
test_culture_per_turn_not_from_C()           # C grande NON deve gonfiare culture_per_turn
test_gold_per_turn_not_from_population()     # N grande NON deve diventare gold_per_turn
```

---

## Validazione (criterio di chiusura Fase A)

Run breve (~30k step) e verificare in TensorBoard:
- `built_*_mean > 0` per almeno Monument/Granary (l'agente ora costruisce davvero)
- `trained_*_mean > 1` (unità prodotte oltre il Worker iniziale)
- `food_per_turn`/`production_per_turn` nell'obs non più costanti a 0

---

## Note implementative

- La produzione **viene** processata dal motore per il player civ (overflow cresce, Worker
  iniziale completato): NON serve accumularla a mano come per la scienza. Basta la coda corretta.
- Non toccare `_advance_tech`: legge/scrive campi corretti (`techsResearched`,
  `techsInProgress`, `scienceOfLast8Turns`).
- Nessuna modifica a obs shape o action space → checkpoint compatibili (ma conviene comunque
  ripartire da zero perché il comportamento appreso finora è su un ambiente "rotto").
