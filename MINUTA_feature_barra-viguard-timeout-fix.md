```markdown
# Prompts de Desarrollo para Cursor (Proyecto: BioGuard ID)

## 1. Contexto del Cambio (Agnóstico a la tecnología)
Lee el contexto de mi espacio de trabajo actual para determinar el lenguaje y framework utilizado por el proyecto BioGuard ID en la rama feature/barra-viguard-timeout-fix.

## 2. Prompt listo para Cursor (Copiar y Pegar)

1. Analiza el código aberto en este espacio de trabajo.
2. Identifica las tecnologías, frameworks y patrones de diseño en uso con base en los archivos abiertos.
3. Confirma que comprendes el contexto del proyecto bioGuard ID y la rama feature/barra-viguard-timeout-fix.

**Requisitos Específicos:**
- Agrega un timeout de 15 segundos en el flujo de validación de identidad para BioGuard D y BioGuard.
- Implementa una manejo seguro de cancelaciones del proceso si la verificación biométrica no responde dentro del tiempo.
- Libera la cámara cuando hay una mala conexión durante la validación.
- Lanza un error claro que indique "tiempo de espera agotado".
- Modifica el componente de la cámara y la lógica de validación en el backend para evitar peticiones colgadas.

**Paso a Paso:**
1. Identifica los componentes actuales relacionados con las validaciones biométricas y la gestión de cámaras.
2. Implementa la funcionalidad de timeout, asegurándote de que se ejecuta correctamente en el flujo de procesos existentes.
3. Asegúrate de manejar adecuadamente la cancelación del proceso cuando no se reciba una respuesta dentro del tiempo indicado.
4. Modifica el control de cámara para cerrarla automáticamente cuando la conexión sea mala o si ocurre algún error.
5. Implementa la lógica necesaria para lanzar un error claro "tiempo de espera agotado" cuando el timeout se expire.
6. Prueba las funcionalidades modificadas asegurándote de que todo funciona según lo especificado.

**Consideraciones Adicionales:**
- Asegúrate de no modificar o eliminar cualquier otro código que no sea necesario para este cambio.
- Comueba la documentación y pruebas asociadas con los componentes afectados para garantizar una integración correcta.
- Realiza pruebas exhaustivas, incluyendo escenarios de éxito y casos limite donde se esperan errores.

**Revisión Final:**
Verifica que toda la funcionalidad requerida ha sido implementada correctamente y asegura que las pruebas funcionales pasen con éxito. Genera un registro detallado de todos los cambios realizados, incluidos cualquier refactorización o modificación en el código existente.
```