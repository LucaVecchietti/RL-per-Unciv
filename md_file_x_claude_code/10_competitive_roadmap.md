# 10 — Roadmap verso agente competitivo

## Obiettivo finale

Agente PPO in grado di giocare partite competitive di Unciv contro giocatori umani,
via interfaccia HTTP multiplayer.

Questo file descrive tutte le fasi successive a File 09, dalla gestione unità
alla partita multiplayer reale.

---

## Overview fasi

```
File 08 — Fork Unciv + CLI headless           (prerequisito tecnico)
File 09 — Real obs (48,)                      (prerequisito competitivo)
File 10a — Fase 2.1: unità + movimento        ← questo documento
File 10b — Fase 2.2: multi-città + settler
File 10c — Fase 3: combattimento
File 10d — Fase 4: self-play + curricolo
File 10e — Play mode: HTTP server per umani
```

---

## FASE 2.1 — Unità e Movimento

### Obiettivo
Agente costruisce Warrior (build-first), lo muove per esplorare mappa.
Base per qualsiasi meccanica che richiede movimento unità.

### Action space: `Discrete(11)`
```python
ACTION_MAP = {
    # Costruzione città (invariati)
    0: "Monument", 1: "Granary", 2: "Library", 3: "Barracks",
    4: "Settler",  5: "Warrior", 6: None,  # END_TURN/skip

    # Movimento unità selezionata
    7: "MOVE_NORTH",
    8: "MOVE_SOUTH",
    9: "MOVE_EAST",
    10: "MOVE_WEST",
}
```

### Observation: `(52,)` = `(48,)` + 4 campi unità selezionata
```
[48] selected_unit_x / map_width   ← unità corrente in rotation
[49] selected_unit_y / map_height
[50] selected_unit_movement / max_movement  ← MP rimasti (0→1)
[51] tiles_explored / total_tiles
```

### Per-entity rotation
Ogni game turn = N step Python (uno per entità da decidere):
```
Step 1: city decision  → azioni [0-6] valide
Step 2: warrior_0      → azioni [6-10] valide (skip o direzione)
Step 3: warrior_1      → azioni [6-10] valide
...
Tutti decisi → Unciv headless avanza turno
```

### MaskablePPO
```python
from sb3_contrib import MaskablePPO
# requirements.txt: sb3-contrib>=2.0.0
```

`action_masks()` in `unciv_env.py`:
```python
def action_masks(self) -> np.ndarray:
    mask = np.zeros(11, dtype=bool)
    if self._step_type == "city":
        mask[0:7] = True
    elif self._step_type == "unit":
        mask[6] = True    # skip
        mask[7:11] = True # movimento
    return mask
```

### Reward aggiuntiva
```python
"exploration": 0.3   # per tile nuova esplorata
```

### Criterio successo Fase 2.1
- Agente costruisce ≥1 Warrior entro turno 50
- Esplora >30% mappa entro fine episodio
- `ep_rew_mean > 5.0`

---

## FASE 2.2 — Multi-città e Settler

### Obiettivo
Agente fonda seconda città (costruisce Settler → lo muove → fonda).
Impara gestione happiness multi-città.

### Nuove azioni
```python
11: "FOUND_CITY",   # Settler sulla tile corrente → fonda città
```
Action space: `Discrete(12)`

### Observation: `(52,)` → `(60,)` (aggiunge seconda città)
Seconda città già prevista in File 09 — aggiungere solo `has_settler` flag
e logica fondazione.

### Logica fondazione nel fork Unciv
Il fork deve supportare:
```
java -jar Unciv.jar --found-city --unit-id <id> --save-file <path>
```
Oppure: scrivere nel JSON la azione "FoundCity" e lasciare che `nextTurn()` la processi.

### Reward
```python
"new_city": 5.0   # fondare città vale molto
"city_growth": 1.0  # pop crescita in qualsiasi città
```

### Criterio successo Fase 2.2
- Agente fonda città #2 entro turno 80
- Entrambe le città positive happiness
- `ep_rew_mean > 10.0`

---

## FASE 3 — Combattimento

### Obiettivo
Agente impara a difendere città e attaccare unità nemiche.
Prerequisito: Fase 2.2 stabile.

**Prima della fase 3:** aggiungere AI avversari nel template di gioco.
Attualmente il template ha 0 avversari — aggiungerne 1 (difficoltà: Chieftain).

### Nuove azioni
```python
12: "ATTACK_UNIT",    # attacca unità nemica adiacente
13: "FORTIFY",        # Warrior si fortifica (+strength bonus)
```
Action space: `Discrete(14)`

### Observation: aggiunge info nemici
```
[60] n_enemy_units_visible / 10
[61] nearest_enemy_x / map_width
[62] nearest_enemy_y / map_height
[63] nearest_enemy_health / 100
[64] nearest_enemy_strength / 50
```
Shape: `(65,)`

### Reward combattimento
```python
"kill_unit": 3.0           # uccidi unità nemica
"defend_city": 2.0         # respingi attacco a città
"city_captured_penalty": -10.0  # avversario conquista tua città
```

### Curriculum combattimento
1. Prima: impara a non perdere città (difesa)
2. Poi: impara ad attaccare quando conveniente
3. Self-play contro versione precedente (vedi Fase 4)

---

## FASE 4 — Self-play e Curricolo

### Obiettivo
Training contro versioni precedenti dell'agente per emergere strategie reali.

### Self-play setup
```python
# Ogni episodio: agente corrente vs copia frozen della versione precedente
# Periodicamente: aggiorna "opponent" con versione corrente

class SelfPlayEnv(UncivEnv):
    def __init__(self, opponent_model_path: str, ...):
        self.opponent = PPO.load(opponent_model_path)

    def _opponent_act(self, obs):
        action, _ = self.opponent.predict(obs, deterministic=True)
        return action
```

### League training (opzionale, avanzato)
- Pool di modelli con rating ELO
- Agente gioca contro avversari di rating simile
- Evolutivo: ogni N step aggiorna pool

### Reward shaping per vittoria reale
Obiettivo science victory (primo a completare albero tech):
```python
"tech_victory": 50.0  # vince la partita
"tech_lead": 0.5 * (my_techs - opponent_techs) / 80  # vantaggio tecnico
```

---

## FASE PLAY — HTTP Server per partite umane

### Obiettivo
Agente gioca in partite Unciv multiplayer reali contro umani.

### Architettura
```
Unciv client (umano) ←→ Unciv server (multiplayer) ←→ Python HTTP agent
```

Quando è il turno dell'AI:
1. Unciv carica il save file dell'AI
2. Invia POST a `http://localhost:8765/action` con obs JSON
3. Python agent risponde con `{"action": 5}` (costruisci Warrior, ecc.)
4. Unciv esegue l'azione e avanza turno

### Python HTTP server
```python
from flask import Flask, request, jsonify
app = Flask(__name__)
model = MaskablePPO.load("models/checkpoints/best/best_model.zip")

@app.route("/action", methods=["POST"])
def get_action():
    data = request.json
    obs = np.array(data["observation"], dtype=np.float32)
    masks = np.array(data["action_masks"], dtype=bool)
    action, _ = model.predict(obs, action_masks=masks, deterministic=True)
    return jsonify({"action": int(action)})

app.run(port=8765)
```

### Modifiche Unciv fork (aggiuntive)
Il fork deve anche supportare la modalità HTTP client:
- Quando una civ è configurata come "AI_HTTP", Unciv invia obs al server Python
- Riceve azione, la esegue

Questa è la modifica più grossa al fork — pianificare quando Fase 3 è stabile.

---

## Migration guide per ogni fase

Per ogni fase, seguire questo ordine:
```
1. Backup model corrente: cp best_model.zip fase_X_final.zip
2. Aggiorna CLAUDE.md contratti (obs shape, n azioni)
3. Aggiorna state_parser.py
4. Aggiorna test_parser.py
5. pytest tests/test_parser.py -v  ← verde
6. Aggiorna unciv_env.py
7. Aggiorna test_env.py
8. pytest tests/test_env.py -v    ← verde
9. Aggiorna reward.py
10. pytest tests/ -v              ← tutti verdi
11. python train.py
12. Aggiorna WORK_LOG.md
13. git commit
```

---

## Summary obs/action space per fase

| Fase | Obs shape | Actions | PPO |
|---|---|---|---|
| 1.5 (attuale) | `(7,)` | `Discrete(7)` | PPO |
| 2.0 | `(48,)` | `Discrete(7)` | PPO |
| 2.1 | `(52,)` | `Discrete(11)` | MaskablePPO |
| 2.2 | `(60,)` | `Discrete(12)` | MaskablePPO |
| 3.0 | `(65,)` | `Discrete(14)` | MaskablePPO |
| 4.0+ | `(65+,)` | `Discrete(14+)` | MaskablePPO + self-play |

---

## Note per Claude Code

- Implementare una fase per volta — mai saltare avanti
- Ogni fase inizia con "backup model" e finisce con "tutti i test verdi + commit"
- Se una fase fa regredire `ep_rew_mean`, tornare alla fase precedente e diagnosticare
- Transfer learning: per ogni fase, caricare modello fase precedente come punto di partenza
  (obs space diverso = non direttamente compatibile, ma architettura rete può essere riciclata)
- Self-play (Fase 4): non implementare prima che Fase 3 sia stabile
- HTTP server (Fase Play): non implementare prima di aver validato Fase 4 vs AI Unciv
