# 13 — Diagnostica Training: Come Leggere i Risultati della Fase 1.5

## Obiettivo
Sapere esattamente come interpretare i grafici TensorBoard e decidere
quando il training è abbastanza buono per passare alla Fase 2 (file 08 — headless).

---

## Posizione nella sequenza

```
File 11  → Simulatore Python ✅ (completare prima)
File 12  → Fix race condition ✅ (completare prima)
► File 13 → QUESTO FILE — diagnostica

File 08-10 → Solo dopo che il modello Fase 1.5 è salvato
```

---

## Parametri del run target per Fase 1.5

```yaml
# config/default_config.yaml — valori raccomandati
training:
  total_timesteps: 500_000   # ~30-40 minuti su CPU con simulatore
  n_envs: 4
  n_steps: 1024
  batch_size: 64
  n_epochs: 10
  learning_rate: 0.0003
  ent_coef: 0.01
  max_turns: 150
```

> ⚠️ Il run attuale (Sessione 7, ~16k step, stub JSON) va interrotto e
> rilanciato dopo aver implementato i file 11 e 12.

---

## Tabella di interpretazione TensorBoard

### rollout/

| Metrica | Run stub (attuale) | Target 100k step | Target 500k step |
|---|---|---|---|
| `ep_rew_mean` | ~-1.1 | > 0.0 | > 2.0 |
| `ep_len_mean` | ~50 (truncated) | > 80 | ~150 |
| `ep_rew_max` | ~0 | > 3.0 | > 8.0 |

### unciv/ (custom)

| Metrica | Segnale positivo | Segnale negativo |
|---|---|---|
| `happiness_mean` | Stabile ~9-10 | < 5 → agente non gestisce città |
| `gold_mean` | Cresce lentamente | Flat a 50 → simulatore oro rotto |
| `action_*` | Distribuzione non uniforme | Tutti ~14% → policy non impara |

### train/

| Metrica | Sano | Problema |
|---|---|---|
| `entropy_loss` | Decresce lentamente | Crolla a 0 → aumentare `ent_coef` |
| `value_loss` | Decresce nel tempo | Piatta → value function non impara |
| `approx_kl` | < 0.02 | > 0.05 → ridurre `learning_rate` |

---

## Albero decisionale post-run

```
Dopo 500k step:

ep_rew_mean > 1.0?
    ├── SÌ ──► salva modello, procedi a File 08 (headless)
    │
    └── NO ──► ep_rew_mean completamente flat?
               ├── SÌ ──► simulatore non funziona
               │           python src/utils/diagnose_run.py sim
               │           verifica che gli edifici vengano costruiti
               │
               └── NO ──► reward negativa e in peggioramento?
                           ├── SÌ ──► ent_coef 0.01 → 0.05 e rilancia
                           └── NO ──► aumenta total_timesteps a 1M
```

---

## Script diagnostica: `src/utils/diagnose_run.py`

```python
"""
Diagnostica training — eseguire dopo ogni run o per debug.
Non richiede TensorBoard.

Uso:
    python src/utils/diagnose_run.py        # analizza save file
    python src/utils/diagnose_run.py sim    # simula 30 turni manualmente
"""
import json
import sys
from pathlib import Path


def diagnose_save_file(save_path: str = "saves/current_game_0.json") -> None:
    """Verifica stato del save file e segnala warning."""
    path = Path(save_path)
    if not path.exists():
        print(f"❌ Save file non trovato: {save_path}")
        return

    with open(path) as f:
        raw = json.load(f)

    civ = next(
        (c for c in raw.get("civilizations", []) if c.get("civName") == "India"),
        None
    )
    if not civ:
        print("❌ Civilizzazione India non trovata")
        return

    city = civ.get("cities", [{}])[0]
    constructions = city.get("cityConstructions", {})
    pop = city.get("population", {})
    tech = civ.get("tech", {})

    print(f"\n{'='*50}")
    print(f"Turno:              {raw.get('turns', 0)}")
    print(f"Oro:                {civ.get('gold', 0):.1f}")
    print(f"Happiness:          {civ.get('happiness', 0):.1f}")
    print(f"Popolazione:        {pop.get('population', 1)}")
    print(f"Cibo accumulato:    {pop.get('storedFood', 0)}")
    print(f"Produzione acc.:    {constructions.get('productionAccumulated', 0)}")
    print(f"Scienza acc.:       {tech.get('scienceAccumulated', 0)}")
    print(f"Edifici:            {constructions.get('builtBuildings', [])}")
    print(f"Tech:               {tech.get('techsResearched', [])}")
    print(f"{'='*50}")

    turn = raw.get("turns", 0)
    built = constructions.get("builtBuildings", [])
    techs = tech.get("techsResearched", [])

    if turn > 10 and len(built) == 0:
        print("⚠️  Nessun edificio dopo 10+ turni — simulatore produzione rotto?")
    if turn > 20 and len(techs) <= 1:
        print("⚠️  Nessuna tech nuova dopo 20+ turni — simulatore scienza rotto?")
    if civ.get("happiness", 0) < 0:
        print("⚠️  Happiness negativa — episodio terminato prematuramente")
    if civ.get("gold", 0) == 50.0 and turn > 5:
        print("⚠️  Oro invariato a 50 — simulatore oro non funziona")

    print("✅ Diagnostica completata")


def simulate_30_turns() -> None:
    """Simula manualmente 30 turni e stampa l'evoluzione."""
    from src.utils.simulator import UncivSimulator

    sim = UncivSimulator()
    raw = {
        "turns": 0,
        "civilizations": [{
            "civName": "India",
            "gold": 50.0, "happiness": 9.0,
            "cities": [{
                "name": "Delhi",
                "population": {"population": 1, "storedFood": 0},
                "cityConstructions": {
                    "currentConstruction": "Monument",
                    "builtBuildings": [],
                    "productionAccumulated": 0,
                },
                "health": 200, "tiles": [],
            }],
            "tech": {
                "techsResearched": ["Agriculture"],
                "currentTechnology": "Pottery",
                "scienceAccumulated": 0,
            }
        }]
    }

    print(f"\n{'Turn':>5} | {'Gold':>6} | {'Happy':>6} | {'Pop':>4} | {'Built':<25} | Techs")
    print("-" * 80)
    for _ in range(30):
        sim.advance_turn(raw)
        civ = raw["civilizations"][0]
        city = civ["cities"][0]
        print(
            f"{raw['turns']:>5} | "
            f"{civ['gold']:>6.1f} | "
            f"{civ['happiness']:>6.1f} | "
            f"{city['population']['population']:>4} | "
            f"{str(city['cityConstructions']['builtBuildings']):<25} | "
            f"{civ['tech']['techsResearched']}"
        )


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "sim":
        simulate_30_turns()
    else:
        diagnose_save_file()
```

### Aggiungere in `COMMANDS.md`

```powershell
# Diagnostica save file
.venv\Scripts\python src/utils/diagnose_run.py

# Simulazione manuale 30 turni (verifica simulatore)
.venv\Scripts\python src/utils/diagnose_run.py sim
```

---

## Condizioni per procedere a File 08 (headless)

```
✅ ep_rew_mean > 1.0  (media ultime 100 ep)
✅ ep_len_mean > 100  (agente sopravvive quasi tutto l'episodio)
✅ distribuzione azioni non uniforme
✅ happiness_mean > 7
✅ almeno 1 edificio completato per episodio in media
```

Quando raggiunte:

```powershell
Copy-Item "models\checkpoints\best\best_model.zip"
          "models\checkpoints\fase1_5_final.zip"
git add -A
git commit -m "feat: training Fase 1.5 completato"
git push
```

Poi aprire il file `08_headless_integration.md` per la Fase 2.

---

## Note per Claude Code
- `diagnose_run.py` va creato in `src/utils/` se non esiste
- I target numerici sono euristici — il trend positivo conta più del valore assoluto
- Se dopo 1M step il modello non converge, documentare nel WORK_LOG e discutere
  prima di procedere con il file 08
