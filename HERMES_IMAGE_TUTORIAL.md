# Tutorial para Hermes: edición de fotografías e identidad con Krea2

Este endpoint **no hace text-to-image**. Solo admite solicitudes que incluyan al
menos una fotografía real de referencia y sirve para:

1. Editar esa fotografía: fondo, ropa, atributos, objetos, iluminación o
   composición.
2. Crear una nueva fotografía o toma de la misma persona, conservando su
   identidad y cambiando pose, posición, encuadre o escena.

Nunca sustituyas la referencia por ruido ni aceptes una solicitud sin imagen
real. Si el usuario pide una imagen sin referencia, explica que este endpoint no
puede realizarla.

## Reglas de seguridad

- No guardes secretos en el repositorio, prompts, URLs ni logs.
- No imprimas payloads que contengan Base64. El gateway conserva metadatos
  redacted; registra solo identificadores, estados y metadatos no sensibles.
- Usa `/tmp` para temporales, valida el tipo/tamaño de la imagen y valida el
  archivo descargado antes de entregarlo. Elimina los temporales cuando ya no
  sean necesarios.
- Filebin es público: úsalo solo si el usuario lo pide explícitamente y solo
  para una imagen que haya autorizado.

## Gateway local y contrato canónico

El gateway probado escucha en `http://127.0.0.1:8173`.

```http
POST http://127.0.0.1:8173/api/v1/calls
Content-Type: application/json
```

El cuerpo debe incluir `images`, con al menos una entrada `{name, image}`, y
`prompt`. `image` acepta Base64 o una Data URL. `image_url` no es un campo
directo del worker; si se parte de una URL, descárgala con HTTPS, límites de
tamaño y timeout, y conviértela antes a Base64.

Ejemplo de edición:

```json
{
  "images": [{"name": "persona.jpg", "image": "data:image/jpeg;base64,..."}],
  "prompt": "Replace the background with a modern studio. Preserve the person, face, hairstyle and clothing.",
  "steps": 12,
  "cfg": 1,
  "resolution": 1344,
  "seed": 42
}
```

Ejemplo de nueva toma con identidad conservada:

```json
{
  "images": [{"name": "persona.jpg", "image": "data:image/jpeg;base64,..."}],
  "prompt": "Create a new full-body photograph of the same person standing in side profile on a city street. Preserve facial identity, face structure and hairstyle; change the pose, framing and scene.",
  "steps": 12,
  "cfg": 1,
  "resolution": 1344,
  "seed": 42
}
```

Consulta el trabajo con `GET /api/v1/calls/{id}`. Espera uno de estos estados
terminales: `COMPLETED`, `FAILED`, `TIMED_OUT`, `CANCELLED` o
`COMPLETED_OUTPUT_UNAVAILABLE`. Solo `COMPLETED` permite entregar normalmente
el resultado. Descarga un archivo terminado con:

```http
GET /api/v1/calls/{id}/outputs/{filename}
```

La respuesta limpia del gateway puede contener metadatos del call y referencias
a archivos; no asumas que `outputs` es una lista ni imprimas su contenido.

## Ejemplo Python (stdlib)

El siguiente ejemplo lee una imagen local, la codifica, crea el call, hace
polling y muestra únicamente metadatos seguros:

```python
import base64
import json
import mimetypes
import time
import urllib.request
from pathlib import Path

GATEWAY = "http://127.0.0.1:8173"
TERMINAL = {"COMPLETED", "FAILED", "TIMED_OUT", "CANCELLED",
            "COMPLETED_OUTPUT_UNAVAILABLE"}


def request_json(url, payload=None, headers=None):
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url, data=body, headers=headers or {},
        method="POST" if payload is not None else "GET",
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.loads(response.read().decode("utf-8"))


def edit(path, prompt):
    source = Path(path)
    raw = source.read_bytes()
    media_type = mimetypes.guess_type(source.name)[0] or "application/octet-stream"
    image = "data:%s;base64,%s" % (
        media_type, base64.b64encode(raw).decode("ascii"))
    payload = {
        "images": [{"name": source.name, "image": image}],
        "prompt": prompt, "steps": 12, "cfg": 1, "resolution": 1344,
        "seed": 42,
    }
    call = request_json(
        GATEWAY + "/api/v1/calls", payload,
        {"Content-Type": "application/json"},
    )
    call_id = call["id"]
    while True:
        result = request_json(GATEWAY + "/api/v1/calls/" + call_id)
        state = result.get("state")
        if state in TERMINAL:
            if state != "COMPLETED":
                raise RuntimeError("call ended with state " + str(state))
            return result
        time.sleep(3)


result = edit(
    "/tmp/persona.jpg",
    "Create a new photograph of the same person sitting in a cafe. Preserve identity and hairstyle; change pose and scene.",
)
print({key: result.get(key) for key in ("id", "state", "job_id", "created", "updated", "outputs")})
```

## Controles confirmados

- `prompt` se aplica al nodo `317`.
- `negative_prompt` se aplica al nodo `318`.
- `steps`, `seed` y otros parámetros del muestreador se aplican al nodo `320`.
- `cfg` se aplica al nodo `321`.
- `resolution`/`longest_side` se aplica al nodo `264`.
- `ref_boost`, `ref_boost_a`, `fit_mode` y `grounding_px` son controles del
  workflow, no promesas universales del gateway. Solo pueden enviarse mediante
  `extra_input` si el workflow activo los soporta. En el workflow probado son
  `319.ref_boost`, `319.ref_boost_a`, `319.fit_mode`, `317.grounding_px` y
  `318.grounding_px`.

`denoise=1` es un ajuste del workflow y no transforma este endpoint en un flujo
sin referencia: no inventes una imagen de ruido ni omitas la fotografía real.

## Payload directo al worker (referencia avanzada)

Si no se usa el gateway, `workflow` debe ser el objeto API completo, nunca un
string. Usa `api-workflow.json`, no `workflow.json` (este último es el formato
canvas). El nombre de cada `images[].name` debe coincidir con
`LoadImage.inputs.image` del workflow; por ejemplo:

```json
{
  "input": {
    "workflow": "<objeto completo de api-workflow.json, con el prompt en el nodo 317>",
    "images": [{"name": "persona.jpg", "image": "BASE64_SIN_PREFIJO"}]
  }
}
```

El ejemplo es ilustrativo: `workflow` debe ser un objeto JSON completo, no una
cadena; el prompt debe estar dentro de `workflow["317"].inputs.prompt` y todos
los nodos deben estar conectados. Para Hermes, usa el gateway descrito arriba:
él aplica `prompt`, valida la solicitud y construye el payload directo correcto.

## Checklist

```text
¿Hay al menos una fotografía real? -> si no, rechazar esta solicitud.
Edición de fotografía              -> describir cambios y qué preservar.
Nueva toma de la persona           -> decir explícitamente “misma persona” e identidad.
Polling                            -> esperar estado terminal.
Resultado                          -> descargar por /outputs/{filename} y validar.
Compartir                          -> Filebin solo por petición explícita.
```
