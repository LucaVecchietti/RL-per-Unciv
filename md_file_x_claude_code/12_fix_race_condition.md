# 12 — Fix Race Condition: env_rank e Save Files Paralleli

## Obiettivo
Eliminare la race condition con `n_envs=4` dove tutti gli env leggono/scrivono
lo stesso `current_game.json`, corrompendo silenziosamente il training.

---

## Posizione nella sequenza

```
File 11  → Simulatore Python ← eseguire prima di questo
► File 12 → QUESTO FILE — fix env_rank
  File 13 → Diagnostica training

File 08  → Headless Integration (Fase 2) — ha già env_rank al suo interno,
           ma introduce anche UncivHeadless che richiede headless.py.
           Eseguire DOPO che Fase 1.5 è completa.
```

> ⚠️ Il file `08_headless_integration.md` prevede una versione di `unciv_env.py`
> con `env_rank` + `UncivHeadless` insieme. Questo file aggiunge **solo `env_rank`**,
> senza toccare headless. Quando si eseguirà il file `08`, aggiornerà anche la
> parte headless dell'`__init__` — le due modifiche non si sovrappongono.

---

## Il problema

```
Env 0 legge current_game.json  → stato (turn=5, gold=52)
Env 1 legge current_game.json  → stesso stato
Env 0 simula, scrive           → (turn=6, gold=53)
Env 1 simula su dati vecchi, scrive → sovrascrive con (turn=6, gold=53)
Risultato: stati inconsistenti → reward corrotte → segnale RL rumoroso
```

---

## Soluzione: un save file per env

```
saves/
├── template_game.json     # read-only, mai modificato
├── current_game_0.json    # Env rank 0
├── current_game_1.json    # Env rank 1
├── current_game_2.json    # Env rank 2
├── current_game_3.json    # Env rank 3
└── current_game_4.json    # Eval env (rank = n_envs)
```

---

## File da modificare

| File | Modifiche |
|---|---|
| `src/envs/unciv_env.py` | Aggiungere `env_rank` — SOLO questo |
| `train.py` | Aggiornare `make_env` e creazione env |
| `tests/test_env.py` | Aggiornare fixture + aggiungere test race condition |
| `WORK_LOG.md` | Aggiornare al termine |

---

## Modifica 1: `src/envs/unciv_env.py`

### Aggiornare solo la firma di `__init__` e `self.save_path`

Trovare:
```python
def __init__(self, config_path: str = "config/default_config.yaml", render_mode=None) -> None:
```

Sostituire con:
```python
def __init__(
    self,
    config_path: str = "config/default_config.yaml",
    env_rank: int = 0,
    render_mode: Optional[str] = None,
) -> None:
```

Trovare la riga che imposta `self.save_path` (contiene `current_game.json`):
```python
self.save_path = Path(self.config["paths"]["unciv_saves"]) / "current_game.json"
```

Sostituire con:
```python
self.env_rank = env_rank
self.save_path = Path(self.config["paths"]["unciv_saves"]) / f"current_game_{env_rank}.json"
```

> ⚠️ Queste sono le UNICHE due modifiche a `unciv_env.py` in questo file.
> NON aggiungere `UncivHeadless` — arriverà con il file `08`.
> NON modificare `observation_space`, `action_space`, o altri metodi.
> La firma con `env_rank=0` mantiene retrocompatibilità con i test esistenti.

---

## Modifica 2: `train.py`

### Sostituire la funzione `make_env`

Trovare la funzione `make_env` esistente e sostituirla con:

```python
def make_env(config_path: str, rank: int = 0):
    """
    Factory function per make_vec_env.
    Ogni env riceve rank univoco → save file separato → no race condition.
    """
    def _init():
        env = UncivEnv(config_path=config_path, env_rank=rank)
        return Monitor(env)
    return _init
```

### Aggiornare la creazione di `env` e `eval_env` nella funzione `train`

Trovare dove viene creato `env` (cerca `make_vec_env`) e sostituire con:

```python
n_envs = tc["n_envs"]

env = make_vec_env(
    [make_env(config_path, rank=i) for i in range(n_envs)],
    n_envs=n_envs,
)
# L'eval env usa rank=n_envs per non sovrapporsi ai training env
eval_env = make_vec_env(
    [make_env(config_path, rank=n_envs)],
    n_envs=1,
)
```

---

## Modifica 3: `tests/test_env.py`

### Aggiornare la fixture `env` (passare `env_rank=0` esplicitamente)

Trovare la fixture:
```python
@pytest.fixture
def env(tmp_path):
    ...
    return UncivEnv(config_path=str(config_path))
```

Aggiornare a:
```python
@pytest.fixture
def env(tmp_path):
    ...
    return UncivEnv(config_path=str(config_path), env_rank=0)
```

### Aggiungere test race condition

```python
def test_env_rank_uses_separate_save_files(tmp_path):
    """Due env con rank diversi devono usare save file separati."""
    import yaml
    config = {
        "training": {"total_timesteps": 1000},
        "environment": {"max_turns": 50, "map_size": "tiny", "victory_type": "science"},
        "paths": {
            "save_dir": str(tmp_path / "models"),
            "log_dir": str(tmp_path / "logs"),
            "unciv_saves": str(tmp_path / "saves"),
        }
    }
    config_path = tmp_path / "config.yaml"
    with open(config_path, 'w') as f:
        yaml.dump(config, f)

    env0 = UncivEnv(config_path=str(config_path), env_rank=0)
    env1 = UncivEnv(config_path=str(config_path), env_rank=1)

    assert env0.save_path != env1.save_path
    assert "current_game_0" in str(env0.save_path)
    assert "current_game_1" in str(env1.save_path)
```

---

## Checklist esecuzione

```
Step 1  → Assicurati che il file 11 sia completato e i test passino
Step 2  → Modifica unciv_env.py (SOLO firma __init__ + save_path)
Step 3  → pytest tests/test_env.py -v  ← deve passare
Step 4  → Modifica train.py (make_env + env creation)
Step 5  → pytest tests/ -v  ← TUTTI devono passare
Step 6  → python train.py
          Verifica che in saves/ compaiano:
          current_game_0.json, current_game_1.json, current_game_2.json, current_game_3.json
Step 7  → Aggiorna WORK_LOG.md
Step 8  → Includi nel commit del file 11 (stesso commit ok):
          git add -A
          git commit -m "fix: race condition n_envs con env_rank separati"
          git push
```

---

## Note per Claude Code
- `env_rank=0` come default garantisce che i test esistenti (che non passano rank)
  continuino a funzionare senza modifiche aggiuntive
- Il file `08_headless_integration.md` include già `env_rank` nella sua versione
  dell'`__init__` — quando verrà eseguito, troverà già il parametro presente e
  dovrà solo aggiungere la logica `UncivHeadless` (non è un conflitto, è additivo)
- `template_game.json` rimane invariato e read-only
- I file `current_game_N.json` sono già coperti da `.gitignore` (pattern `saves/`)
