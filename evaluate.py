import argparse
from stable_baselines3 import PPO
from src.envs.unciv_env import UncivEnv


def evaluate(model_path: str, n_episodes: int = 10) -> None:
    """
    Valuta un modello PPO salvato su N episodi.

    Args:
        model_path: Path al file .zip del modello.
        n_episodes: Numero di episodi di valutazione.
    """
    env = UncivEnv()
    model = PPO.load(model_path)

    rewards = []
    for ep in range(n_episodes):
        obs, _ = env.reset()
        total_reward = 0.0
        done = False
        while not done:
            action, _ = model.predict(obs, deterministic=True)
            obs, reward, terminated, truncated, info = env.step(action)
            total_reward += reward
            done = terminated or truncated
            env.render()
        rewards.append(total_reward)
        print(f"Episodio {ep + 1}: reward totale = {total_reward:.2f} | turns = {info['turn']}")

    print(f"\nMedia reward: {sum(rewards) / len(rewards):.2f}")
    env.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Evaluate PPO agent for Unciv")
    parser.add_argument("--model", default="models/checkpoints/best/best_model.zip")
    parser.add_argument("--episodes", type=int, default=10)
    args = parser.parse_args()
    evaluate(model_path=args.model, n_episodes=args.episodes)
