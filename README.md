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
├── config.py               ← lee el .env + helpers
├── .env                    ← TU configuración (no se sube a git)
├── .env.example            ← plantilla para copiar
├── requirements.txt
├── README.md
├── .gitignore
│
├── orquestador/            ← código interno
│   ├── audio_processor.py
│   ├── diarization.py
│   ├── speaker_registry.py
│   ├── task_ownership.py
│   ├── project_input.py
│   ├── project_manager.py
│   ├── docs_manager.py
│   ├── git_automation.py
│   └── hotkeys.py
│
├── docs/                   ← salidas de cada reunión
├── .voice_profiles/        ← biblioteca de voces (local)
├── .tmp_audio/             ← WAV temporales
└── .venv/                  ← entorno virtual
```

| Archivo | ¿Lo editas? | Qué es |
|---------|-------------|--------|
| `.env` | **Sí** | Toda tu configuración (nombre, rutas, flags, token) |
| `.env.example` | Consulta | Plantilla sin secretos |
| `config.py` | Casi nunca | Carga el `.env` |
| `main.py` | Casi nunca | Punto de entrada |
| `orquestador/` | Solo si desarrollas | Lógica interna |
| `docs/` | Consultas | Resultados de reuniones |

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
copy .env.example .env
# Edita .env: USUARIO_LOCAL, rutas, HF_TOKEN si usas pyannote
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

## Configuración — archivo `.env`

Toda la configuración editable vive en **`.env`** (en la raíz del proyecto).  
`config.py` solo la lee y mantiene aliases/helpers.

1. Copia el ejemplo:

```powershell
copy .env.example .env
```

2. Edita `.env` con Bloc de notas / Cursor.  
3. **No subas `.env` a git** (ya está en `.gitignore`). Sí se versiona `.env.example`.

### Variables principales

| Variable | Ejemplo | Para qué |
|----------|---------|----------|
| `USUARIO_LOCAL` | `Felipe` | Tu nombre (canal mic) |
| `PARTICIPANTES_CONOCIDOS` | `Felipe,Ana,Carlos` | Sugerencias al escribir nombres (coma) |
| `OLLAMA_LLM` | `ollama/qwen2.5-coder:7b` | Modelo de agentes |
| `WHISPER_MODEL` | `small` | Modelo Whisper |
| `HOTKEY` | `ctrl+shift+r` | Atajo grabar/parar |
| `AUTO_GIT_COMMIT` | `true` | Ofrecer Git en repo producto |
| `CONFIRMAR_RESPONSABLES` | `true` | Preguntar dueño si falta |
| `NOMBRAR_REMOTOS` | `true` | Identificar Remoto_N tras grabar |
| `USAR_RECONOCIMIENTO_VOZ` | `true` | Biblioteca `.voice_profiles/` |
| `VOICE_AUTO_APPLY` | `true` | Asignar nombre solo si hay confianza |
| `VOICE_MATCH_THRESHOLD` | `0.72` | Umbral para sugerir |
| `VOICE_AUTO_THRESHOLD` | `0.78` | Umbral para auto-asignar |
| `USE_PYANNOTE` | `true` | Separar varias voces remotas |
| `HF_TOKEN` | `hf_...` | Token Hugging Face (secreto) |
| `RUTA_VIGO_WEB` | ruta absoluta | Repo front VIGO |
| `RUTA_VIGO_API` | ruta absoluta | Repo API VIGO |
| `RUTA_PIPELINES` | ruta absoluta | Repo pipelines |

Valores booleanos: `true` / `false` (también acepta `1`/`0`, `yes`/`no`).

Token HF: puedes ponerlo en `.env` **o** en la sesión:

```powershell
$env:HF_TOKEN = "hf_..."
```

(La variable de entorno del sistema no la pisa el `.env` por defecto.)

### Biblioteca de voces (active learning)

1. Primera vez → escribes el nombre de `Remoto_N` → se crea perfil en `.voice_profiles/`.  
2. Próximas → si la voz coincide (≥ `VOICE_AUTO_THRESHOLD`) se asigna **sola**.  
3. Persona nueva → pregunta → nuevo perfil. Se puede repetir sin límite.

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
