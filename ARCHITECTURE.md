# ARCHITECTURE.md — Schema di funzionamento

## Visione d'insieme

```
┌─────────────────────────────────────────────────────────────────────┐
│                         TRAINING LOOP                               │
│                                                                     │
│   ┌──────────────┐  azione (0-10)  ┌──────────────────┐            │
│   │ MaskablePPO  │ ──────────────► │   UncivEnv       │            │
│   │  (sb3-contrib│                 │   (Gymnasium)    │            │
│   │  ActionMasker│ ◄────────────── └────────┬─────────┘            │
│   └──────────────┘  obs(52,)+masks          │ legge/scrive         │
│                                   ┌─────────▼──────────┐           │
│                                   │  saves/             │           │
│                                   │  current_game_N.json│           │
│                                   └─────────┬──────────┘           │
│                                             │ stdin/stdout         │
│                                   ┌─────────▼──────────┐           │
│                                   │  Unciv fork JAR    │           │
│                                   │  (--server mode)   │           │
│                                   │  1 JVM per env     │           │
│                                   └────────────────────┘           │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Flusso dettagliato — un game turn (Fase 2.1)

Un game turn Unciv = N step Python (per-entity rotation):

```
MaskablePPO sceglie azione con action_masks()
         │
         ▼
UncivEnv.step(action)
         │
         ├─ [CITY STEP] _step_type == "city"
         │       │
         │       ├─► _apply_action(action)      ← azioni 0-6 costruzione
         │       │       └─► scrive costruzione in JSON
         │       │
         │       ├─► cerca warriors con movement_points > 0
         │       │
         │       ├─► se warriors trovati:
         │       │       _step_type = "unit"
         │       │       return (obs, reward=0, False, False, info)
         │       │       ← NO advance_turn ancora
         │       │
         │       └─► se nessun warrior: → _advance_game_turn()
         │
         ├─ [UNIT STEP] _step_type == "unit"
         │       │
         │       ├─► _apply_movement(action, unit)  ← azioni 6 skip, 7-10 movimento
         │       │       └─► sposta warrior nel JSON (tile swap)
         │       │
         │       ├─► unit_rotation_index += 1
         │       │
         │       ├─► se altri warriors da muovere:
         │       │       return (obs, reward=0, False, False, info)
         │       │
         │       └─► tutti decisi: _step_type = "city" → _advance_game_turn()
         │
         └─ _advance_game_turn()
                 │
                 ├─► _advance_turn()
                 │       └─► UncivHeadless.advance_turn(save_path)
                 │               └─► stdin: "advance <path>\n" → JVM server
                 │                   stdout: "ok <turn>\n"      ← (1 JVM per env)
                 │                   ~50ms/turno (vs ~5s spawn)
                 │
                 ├─► parser.parse(save_path)
                 │       └─► UncivStateParser
                 │               ├─► load() — plain JSON o gzip
                 │               ├─► _find_player_civ() — cerca "India"
                 │               ├─► _extract_game_state()
                 │               │       ├─► turn, gold, happiness
                 │               │       ├─► statsHistory → science, culture, gold/turn
                 │               │       ├─► techsInProgress → current_tech, progress
                 │               │       ├─► tileList → units, tiles_explored
                 │               │       ├─► proximity → n_known_civs
                 │               │       └─► diplomacy → at_war
                 │               └─► _parse_city() per ogni città
                 │                       ├─► population, foodStored
                 │                       ├─► constructionQueue[0]
                 │                       ├─► inProgressConstructions
                 │                       └─► builtBuildings, workedTiles, location
                 │
                 ├─► parser.to_observation_vector(state, selected_unit)
                 │       └─► vettore numpy (52,) float32:
                 │             [0-5]   Globale: turn, gold, happiness, sci/t, cult/t, n_cities
                 │             [6-21]  Città 1: pop, food_prog, prod_prog, gold/t, food/t,
                 │                              prod/t, n_buildings, has_monument..has_market,
                 │                              tiles_worked, x, y
                 │             [22-29] Tech: n_techs, tech_progress, has_agri..has_bronze
                 │             [30-37] Unità: n_warriors, n_settlers, n_other,
                 │                            warrior_xy, settler_xy, tiles_explored
                 │             [38-45] Città 2 (zeros se assente)
                 │             [46-47] Diplomazia: n_known_civs, at_war
                 │             [48-51] Unità selezionata: sel_x, sel_y, sel_movement,
                 │                                         tiles_explored_ratio
                 │
                 ├─► compute_reward(prev_state, curr_state, city_action)
                 │       ├─► +pop_delta * 2.0
                 │       ├─► +new_buildings * 1.5
                 │       ├─► +new_techs * 3.0
                 │       ├─► +clip(gold_delta/100, ±0.5)
                 │       ├─► happiness < 0 → happiness * 0.1
                 │       ├─► city_action == 6 → -0.05
                 │       └─► +explored_delta * 0.3   ← Fase 2.1
                 │
                 ├─► _is_terminated() — happiness < -10
                 │
                 ├─► se terminated → compute_terminal_reward()
                 │
                 └─► return (obs, reward, terminated, truncated, info)
```

---

## Spazi Gymnasium (Fase 2.1)

```
observation_space = Box(low=0.0, high=1.0, shape=(52,), dtype=float32)
action_space      = Discrete(11)

ACTION_MAP = {
    0: "Monument",    1: "Granary",      2: "Library",   3: "Barracks",
    4: "Settler",     5: "Warrior",      6: None,        # skip/EndTurn
    7: "MOVE_NORTH",  8: "MOVE_SOUTH",   9: "MOVE_EAST", 10: "MOVE_WEST",
}

action_masks():
    city step → [True]*7 + [False]*4    # solo costruzione valida
    unit step → [False]*6 + [True]*5    # solo skip+movimento validi
```

---

## Componenti e responsabilità

### `src/parsers/state_parser.py`

| Classe/Funzione | Input | Output | Responsabilità |
|---|---|---|---|
| `UncivStateParser.load()` | path | dict raw | Legge JSON (plain o gzip) |
| `UncivStateParser.parse()` | path | `GameState` | Entry point: file → struttura dati |
| `UncivStateParser.to_observation_vector()` | `GameState`, `UnitState?` | `np.ndarray (52,)` | Stato → input MaskablePPO |
| `_find_player_civ()` | dict raw | dict civ | Filtra civ "India" |
| `_parse_city()` | dict city | `CityState` | Estrae dati singola città |
| `_parse_units()` | tileList | `list[UnitState]` | Estrae unità player da tileList |
| `_parse_stats_history()` | dict civ | dict | Parsa statsHistory compressa |

**Contratto:** output sempre `shape=(52,)`, `dtype=float32`.

---

### `src/envs/unciv_env.py`

| Metodo | Chiamato da | Cosa fa |
|---|---|---|
| `reset()` | SB3 inizio episodio | Init rotazione, copia template, legge stato |
| `step(action)` | SB3 ogni step | Per-entity rotation: city/unit, advance turn |
| `action_masks()` | MaskablePPO | Restituisce maschera 11 bool (city vs unit step) |
| `_apply_action()` | `step()` city | Scrive costruzione nel JSON (azioni 0-5) |
| `_apply_movement()` | `step()` unit | Sposta warrior nel JSON (tile swap) |
| `_advance_game_turn()` | `step()` | Advance turn + parse + reward + return |
| `_advance_turn()` | `_advance_game_turn()` | Invia comando al server JVM persistente |
| `_get_obs()` | `step()`, `reset()` | obs con selected_unit se in unit step |
| `_compute_reward()` | `_advance_game_turn()` | Delega a `src/utils/reward.py` |
| `_is_terminated()` | `_advance_game_turn()` | `happiness < -10` |

**Per-entity rotation state:**
```python
_step_type: str           # "city" | "unit"
_unit_rotation_index: int # indice warrior corrente
_pending_warriors: list   # warriors da muovere questo turno
_buffered_city_action: int # azione città bufferizzata per reward
```

---

### `src/utils/reward.py`

```
compute_reward(prev, curr, action, weights) → float
    │
    ├─ prev is None → return 0.0
    ├─ popolazione aumentata  → +2.0 per cittadino
    ├─ edificio completato    → +1.5 per edificio
    ├─ tecnologia scoperta    → +3.0 per tech
    ├─ oro accumulato         → clip(delta/100, -0.5, +0.5)
    ├─ happiness < 0          → happiness * 0.1 (negativo)
    ├─ action == 6 (idle)     → -0.05
    └─ tile nuova esplorata   → explored_delta * 0.3   ← Fase 2.1

compute_terminal_reward(state, max_turns) → float
    ├─ happiness >= 0 → +1.0
    ├─ happiness < 0  → -1.0
    ├─ +techs_count * 0.1
    └─ +total_population * 0.05
```

---

### `src/utils/headless.py`

**Architettura: persistent JVM server** (Fase 2.2+)

Un processo JVM per `UncivHeadless` instance (= uno per env_rank). Il JVM parte una
sola volta al primo `advance_turn()` e rimane vivo per tutto l'episodio.

**Protocollo stdin/stdout:**
```
Python → JVM:  "advance <path>\n"  |  "quit\n"
JVM → Python:  "READY\n" (startup) |  "ok <turn>\n"  |  "error <msg>\n"
```

| Metodo | Cosa fa |
|---|---|
| `advance_turn(save_path)` | Invia `advance <path>` al server JVM, attende `ok N` |
| `start_new_game(template, save_path)` | Copia template in save_path |
| `is_available()` | Verifica JAR e java raggiungibili |
| `close()` | Invia `quit`, attende terminazione JVM |
| `_ensure_running()` | Avvia il processo se non in vita (Popen `--server`) |
| `_readline_timeout(stream, t)` | Legge riga da stream con timeout (thread daemon) |

**Costo per turno:** ~50ms (vs ~5s prima — JVM avviato una sola volta)

**Config necessaria:**
```yaml
unciv:
  jar_path: "unciv/Unciv.jar"
  java_path: "C:/Program Files/Eclipse Adoptium/jdk-25.0.3.9-hotspot/bin/java.exe"
  headless_timeout: 60
```

---

### `src/utils/simulator.py`

Micro-simulatore Python usato per sviluppo/test veloci (Fase 1.5).
Non usato in training Fase 2.0+. Mantiene formule Unciv per riferimento:

```
produzione/turno  = 3 + max(0, population - 1)
food_threshold    = 10 + population * 3
scienza/turno     = 2 + (2 se Library) + int(population * 0.5)
happiness         = 9.0 + (1.0 se Monument) - max(0, (pop-1) * 0.5)
```

---

### `src/utils/diagnose_run.py`

```
diagnose_save_file(save_path)
    └─► legge save file, stampa stato, warning automatici

simulate_30_turns()
    └─► UncivSimulator — verifica formule senza headless
```

---

### `src/utils/callbacks.py`

```
UncivMetricsCallback
    _on_rollout_end() → TensorBoard:
        unciv/gold_mean, unciv/happiness_mean,
        unciv/cities_mean, unciv/turns_mean

ActionDistributionCallback
    ogni 10k step → TensorBoard:
        unciv/action_Monument ... unciv/action_MOVE_WEST  (11 azioni)
```

---

### `train.py`

```
load_config(yaml) → dict

DummyVecEnv([make_env(rank=i) for i in range(n_envs)])
    └─► per ogni env:
        UncivEnv(rank=i)
        ActionMasker(env, lambda e: e.action_masks())  ← espone masks a MaskablePPO
        Monitor(masked_env)
    eval env usa rank=n_envs

MaskablePPO(
    policy="MlpPolicy",
    env=env,
    learning_rate=3e-4,
    n_steps=1024,
    batch_size=64,
    n_epochs=10,
    gamma=0.99,
    clip_range=0.2,
    ent_coef=0.01,
)

CallbackList([
    CheckpointCallback,       # salva ogni 10k step → unciv_mppo_*.zip
    MaskableEvalCallback,     # valuta ogni 50k step con masks
    UncivMetricsCallback,     # metriche Unciv custom
    ActionDistributionCallback,
])

model.learn(total_timesteps=500_000)
    └─► salva fase2_1_final_model.zip
```

---

## Ciclo completo training

```
train.py avvia
    │
    ▼
4 ambienti paralleli DummyVecEnv (n_envs=4)
    │
    ▼
ogni ambiente: reset() → copia template → legge stato
    │
    ▼
MaskablePPO raccoglie 1024 step per ambiente = 4096 step totali
    azione campionata con action_masks() (no azioni illegali)
    │
    ▼
calcola vantaggio (GAE) e aggiorna policy (10 epochs)
    │
    ▼
ogni 10.000 step → CheckpointCallback → unciv_mppo_N_steps.zip
ogni 50.000 step → MaskableEvalCallback → best_model.zip
ogni rollout     → UncivMetricsCallback → metriche TensorBoard
    │
    ▼
ripeti fino a 500.000 step totali
    │
    ▼
salva fase2_1_final_model.zip
```

---

## Metriche TensorBoard

| Metrica | Sana | Problema |
|---|---|---|
| `rollout/ep_rew_mean` | cresce verso 5.0 | piatta → reward mal progettata |
| `train/entropy_loss` | non scende a 0 | → 0 = policy collassata |
| `train/approx_kl` | < 0.02 | > 0.05 = learning rate troppo alto |
| `train/clip_fraction` | < 0.2 | > 0.3 = aggiornamenti troppo grandi |
| `unciv/action_Warrior` | sale entro 100k | 0 → agente non costruisce |
| `unciv/action_MOVE_*` | sale entro 50k | 0 → masking non funziona |
| `unciv/action_Monument` | sale | base costruzione |

---

## Dipendenze tra moduli

```
train.py
    ├── sb3_contrib.MaskablePPO
    ├── sb3_contrib.common.wrappers.ActionMasker
    ├── sb3_contrib.common.maskable.callbacks.MaskableEvalCallback
    ├── src/envs/unciv_env.py
    │       ├── src/parsers/state_parser.py
    │       ├── src/utils/reward.py
    │       └── src/utils/headless.py
    └── src/utils/callbacks.py

evaluate.py
    ├── sb3_contrib.MaskablePPO
    └── src/envs/unciv_env.py

src/utils/diagnose_run.py
    └── src/utils/simulator.py

config/default_config.yaml
    └── letto da: train.py, unciv_env.py
```

---

## File su disco durante il training

```
saves/
    template_game.json          ← read-only, mai modificato
    current_game_0.json         ← Env rank 0 (training)
    current_game_1.json         ← Env rank 1 (training)
    current_game_2.json         ← Env rank 2 (training)
    current_game_3.json         ← Env rank 3 (training)
    current_game_4.json         ← Eval env (rank=n_envs)

models/checkpoints/
    unciv_mppo_10000_steps.zip  ← checkpoint automatici
    unciv_mppo_20000_steps.zip
    ...
    fase2_1_final_model.zip
    best/
        best_model.zip

logs/
    MaskablePPO_1/
        events.out.tfevents.*   ← TensorBoard
        evaluations.npz         ← dati MaskableEvalCallback
```
