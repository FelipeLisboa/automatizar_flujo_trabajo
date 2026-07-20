# Asistente de Reuniones (Orquestador)

Herramienta local para Windows que **graba tus reuniones** (Teams u otro audio del PC + tu micrófono), **separa quién habló**, te ayuda a **poner nombres a cada persona** (con biblioteca de voces que aprende sola), **extrae tareas con responsables** y genera un **prompt listo para pegar en Cursor**.

Opcionalmente crea la rama y el commit en el **repo del producto** (VIGO, pipelines, etc.). Este repositorio del orquestador **siempre permanece en `main`**.

**Repo:** https://github.com/FelipeLisboa/automatizar_flujo_trabajo  
**SO:** Windows 10/11

---

## Qué hace la app (en una frase)

**Graba → distingue tu voz de la de los demás → nombra remotos (aprendiendo caras de voz) → entiende tareas y dueños → deja el prompt en `docs/` → (si quieres) prepara la rama en el repo correcto.**

### Flujo completo

```
grabar (mic + sistema)
  → WAV mix / mic / sys
  → diarizar (tú vs Remoto_1, Remoto_2, …)
  → biblioteca de voces (auto o te pregunta nombres nuevos)
  → Whisper + agentes (Ollama / Qwen)
  → proyecto + responsables
  → docs/<proyecto>/<fecha>/
  → (opcional) Git en repo de producto
```

---

## Estructura del proyecto

```text
automatizar_flujo_trabajo/
│
├── main.py                 ← arranque: python main.py
├── config.py               ← TODA la configuración (edita aquí)
├── requirements.txt
├── README.md
├── .gitignore
│
├── orquestador/            ← código interno (no hace falta tocarlo a diario)
│   ├── audio_processor.py  ← captura mic + loopback, Whisper
│   ├── diarization.py      ← mic=tú / sys=remotos + pyannote
│   ├── speaker_registry.py ← nombres Remoto_N + biblioteca de voces
│   ├── task_ownership.py   ← responsables de tareas
│   ├── project_input.py    ← detección / consola de proyecto
│   ├── project_manager.py  ← agentes CrewAI
│   ├── docs_manager.py     ← escribe docs/
│   ├── git_automation.py   ← rama/commit en repos producto
│   └── hotkeys.py          ← Ctrl+Shift+R
│
├── docs/                   ← salidas de cada reunión
│   └── <proyecto>/<fecha>/
│         prompt_cursor.md
│         transcripcion.txt
│         transcripcion_diarizada.txt
│         meta.json
│         audio_reunion.wav
│
├── .voice_profiles/        ← biblioteca de voces (local, no se sube a git)
├── .tmp_audio/             ← WAV temporales mientras grabas
└── .venv/                  ← entorno virtual (recomendado)
```

| Carpeta / archivo | ¿Lo editas? | Qué es |
|-------------------|-------------|--------|
| `config.py` | **Sí** | Tu nombre, rutas, flags de voz/Git |
| `main.py` | Casi nunca | Punto de entrada |
| `orquestador/` | Solo si desarrollas | Lógica interna |
| `docs/` | Consultas | Resultados de reuniones |
| `.voice_profiles/` | Automático | Perfiles Ana.npy, Carlos.npy, … |

---

## Instalación desde cero

### 1. Git

https://git-scm.com/download/win → instalar → reiniciar PowerShell → `git --version`

### 2. Python 3.12+

https://www.python.org/downloads/ → marcar **Add python.exe to PATH** → reiniciar PowerShell:

```powershell
python --version
python -m pip --version
```

### 3. Clonar el repo

```powershell
cd $HOME\Documents
git clone https://github.com/FelipeLisboa/automatizar_flujo_trabajo.git
cd automatizar_flujo_trabajo
```

### 4. Entorno virtual (recomendado)

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Si PowerShell bloquea scripts:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

### 5. Dependencias

```powershell
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

### 6. Ollama (IA local)

1. https://ollama.com/download → instalar y dejarlo abierto  
2. Descargar el modelo:

```powershell
ollama pull qwen2.5-coder:7b
ollama list
```

### 7. Audio de Windows

- Reproducción **por defecto** = por donde suena Teams  
- Micrófono **por defecto** = el tuyo  
- Auriculares ayudan a evitar eco en el mic  

### 8. (Opcional) Varios remotos + biblioteca de voces

```powershell
python -m pip install pyannote.audio
```

Token HF: `$env:HF_TOKEN = "hf_..."`  

Acepta (logueado) en:

- https://huggingface.co/pyannote/speaker-diarization-3.1  
- https://huggingface.co/pyannote/segmentation-3.0  
- https://huggingface.co/pyannote/speaker-diarization-community-1  
- https://huggingface.co/pyannote/embedding  

---

## Configuración (`config.py`) — qué es cada “flag”

Un **flag** es una opción True/False o un número en `config.py`. No es un archivo aparte: abres `config.py` y cambias el valor.

### Identidad y equipo

| Variable | Ejemplo | Para qué |
|----------|---------|----------|
| `USUARIO_LOCAL` | `"Felipe"` | Tu nombre en la diarización (canal mic) |
| `PARTICIPANTES_CONOCIDOS` | `["Felipe", "Ana"]` | Solo **sugerencias** al escribir nombres (no asigna solo por orden) |

### Biblioteca de voces (active learning)

| Variable | Default | Para qué |
|----------|---------|----------|
| `NOMBRAR_REMOTOS` | `True` | Tras grabar, identificar Remoto_N (auto o pregunta) |
| `USAR_RECONOCIMIENTO_VOZ` | `True` | Usar `.voice_profiles/` para reconocer voces |
| `VOICE_AUTO_APPLY` | `True` | Si la voz es muy parecida → asigna el nombre **sin preguntar** |
| `VOICE_MATCH_THRESHOLD` | `0.72` | Similitud mínima para **sugerir** (0–1) |
| `VOICE_AUTO_THRESHOLD` | `0.78` | Similitud mínima para asignar **automático** |

**Cómo se usa en la práctica**

1. Primera vez que habla Ana → ves citas de `Remoto_1` → escribes `Ana` → se crea `.voice_profiles/Ana.npy`.  
2. Próxima reunión → si la voz coincide (≥ 0.78) → `Remoto_1 → Ana` solo, y el perfil se refuerza.  
3. Persona nueva → no hay match → te pregunta → escribes el nombre → nuevo perfil. Se puede repetir indefinidamente.

Si `VOICE_AUTO_APPLY = False`, siempre pregunta (aunque sugiera el nombre).  
Si `USAR_RECONOCIMIENTO_VOZ = False`, solo nombrado manual (sin biblioteca).

### Diarización remota (pyannote)

| Variable | Default | Para qué |
|----------|---------|----------|
| `USE_PYANNOTE` | `True` | Separar varias voces en el audio de Teams (`Remoto_1`, `Remoto_2`, …) |
| `HF_TOKEN` | `""` | Mejor usar `$env:HF_TOKEN` (no subas el token a git) |

Sin pyannote sigue funcionando: tú vs un solo `Remoto`.

### Whisper, agentes, Git

| Variable | Default | Para qué |
|----------|---------|----------|
| `WHISPER_MODEL` | `"small"` | Modelo de transcripción (`medium` = más preciso/lento) |
| `OLLAMA_LLM` | `"ollama/qwen2.5-coder:7b"` | Modelo de los agentes |
| `AUTO_GIT_COMMIT` | `True` | Ofrecer crear rama/commit en repo de producto |
| `CONFIRMAR_RESPONSABLES` | `True` | Preguntar dueño de tarea si falta |
| `HOTKEY` | `"ctrl+shift+r"` | Atajo grabar/parar |
| `RECORDING_HEARTBEAT_SEC` | `10` | Cada cuántos segundos muestra `🔴 mm:ss` |
| `RUTAS_PROYECTOS` | rutas locales | Mapa clave → carpeta Git de cada producto |

---

## Levantar la app (día a día)

```powershell
cd $HOME\Documents\automatizar_flujo_trabajo
.\.venv\Scripts\Activate.ps1          # si usas venv
# Ollama debe estar abierto
$env:HF_TOKEN = "hf_..."              # solo si usas pyannote / voces
python main.py
```

Comandos: `grabar` · `parar` · `toggle` · `proyectos` · `docs` · `salir`  
Hotkey: `Ctrl+Shift+R` (a veces hace falta terminal como Administrador).

### Reunión típica

1. `grabar` (o hotkey)  
2. Habla con normalidad en Teams  
3. `parar` → Enter  
4. Si hay voces nuevas, nómbralas; si ya están en la biblioteca, se asignan solas  
5. Confirma proyecto / responsables / rama si pregunta  
6. Abre `docs\<proyecto>\<fecha>\prompt_cursor.md` en Cursor  

---

## Salida de una sesión

```text
docs/<proyecto>/<YYYY-MM-DD_HH-MM-SS>/
  prompt_cursor.md
  transcripcion.txt
  transcripcion_diarizada.txt
  meta.json
  audio_reunion.wav
```

Fallos tempranos: `docs/_fallidos/<fecha>/`.

---

## Solución rápida de problemas

| Problema | Qué hacer |
|----------|-----------|
| `python` no existe | Reinstalar con Add to PATH |
| Agentes fallan | ¿Ollama abierto? ¿`qwen2.5-coder:7b` en `ollama list`? |
| No se oye Teams | Salida default = dispositivo de Teams |
| Eco / basura en tu canal | Baja volumen auriculares; habla después del remoto |
| pyannote 403 | Acepta los 4 modelos HF + token |
| No reconoce voces | Primera vez hay que nombrar; acepta `pyannote/embedding` |
| Hotkey muerto | Admin o usa `grabar`/`parar` |

---

## Checklist

**Primera vez:** Git · Python · clone · venv · `pip install -r requirements.txt` · Ollama + modelo · editar `config.py` · (opcional) pyannote + token  

**Cada reunión:** Ollama · venv · `$env:HF_TOKEN` si aplica · `python main.py` · grabar/parar · usar el prompt en Cursor  

---

*https://github.com/FelipeLisboa/automatizar_flujo_trabajo*
