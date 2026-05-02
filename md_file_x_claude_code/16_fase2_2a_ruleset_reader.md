# File 16 — Fase 2.2a: Ruleset Reader

## Obiettivo
Creare `src/utils/ruleset_reader.py` che legge `Buildings.json`, `Units.json`, `Techs.json`
dal JAR di Unciv e restituisce le costruzioni early-game (Ancient + Classical) disponibili per l'agente.

Nessuna modifica all'ambiente o all'action space in questo step — solo il modulo reader + test.

---

## Contesto tecnico
- Il JAR è un archivio ZIP standard — leggibile con `zipfile`
- I JSON usano commenti `//`, `/* */` e trailing commas → non JSON standard (JSONC)
- Path dentro il JAR: `jsons/Civ V - Vanilla/Buildings.json` ecc.
- Era tech disponibili: Ancient, Classical, Medieval, Renaissance, Industrial, Modern, Future
- Target: solo Ancient + Classical

---

## Dataclass output

```python
@dataclass
class ConstructionInfo:
    name: str
    required_tech: Optional[str]   # None = sempre disponibile (no prereq)
    is_unit: bool                   # False = edificio, True = unità
```

---

## API pubblica

```python
def load_early_game_constructions(jar_path: str) -> list[ConstructionInfo]:
    """
    Legge dal JAR e restituisce edifici + unità dell'era Ancient + Classical.
    Esclude wonders, national wonders, civ-unique, acquatici, Great People.
    Ordine: edifici alfabetico, poi unità alfabetico.
    """

def get_ancient_classical_techs(jar_path: str) -> set[str]:
    """
    Restituisce i nomi di tutte le tech Ancient + Classical.
    Usato internamente per filtrare le costruzioni.
    """
```

---

## Filtri — Edifici

**Includi se:**
- `requiredTech` è None oppure è in `ancient_classical_techs`
- Non ha campo `isNationalWonder: true`
- Non ha campo `isWonder: true`
- Nome NON è in lista civ-unique da escludere

**Lista civ-unique da escludere (edifici):**
```
Krepost, Burial Tomb, Mud Pyramid Mosque, Paper Maker,
Floating Gardens, Stone Works, Water Mill, Circus, Longhouse
```
> Motivo: resource-dependent o civ-specifici non disponibili per India.

**Lista attesa edifici risultanti (~9):**
```
Barracks, Colosseum, Courthouse, Granary, Library,
Monument, Stable, Temple, Walls
```

---

## Filtri — Unità

**Includi se:**
- `requiredTech` è None oppure è in `ancient_classical_techs`
- `unitType` in `{"Sword", "Scout", "Civilian"}`
  - Esclude acquatici (`Ranged Water`, `Melee Water`), `Archery`, `Mounted`, `Siege`
  - Nota: Archer (Archery type) escluso per ora — aggiunto in 2.3 con espansione militare
- Nome NON inizia con `"Great "` e NON è in `{"Khan", "SS Booster", "SS Cockpit", "SS Engine", "SS Stasis Chamber"}`
- Nome NON è in lista civ-unique da escludere

**Lista civ-unique da escludere (unità):**
```
Maori Warrior, Jaguar, Brute
```

**Lista attesa unità risultanti (~5):**
```
Settler, Scout, Warrior, Worker, Spearman
```
> Worker incluso nel buildable list (il movimento Worker è Fase 2.3).

---

## Parser JSONC interno

```python
def _load_jsonc(jar: zipfile.ZipFile, path: str) -> list[dict]:
    """Legge file JSONC dal JAR: strip commenti // e /* */, trailing commas."""
    raw = jar.read(path).decode('utf-8')
    raw = re.sub(r'/\*.*?\*/', '', raw, flags=re.DOTALL)
    raw = re.sub(r'//[^\n]*', '', raw)
    raw = re.sub(r',(\s*[}\]])', r'\1', raw)
    return json.loads(raw)
```

---

## File da creare

- `src/utils/ruleset_reader.py` (nuovo)
- `tests/test_ruleset_reader.py` (nuovo)

---

## Test richiesti

```python
test_load_returns_monument()
    # Monument presente, required_tech=None, is_unit=False

test_load_returns_barracks()
    # Barracks presente, required_tech="Bronze Working", is_unit=False

test_no_wonders_included()
    # Stonehenge, Great Library, Colossus NON presenti

test_no_national_wonders()
    # National College, National Epic NON presenti

test_no_civ_unique_buildings()
    # Krepost, Burial Tomb NON presenti

test_no_medieval_buildings()
    # Market (Currency = Medieval) NON presente

test_warrior_is_unit()
    # Warrior presente, is_unit=True, required_tech=None o "Agriculture"

test_no_great_people()
    # "Great Scientist" NON presente

test_no_water_units()
    # Trireme, Galley NON presenti

test_total_count_reasonable()
    # len(constructions) tra 10 e 20
```

---

## Note implementative

- `jar_path` letto da `config["unciv"]["jar_path"]` — non hardcodato
- Il modulo non dipende da `unciv_env.py` né da `state_parser.py`
- Nessuna connessione JVM — solo lettura ZIP
- Import: `zipfile`, `json`, `re`, `dataclasses`, `pathlib`
