# ARCHITECTURE.md — Schema di funzionamento

## Visione d'insieme

```
┌─────────────────────────────────────────────────────────────────┐
│                        TRAINING LOOP                            │
│                                                                 │
│   ┌──────────┐    azione     ┌──────────────┐   obs, reward    │
│   │  PPO     │ ──────────► │  UncivEnv    │ ──────────────►  │
│   │  Agent   │              │  (Gymnasium) │                   │
│   │  (SB3)   │ ◄──────────  └──────┬───────┘                   │
│   └──────────┘  obs, reward        │                           │
│                                    │ legge/scrive              │
│                          ┌─────────▼──────────┐                │
│                          │  saves/             │                │
│                          │  current_game.json  │                │
│                          └─────────────────────┘                │
└─────────────────────────────────────────────────────────────────┘
```

---

## Flusso dettagliato — un singolo step

```
PPO sceglie azione (0-6)
         │
         ▼
UncivEnv.step(action)
         │
         ├─► _apply_action(action)
         │       │
         │       └─► ACTION_MAP[action] → nome costruzione
         │               │
         │               └─► legge current_game.json
         │                   modifica cityConstructions
         │                   scrive current_game.json
         │
         ├─► _advance_turn()
         │       │
         │       └─► legge current_game_{rank}.json
         │           UncivSimulator.advance_turn(raw)
         │               ├─► produzione: 3 + max(0, pop-1) prod/turno
         │               │   completamento → builtBuildings, reset accumulatore
         │               ├─► popolazione: food += 2(+2 Granary)
         │               │   threshold = 10 + pop*3 → crescita
         │               ├─► scienza: 2(+2 Library) + int(pop*0.5)
         │               │   tech completata → next_tech da TECH_TREE
         │               ├─► oro: +1 per città
         │               └─► happiness: 9.0 + Monument(+1) - max(0,(pop-1)*0.5)
         │           scrive current_game_{rank}.json
         │
         ├─► parser.parse(save_path)
         │       │
         │       └─► UncivStateParser.load()
         │               │ plain JSON o gzip
         │               ▼
         │           _find_player_civ(raw)
         │               │ cerca civName == "India"
         │               ▼
         │           _extract_game_state(raw)
         │               │
         │               ├─► turn, gold, happiness, current_player
         │               ├─► techs_researched, current_tech
         │               ├─► map_width, map_height
         │               └─► [_parse_city(c) for c in cities]
         │                       │
         │                       └─► CityState(name, population,
         │                                     current_construction,
         │                                     built_buildings,
         │                                     health, tiles_count)
         │           restituisce GameState
         │
         ├─► parser.to_observation_vector(state)
         │       │
         │       └─► vettore numpy (7,) float32:
         │               [0] turn / 500
         │               [1] gold / 1000
         │               [2] happiness / 20
         │               [3] len(cities) / 10
         │               [4] len(techs) / 80
         │               [5] cities[0].population / 20
         │               [6] len(cities[0].built_buildings) / 20
         │
         ├─► compute_reward(prev_state, curr_state, action)
         │       │
         │       ├─► +pop_delta * 2.0          (crescita città)
         │       ├─► +new_buildings * 1.5      (edifici completati)
         │       ├─► +new_techs * 3.0          (ricerca tecnologica)
         │       ├─► +clip(gold_delta/100, ±0.5) (gestione oro)
         │       ├─► happiness < 0 → +happiness * 0.1  (penalty)
         │       └─► action == 6 → -0.05       (penalty idle)
         │
         ├─► _is_terminated()
         │       └─► happiness < -10 → True
         │
         ├─► se terminated:
         │       └─► compute_terminal_reward(state, max_turns)
         │               ├─► +1.0 se happiness >= 0 (survival bonus)
         │               └─► +techs*0.1 + population*0.05
         │
         └─► return (obs, reward, terminated, truncated, info)
```

---

## Componenti e responsabilità

### `src/parsers/state_parser.py`

| Classe/Funzione | Input | Output | Responsabilità |
|---|---|---|---|
| `UncivStateParser.load()` | path file | dict raw | Legge JSON (plain o gzip) |
| `UncivStateParser.parse()` | path file | `GameState` | Entry point: file → struttura dati |
| `UncivStateParser.to_observation_vector()` | `GameState` | `np.ndarray (7,)` | Converte stato in input per PPO |
| `_find_player_civ()` | dict raw | dict civ | Filtra civilizzazione "India" |
| `_parse_city()` | dict city | `CityState` | Estrae dati singola città |

**Contratto:** output sempre `shape=(7,)`, `dtype=float32`, valori in `[0, ~1]`.

---

### `src/envs/unciv_env.py`

| Metodo | Chiamato da | Cosa fa |
|---|---|---|
| `reset()` | SB3 inizio episodio | Copia template, legge stato iniziale |
| `step(action)` | SB3 ogni turno | Applica azione, avanza turno, calcola reward |
| `_start_new_game()` | `reset()` | Copia `saves/template_game.json` → `saves/current_game_{rank}.json` |
| `_apply_action()` | `step()` | Scrive costruzione scelta nel JSON |
| `_advance_turn()` | `step()` | Esegue `UncivSimulator.advance_turn(raw)` (Fase 1.5) |
| `_compute_reward()` | `step()` | Delega a `src/utils/reward.py` |
| `_is_terminated()` | `step()` | `happiness < -10` → episodio finito |

**Spazi Gymnasium:**
```
observation_space = Box(low=0.0, high=1.0, shape=(7,), dtype=float32)
action_space      = Discrete(7)
```

---

### `src/utils/reward.py`

```
compute_reward(prev, curr, action) → float
    │
    ├─ prev is None → return 0.0      (primo step)
    ├─ popolazione aumentata → +2.0 per cittadino
    ├─ edificio completato  → +1.5 per edificio
    ├─ tecnologia scoperta  → +3.0 per tech
    ├─ oro accumulato       → clip(delta/100, -0.5, +0.5)
    ├─ happiness < 0        → happiness * 0.1 (negativo)
    └─ action == 6 (idle)   → -0.05

compute_terminal_reward(state, max_turns) → float
    ├─ happiness >= 0 → +1.0 (survived)
    ├─ happiness < 0  → -1.0
    ├─ +techs_count * 0.1
    └─ +total_population * 0.05
```

---

### `src/utils/simulator.py`

| Metodo | Input | Output | Responsabilita |
|---|---|---|---|
| `advance_turn(raw)` | dict JSON | dict JSON | Simula un turno completo (in-place) |
| `_simulate_production(city)` | dict city | - | Accumula produzione, completa edificio |
| `_simulate_population(city)` | dict city | - | Accumula cibo, cresce popolazione |
| `_simulate_science(civ, tech)` | dict, dict | - | Accumula scienza, sblocca tech |
| `_simulate_gold(civ, cities)` | dict, list | - | +1 oro per citta |
| `_simulate_happiness(civ, cities)` | dict, list | - | 9.0 +/- bonus Monument +/- pop penalty |

**Formule chiave:**
```
produzione/turno  = 3 + max(0, population - 1)
food_threshold    = 10 + population * 3
scienza/turno     = 2 + (2 se Library) + int(population * 0.5)
happiness         = 9.0 + (1.0 se Monument) - max(0, (pop-1) * 0.5)
```

**Nota:** Fa da ponte tra Fase 1 (stub) e Fase 2 (headless). Sostituito da
`UncivHeadless.advance_turn()` quando si implementa `08_headless_integration.md`.

---

### `src/utils/diagnose_run.py`

```
diagnose_save_file(save_path)
    └─► legge current_game_0.json
        stampa: turno, oro, happiness, pop, edifici, tech
        warning automatici:
            turn > 10 e nessun edificio  → produzione rotta
            turn > 20 e nessuna tech     → scienza rotta
            happiness < 0               → episodio terminato prematuramente
            oro invariato a 50          → simulatore oro rotto

simulate_30_turns()
    └─► crea raw minimale (India, Delhi, pop=1)
        esegue 30 turni con UncivSimulator
        stampa tabella: turn | gold | happy | pop | built | techs
```

**Uso:**
```
python src/utils/diagnose_run.py        # analizza saves/current_game_0.json
python src/utils/diagnose_run.py sim    # simula 30 turni (verifica simulatore)
``` 

---

### `src/utils/callbacks.py`

```
UncivMetricsCallback
    _on_step()        → raccoglie info da episodi completati
    _on_rollout_end() → logga su TensorBoard:
                        unciv/gold_mean
                        unciv/happiness_mean
                        unciv/cities_mean
                        unciv/turns_mean

ActionDistributionCallback
    _on_step()        → conta ogni azione eseguita
    ogni 10k step     → logga frequenza:
                        unciv/action_Monument
                        unciv/action_Granary
                        ... (7 azioni)
```

---

### `train.py`

```
load_config(yaml) → dict iperparametri

make_vec_env([make_env(rank=i) for i in range(n_envs)], n_envs=4)
    └─► 4 istanze parallele di UncivEnv + Monitor wrapper
        ogni env usa current_game_{rank}.json separato (no race condition)
        eval env usa rank=n_envs (es. rank=4)

PPO(
    policy="MlpPolicy",    # rete neurale fully-connected
    learning_rate=3e-4,
    n_steps=1024,          # step raccolti prima di ogni update (Fase 1.5)
    batch_size=64,
    n_epochs=10,
    gamma=0.99,
    clip_range=0.2,
    ent_coef=0.01          # entropia — aumentare a 0.05 se policy collassa
)

CallbackList([
    CheckpointCallback,         # salva ogni 10k step
    EvalCallback,               # valuta ogni 50k step
    UncivMetricsCallback,       # metriche Unciv custom
    ActionDistributionCallback  # distribuzione azioni
])

model.learn(total_timesteps=1_000_000)
    └─► salva final_model.zip
```

---

## Ciclo completo training

```
train.py avvia
    │
    ▼
4 ambienti paralleli (n_envs=4)
    │
    ▼
ogni ambiente: reset() → copia template → legge stato
    │
    ▼
PPO raccoglie 2048 step per ambiente = 8192 step totali
    │
    ▼
calcola vantaggio (GAE) e aggiorna policy (10 epochs)
    │
    ▼
ogni 10.000 step → CheckpointCallback → salva .zip
ogni 50.000 step → EvalCallback → valuta 5 episodi → salva best_model.zip
ogni rollout     → UncivMetricsCallback → logga metriche custom
    │
    ▼
ripeti fino a 1.000.000 step totali
    │
    ▼
salva final_model.zip
```

---

## Metriche TensorBoard

| Metrica | Sana | Problema |
|---|---|---|
| `rollout/ep_rew_mean` | cresce nel tempo | piatta → reward mal progettata |
| `train/entropy_loss` | non scende a 0 | → 0 = policy collassata |
| `train/approx_kl` | < 0.02 | > 0.05 = learning rate troppo alto |
| `train/clip_fraction` | < 0.2 | > 0.3 = aggiornamenti troppo grandi |
| `unciv/action_Idle` | < 30% | > 70% = reward hacking idle |

---

## Dipendenze tra moduli

```
train.py
    ├── src/envs/unciv_env.py
    │       ├── src/parsers/state_parser.py
    │       ├── src/utils/reward.py
    │       └── src/utils/simulator.py
    └── src/utils/callbacks.py

src/utils/diagnose_run.py
    └── src/utils/simulator.py  (modalità sim)

evaluate.py
    └── src/envs/unciv_env.py

config/default_config.yaml
    └── letto da: train.py, unciv_env.py
```

---

## File su disco durante il training

```
saves/
    template_game.json      ← read-only, mai modificato
    current_game_0.json     ← Env rank 0 (training)
    current_game_1.json     ← Env rank 1 (training)
    current_game_2.json     ← Env rank 2 (training)
    current_game_3.json     ← Env rank 3 (training)
    current_game_4.json     ← Eval env (rank = n_envs)

models/checkpoints/
    unciv_ppo_10000_steps.zip
    unciv_ppo_20000_steps.zip
    ...
    final_model.zip
    best/
        best_model.zip

logs/
    PPO_1/
        events.out.tfevents.*   ← TensorBoard
        evaluations.npz         ← dati EvalCallback
```
