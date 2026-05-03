# 15 — MaskablePPO Training (Fase 2.1)

## Obiettivo

Migrare `train.py` ed `evaluate.py` da `PPO` a `MaskablePPO` (sb3-contrib)
per sfruttare l'action masking implementato in Fase 2.1.

**Perché serve:** `PPO` standard ignora `action_masks()` — l'agente potrebbe
scegliere azioni di movimento in city step (e viceversa), rendendo il training
caotico. `MaskablePPO` azzera la probabilità delle azioni non valide prima di
ogni sampling.

**File modificati:** `train.py`, `evaluate.py`, `tests/test_training.py`
**File invariati:** tutto il resto

---

## Prerequisiti

sb3-contrib non è incluso in stable-baselines3. Va installato separatamente:

```powershell
# Passo manuale — eseguire prima di qualsiasi implementazione
.venv\Scripts\pip install "sb3-contrib>=2.0.0"
```

Verificare installazione:
```powershell
.venv\Scripts\python -c "from sb3_contrib import MaskablePPO; print('ok')"
```

> ⚠️ I checkpoint PPO esistenti (Fase 1.5) **non sono compatibili** con MaskablePPO.
> Il training Fase 2.1 riparte da zero — questo è atteso.
> Salvare il modello Fase 1.5 come backup prima di avviare:
> ```powershell
> Copy-Item models\checkpoints\best\best_model.zip models\checkpoints\fase2_0_final.zip
> ```

---

## Step 1 — Aggiornare `train.py`

Leggere `train.py` per intero prima di modificarlo.

**Cambiamenti:**
1. Import: `PPO` → `MaskablePPO` + `ActionMasker` + `MaskableEvalCallback`
2. `make_env`: aggiungere `ActionMasker` wrapper tra `UncivEnv` e `Monitor`
3. `train()`: sostituire `PPO(...)` e `PPO.load(...)` con `MaskablePPO`
4. `EvalCallback` → `MaskableEvalCallback`
5. Nome prefix checkpoint: `unciv_ppo` → `unciv_mppo`

```python
import yaml
import argparse
from pathlib import Path
from sb3_contrib import MaskablePPO
from sb3_contrib.common.wrappers import ActionMasker
from sb3_contrib.common.maskable.callbacks import MaskableEvalCallback
from stable_baselines3.common.vec_env import DummyVecEnv
from stable_baselines3.common.callbacks import CheckpointCallback, CallbackList
from stable_baselines3.common.monitor import Monitor
from src.envs.unciv_env import UncivEnv
from src.utils.callbacks import UncivMetricsCallback, ActionDistributionCallback


def load_config(path: str) -> dict:
    """Carica config YAML da path."""
    with open(path) as f:
        return yaml.safe_load(f)


def make_env(config_path: str, rank: int = 0):
    """
    Factory function per DummyVecEnv.
    ActionMasker espone action_masks() a MaskablePPO tramite env_method.
    """
    def _init():
        env = UncivEnv(config_path=config_path, env_rank=rank)
        env = ActionMasker(env, lambda e: e.action_masks())
        return Monitor(env)
    return _init


def train(config_path: str = "config/default_config.yaml", resume: str = None) -> None:
    """Avvia o riprende il training MaskablePPO."""
    config = load_config(config_path)
    tc = config["training"]
    paths = config["paths"]

    Path(paths["save_dir"]).mkdir(parents=True, exist_ok=True)
    Path(paths["log_dir"]).mkdir(parents=True, exist_ok=True)

    n_envs = tc["n_envs"]
    env = DummyVecEnv([make_env(config_path, rank=i) for i in range(n_envs)])
    eval_env = DummyVecEnv([make_env(config_path, rank=n_envs)])

    checkpoint_cb = CheckpointCallback(
        save_freq=max(10_000 // tc["n_envs"], 1),
        save_path=paths["save_dir"],
        name_prefix="unciv_mppo",
        verbose=1,
    )

    eval_cb = MaskableEvalCallback(
        eval_env,
        best_model_save_path=paths["save_dir"] + "/best",
        log_path=paths["log_dir"],
        eval_freq=max(50_000 // tc["n_envs"], 1),
        n_eval_episodes=5,
        deterministic=True,
        verbose=1,
    )

    metrics_cb = UncivMetricsCallback(verbose=0)
    action_cb = ActionDistributionCallback(log_freq=10_000)

    callbacks = CallbackList([checkpoint_cb, eval_cb, metrics_cb, action_cb])

    if resume:
        print(f"Riprendendo training da: {resume}")
        model = MaskablePPO.load(resume, env=env, tensorboard_log=paths["log_dir"])
    else:
        print("Nuovo training Fase 2.1 da zero")
        model = MaskablePPO(
            policy="MlpPolicy",
            env=env,
            learning_rate=tc["learning_rate"],
            n_steps=tc["n_steps"],
            batch_size=tc["batch_size"],
            n_epochs=tc["n_epochs"],
            gamma=tc["gamma"],
            clip_range=tc["clip_range"],
            ent_coef=tc.get("ent_coef", 0.0),
            verbose=1,
            tensorboard_log=paths["log_dir"],
        )

    model.learn(
        total_timesteps=tc["total_timesteps"],
        callback=callbacks,
        reset_num_timesteps=not bool(resume),
    )

    final_path = Path(paths["save_dir"]) / "fase2_1_final_model"
    model.save(final_path)
    print(f"Training completato. Modello salvato in: {final_path}.zip")

    env.close()
    eval_env.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Train MaskablePPO agent for Unciv")
    parser.add_argument("--config", default="config/default_config.yaml")
    parser.add_argument("--resume", default=None)
    args = parser.parse_args()
    train(config_path=args.config, resume=args.resume)
```

---

## Step 2 — Aggiornare `evaluate.py`

`model.predict()` con MaskablePPO richiede `action_masks` esplicito.

```python
import argparse
from sb3_contrib import MaskablePPO
from sb3_contrib.common.wrappers import ActionMasker
from src.envs.unciv_env import UncivEnv


def evaluate(model_path: str, n_episodes: int = 10) -> None:
    """Valuta un modello MaskablePPO salvato su N episodi."""
    env = UncivEnv()
    model = MaskablePPO.load(model_path)

    rewards = []
    for ep in range(n_episodes):
        obs, _ = env.reset()
        total_reward = 0.0
        done = False
        while not done:
            masks = env.action_masks()
            action, _ = model.predict(obs, action_masks=masks, deterministic=True)
            obs, reward, terminated, truncated, info = env.step(int(action))
            total_reward += reward
            done = terminated or truncated
            env.render()
        rewards.append(total_reward)
        print(f"Episodio {ep + 1}: reward totale = {total_reward:.2f} | turns = {info['turn']}")

    print(f"\nMedia reward: {sum(rewards) / len(rewards):.2f}")
    env.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Evaluate MaskablePPO agent for Unciv")
    parser.add_argument("--model", default="models/checkpoints/best/best_model.zip")
    parser.add_argument("--episodes", type=int, default=10)
    args = parser.parse_args()
    evaluate(model_path=args.model, n_episodes=args.episodes)
```

---

## Step 3 — Aggiornare `tests/test_training.py`

Leggere `tests/test_training.py`. L'import test deve verificare `MaskablePPO`
invece di `PPO`. Aggiornare eventuali assert sugli import.

Se il test fa solo `from train import train, load_config, make_env` senza
verificare quale classe PPO viene usata internamente, probabilmente non serve
nessuna modifica — i test passano già una volta che train.py è aggiornato.
Verificarlo eseguendo i test prima di toccare il file.

---

## Step 4 — Verificare test suite

```powershell
.venv\Scripts\python -m pytest tests/ -v
```

Output atteso: tutti i test verdi (60+).

Se `test_train_module_imports` fallisce perché non trova `sb3_contrib`:
→ sb3-contrib non è installato nel venv. Rifare Step 0.

Se altri test falliscono:
→ Non modificare i test. Analizzare il problema in `train.py` o `evaluate.py`.

---

## Step 5 — Avviare training Fase 2.1

```powershell
.venv\Scripts\python train.py
```

### Cosa monitorare nei primi 50k step

```powershell
tensorboard --logdir logs
```

| Metrica | Atteso | Problema se |
|---|---|---|
| `train/entropy_loss` | decresce | stagna → aumenta `ent_coef` a 0.05 |
| `unciv/action_MOVE_*` | sale entro 50k | rimane a 0 → masking non funziona |
| `unciv/action_Warrior` | sale | agente non costruisce warrior |
| `ep_rew_mean` | cresce verso 5.0 | negativa dopo 200k → diagnostica |

### Diagnostica masking

Se `unciv/action_MOVE_*` rimane sempre a 0 il masking non funziona.
Verificare che `env.env_method("action_masks")` funzioni:

```python
# Script di verifica rapida (eseguire una volta)
from stable_baselines3.common.vec_env import DummyVecEnv
from train import make_env
env = DummyVecEnv([make_env("config/default_config.yaml", rank=0)])
# Questo deve chiamare action_masks() sull'env interno:
masks = env.env_method("action_masks")
print(masks)  # atteso: [array([True, True, True, True, True, True, True, False, False, False, False])]
env.close()
```

---

## Criteri di successo Fase 2.1

| Criterio | Target |
|---|---|
| Warrior costruito entro turno 50 | `unciv/action_Warrior > 0` entro 100k step |
| Mappa esplorata | `ep_rew_mean > 5.0` entro 500k step |
| Policy stabile | `ep_rew_mean` non regredisce tra checkpoint |

Se `ep_rew_mean > 5.0` e warrior viene costruito regolarmente → Fase 2.1 completata.
Salvare `fase2_1_final_model.zip` e procedere a Fase 2.2 (File 10b — multi-città).

---

## Checklist

```
[ ] sb3-contrib installato: python -c "from sb3_contrib import MaskablePPO; print('ok')"
[ ] Backup modello Fase 1.5/2.0: fase2_0_final.zip salvato
[ ] train.py aggiornato (MaskablePPO, ActionMasker, MaskableEvalCallback)
[ ] evaluate.py aggiornato (action_masks in predict)
[ ] test_training.py verificato (modificare solo se necessario)
[ ] python -m pytest tests/ -v → tutti verdi
[ ] Diagnostica masking: env.env_method("action_masks") restituisce masks corrette
[ ] python train.py → nessun crash
[ ] TensorBoard: action_MOVE_* sale entro 50k step (masking funzionante)
[ ] ep_rew_mean > 5.0 entro 500k step
```

---

## Note per Claude Code

- **Leggere `train.py` e `evaluate.py` per intero** prima di modificare — la struttura
  è cambiata tra Sessione 5 (spec originale) e Sessione 14 (versione attuale).
  Lo spec qui sopra è basato sulla versione attuale, ma verificare sempre.

- `ActionMasker(env, lambda e: e.action_masks())` — `e` è `UncivEnv`, non `Monitor`.
  L'ordine dei wrapper è: `Monitor(ActionMasker(UncivEnv))`. Non invertire.

- `MaskablePPO.load(path)` fallisce se il file `.zip` è stato salvato con `PPO`.
  Se l'utente vuole fare transfer learning da Fase 1.5: **non è possibile direttamente**.
  Unica opzione: copiare solo i pesi della policy network (complesso, non necessario ora).

- `ActionDistributionCallback` logga `n` azioni. Con `Discrete(11)` logga 11 azioni
  automaticamente (legge `action_space.n`). Nessuna modifica necessaria.

- `MaskableEvalCallback` ha la stessa firma di `EvalCallback` — sostituzione 1:1.

- Se il test `test_train_module_imports` importa `from stable_baselines3 import PPO`
  internamente per verificare il tipo del modello, aggiornarlo a `MaskablePPO`.
  Se testa solo che i moduli siano importabili senza crash, non toccare nulla.

- TensorBoard: i log MaskablePPO finiscono in `logs/MaskablePPO_1/` (non `PPO_1/`).
  `tensorboard --logdir logs` mostra entrambe le run in parallelo — utile per confronto.
