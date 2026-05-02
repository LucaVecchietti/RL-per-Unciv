# 08 — Unciv Fork + Headless CLI

## Obiettivo

Creare un fork di Unciv che aggiunge argomenti CLI per avanzamento turno
programmatico. Questo è il **prerequisito fondamentale** per tutto il training reale.

**Problema:** Unciv ufficiale non supporta `--advance-turn`. La modalità `headless`
è un server multiplayer, non un tool di automazione single-player.

**Soluzione:** Fork Unciv (open source Kotlin), aggiungere ~80 righe in
`DesktopLauncher.kt` per abilitare il ciclo:
```
Python → scrive azione in JSON → java -jar Unciv_fork.jar --advance-turn --save-file X → Unciv avanza turno → Python legge nuovo stato
```

---

## Prerequisiti

- JDK installato (`C:\Program Files\Eclipse Adoptium\jdk-25.0.3.9-hotspot\bin\java.exe`)
- Git installato
- ~3GB spazio disco (repo Unciv + build)
- Connessione internet per clone + dipendenze Gradle

---

## Step 1 — Clone Unciv

```powershell
# Clona nella root del progetto RL
cd "C:\Users\Luca Vecchietti\Desktop\RL-per-Unciv"
git clone https://github.com/yairm210/Unciv.git unciv-src
cd unciv-src
```

Verificare che il build funzioni prima di modificare:
```powershell
.\gradlew desktop:dist
```
Output atteso: `unciv-src/desktop/build/libs/Unciv.jar`

> ⚠️ Il build richiede 5-15 minuti al primo avvio (scarica dipendenze Gradle).

---

## Step 2 — Comprendere la struttura

File rilevanti:
```
unciv-src/
├── desktop/src/com/unciv/app/desktop/
│   └── DesktopLauncher.kt   ← entry point desktop, QUI aggiungiamo il CLI
├── core/src/com/unciv/
│   ├── UncivGame.kt          ← classe principale del gioco
│   ├── logic/GameInfo.kt     ← stato della partita, ha nextTurn()
│   └── files/UncivFiles.kt   ← load/save partite
```

Leggere `DesktopLauncher.kt` per capire come viene gestito il ramo `headless`
esistente prima di aggiungere il nuovo ramo `--advance-turn`.

---

## Step 3 — Modificare DesktopLauncher.kt

Aprire `unciv-src/desktop/src/com/unciv/app/desktop/DesktopLauncher.kt`.

Trovare il blocco `fun main(args: Array<String>)` e aggiungere il ramo
`--advance-turn` **prima** del ramo `headless` esistente:

```kotlin
fun main(args: Array<String>) {

    // --- NUOVO RAMO: avanzamento turno headless per RL training ---
    if (args.contains("--advance-turn")) {
        val saveFileIndex = args.indexOf("--save-file")
        if (saveFileIndex < 0 || saveFileIndex + 1 >= args.size) {
            println("Uso: Unciv.jar --advance-turn --save-file <path>")
            System.exit(1)
        }
        val savePath = java.io.File(args[saveFileIndex + 1])
        if (!savePath.exists()) {
            println("Save file non trovato: ${savePath.absolutePath}")
            System.exit(1)
        }

        val headlessConfig = com.badlogic.gdx.backends.headless.HeadlessApplicationConfiguration()
        com.badlogic.gdx.backends.headless.HeadlessApplication(
            object : com.badlogic.gdx.ApplicationAdapter() {
                override fun create() {
                    try {
                        val gameInfo = com.unciv.UncivGame.Current.files.loadGameFromFile(savePath)
                        gameInfo.nextTurn()
                        com.unciv.UncivGame.Current.files.saveGame(gameInfo, savePath.path)
                        println("Turn advanced. New turn: ${gameInfo.turns}")
                    } catch (e: Exception) {
                        System.err.println("Errore avanzamento turno: ${e.message}")
                        com.badlogic.gdx.Gdx.app.exit()
                        System.exit(1)
                    }
                    com.badlogic.gdx.Gdx.app.exit()
                }
            },
            headlessConfig
        )
        return
    }
    // --- FINE NUOVO RAMO ---

    // ... resto del main esistente invariato ...
}
```

> ⚠️ **Nota implementativa:** Le API esatte (`loadGameFromFile`, `saveGame`,
> `UncivGame.Current`) dipendono dalla versione di Unciv clonata. Leggere il
> sorgente reale prima di scrivere il codice definitivo. Lo snippet sopra è
> orientativo — adattare ai nomi effettivi trovati nel sorgente.

---

## Step 4 — Aggiungere dipendenza headless LibGDX

In `unciv-src/desktop/build.gradle.kts` verificare che sia presente
la dipendenza `gdx-backend-headless`. Se mancante, aggiungerla:

```kotlin
dependencies {
    // ... dipendenze esistenti ...
    implementation("com.badlogicgames.gdx:gdx-backend-headless:${gdxVersion}")
    implementation("com.badlogicgames.gdx:gdx:${gdxVersion}")
}
```

---

## Step 5 — Build JAR custom

```powershell
cd "C:\Users\Luca Vecchietti\Desktop\RL-per-Unciv\unciv-src"
.\gradlew desktop:dist
```

Copiare JAR custom nella cartella del progetto RL:
```powershell
Copy-Item "desktop\build\libs\Unciv.jar" "..\unciv\Unciv.jar" -Force
```

---

## Step 6 — Verificare che funzioni

Test manuale dal terminale (dalla root del progetto RL):

```powershell
& "C:\Program Files\Eclipse Adoptium\jdk-25.0.3.9-hotspot\bin\java.exe" `
  -jar unciv\Unciv.jar `
  --advance-turn `
  --save-file saves\template_game.json
```

Output atteso:
```
Turn advanced. New turn: 3
```

Se funziona, il save file `template_game.json` avrà il turno incrementato.

---

## Step 7 — Aggiornare config e headless.py

**`config/default_config.yaml`** — aggiungere `java_path`:
```yaml
unciv:
  jar_path: "unciv/Unciv.jar"
  java_path: "C:/Program Files/Eclipse Adoptium/jdk-25.0.3.9-hotspot/bin/java.exe"
  headless_timeout: 60    # aumentato: JVM startup ~5s
  saves_prefix: "current_game"
```

**`src/utils/headless.py`** — rendere `java_path` configurabile:
```python
def __init__(self, jar_path: str, timeout: int = 60, java_path: str = "java") -> None:
    self.jar_path = Path(jar_path)
    self.java_path = java_path
    self.timeout = timeout
    self._validate_jar()

def advance_turn(self, save_path: Path) -> None:
    result = subprocess.run(
        [
            self.java_path, "-jar", str(self.jar_path),
            "--advance-turn",
            "--save-file", str(save_path),
        ],
        ...
    )
```

**`src/envs/unciv_env.py`** — passare `java_path` a UncivHeadless:
```python
java_path = unciv_cfg.get("java_path", "java")
self.headless = UncivHeadless(jar_path=jar_path, timeout=timeout, java_path=java_path)
```

---

## Step 8 — Ottimizzare JVM startup (opzionale)

JVM impiegha ~3-5 secondi per avviarsi. Con n_envs=4 e 150 turni/episodio:
`5s × 4 env × ~1000 episodi = ~6 ore solo di startup JVM`.

Soluzione: **JVM persistente** — avviare Unciv come processo long-running
che riceve comandi via stdin/socket invece di riavviarsi ogni turno.

```
Python → scrive comando in stdin: "advance current_game_0.json"
Unciv fork (long-running) → avanza turno → scrive "done" su stdout
Python → legge "done" → continua
```

Questo riduce overhead a <100ms/turno.

> Implementare DOPO aver verificato che il ciclo base funziona.
> Spec dettagliata in un file separato quando necessario.

---

## Step 9 — Prima run training con Unciv reale

```powershell
# Dalla root del progetto RL
.venv\Scripts\python train.py
```

Monitorare:
- Nessun crash (subprocess headless funziona)
- `ep_rew_mean` cresce (Unciv reale produce reward corrette)
- Tempo medio per turno (`unciv/turn_time_ms` su TensorBoard) < 10s

---

## Checklist

```
[ ] Unciv clonato in unciv-src/
[ ] Build originale funziona (gradlew desktop:dist)
[ ] DesktopLauncher.kt modificato (leggere API reale prima)
[ ] Build custom funziona
[ ] Test manuale --advance-turn su template_game.json
[ ] config.yaml aggiornato (java_path, headless_timeout=60)
[ ] headless.py aggiornato (java_path configurabile)
[ ] unciv_env.py aggiornato (passa java_path)
[ ] test_headless.py aggiornato (java_path nei test)
[ ] python -m pytest tests/ -v → tutti verdi
[ ] python train.py → nessun crash, reward cresce
```

---

## Note per Claude Code

- **Leggere il sorgente Unciv prima di scrivere Kotlin** — le API cambiano tra versioni.
  Cercare `loadGameFromFile`, `saveGame`, `nextTurn` nel sorgente clonato.
- Il ramo `--advance-turn` va aggiunto PRIMA del ramo `headless` esistente.
- `HeadlessApplication` di LibGDX non renderizza nulla — sicuro per server/CI.
- Se `UncivGame.Current` non è inizializzato in headless mode, serve istanziarlo
  prima di chiamare `files.loadGameFromFile()`.
- Loggare il tempo medio turno su TensorBoard: se >10s il training è impraticabile.
- **Non toccare** `test_env.py`, `test_simulator.py`, `test_reward.py` — già verdi.
