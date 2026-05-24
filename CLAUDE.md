# CLAUDE.md — Contesto progetto per Claude Code

## Progetto
Agente RL per Unciv (clone open-source di Civilization V).
L'agente impara a giocare tramite Reinforcement Learning (PPO + self-play).
Interfaccia con Unciv tramite file JSON di salvataggio.

## Stack tecnico
- **Python** 3.11+
- **Virtual env:** `C:\Users\lucav\Desktop\RL-per-Unciv\.venv` — **usa SEMPRE questo venv** per test, training, script e qualsiasi comando Python. Non usare il Python di sistema. Esempi: `.venv\Scripts\python -m pytest tests/ -v`, `.venv\Scripts\python train.py`
- **RL Framework:** Stable-Baselines3 v2+ (PPO)
- **Ambiente:** Gymnasium (non gym legacy)
- **Monitoring:** TensorBoard
- **Config:** `config/default_config.yaml` — unica fonte di verità per iperparametri e path

## Struttura del progetto
```
unciv-rl-agent/
├── src/
│   ├── envs/unciv_env.py        # Ambiente Gymnasium custom
│   ├── agents/ppo_agent.py      # Logica agente PPO
│   ├── parsers/state_parser.py  # Lettura JSON Unciv → numpy
│   └── utils/
│       ├── reward.py            # Reward function (pura, no side effects)
│       ├── callbacks.py         # Callback TensorBoard custom
│       ├── analyze_run.py       # Analisi run senza TensorBoard
│       ├── simulator.py         # Micro-simulatore turno Unciv (Fase 1.5)
│       └── diagnose_run.py      # Diagnostica training e save file
├── config/default_config.yaml
├── models/checkpoints/          # Ignorato da git
├── logs/                        # Ignorato da git
├── saves/                       # Ignorato da git
├── tests/
├── train.py                     # Entry point training
├── evaluate.py                  # Valutazione modello salvato
├── WORK_LOG.md                  # Diario sessioni — aggiornare sempre
└── CLAUDE.md                    # Questo file
```

## Regole di sviluppo
1. **Leggi prima di scrivere** — prima di modificare un file esistente, leggilo per intero
2. **Un file per volta** — implementa solo il file richiesto esplicitamente
3. **Nessun valore hardcoded** — tutto in `config/default_config.yaml`
4. **Type hints ovunque** — ogni funzione pubblica deve avere type hints completi
5. **Docstring obbligatorie** — ogni classe e metodo pubblico deve avere docstring
6. **Test prima del fix** — se un test fallisce, non modificare il test, correggi il codice
7. **Niente codice extra** — non aggiungere funzionalità non richieste esplicitamente
8. **Zero debiti a fine sessione** — ogni bug, regression o test fallito introdotto o scoperto durante la sessione deve essere risolto **prima** di chiudere la sessione corrente. Non chiudere mai una sessione con la suite rossa per modifiche fatte in quella sessione

## Contratti critici tra moduli
| Contratto | Valore attuale | File coinvolti |
|---|---|---|
| Dimensione observation vector | `(57,)` float32 | `state_parser.py` ↔ `unciv_env.py` |
| Numero azioni | `22` (Discrete) — 9 edifici + 5 unità + skip + 6 direzioni hex + FoundCity | `unciv_env.py` ↔ `train.py` |
| Nome civilizzazione default | `"India"` | `state_parser.py`, `unciv_env.py` |
| Save file per env | `saves/current_game_{rank}.json` | `unciv_env.py` ↔ `train.py` |
| Advance turn | `UncivHeadless` in `_advance_turn` | `headless.py` ↔ `unciv_env.py` |

> ⚠️ Se modifichi uno di questi valori, aggiorna **tutti** i file coinvolti e la tabella qui sopra.

## Fasi di sviluppo
- [x] **Fase 1** — Gestione singola città (produzione, tech, oro, happiness)
- [x] **Fase 1.5** — Micro-simulatore Python (reward reali, training rapido)
- [ ] **Fase 2** — Unciv Headless + espansione (File 08-10)
- [ ] **Fase 3** — Combattimento (unità militari)
- [ ] **Fase 4** — Diplomazia + vittoria completa

## Stato training corrente

| Run | Timesteps | ep_rew_mean | Note |
|---|---|---|---|
| Fase 1 (stub JSON) | ~16k | ~-1.1 | Nessun segnale reale |
| Fase 1.5 (simulatore) | in corso | TBD | Reward da simulazione Python |

> Aggiornare dopo ogni run significativo.

## Metodo di lavoro — Seguire sempre questo flusso

### Fase 1 — Orientamento (inizio sessione obbligatorio)
1. Leggi `CLAUDE.md` (questo file)
2. Leggi `WORK_LOG.md` — identifica l'ultima sessione e i TODO
3. **Scrivi un riepilogo di 3 righe** di dove siamo prima di toccare qualsiasi file:
   ```
   Stato attuale: [cosa è implementato]
   Obiettivo sessione: [cosa faremo oggi]
   File che toccherò: [lista esplicita]
   ```
4. Aspetta conferma prima di procedere

### Fase 2 — Implementazione (un task per volta)
1. **Leggi** il file `.md` di specifica relativo al task (es. `02_unciv_state_parser.md`)
2. **Leggi** i file esistenti che verranno modificati o che hanno dipendenze
3. **Pianifica** ad alta voce: "Creerò X, modificherò Y, lascerò intatto Z"
4. **Implementa** solo quanto pianificato — niente scope creep
5. **Mai** modificare più di un modulo per volta senza conferma esplicita

### Fase 3 — Verifica (dopo ogni implementazione)
1. Esegui i test del modulo appena scritto:
   ```bash
   python -m pytest tests/test_<modulo>.py -v
   ```
2. Se i test falliscono: correggi il codice, **mai** il test
3. Se non esistono test per quel modulo: scrivili prima dell'implementazione
4. Riporta l'output dei test testualmente — non interpretarlo, mostralo

### Fase 4 — Chiusura (fine sessione obbligatoria)
1. Esegui la suite completa: `python -m pytest tests/ -v`
2. Aggiorna `WORK_LOG.md` appendendo in cima una nuova voce con:
   - Data e ora
   - File modificati (con tipo: creato / modificato / eliminato)
   - Cosa è stato fatto (bullet points)
   - Problemi incontrati e come risolti
   - TODO espliciti per la prossima sessione
3. Conferma che `WORK_LOG.md` è aggiornato prima di considerare la sessione chiusa

---

## Regole di comunicazione

- **Prima di ogni azione** dichiara cosa stai per fare e perché
- **Se hai dubbi** su un requisito, chiedi — non assumere e non inventare
- **Se trovi un bug** fuori scope, segnalalo nel report ma non correggerlo nella stessa sessione
- **Se un task è ambiguo**, presenta 2 opzioni con pro/contro e aspetta scelta
- **Niente sorprese**: nessun file viene modificato senza averlo dichiarato prima

---

## Gestione degli errori

| Situazione | Comportamento corretto |
|---|---|
| Test fallisce | Analizza, correggi codice, NON il test |
| Import mancante | Aggiungi a `requirements.txt` e segnalalo |
| Contratto tra moduli rotto | Ferma tutto, segnala, aspetta istruzioni |
| File non trovato | Segnala il path esatto, non creare file non previsti |
| Comportamento ambiguo nelle spec | Chiedi, non assumere |

---

## Come iniziare ogni sessione
1. Leggi `CLAUDE.md` e `WORK_LOG.md`
2. Scrivi il riepilogo di orientamento (vedi Metodo → Fase 1)
3. Aspetta conferma prima di scrivere codice

## Come terminare ogni sessione
1. Esegui `.venv\Scripts\python -m pytest tests/ -v` e mostra output
2. **Risolvi ogni bug, regression o test fallito introdotto/scoperto nella sessione prima di proseguire** (vedi Regola di sviluppo 8) — non chiudere con la suite rossa
3. Aggiorna `WORK_LOG.md`
4. Elenca esplicitamente i TODO per la prossima sessione
5. **Fai git add, commit, push delle modifiche — obbligatorio, senza aspettare conferma.**

## Convenzione commit
Usa sempre il formato Conventional Commits:
- feat: nuova funzionalità
- fix: correzione bug
- docs: solo documentazione
- refactor: refactoring senza nuove feature
- test: aggiunta o modifica test
- chore: setup, config, dipendenze