# Manual: Asistente de Reuniones (Orquestador)

**Ubicación del proyecto:**  
`C:\Users\Felipe Lisboa\Documents\Personal\Automatizar_flujo_trabajo`

**Propósito:** capturar el audio de una reunión (Teams / sistema + tu micrófono), **diarizar** quién habla, transcribir, extraer tareas **con responsables** y generar un **prompt listo para Cursor**, guardándolo en `docs/`. Opcionalmente crea una rama y commit en el **repo del producto** (nunca en este orquestador).

Este repositorio es solo el **orquestador**: permanece siempre en `main`.

---

## 1. Qué hace el flujo (de punta a punta)

```
Grabar (mic + audio del PC)
    → Guardar WAV mix / mic / sys
    → Diarizar (mic = tú, sistema = remotos)
    → Transcribir con Whisper (local)
    → Analizar con agentes CrewAI + Ollama (Qwen)
    → Resolver proyecto (audio o consola)
    → Confirmar responsables de tareas (si faltan)
    → Guardar sesión en docs/
    → (Opcional) Confirmar rama Y/N → Git en el repo del producto
```

### Detalle por etapa

| Etapa | Qué ocurre |
|--------|------------|
| **Captura** | Micrófono (WASAPI) + audio del sistema (WASAPI Loopback: Teams, navegador, etc.) |
| **WAV** | Guarda tres pistas: mezcla (`mix`), solo mic, solo sistema |
| **Mezcla** | Alinea ambas pistas al largo mayor (sin cortar tu voz al final) |
| **Diarización** | Mic → `USUARIO_LOCAL` (p. ej. Felipe); sistema → `Remoto` (o `Remoto_N` con pyannote) |
| **Transcripción** | Whisper `small` en español, sin depender de ffmpeg |
| **Agentes** | PM extrae proyecto/rama/tareas con dueño; Dev genera Markdown con prompt para Cursor |
| **Proyecto** | Si el audio no nombra un proyecto claro, **te lo pide por consola** (también nombres libres, p. ej. NovaTrack) |
| **Responsables** | Si una tarea no tiene dueño claro, pregunta por consola |
| **Docs** | Guarda prompt, transcripciones, `meta.json`, audio |
| **Git** | Solo en repos de producto; con confirmación `Y/N` del nombre de rama |

---

## 2. Requisitos previos

1. **Python 3.12+** instalado.
2. Dependencias:

```powershell
cd "C:\Users\Felipe Lisboa\Documents\Personal\Automatizar_flujo_trabajo"
python -m pip install -r requirements.txt
```

3. **Ollama** corriendo en local con el modelo:

```text
qwen2.5-coder:7b
```

4. Audio de Windows:
   - El sonido de Teams/navegador debe salir por el **dispositivo de reproducción por defecto** (el loopback captura ese dispositivo).
   - Si usas auriculares Bluetooth distintos al default, el sistema puede no capturarse.
   - Si la salida es altavoces del PC pero el mic default son audífonos, el orquestador intenta detectar el mic integrado.

5. Hotkey global (`Ctrl+Shift+R`): el paquete `keyboard` a veces requiere **ejecutar la terminal como Administrador**. Si falla el hotkey, usa los comandos `grabar` / `parar`.

### Extra opcional: pyannote (varios remotos)

Por defecto ya separas **tú (mic) vs Remoto (PC)**. Si quieres separar a varias personas en el canal de Teams:

1. Token en [https://huggingface.co/settings/tokens](https://huggingface.co/settings/tokens) (tipo Read).
2. Acepta condiciones en:
   - [pyannote/speaker-diarization-3.1](https://huggingface.co/pyannote/speaker-diarization-3.1)
   - [pyannote/segmentation-3.0](https://huggingface.co/pyannote/segmentation-3.0)
3. Instala: `python -m pip install pyannote.audio`
4. En `config.py` pon `HF_TOKEN = "hf_..."` (o `$env:HF_TOKEN`).
5. Opcional: lista nombres en `PARTICIPANTES_CONOCIDOS` (después de ti) para mapear `Remoto_1`, `Remoto_2`, …

Sin token, el flujo sigue funcionando con Felipe vs Remoto.

---

## 3. Cómo iniciar

```powershell
cd "C:\Users\Felipe Lisboa\Documents\Personal\Automatizar_flujo_trabajo"
python main.py
```

Verás el menú, los proyectos mapeados y el hotkey activo.

---

## 4. Manual de uso (paso a paso)

### Reunión típica

1. Abre el orquestador (`python main.py`).
2. Únete a la reunión de Teams (o reproduce audio de prueba).
3. Escribe `grabar` **o** pulsa `Ctrl+Shift+R`.
4. Habla con normalidad; verás latido tipo `🔴 mm:ss`.
5. Al terminar: `parar` / Enter **o** otra vez `Ctrl+Shift+R`.
6. Cuando diga *Presiona Enter…*, pulsa **Enter** en la consola.
7. Espera diarización + Whisper + agentes (la primera carga de Whisper `small` tarda más).
8. Si el proyecto no quedó claro, elige en la lista (número, clave o **nombre libre**).
9. Si hay tareas sin responsable, asígnalos por consola.
10. Si aplica Git de producto: confirma la rama `Y/N` (si `N`, escribe el nombre y confirma otra vez).
11. Abre el `prompt_cursor.md` generado y pégalo en Cursor sobre el repo correcto.

### Comandos de consola

| Comando | Acción |
|---------|--------|
| `grabar` | Inicia captura mic + sistema |
| `parar` / Enter | Detiene (si grababas) o continúa el flujo pendiente |
| `toggle` | Alterna grabar/parar |
| `proyectos` | Lista rutas mapeadas |
| `docs` | Abre la carpeta `docs/` en el Explorador |
| `salir` | Cierra la app |

### Hotkey

| Teclas | Acción |
|--------|--------|
| `Ctrl+Shift+R` | Alternar grabar / parar (también con Teams en foco) |

---

## 5. Diarización (quién habla)

| Etiqueta | Origen |
|----------|--------|
| `[Felipe mm:ss]` (o el valor de `USUARIO_LOCAL`) | Canal micrófono |
| `[Remoto mm:ss]` | Canal sistema (Teams / PC), un solo remoto |
| `[Remoto_N mm:ss]` o nombre | Canal sistema con pyannote + `PARTICIPANTES_CONOCIDOS` |

Eso alimenta a los agentes para inferir responsables (“yo me encargo”, “tú haz X”, etc.) sin inventar dueños.

---

## 6. Proyectos mapeados

Configurados en `config.py` → `RUTAS_PROYECTOS`.

### Con repositorio Git (sí pueden crear rama)

| Clave | Ruta |
|-------|------|
| `vigo_web` | `...\PROYECTOS\VIGO\Código_fuente\DET_MINCO_PCE_Web` |
| `vigo_api` | `...\PROYECTOS\VIGO\Código_fuente\DET_MINCO_PCM_Api` |
| `pipelines` | `...\PROYECTOS\Pipelines\COMMON_pipelines` |

### Sin repo local aún (solo documentación)

| Clave / nombre | Destino |
|----------------|---------|
| `General` | docs genéricos |
| Nombre libre (ej. `NovaTrack`) | `docs/NovaTrack/` (sin Git de producto) |

### Cómo se elige el proyecto

1. Se buscan menciones **explícitas** en la transcripción (`VIGO`, `pipelines`, etc.).
2. Si hay duda o no hay mención clara → **pregunta por consola** con lista numerada.
3. Puedes escribir un nombre nuevo: se guarda bajo `docs/<ese-nombre>/` y **no** se usa el repo del orquestador como destino Git.

---

## 7. Salida de archivos

Cada sesión exitosa crea:

```text
Automatizar_flujo_trabajo\docs\<proyecto>\<YYYY-MM-DD_HH-MM-SS>\
  ├── prompt_cursor.md              ← prompt para pegar en Cursor
  ├── transcripcion.txt             ← texto (plana o diarizada según flujo)
  ├── transcripcion_diarizada.txt   ← con etiquetas [hablante mm:ss] (si aplica)
  ├── meta.json                     ← proyecto, rama, tareas[{descripcion,responsable,evidencia}], rutas
  └── audio_reunion.wav             ← copia de la mezcla
```

Durante la captura (temporal en `.tmp_audio/`, luego se limpia):

```text
reunion_activa.wav   ← mezcla
mic_reunion.wav      ← solo tu voz
sys_reunion.wav      ← solo audio del PC
```

Si falla Whisper u otra etapa temprana:

```text
docs\_fallidos\<fecha_hora>\
  ├── error.txt
  ├── audio_reunion.wav
  └── meta.json
```

### Git en el producto (si confirmas la rama)

También copia a:

```text
<repo_producto>\docs\reuniones\<proyecto>\<fecha_hora>\
  ├── prompt_cursor.md
  ├── transcripcion.txt
  └── meta.json
```

…y hace commit en la rama que confirmaste.

---

## 8. Confirmaciones interactivas

### Proyecto (si no está claro)

```text
Ingresa el proyecto (número, clave, o nombre). Ej: 1 / vigo_web / NovaTrack:
```

### Responsables (si `CONFIRMAR_RESPONSABLES = True`)

Para cada tarea sin dueño claro, la consola pide asignar un nombre (o dejar sin asignar).

### Rama Git (solo repos de producto)

```text
Confirmar crear rama: feature/ejemplo? [Y/N]:
```

- `Y` → crea/cambia a esa rama y commit.
- `N` → te pide escribir el nombre y vuelve a confirmar.
- `cancelar` → no toca Git; el prompt queda solo en `docs/` local.

---

## 9. Arquitectura de archivos (código)

| Archivo | Rol |
|---------|-----|
| `main.py` | Menú, hotkey, orquestación del pipeline |
| `audio_processor.py` | Grabación dual, mezcla, WAV mic/sys/mix, Whisper |
| `diarization.py` | Mic = local / sys = remoto (+ pyannote opcional) |
| `task_ownership.py` | Normaliza tareas y confirma responsables |
| `project_manager.py` | Agentes CrewAI (PM + Dev) |
| `project_input.py` | Detección de proyecto + input por consola |
| `docs_manager.py` | Escritura en `docs/` y `_fallidos/` |
| `git_automation.py` | Rama/commit en repos de producto (nunca aquí) |
| `hotkeys.py` | Registro de `Ctrl+Shift+R` |
| `config.py` | Rutas, aliases, Whisper, diarización, flags |
| `requirements.txt` | Dependencias Python |

---

## 10. Configuración útil (`config.py`)

| Variable | Significado | Valor típico |
|----------|-------------|--------------|
| `WHISPER_MODEL` | Modelo Whisper | `small` |
| `OLLAMA_LLM` | Modelo CrewAI | `ollama/qwen2.5-coder:7b` |
| `HOTKEY` | Atajo global | `ctrl+shift+r` |
| `AUTO_GIT_COMMIT` | Ofrecer Git en producto | `True` |
| `RECORDING_HEARTBEAT_SEC` | Latido en consola | `10` |
| `USUARIO_LOCAL` | Tu nombre en la diarización (canal mic) | `"Felipe"` |
| `PARTICIPANTES_CONOCIDOS` | Nombres frecuentes / mapeo pyannote | `["Felipe", …]` |
| `CONFIRMAR_RESPONSABLES` | Preguntar dueño si falta | `True` |
| `HF_TOKEN` | Token Hugging Face (pyannote) | `""` o `hf_…` |
| `RUTAS_PROYECTOS` | Mapa clave → carpeta Git | editar al agregar repos |
| `ALIAS_PROYECTOS` | Sinónimos → clave | editar según nombres de reunión |

Para **no** crear ramas automáticamente en productos:

```python
AUTO_GIT_COMMIT = False
```

(Igual se guarda todo en `docs/`.)

Para desactivar preguntas de responsables:

```python
CONFIRMAR_RESPONSABLES = False
```

---

## 11. Buenas prácticas al hablar en la reunión

- Nombra el proyecto al menos una vez: *“esto es para VIGO”* / *“en VIGO web…”*.
- Di la rama de forma clara: *“feature barra timeout guion fix”* → `feature/timeout-fix`.
- Asigna trabajo en voz alta: *“yo me encargo del timeout”*, *“Ana revisa el checkout”*.
- Menciona pantallas/componentes si los conoces: mejora el prompt de Cursor.
- Evita hablar solo de “la falla” sin decir el producto: el sistema te pedirá el proyecto por consola (correcto, pero más lento).

---

## 12. Solución de problemas

| Síntoma | Qué revisar |
|---------|-------------|
| Solo se oye tu voz, no Teams | Salida de audio por el dispositivo **default**; volumen del sistema |
| Solo Remoto, sin tu voz | Micrófono correcto / permisos; prueba mic integrado si usas altavoces PC |
| `WinError 2` en Whisper | Ya no debería pasar (carga WAV directa). Actualiza el código |
| Hotkey no responde | Terminal como Administrador, o usa `grabar`/`parar` |
| Proyecto sale como VIGO sin haberlo dicho | Debe pedir consola; actualiza si tienes versión vieja |
| Nombre libre cae en carpeta del orquestador | Debe usar `slug_carpeta_proyecto`; actualiza el código |
| Agentes fallan | ¿Ollama abierto? ¿Modelo `qwen2.5-coder:7b` descargado? |
| pyannote falla / 401 | Token válido + condiciones aceptadas en HF; sin token sigue Felipe vs Remoto |
| Transcripción floja | Habla más cerca; Whisper `small` ya ayuda; opcional subir a `medium` |
| Falló a mitad | Mira `docs/_fallidos/` — ahí está el WAV |

---

## 13. Checklist rápida antes de una reunión

- [ ] Ollama en ejecución  
- [ ] `python main.py` arrancado  
- [ ] Teams/audio por altavoces (o default) correctos  
- [ ] `grabar` al empezar / `parar` al terminar  
- [ ] Enter para continuar el pipeline  
- [ ] Confirmar proyecto si pregunta  
- [ ] Confirmar responsables si pregunta  
- [ ] Confirmar rama si aplica  
- [ ] Abrir `prompt_cursor.md` y usarlo en Cursor  

---

## 14. Resumen en una frase

**Graba la reunión → separa quién habló → entiende qué hay que hacer y quién → te deja el prompt en `docs/` → (si quieres) prepara la rama en el repo correcto, sin ensuciar el orquestador.**

---

*Documento del asistente en*  
`C:\Users\Felipe Lisboa\Documents\Personal\Automatizar_flujo_trabajo`
