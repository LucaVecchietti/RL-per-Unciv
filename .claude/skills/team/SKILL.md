---
name: team
description: Orchestra il team di sub-agenti project-scoped (unciv-engine, rl-trainer, tests-engineer, docs-keeper) in due modalità — `implement <descrizione task>` per implementazioni multi-agente coordinate, `plan` per analizzare lo stato, decidere i prossimi passi e scrivere il prossimo file di spec numerato in md_file_x_claude_code/. Usa quando il lavoro attraversa più domini (motore Kotlin + RL + test + docs) o richiede pianificazione strutturata.
---

# /team — Orchestratore del team di sub-agenti

Coordina i 4 sub-agenti project-scoped definiti in `.claude/agents/`. Due modalità: `implement` ed `plan`. La modalità è il **primo token** degli argomenti.

## Agenti disponibili (tabella di routing)

| Dominio | Agente | Tools tipici |
|---|---|---|
| Fork Kotlin Unciv, protocollo `--server` in `DesktopLauncher.kt`, rebuild JAR (`gradlew desktop:dist`), parsing campi del save, `ruleset_reader.py` | `unciv-engine` | Edit/Read/Bash su `unciv/`, smoke JVM |
| `src/envs/unciv_env.py`, `src/utils/reward.py`, action masking, `to_observation_vector`, callbacks/metriche, `train.py`, interpretazione log training | `rl-trainer` | Edit/Read/Bash su `src/` e `train.py` |
| Suite `tests/`, mock di `UncivHeadless`, shape/contract asserts (tabella in CLAUDE.md), TDD, restore green dopo regressione | `tests-engineer` | Edit/Read/Bash su `tests/`, esecuzione pytest |
| `WORK_LOG.md`, `CLAUDE.md` (regole + tabella contratti), `md_file_x_claude_code/*.md` | `docs-keeper` | Edit/Read sui doc, niente codice di produzione |

**Regola di scope**: ogni agente tocca solo il suo dominio. Sovrapposizioni note:
- `state_parser.py`: `unciv-engine` possiede i campi letti dal save; `rl-trainer` possiede `to_observation_vector`.
- `headless.py`: `unciv-engine` aggiunge wrapper Python quando aggiunge un comando server; `rl-trainer` li chiama.
- Test del proprio dominio: ognuno coordina con `tests-engineer`.

---

## Modalità `implement <descrizione del task>`

Distribuisci il task agli agenti giusti, in parallelo dove possibile, poi consolida con suite verde e commit.

### Flusso obbligatorio

1. **Inquadra il task in ≤100 parole.** Prima di delegare nulla, dichiara nella chat:
   - dominio/i coinvolto/i
   - quali contratti della tabella in `CLAUDE.md` toccano (obs vector shape, action space, save path, headless commands, civ name)
   - se richiede rebuild JAR (qualunque modifica Kotlin → sì)
   - prerequisiti / blocker noti

2. **Mappa agenti → sotto-task.** Esempio canonico per una feature nuova end-to-end:
   - `unciv-engine`: aggiungi comando server + smoke + rebuild JAR
   - `rl-trainer`: aggiungi wrapper Python + masking + reward + obs (se serve)
   - `tests-engineer`: scrivi/aggiorna test (TDD prima, oppure regressivo dopo)
   - `docs-keeper`: aggiorna WORK_LOG + CLAUDE.md (solo a fine)

3. **Lancia in parallelo i sotto-task indipendenti.** Sequenziale solo se c'è dipendenza dura (es. wrapper Python ha bisogno del comando Kotlin già committato).

4. **Brief degli agenti — obbligatorio includere:**
   - cosa fare (input + output atteso)
   - path:linea dei file da toccare
   - vincoli (es. "non modificare la tabella contratti", "non rompere `to_observation_vector` shape (61,)")
   - se è solo ricerca o anche scrittura codice
   - lingua: italiano

5. **Verifica end-to-end inline** (non delegare la verifica):
   - leggi i diff effettivi prodotti dagli agenti (la loro summary descrive l'intento, non il fatto)
   - esegui la suite: `.venv\Scripts\python -m pytest tests/ -q`
   - mostra l'output testualmente, non interpretarlo
   - se la suite è rossa: rilancia `tests-engineer` con il fail specifico oppure fixa inline. **Non chiudere con suite rossa** (regola 8 CLAUDE.md)

6. **Chiusura via `docs-keeper`**: nuova sessione in `WORK_LOG.md` (file modificati con tipo, fatto, test, TODO prossima sessione). Aggiorna `CLAUDE.md` solo se sono cambiati contratti.

7. **Commit + push.** Conventional commit (`feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:`). Niente `--no-verify`. Push obbligatorio (regola di chiusura sessione CLAUDE.md).

### Regole anti-deriva

- Mai delegare senza brief completo. Prompt vaghi → output vago.
- Mai accettare risultati senza verifica (leggi i diff, esegui i test, valuta le metriche).
- Mai mischiare scope: se un agente trova un bug fuori scope, va segnalato nel report ma non corretto in questa sessione.
- Mai aggiornare la tabella contratti di `CLAUDE.md` se i contratti non sono effettivamente cambiati.

---

## Modalità `plan`

Analizza lo stato e produci il prossimo file di spec numerato `md_file_x_claude_code/NN_<slug>.md` (slug kebab-case). NN = ultimo numero in `md_file_x_claude_code/` + 1.

### Flusso obbligatorio

1. **Discovery in parallelo** — lancia tutti e quattro con brief specifici:

   - `rl-trainer`: 
     - leggi metriche ultimo run da `logs/MaskablePPO_<N>/` via TensorBoard event_accumulator
     - identifica metriche in trend cattivo / piatte
     - copertura attuale action space e obs vector
     - rischi noti aperti (es. units_stuck, masking, reward shaping)
     - output: ≤300 parole

   - `unciv-engine`: 
     - inventario comandi `--server` esistenti in `DesktopLauncher.kt`
     - campi del save sfruttati vs disponibili (con riferimenti `Tile.kt`, `MapUnit.kt`, ecc.)
     - gap noti / known issues lato JVM
     - output: ≤300 parole

   - `tests-engineer`: 
     - copertura test attuale (per modulo)
     - contratti della tabella CLAUDE.md non coperti da test
     - test fragili / dipendenti da fixture instabili
     - output: ≤200 parole

   - `docs-keeper`: 
     - ultima sessione `WORK_LOG.md` (data + TODO espliciti rimasti aperti)
     - stato `CLAUDE.md` tabella contratti
     - ultimo numero NN in `md_file_x_claude_code/` (= numero da usare + 1)
     - output: ≤200 parole

2. **Sintesi.** Dai 4 report, produci:
   - blocker attuali (cosa impedisce il prossimo step)
   - 2-3 candidati per il prossimo task con pro/contro misurabili
   - opzione raccomandata + 1-2 frasi di motivazione

3. **Presenta all'utente** sintesi + opzioni e **attendi conferma**. Non scrivere il file di spec prima della conferma.

4. **Su conferma**, delega a `docs-keeper` la scrittura di `md_file_x_claude_code/NN_<slug>.md` con questa struttura (allineata ai file 19-23 esistenti):
   - **Obiettivo** (1-3 righe)
   - **Contesto / motivazione** (riferimenti a sessioni WORK_LOG e metriche/dati)
   - **Prerequisiti** (link a file di spec precedenti, se applicabile)
   - **Modifiche per file** (path + cosa cambia + perché)
   - **Contratti coinvolti** (cosa nella tabella CLAUDE.md cambia, se cambia)
   - **Test richiesti** (esempi concreti, riferimenti a fixture esistenti)
   - **Criteri di accettazione** (smoke + suite verde + metriche misurabili)
   - **Rischi / open questions**
   - **Validazione richiesta** prima del merge

5. `docs-keeper` aggiunge una entry di planning in `WORK_LOG.md` (sessione tipo "Pianificazione File NN — opzione X scelta").

6. **Commit + push** di `md_file_x_claude_code/NN_<slug>.md` + `WORK_LOG.md`. Conventional commit `docs: spec File NN — <slug>`.

### Regole anti-deriva

- Non saltare la discovery — un file spec senza analisi è scope creep.
- NN = ultimo + 1, sempre. Verifica con `ls md_file_x_claude_code/` prima di scrivere.
- Slug = kebab-case, descrittivo dell'obiettivo (es. `24_diagnose_units_stuck.md`, non `24_next_step.md`).
- La spec NON contiene codice eseguibile completo — solo indicazioni puntuali (path:linea, snippet di firma di funzione, contratto atteso). L'implementazione è di `implement`.

---

## Contesto del progetto (sempre applicabile)

- **Venv**: `C:\Users\lucav\Desktop\RL-per-Unciv\.venv` — `.venv\Scripts\python` per qualsiasi cosa Python. Mai Python di sistema.
- **Test**: `.venv\Scripts\python -m pytest tests/ -q`
- **Save files**: `saves/current_game_{rank}.json` (env paralleli, una JVM per rank)
- **Contratti critici** (tabella in CLAUDE.md): obs `(61,)` float32, action `Discrete(23)`, civ `"India"`, save path pattern, headless commands.
- **Lingua**: italiano per messaggi, log, spec, commit.
- **Convention commits**: `feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:`.
- **Zero debiti a fine sessione** (regola 8 CLAUDE.md): ogni bug/regression/test rosso introdotto in sessione va chiuso prima del commit finale.
