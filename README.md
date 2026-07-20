# Asistente de Reuniones (Orquestador)

Captura el audio de una reunión (**Teams / sistema + tu micrófono**), **diariza** quién habla, transcribe con Whisper, extrae tareas **con responsables** (agentes locales + Ollama) y genera un **prompt listo para Cursor** en `docs/`.

Opcionalmente crea rama y commit en el **repo del producto** (nunca en este orquestador). Este repo permanece siempre en `main`.

**Sistema soportado:** Windows 10/11 (captura WASAPI Loopback).

**Repo:** https://github.com/FelipeLisboa/automatizar_flujo_trabajo

---

## Índice

1. [Qué hace el flujo](#1-qué-hace-el-flujo)
2. [Instalación desde cero (sin Python ni nada)](#2-instalación-desde-cero-sin-python-ni-nada)
3. [Configurar el proyecto para ti](#3-configurar-el-proyecto-para-ti)
4. [Levantar la aplicación (día a día)](#4-levantar-la-aplicación-día-a-día)
5. [Uso en una reunión](#5-uso-en-una-reunión)
6. [Diarización y pyannote (varios remotos)](#6-diarización-y-pyannote-varios-remotos)
7. [Proyectos, docs y Git](#7-proyectos-docs-y-git)
8. [Arquitectura y configuración](#8-arquitectura-y-configuración)
9. [Solución de problemas](#9-solución-de-problemas)
10. [Checklist](#10-checklist)

---

## 1. Qué hace el flujo

```
Grabar (mic + audio del PC)
    → Guardar WAV mix / mic / sys
    → Diarizar (mic = tú, sistema = remotos)
    → Transcribir con Whisper (local)
    → Analizar con agentes CrewAI + Ollama (Qwen)
    → Resolver proyecto (audio o consola)
    → Confirmar responsables (si faltan)
    → Guardar sesión en docs/
    → (Opcional) Confirmar rama Y/N → Git en el repo del producto
```

| Etapa | Qué ocurre |
|--------|------------|
| **Captura** | Micrófono + audio del sistema (WASAPI Loopback: Teams, navegador, etc.) |
| **Diarización** | Mic → tu nombre; sistema → `Remoto` o `Remoto_N` (pyannote) |
| **Transcripción** | Whisper `small` en español |
| **Agentes** | Extraen proyecto, rama, tareas y responsables; generan prompt Cursor |
| **Docs** | `prompt_cursor.md`, transcripciones, `meta.json`, audio |
| **Git** | Solo en repos de producto mapeados, con confirmación |

### Requisitos de hardware / PC (recomendado)

| Recurso | Mínimo razonable |
|---------|------------------|
| RAM | 16 GB (8 GB puede ir justo con Whisper + Ollama) |
| Disco | ~10–15 GB libres (Python, modelos Whisper, Ollama, opcional pyannote) |
| CPU | Cualquier PC moderno; GPU NVIDIA ayuda pero **no es obligatoria** |
| Audio | Micrófono + salida de audio (auriculares o altavoces) |

---

## 2. Instalación desde cero (sin Python ni nada)

Sigue los pasos **en orden**. Todo se hace en **Windows** con **PowerShell**.

### Paso 0 — Abrir PowerShell

1. Tecla Windows → escribe `PowerShell` → Ábrelo.
2. (Opcional pero útil) Ejecutar como Administrador si más adelante el hotkey `Ctrl+Shift+R` no funciona.

---

### Paso 1 — Instalar Git (para clonar el repo)

1. Descarga: https://git-scm.com/download/win  
2. Instala con las opciones por defecto (marca “Add to PATH” si aparece).  
3. Cierra y vuelve a abrir PowerShell.  
4. Verifica:

```powershell
git --version
```

Debe mostrar algo como `git version 2.x.x`.

> Si no quieres Git: descarga el ZIP del repo en GitHub → Code → Download ZIP → descomprímelo en una carpeta fija.

---

### Paso 2 — Instalar Python 3.12+

1. Descarga el instalador oficial: https://www.python.org/downloads/  
   - Elige **Python 3.12** o superior (64-bit).
2. **Importante:** en el instalador marca:
   - **Add python.exe to PATH**
3. Instala y cierra/reabre PowerShell.
4. Verifica:

```powershell
python --version
python -m pip --version
```

Ejemplo esperado: `Python 3.12.x` y `pip 24.x`.

Si `python` no se reconoce:

- Reinstala marcando PATH, **o**
- Usa el launcher: `py -3.12 --version`

---

### Paso 3 — Obtener el código del orquestador

```powershell
cd $HOME\Documents
git clone https://github.com/FelipeLisboa/automatizar_flujo_trabajo.git
cd automatizar_flujo_trabajo
```

Anota la ruta (la usarás siempre). Ejemplo:

```text
C:\Users\TU_USUARIO\Documents\automatizar_flujo_trabajo
```

---

### Paso 4 — (Recomendado) Crear un entorno virtual

Así las dependencias no se mezclan con otros proyectos:

```powershell
cd $HOME\Documents\automatizar_flujo_trabajo
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Si PowerShell bloquea scripts:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
.\.venv\Scripts\Activate.ps1
```

Verás `(.venv)` al inicio de la línea. **Activa el venv cada vez** que abras una terminal nueva para usar la app.

Para salir del venv: `deactivate`

---

### Paso 5 — Instalar dependencias Python

Con el venv activo (o sin venv, si preferiste instalación global):

```powershell
cd $HOME\Documents\automatizar_flujo_trabajo
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Esto instala, entre otras:

- `openai-whisper` + `torch` (transcripción)
- `PyAudioWPatch` / `sounddevice` (captura de audio Windows)
- `crewai` (agentes)
- `keyboard` (hotkey)
- `numpy`, `scipy`

**La primera instalación puede tardar varios minutos** (sobre todo `torch` y Whisper).

#### Si falla `PyAudioWPatch` / audio

1. Asegúrate de estar en Windows 10/11 64-bit.  
2. Reintenta: `python -m pip install --upgrade PyAudioWPatch`  
3. Si sigue fallando, reinicia el PC tras instalar Python y vuelve a intentar.

---

### Paso 6 — Instalar Ollama (IA local para los agentes)

1. Descarga: https://ollama.com/download  
2. Instala Ollama en Windows.  
3. Ábrelo (debe quedar el icono en la bandeja del sistema).  
4. En PowerShell descarga el modelo que usa el proyecto:

```powershell
ollama pull qwen2.5-coder:7b
```

La descarga es grande (~4–5 GB). Verifica:

```powershell
ollama list
```

Debe aparecer `qwen2.5-coder:7b`.

Prueba rápida:

```powershell
ollama run qwen2.5-coder:7b "Di hola en una frase"
```

(Sal con `/bye` o Ctrl+C.)

> **Ollama debe estar abierto** cada vez que uses el orquestador. Si no, los agentes fallan.

---

### Paso 7 — (Opcional) pyannote para varios remotos en Teams

Sin esto ya funciona: **tú (mic) vs Remoto (PC)**.  
Actívalo solo si en Teams hay **varias personas** y quieres separarlas (`Remoto_1`, `Remoto_2`, …).

1. Cuenta en https://huggingface.co  
2. Token Read: https://huggingface.co/settings/tokens  
3. Acepta condiciones (logueado) en **estas tres** páginas:
   - https://huggingface.co/pyannote/speaker-diarization-3.1  
   - https://huggingface.co/pyannote/segmentation-3.0  
   - https://huggingface.co/pyannote/speaker-diarization-community-1  
4. Instala:

```powershell
python -m pip install pyannote.audio
```

5. En `config.py` deja `USE_PYANNOTE = True` (ya viene así por defecto en este repo).  
6. **No pongas el token en el archivo.** En cada sesión de PowerShell:

```powershell
$env:HF_TOKEN = "hf_TU_TOKEN_AQUI"
```

La primera vez descarga modelos extra y puede tardar.

Para desactivar: `USE_PYANNOTE = False` en `config.py`.

---

### Paso 8 — Ajustar Windows (audio)

1. **Configuración → Sistema → Sonido**
2. El dispositivo de **reproducción** por defecto debe ser el que usa Teams (auriculares/altavoces).
3. El **micrófono** por defecto debe ser el tuyo.
4. Volumen del sistema audible (el loopback captura lo que sale por el default).

Consejos:

- Auriculares ayudan a que tu mic **no grabe el eco** de Teams.
- Si Teams sale por un dispositivo y el default es otro, el orquestador **no** oirá la reunión.

---

## 3. Configurar el proyecto para ti

Edita `config.py` (Bloc de notas, VS Code o Cursor):

### Obligatorio / muy recomendado

```python
USUARIO_LOCAL = "TuNombre"   # cómo te etiqueta la diarización (canal mic)
```

```python
PARTICIPANTES_CONOCIDOS = [
    "TuNombre",
    # "Ana",
    # "Carlos",
]
```

### Rutas de tus repos de producto (para Git automático)

Cambia `RUTAS_PROYECTOS` a las carpetas reales de **tu** máquina:

```python
RUTAS_PROYECTOS = {
    "vigo_web": Path(r"C:\Users\TU_USUARIO\...\DET_MINCO_PCE_Web"),
    "vigo_api": Path(r"C:\Users\TU_USUARIO\...\DET_MINCO_PCM_Api"),
    "pipelines": Path(r"C:\Users\TU_USUARIO\...\COMMON_pipelines"),
    # ...
}
```

Si un proyecto no existe en tu PC, quítalo o déjalo y el sistema solo guardará docs locales / nombres libres (`NovaTrack`, etc.).

### Otras opciones útiles

| Variable | Para qué |
|----------|----------|
| `AUTO_GIT_COMMIT` | `True` = ofrecer crear rama en repo producto |
| `CONFIRMAR_RESPONSABLES` | `True` = preguntar dueño si falta |
| `WHISPER_MODEL` | `small` (default); `medium` = más preciso/lento |
| `USE_PYANNOTE` | Varios speakers remotos |

---

## 4. Levantar la aplicación (día a día)

Cada vez que vayas a usarla:

```powershell
# 1) Ir al proyecto
cd $HOME\Documents\automatizar_flujo_trabajo

# 2) Activar venv (si lo creaste)
.\.venv\Scripts\Activate.ps1

# 3) Ollama abierto (icono en bandeja) + modelo ya descargado

# 4) Token solo si usas pyannote
$env:HF_TOKEN = "hf_..."

# 5) Arrancar
python main.py
```

Deberías ver el menú:

```text
=======================================================
  ASISTENTE DE REUNIONES (orquestador)
=======================================================
Comandos:
  grabar / parar / toggle  — control de captura
  ...
```

Para salir: escribe `salir` o Ctrl+C.

### Primera ejecución

- Whisper descarga el modelo `small` la primera vez (tarda).  
- pyannote (si está activo) también descarga pesos la primera vez.

---

## 5. Uso en una reunión

1. `python main.py` en marcha + Ollama abierto.  
2. Únete a Teams (audio por el dispositivo default).  
3. `grabar` **o** `Ctrl+Shift+R`.  
4. Habla con normalidad; latido `🔴 mm:ss`.  
5. Al terminar: `parar` / Enter **o** otra vez el hotkey.  
6. Cuando diga *Presiona Enter…*, pulsa **Enter**.  
7. Espera transcripción + agentes.  
8. Confirma proyecto / responsables / rama si pregunta.  
9. Abre `docs\<proyecto>\<fecha>\prompt_cursor.md` y úsalo en Cursor.

### Comandos

| Comando | Acción |
|---------|--------|
| `grabar` | Inicia captura mic + sistema |
| `parar` / Enter | Detiene o continúa el flujo pendiente |
| `toggle` | Alterna grabar/parar |
| `proyectos` | Lista rutas mapeadas |
| `docs` | Abre la carpeta `docs/` |
| `salir` | Cierra la app |

| Hotkey | Acción |
|--------|--------|
| `Ctrl+Shift+R` | Alternar grabar / parar |

Si el hotkey no responde: terminal como Administrador, o usa solo `grabar` / `parar`.

### Buenas prácticas al hablar

- Nombra el proyecto: *“esto es para VIGO”* / *“proyecto NovaTrack”*.  
- Asigna trabajo en voz alta: *“yo me encargo del filtro”*.  
- Evita hablar solo de “la falla” sin producto.

### Prueba sin Teams (ElevenLabs u otro audio)

1. `grabar`  
2. Reproduce audio por los **altavoces/auriculares default**.  
3. Cuando termine, habla tú al mic.  
4. `parar` → Enter.

---

## 6. Diarización y pyannote (varios remotos)

| Etiqueta | Origen |
|----------|--------|
| `[TuNombre mm:ss]` | Canal micrófono (`USUARIO_LOCAL`) |
| `[Remoto mm:ss]` | Canal sistema, un solo remoto |
| `[Remoto_N mm:ss]` o nombre | Canal sistema + pyannote + `PARTICIPANTES_CONOCIDOS` |

Con **una** voz remota (ElevenLabs) es normal ver un solo remoto.  
La separación `Remoto_1` / `Remoto_2` se nota con **2+ personas** en Teams.

Si pyannote falla (403, token, etc.), el flujo **sigue** con Remoto único.

---

## 7. Proyectos, docs y Git

### Cómo se elige el proyecto

1. Menciones explícitas (`VIGO`, `pipelines`, …) o *“proyecto NovaTrack”*.  
2. Si hay duda → consola (número, clave o nombre libre).  
3. Nombre libre → carpeta `docs/NovaTrack/` (sin Git de producto).

### Salida de una sesión

```text
docs\<proyecto>\<YYYY-MM-DD_HH-MM-SS>\
  ├── prompt_cursor.md
  ├── transcripcion.txt
  ├── transcripcion_diarizada.txt
  ├── meta.json
  └── audio_reunion.wav
```

Si falla temprano: `docs\_fallidos\<fecha>\` (conserva el WAV).

### Git en el producto (si confirmas)

Copia a `<repo_producto>\docs\reuniones\...` y hace commit en la rama confirmada.  
Este orquestador **nunca** cambia de rama: siempre `main`.

---

## 8. Arquitectura y configuración

| Archivo | Rol |
|---------|-----|
| `main.py` | Menú, hotkey, orquestación |
| `audio_processor.py` | Grabación dual, WAV, Whisper |
| `diarization.py` | Mic/sys + pyannote + anti-eco |
| `task_ownership.py` | Responsables |
| `project_manager.py` | Agentes CrewAI |
| `project_input.py` | Detección / consola de proyecto |
| `docs_manager.py` | Escritura en `docs/` |
| `git_automation.py` | Rama/commit en repos producto |
| `hotkeys.py` | `Ctrl+Shift+R` |
| `config.py` | Toda la configuración |
| `requirements.txt` | Dependencias |

---

## 9. Solución de problemas

| Síntoma | Qué hacer |
|---------|-----------|
| `python` no se reconoce | Reinstalar Python con **Add to PATH**; reiniciar PowerShell |
| `pip` falla / permisos | Usa venv (Paso 4) o `python -m pip …` |
| Instalación de `torch` muy lenta | Normal la primera vez; espera o usa red estable |
| Ollama / agentes fallan | ¿Ollama abierto? ¿`ollama list` muestra `qwen2.5-coder:7b`? |
| Solo se oye tu voz, no Teams | Reproducción **default** = donde suena Teams; sube volumen |
| Solo Remoto, sin tu voz | Mic default correcto; permisos de mic en Windows |
| Basura en tu canal (eco) | Baja volumen auriculares; habla **después** del remoto |
| Hotkey no responde | Admin o usa `grabar`/`parar` |
| pyannote 403 | Acepta los 3 modelos HF + `$env:HF_TOKEN` válido |
| pyannote `itertracks` / API | Actualiza el código del repo (`git pull`) |
| Falló a mitad | Mira `docs/_fallidos/` |

---

## 10. Checklist

### Primera instalación

- [ ] Git instalado (o ZIP descargado)  
- [ ] Python 3.12+ con PATH  
- [ ] Repo clonado  
- [ ] venv creado y activado  
- [ ] `pip install -r requirements.txt` OK  
- [ ] Ollama instalado + `ollama pull qwen2.5-coder:7b`  
- [ ] `config.py`: `USUARIO_LOCAL` y rutas de proyectos  
- [ ] (Opcional) pyannote + token HF  
- [ ] Audio Windows: mic + salida default correctos  
- [ ] `python main.py` abre el menú  

### Antes de cada reunión

- [ ] Ollama en ejecución  
- [ ] venv activado (si aplica)  
- [ ] `$env:HF_TOKEN` si usas pyannote  
- [ ] `python main.py`  
- [ ] `grabar` al empezar / `parar` al terminar  
- [ ] Enter para continuar el análisis  
- [ ] Abrir `prompt_cursor.md` en Cursor  

---

## Resumen

**Instala Python + Ollama + dependencias → configura tu nombre y rutas → `python main.py` → graba la reunión → obtén el prompt en `docs/` → (opcional) rama en el repo del producto.**

---

*Orquestador:* https://github.com/FelipeLisboa/automatizar_flujo_trabajo
