# 06 — Monitoring e TensorBoard

## Obiettivo
Configurare il monitoraggio del training per capire se l'agente sta imparando,
diagnosticare problemi e salvare le metriche rilevanti.

---

## Metriche automatiche di SB3 su TensorBoard

Stable-Baselines3 logga automaticamente queste metriche:

| Metrica | Cosa indica | Valore atteso (sano) |
|---|---|---|
| `rollout/ep_rew_mean` | Reward media per episodio | Deve crescere nel tempo |
| `rollout/ep_len_mean` | Lunghezza media episodio | Cresce se l'agente sopravvive più turni |
| `train/loss` | Loss totale PPO | Deve scendere e stabilizzarsi |
| `train/policy_gradient_loss` | Loss sulla policy | Vicino a 0, non esplodere |
| `train/value_loss` | Loss sul value function | Deve decrescere |
| `train/entropy_loss` | Entropia della policy | Non deve scendere a 0 (esplorazione) |
| `train/clip_fraction` | % update clippati | Idealmente < 0.2 |
| `train/approx_kl` | KL divergence policy update | Idealmente < 0.02 |

---

## Metriche custom di Unciv da aggiungere

Queste vanno loggate manualmente tramite callback:

```
unciv/gold_mean          → Oro medio a fine episodio
unciv/happiness_mean     → Happiness media
unciv/cities_mean        → Numero medio città
unciv/techs_mean         → Tecnologie scoperte in media
unciv/population_mean    → Popolazione media
unciv/action_distribution → Frequenza di ogni azione scelta
```

---

## Implementazione: `src/utils/callbacks.py`

```python
import numpy as np
from stable_baselines3.common.callbacks import BaseCallback

class UncivMetricsCallback(BaseCallback):
    """
    Logga metriche custom di Unciv su TensorBoard ad ogni rollout.
    """

    def __init__(self, verbose: int = 0):
        super().__init__(verbose)
        self._episode_infos = []

    def _on_step(self) -> bool:
        # Raccoglie info da ogni environment step
        for info in self.locals.get("infos", []):
            if "episode" in info:
                # Fine episodio: info contiene le metriche finali
                self._episode_infos.append(info)

        return True  # True = continua training

    def _on_rollout_end(self) -> None:
        """Chiamato alla fine di ogni rollout (ogni n_steps * n_envs step)."""
        if not self._episode_infos:
            return

        # Calcola medie sugli episodi completati in questo rollout
        gold_values = [i.get("gold", 0) for i in self._episode_infos]
        happiness_values = [i.get("happiness", 0) for i in self._episode_infos]
        cities_values = [i.get("n_cities", 0) for i in self._episode_infos]
        turn_values = [i.get("turn", 0) for i in self._episode_infos]

        self.logger.record("unciv/gold_mean", np.mean(gold_values))
        self.logger.record("unciv/happiness_mean", np.mean(happiness_values))
        self.logger.record("unciv/cities_mean", np.mean(cities_values))
        self.logger.record("unciv/turns_mean", np.mean(turn_values))

        self._episode_infos.clear()


class ActionDistributionCallback(BaseCallback):
    """
    Logga la distribuzione delle azioni per diagnosticare
    comportamenti degeneri (es. agente che sceglie sempre la stessa azione).
    """
    ACTION_NAMES = ["Monument", "Granary", "Library", "Barracks", "Settler", "Warrior", "Idle"]

    def __init__(self, log_freq: int = 10_000, verbose: int = 0):
        super().__init__(verbose)
        self.log_freq = log_freq
        self._action_counts = np.zeros(7, dtype=int)

    def _on_step(self) -> bool:
        actions = self.locals.get("actions", [])
        for a in actions:
            if 0 <= a < 7:
                self._action_counts[a] += 1

        if self.num_timesteps % self.log_freq == 0 and self._action_counts.sum() > 0:
            total = self._action_counts.sum()
            for i, name in enumerate(self.ACTION_NAMES):
                freq = self._action_counts[i] / total
                self.logger.record(f"unciv/action_{name}", freq)
            self._action_counts[:] = 0  # Reset dopo ogni log

        return True
```

---

## Integrazione in `train.py`

Aggiornare il blocco callbacks in `train.py`:

```python
from src.utils.callbacks import UncivMetricsCallback, ActionDistributionCallback

# Aggiungere ai callbacks esistenti:
metrics_cb = UncivMetricsCallback(verbose=0)
action_cb = ActionDistributionCallback(log_freq=10_000)

callbacks = CallbackList([checkpoint_cb, eval_cb, metrics_cb, action_cb])
```

---

## Avviare TensorBoard

```bash
# Dalla root del progetto
tensorboard --logdir logs/

# Poi apri nel browser:
# http://localhost:6006
```

---

## Guida alla diagnosi dei problemi

### L'agente non impara (reward piatta)
```
Sintomi: ep_rew_mean non cresce dopo 100k+ step
Cause possibili:
  1. Reward function troppo sparsa → aggiungi più segnali intermedi
  2. Learning rate troppo alto/basso → prova 1e-4 o 1e-3
  3. Bug nel parser → verifica che l'observation vector cambi tra step
  4. Ambiente non funziona → esegui 10 episodi con random agent e controlla
```

### La policy collassa (sceglie sempre la stessa azione)
```
Sintomi: action_Idle o action_Monument al 90%+ del tempo
Cause possibili:
  1. Entropy troppo bassa → aumenta ent_coef (default 0.0 in SB3, prova 0.01)
  2. Reward hacking → quella azione dà reward facilmente, bilancia i pesi
```

### Training instabile (loss esplode)
```
Sintomi: policy_gradient_loss o value_loss che oscilla violentemente
Cause possibili:
  1. Learning rate troppo alto → riduci a 1e-4
  2. clip_range troppo grande → riduci a 0.1
  3. approx_kl > 0.05 consistentemente → abbassa learning_rate
```

### Reward media negativa persistente
```
Sintomi: ep_rew_mean < 0 dopo 200k+ step
Cause possibili:
  1. Penalty troppo aggressive → riduci pesi negativi nella reward function
  2. Idle penalty accumula → controlla se action_Idle è troppo alto
```

---

## Script di analisi rapida: `src/utils/analyze_run.py`

```python
"""
Analisi rapida di un run di training senza aprire TensorBoard.
"""
import numpy as np
from pathlib import Path

def analyze_evaluations(log_dir: str):
    """Legge il file evaluations.npz salvato da EvalCallback."""
    eval_file = Path(log_dir) / "evaluations.npz"
    if not eval_file.exists():
        print("Nessun file evaluations.npz trovato. Training ancora in corso?")
        return

    data = np.load(eval_file)
    timesteps = data["timesteps"]
    results = data["results"]  # shape: (n_evals, n_eval_episodes)
    mean_rewards = results.mean(axis=1)

    print(f"{'Timesteps':>12} | {'Reward Media':>14} | {'Reward Max':>10}")
    print("-" * 45)
    for t, r in zip(timesteps, mean_rewards):
        print(f"{t:>12,} | {r:>14.2f} | {results[list(timesteps).index(t)].max():>10.2f}")

if __name__ == "__main__":
    analyze_evaluations("logs")
```

```bash
python src/utils/analyze_run.py
```

---

## Note per Claude Code
- `UncivMetricsCallback` legge `info` dall'env — assicurarsi che `step()` in `unciv_env.py` restituisca sempre `gold`, `happiness`, `n_cities`, `turn` nell'info dict
- TensorBoard aggiorna i grafici ogni 30 secondi — il training può continuare in parallelo
- Salvare sempre il run name nel log: `PPO_1`, `PPO_2` etc. — SB3 incrementa automaticamente
- La metrica più importante da monitorare è `rollout/ep_rew_mean` — tutto il resto è diagnostica
