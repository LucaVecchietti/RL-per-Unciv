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

# Aggiunge root progetto a sys.path per import src.* quando eseguito come script
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


def diagnose_save_file(save_path: str = "saves/current_game_0.json") -> None:
    """Verifica stato del save file e segnala warning."""
    path = Path(save_path)
    if not path.exists():
        print(f"ERRORE: Save file non trovato: {save_path}")
        return

    with open(path) as f:
        raw = json.load(f)

    civ = next(
        (c for c in raw.get("civilizations", []) if c.get("civName") == "India"),
        None,
    )
    if not civ:
        print("ERRORE: Civilizzazione India non trovata")
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

    warnings = []
    if turn > 10 and len(built) == 0:
        warnings.append("Nessun edificio dopo 10+ turni — simulatore produzione rotto?")
    if turn > 20 and len(techs) <= 1:
        warnings.append("Nessuna tech nuova dopo 20+ turni — simulatore scienza rotto?")
    if civ.get("happiness", 0) < 0:
        warnings.append("Happiness negativa — episodio terminato prematuramente")
    if civ.get("gold", 0) == 50.0 and turn > 5:
        warnings.append("Oro invariato a 50 — simulatore oro non funziona")

    for w in warnings:
        print(f"ATTENZIONE: {w}")

    if not warnings:
        print("OK: Diagnostica completata senza anomalie")


def simulate_30_turns() -> None:
    """Simula manualmente 30 turni e stampa l'evoluzione."""
    from src.utils.simulator import UncivSimulator

    sim = UncivSimulator()
    raw = {
        "turns": 0,
        "civilizations": [{
            "civName": "India",
            "gold": 50.0,
            "happiness": 9.0,
            "cities": [{
                "name": "Delhi",
                "population": {"population": 1, "storedFood": 0},
                "cityConstructions": {
                    "currentConstruction": "Monument",
                    "builtBuildings": [],
                    "productionAccumulated": 0,
                },
                "health": 200,
                "tiles": [],
            }],
            "tech": {
                "techsResearched": ["Agriculture"],
                "currentTechnology": "Pottery",
                "scienceAccumulated": 0,
            },
        }],
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
