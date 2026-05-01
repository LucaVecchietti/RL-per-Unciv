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
from src.utils.callbacks import UncivMetricsCallback, ActionDistributionCallback


def load_config(path: str) -> dict:
    """Carica config YAML da path."""
    with open(path) as f:
        return yaml.safe_load(f)


def make_env(config_path: str, rank: int = 0):
    """
    Factory function per make_vec_env.
    Ogni env riceve rank univoco → save file separato → no race condition.
    """
    def _init():
        env = UncivEnv(config_path=config_path, env_rank=rank)
        return Monitor(env)
    return _init


def train(config_path: str = "config/default_config.yaml", resume: str = None) -> None:
    """
    Avvia o riprende il training PPO.

    Args:
        config_path: Path al file YAML di configurazione.
        resume: Path a checkpoint .zip da cui riprendere (None = da zero).
    """
    config = load_config(config_path)
    tc = config["training"]
    paths = config["paths"]

    # Crea cartelle output
    Path(paths["save_dir"]).mkdir(parents=True, exist_ok=True)
    Path(paths["log_dir"]).mkdir(parents=True, exist_ok=True)

    # Crea ambienti vettorizzati (paralleli) — rank univoco per save file separati
    n_envs = tc["n_envs"]
    env = make_vec_env(
        [make_env(config_path, rank=i) for i in range(n_envs)],
        n_envs=n_envs,
    )

    # Eval env usa rank=n_envs per non sovrapporsi ai training env
    eval_env = make_vec_env(
        [make_env(config_path, rank=n_envs)],
        n_envs=1,
    )

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

    metrics_cb = UncivMetricsCallback(verbose=0)
    action_cb = ActionDistributionCallback(log_freq=10_000)

    callbacks = CallbackList([checkpoint_cb, eval_cb, metrics_cb, action_cb])

    # Crea o carica modello
    if resume:
        print(f"Riprendendo training da: {resume}")
        model = PPO.load(resume, env=env, tensorboard_log=paths["log_dir"])
    else:
        print("Nuovo training da zero")
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
    print(f"Training completato. Modello salvato in: {final_path}.zip")

    env.close()
    eval_env.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Train PPO agent for Unciv")
    parser.add_argument("--config", default="config/default_config.yaml")
    parser.add_argument("--resume", default=None, help="Path a checkpoint .zip da cui riprendere")
    args = parser.parse_args()
    train(config_path=args.config, resume=args.resume)
