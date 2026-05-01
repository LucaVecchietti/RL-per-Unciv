# 04 — Reward Function

## Obiettivo
Definire cosa significa "fare bene" per l'agente. La reward function è il componente
più critico del RL: una reward mal progettata produce comportamenti indesiderati
anche con un agente altrimenti ottimo.

---

## Principi di design della reward

### Il problema della reward sparsa
In Civilization, la vittoria arriva dopo centinaia di turni. Se diamo reward solo
alla vittoria finale, l'agente non riceve abbastanza segnale per imparare.
Soluzione: **reward densa** con segnali intermedi ad ogni turno.

### Il problema del reward hacking
L'agente potrebbe trovare scorciatoie: es. costruire infiniti Monument per la
reward "edificio costruito" senza mai espandersi. Soluzione: reward bilanciate
e obiettivi multipli.

### Principio generale
```
reward_totale = reward_progresso + reward_efficienza - penalty_errori
```

---

## Componenti della Reward — Fase 1

### 1. Reward Crescita Città
```python
# Popolazione aumentata
if curr.cities and prev.cities:
    pop_delta = curr.cities[0].population - prev.cities[0].population
    reward += pop_delta * 2.0   # +2 per ogni cittadino guadagnato
```

### 2. Reward Costruzioni
```python
# Nuovo edificio completato
prev_buildings = set(prev.cities[0].built_buildings) if prev.cities else set()
curr_buildings = set(curr.cities[0].built_buildings) if curr.cities else set()
new_buildings = curr_buildings - prev_buildings
reward += len(new_buildings) * 1.5
```

### 3. Reward Ricerca Tecnologica
```python
# Nuova tecnologia scoperta
prev_techs = set(prev.techs_researched)
curr_techs = set(curr.techs_researched)
new_techs = curr_techs - prev_techs
reward += len(new_techs) * 3.0  # Peso alto: la ricerca è strategica
```

### 4. Reward Oro
```python
# Accumulo di oro (segno di buona gestione economica)
gold_delta = curr.gold - prev.gold
reward += np.clip(gold_delta / 100.0, -0.5, 0.5)  # Normalizzato e clippato
```

### 5. Penalty Happiness
```python
# Happiness negativa → instabilità → penalità crescente
if curr.happiness < 0:
    reward += curr.happiness * 0.1   # Es. -5 happiness → -0.5 reward/turno
```

### 6. Penalty Stagnazione
```python
# Nessun progresso per N turni → penalità lieve
# (evita che l'agente stia fermo a "fine turno" continuamente)
if action == 6:  # Fine turno senza costruire
    reward -= 0.05
```

---

## Implementazione: `src/utils/reward.py`

```python
import numpy as np
from src.parsers.state_parser import GameState
from typing import Optional

# Pesi configurabili — non hardcoded nel codice
REWARD_WEIGHTS = {
    "population_growth":  2.0,
    "building_complete":  1.5,
    "tech_researched":    3.0,
    "gold_accumulation":  0.5,
    "happiness_penalty":  0.1,
    "idle_penalty":       0.05,
}

def compute_reward(
    prev: Optional[GameState],
    curr: GameState,
    action: int,
    weights: dict = REWARD_WEIGHTS
) -> float:
    """
    Calcola la reward per un singolo step.
    
    Args:
        prev: Stato al turno precedente (None al primo step)
        curr: Stato attuale
        action: Azione eseguita (0-6)
        weights: Dizionario dei pesi (override da config se necessario)
    
    Returns:
        reward: float, può essere negativa
    """
    if prev is None:
        return 0.0

    reward = 0.0
    w = weights

    # --- 1. Crescita popolazione ---
    if prev.cities and curr.cities:
        pop_delta = curr.cities[0].population - prev.cities[0].population
        reward += pop_delta * w["population_growth"]

    # --- 2. Edifici completati ---
    prev_buildings = set(prev.cities[0].built_buildings) if prev.cities else set()
    curr_buildings = set(curr.cities[0].built_buildings) if curr.cities else set()
    new_buildings = curr_buildings - prev_buildings
    reward += len(new_buildings) * w["building_complete"]

    # --- 3. Tecnologie scoperte ---
    new_techs = set(curr.techs_researched) - set(prev.techs_researched)
    reward += len(new_techs) * w["tech_researched"]

    # --- 4. Gestione oro ---
    gold_delta = curr.gold - prev.gold
    reward += float(np.clip(gold_delta / 100.0, -w["gold_accumulation"], w["gold_accumulation"]))

    # --- 5. Penalty happiness negativa ---
    if curr.happiness < 0:
        reward += curr.happiness * w["happiness_penalty"]

    # --- 6. Penalty azione idle (fine turno senza fare nulla) ---
    if action == 6:
        reward -= w["idle_penalty"]

    return float(reward)


def compute_terminal_reward(final_state: GameState, max_turns: int) -> float:
    """
    Reward bonus/malus alla fine dell'episodio.
    Premia la sopravvivenza e la crescita complessiva.
    """
    survival_bonus = 1.0 if final_state.happiness >= 0 else -1.0
    progress_bonus = (
        len(final_state.techs_researched) * 0.1 +
        sum(c.population for c in final_state.cities) * 0.05
    )
    return survival_bonus + progress_bonus
```

---

## Integrazione in `unciv_env.py`

Sostituire il metodo `_compute_reward` stub con:

```python
from src.utils.reward import compute_reward, compute_terminal_reward

def _compute_reward(self, prev: GameState, curr: GameState, action: int) -> float:
    return compute_reward(prev, curr, action)

# In step(), prima del return:
if terminated:
    reward += compute_terminal_reward(self._current_state, self.max_turns)
```

---

## Tabella di debug reward

Crea `src/utils/reward_logger.py` per monitorare i componenti separati:

```python
def compute_reward_verbose(prev, curr, action, weights=REWARD_WEIGHTS) -> tuple[float, dict]:
    """Come compute_reward ma restituisce anche il breakdown per componente."""
    breakdown = {}
    # ... stesso codice ma salva ogni componente in breakdown
    return total_reward, breakdown
```

Utile per diagnosticare comportamenti inattesi durante il training.

---

## Evoluzione della reward nelle fasi successive

| Fase | Nuovi componenti reward |
|---|---|
| **Fase 1** (attuale) | Popolazione, edifici, tech, oro, happiness |
| **Fase 2** | +reward espansione (nuove città), +reward esplorazione mappa |
| **Fase 3** | +reward vittorie militari, -penalty perdita unità |
| **Fase 4** | +reward accordi diplomatici, reward vittoria finale pesata |

---

## Note per Claude Code
- `REWARD_WEIGHTS` deve poter essere sovrascritto da `config/default_config.yaml` — aggiungere sezione `reward:` al config nella Fase 2
- La funzione `compute_reward` deve essere **pura** (no side effects, no stato interno)
- Loggare sempre la reward media su TensorBoard — se è sempre 0 o diverge, la reward function è rotta
- Il `compute_terminal_reward` va chiamato **solo** su `terminated=True`, non su `truncated=True`
