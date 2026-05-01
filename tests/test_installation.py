def test_imports():
    import gymnasium
    import stable_baselines3
    import numpy
    import yaml
    import tensorboard
    print("Tutte le dipendenze sono installate correttamente")
    print(f"  gymnasium:          {gymnasium.__version__}")
    print(f"  stable-baselines3:  {stable_baselines3.__version__}")
    print(f"  numpy:              {numpy.__version__}")

if __name__ == "__main__":
    test_imports()
