# 05 — PPO Training

## Obiettivo
Configurare e avviare il training dell'agente PPO con Stable-Baselines3,
con salvataggio automatico dei checkpoint e gestione degli iperparametri.

---

## Perché PPO per questo progetto

PPO (Proximal Policy Optimization) è la scelta standard per giochi a turni perché:
- **Stabile**: non diverge facilmente come DQN su spazi di azione grandi
- **On-policy**: impara dalle esperienze recenti (adatto a giochi con stato mutevole)
- **Parallelizzabile**: supporta N ambienti in parallelo nativamente in SB3
- **Ben documentato**: enorme community, molti esempi su giochi simili

---

## Iperparametri chiave spiegati

| Parametro | Valore iniziale | Cosa controlla |
|---|---|---|
| `learning_rate` | `3e-4` | Quanto velocemente aggiorna la policy |
| `n_steps` | `2048` | Quanti step raccoglie prima di ogni update |
| `batch_size` | `64` | Dimensione mini-batch per il gradient descent |
| `n_epochs` | `10` | Quante volte riusa ogni batch raccolto |
| `gamma` | `0.99` | Quanto valuta reward future vs immediate |
| `clip_range` | `0.2` | Quanto può cambiare la policy in un update (stabilità) |
| `n_envs` | `4` | Ambienti paralleli (più = più veloce ma più RAM) |

---

## Implementazione: `train.py`

```python
import yaml
import argparse
from pathlib import Path
from stable_baselines3 import PPO
from stable_baselines3.common.env_util import make_vec_env
from stable_baselines3.common.callbacks import (
    CheckpointCallback,
    EvalCallback,
    CallbackList,
)
from stable_baselines3.common.monitor import Monitor
from src.envs.unciv_env import UncivEnv


def load_config(path: str) -> dict:
    with open(path) as f:
        return yaml.safe_load(f)


def make_env(config_path: str):
    """Factory function per make_vec_env."""
    def _init():
        env = UncivEnv(config_path=config_path)
        return Monitor(env)
    return _init


def train(config_path: str = "config/default_config.yaml", resume: str = None):
    config = load_config(config_path)
    tc = config["training"]
    paths = config["paths"]

    # Crea cartelle output
    Path(paths["save_dir"]).mkdir(parents=True, exist_ok=True)
    Path(paths["log_dir"]).mkdir(parents=True, exist_ok=True)

    # Crea ambienti vettorizzati (paralleli)
    env = make_vec_env(
        make_env(config_path),
        n_envs=tc["n_envs"],
    )

    # Ambiente di valutazione separato (non usato nel training)
    eval_env = make_vec_env(make_env(config_path), n_envs=1)

    # Callbacks
    checkpoint_cb = CheckpointCallback(
        save_freq=max(10_000 // tc["n_envs"], 1),
        save_path=paths["save_dir"],
        name_prefix="unciv_ppo",
        verbose=1,
    )

    eval_cb = EvalCallback(
        eval_env,
        best_model_save_path=paths["save_dir"] + "/best",
        log_path=paths["log_dir"],
        eval_freq=max(50_000 // tc["n_envs"], 1),
        n_eval_episodes=5,
        deterministic=True,
        verbose=1,
    )

    callbacks = CallbackList([checkpoint_cb, eval_cb])

    # Crea o carica modello
    if resume:
        print(f"▶ Riprendendo training da: {resume}")
        model = PPO.load(resume, env=env, tensorboard_log=paths["log_dir"])
    else:
        print("▶ Nuovo training da zero")
        model = PPO(
            policy="MlpPolicy",
            env=env,
            learning_rate=tc["learning_rate"],
            n_steps=tc["n_steps"],
            batch_size=tc["batch_size"],
            n_epochs=tc["n_epochs"],
            gamma=tc["gamma"],
            clip_range=tc["clip_range"],
            verbose=1,
            tensorboard_log=paths["log_dir"],
        )

    # Avvia training
    model.learn(
        total_timesteps=tc["total_timesteps"],
        callback=callbacks,
        reset_num_timesteps=not bool(resume),
    )

    # Salva modello finale
    final_path = Path(paths["save_dir"]) / "final_model"
    model.save(final_path)
    print(f"✅ Training completato. Modello salvato in: {final_path}.zip")

    env.close()
    eval_env.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Train PPO agent for Unciv")
    parser.add_argument("--config", default="config/default_config.yaml")
    parser.add_argument("--resume", default=None, help="Path a checkpoint .zip da cui riprendere")
    args = parser.parse_args()
    train(config_path=args.config, resume=args.resume)
```

---

## Come avviare il training

```bash
# Training da zero
python train.py

# Training con config personalizzata
python train.py --config config/experiment_01.yaml

# Riprendere da checkpoint
python train.py --resume models/checkpoints/unciv_ppo_100000_steps.zip
```

---

## Script di valutazione: `evaluate.py`

```python
from stable_baselines3 import PPO
from src.envs.unciv_env import UncivEnv

def evaluate(model_path: str, n_episodes: int = 10):
    env = UncivEnv()
    model = PPO.load(model_path)

    rewards = []
    for ep in range(n_episodes):
        obs, _ = env.reset()
        total_reward = 0
        done = False
        while not done:
            action, _ = model.predict(obs, deterministic=True)
            obs, reward, terminated, truncated, info = env.step(action)
            total_reward += reward
            done = terminated or truncated
            env.render()
        rewards.append(total_reward)
        print(f"Episodio {ep+1}: reward totale = {total_reward:.2f} | turns = {info['turn']}")

    print(f"\nMedia reward: {sum(rewards)/len(rewards):.2f}")
    env.close()

if __name__ == "__main__":
    evaluate("models/checkpoints/best/best_model.zip")
```

---

## Struttura output attesa dopo il training

```
models/
└── checkpoints/
    ├── unciv_ppo_10000_steps.zip
    ├── unciv_ppo_50000_steps.zip
    ├── unciv_ppo_100000_steps.zip
    ├── final_model.zip
    └── best/
        └── best_model.zip        ← modello con reward media più alta
logs/
└── PPO_1/
    ├── events.out.tfevents.*     ← file TensorBoard
    └── evaluations.npz
```

---

## Note per Claude Code
- `make_vec_env` con `n_envs > 1` richiede che `UncivEnv` sia **thread-safe** — ogni istanza deve usare un save file separato (es. `current_game_{rank}.json`)
- `Monitor` wrapper è obbligatorio per `EvalCallback` — non rimuoverlo
- Il parametro `reset_num_timesteps=not bool(resume)` garantisce che TensorBoard mostri i grafici in continuità quando si riprende il training
- Con `n_steps=2048` e `n_envs=4`, ogni update usa `2048 * 4 = 8192` step — tienilo in mente per scalare `total_timesteps`
