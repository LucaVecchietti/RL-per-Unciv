"""
Analisi rapida di un run di training senza aprire TensorBoard.
"""
import numpy as np
from pathlib import Path


def analyze_evaluations(log_dir: str) -> None:
    """
    Legge il file evaluations.npz salvato da EvalCallback e stampa un riepilogo.

    Args:
        log_dir: Cartella log dove EvalCallback ha salvato evaluations.npz.
    """
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
    for t, r, row in zip(timesteps, mean_rewards, results):
        print(f"{t:>12,} | {r:>14.2f} | {row.max():>10.2f}")


if __name__ == "__main__":
    analyze_evaluations("logs")
