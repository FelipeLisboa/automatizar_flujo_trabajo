## Reporte de Cambios Automatizado

### 1. Contexto (Qué se debía hacer)

Como parte del proyecto VIGO, fue necesario agregar una nueva funcionalidad que permita validar patentes en el backend. Además, se requiere la integración con rama Gitcore para asegurar que las modificaciones sean aplicadas de forma correcta.

### 2. Estado Inicial (Qué se tenía)

Antes de realizar los cambios, se tuvo un estado estable donde:

- El backend no disponía del endpoint específico para validar patentes.
- No existía ninguna integración entre la rama Gitcore y el backend en cuestión.

### 3. Cambios Aplicados (Qué se hizo y por qué)

#### Crear Endpoint en el Backend

Se implementó un endpoint nuevo ubicado en `/api/v1/checkouts/validate-plate`. El objetivo de este endpoint es recibir una patente como parámetro y devolver un valor booleano que indique si la patente es válida según las reglas establecidas (por ejemplo, formato de patente correcto, no está bloqueada o caducada, etc.). 

Justificación:
- Es fundamental tener esta funcionalidad para garantizar que solo peticiones con patentes válidas sean procesadas por nuestro sistema.
- Añadir este endpoint facilitará la implementación de diferentes métodos de validación en el futuro sin cambiar los clientes actuales.

#### Integrar Rama Gitcore

Se realizó una integración entre la rama `feature/nuevo-checkout-validation-future` y la rama principal del backend. La Integración se llevó a cabo siguiendo las políticas para el manejo de ramas de características en Git, asegurando que tuviera los cambios más actuales antes de realizar las modificaciones.

Justificación:
- Integrar con rama Gitcore garantiza que el código de nuestra nueva funcionabilidad se mantenga desactualizado hasta que esté lista para su lanzamiento.
- Además, la integración regular de la rama principal asegura que cualquier defecto o cambio en el backend base no interfiera con nuestro trabajo y pueda revertirse fácilmente en caso de necesitarlo.

### 4. Plan de Pruebas Sugerido

Para validar los cambios aplicados correctamente se sugiere realizar lo siguiente:

1. **Pruebas Unitarias**: Lanzar pruebas unitarias específicas para el nuevo endpoint para asegurar que funciona correctamente con patentes válidas y no válidas.
2. **Pruebas Integración**: Correr pruebas de integración para verificar si las llamadas al nuevo endpoint desde otras partes del systema son respondidas correctamente.
3. **Ejercitar Endpoint con Patentes Válidas y No Válidas**: Realizar peticiones a `/api/v1/checkouts/validate-plate` usando patentes realistas, tanto válidas como no válidas, para asegurar el comportamiento del servidor.

Durante esta fase, es recomendable también revisar si la integración con Gitcore está funcionando correctamente y que los cambios no hayan provocado problemas o dependencias adicionales. Realizar estas pruebas adecuadamente ayudará a minimizar el riesgo de fallos cuando se lanzen las modificaciones al sistema en producción.