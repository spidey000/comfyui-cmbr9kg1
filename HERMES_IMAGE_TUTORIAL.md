# Tutorial para Hermes: generación y edición de imágenes

Este documento describe cómo debe clasificar Hermes tres tipos de petición:

1. **Texto a imagen**: no existe imagen de referencia.
2. **Edición de imagen**: existe una imagen y se quiere modificar su contenido.
3. **Identity edit**: se conserva una persona y se cambia su pose, ropa, escena
   o encuadre.

## Reglas de seguridad

- Nunca escribas `RUNPOD_API_KEY`, `CIVITAI_API_KEY` ni otra credencial en el
  repositorio, en un prompt, en una URL o en los logs.
- No imprimas payloads que contengan Base64.
- Guarda temporales en `/tmp` y elimínalos después de subir/descargar el
  resultado.
- Espera siempre un estado terminal antes de responder:
  `COMPLETED`, `FAILED`, `TIMED_OUT` o `CANCELLED`.
- El worker Krea2 no acepta `image_url` como entrada directa. Descarga la URL
  usando HTTPS, límites de tamaño y timeout, y conviértela a Base64.

## Tabla de decisión

| Petición | Flujo recomendado |
|---|---|
| “Genera una imagen de…” | Endpoint FLUX de texto a imagen |
| “Edita esta imagen…” | Gateway Krea2 o FLUX Kontext, según el schema activo |
| “Pon a esta persona en otra pose/escena” | Gateway Krea2 Identity Edit |

Los endpoints públicos FLUX pueden cambiar su schema. Antes de automatizarlos,
Hermes debe consultar el request template activo. RunPod solo garantiza el
envoltorio común:

```text
POST https://api.runpod.ai/v2/{ENDPOINT_ID}/run
GET  https://api.runpod.ai/v2/{ENDPOINT_ID}/status/{JOB_ID}
```

Con:

```http
Authorization: Bearer $RUNPOD_API_KEY
Content-Type: application/json
```

La respuesta de `/run` contiene `id` y `status`; el contenido de `input` y de
`output` depende del worker.

## 1. Generación desde texto

Usa un endpoint FLUX de texto a imagen, por ejemplo el endpoint configurado en
RunPod para `FLUX.1 [schnell]` o `FLUX.1 [dev]`. No asumas que el nombre visible
del modelo es el `ENDPOINT_ID` ni que los campos opcionales son universales.

La forma general es:

```bash
curl --fail-with-body -X POST \
  "https://api.runpod.ai/v2/${FLUX_ENDPOINT_ID}/run" \
  -H "Authorization: Bearer ${RUNPOD_API_KEY}" \
  -H "Content-Type: application/json" \
  -d '{
    "input": {
      "prompt": "A cinematic editorial portrait in soft natural light"
    }
  }'
```

El campo `prompt` es habitual, pero Hermes debe confirmarlo en el schema del
endpoint antes de enviar la petición. Después consulta:

```bash
curl --fail-with-body \
  "https://api.runpod.ai/v2/${FLUX_ENDPOINT_ID}/status/${JOB_ID}" \
  -H "Authorization: Bearer ${RUNPOD_API_KEY}"
```

El resultado de un worker puede ser una URL, una lista de imágenes o Base64.
Hermes debe inspeccionar el output sin registrarlo completo.

## 2. Edición de una imagen con el gateway Krea2

El gateway local probado en este proyecto escucha en:

```text
http://127.0.0.1:8173
```

La llamada canónica es `POST /api/v1/calls`. La imagen puede ser Base64 puro o
una data URL; el gateway la normaliza antes de enviarla al worker.

Ejemplo Python sin dependencias externas:

```python
import base64
import json
import time
import urllib.request
from pathlib import Path

GATEWAY = "http://127.0.0.1:8173"

def http_json(url, payload=None, headers=None):
    data = None if payload is None else json.dumps(payload).encode()
    request = urllib.request.Request(
        url,
        data=data,
        headers=headers or {},
        method="POST" if payload is not None else "GET",
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.loads(response.read())

def edit_image(path, prompt):
    source = Path(path)
    encoded = base64.b64encode(source.read_bytes()).decode("ascii")
    payload = {
        "images": [{
            "name": source.name,
            "image": "data:image/jpeg;base64," + encoded,
        }],
        "prompt": prompt,
        "steps": 10,
        "cfg": 1.0,
        "resolution": 1344,
        "seed": 42,
    }
    call = http_json(
        GATEWAY + "/api/v1/calls",
        payload,
        {
            "Content-Type": "application/json",
            "Idempotency-Key": "hermes-" + str(time.time_ns()),
        },
    )
    call_id = call["id"]
    while True:
        result = http_json(GATEWAY + "/api/v1/calls/" + call_id)
        state = result.get("state")
        if state == "COMPLETED":
            return result
        if state in {"FAILED", "TIMED_OUT", "CANCELLED",
                     "COMPLETED_OUTPUT_UNAVAILABLE"}:
            raise RuntimeError(result.get("error") or state)
        time.sleep(3)

result = edit_image(
    "/tmp/source.jpg",
    "Replace the background with a modern studio. Preserve the person, face, "
    "hairstyle, clothing and lighting.",
)
print(result["id"], result["state"], result["outputs"])
```

Cuando el estado sea `COMPLETED`, descarga cada archivo con:

```text
GET /api/v1/calls/{CALL_ID}/outputs/{FILENAME}
```

El gateway conserva solo metadatos redacted en SQLite; no guardes el resultado
Base64 en logs.

## 3. Cambiar pose o escena conservando identidad

Usa el mismo gateway Krea2, pero describe explícitamente que es **la misma
persona**. Los ajustes de identidad se aplican mediante `extra_input`, porque
son controles del workflow y no campos top-level del gateway.

```json
{
  "images": [
    {
      "name": "person.jpg",
      "image": "data:image/jpeg;base64,..."
    }
  ],
  "prompt": "Create a new full-body shot of the same person standing in
  side-profile on a city street. Preserve facial identity, face structure,
  hairstyle and clothing.",
  "steps": 12,
  "cfg": 1,
  "resolution": 1344,
  "seed": 42,
  "extra_input": {
    "319.ref_boost": 4.0,
    "319.ref_boost_a": 1.0,
    "319.fit_mode": "fit",
    "317.grounding_px": 768,
    "318.grounding_px": 768
  }
}
```

Prompts útiles:

```text
Create a new shot of the same person sitting in a café, three-quarter view.
Preserve facial identity, hairstyle, clothing and recognizable features.
```

```text
Put the same person in a mountain landscape, walking away and looking over
their shoulder. Preserve the face and identity while changing the pose.
```

```text
Change the pose to a walking pose with the left arm raised. Keep the same
person, face, hairstyle, clothing and lighting.
```

Guía de `ref_boost`:

| Objetivo | Valor orientativo |
|---|---:|
| Máxima fidelidad | 4–6 |
| Equilibrio | 2.5–4 |
| Más libertad creativa | 1–2 |

La identidad no está garantizada al 100 %. Hermes debe advertirlo si el usuario
solicita una pose extrema, perfil completo o cambios grandes de iluminación.

## Workflow directo del worker

Si no se usa el gateway, el worker Krea2 requiere el workflow API completo como
objeto, nunca como string. El siguiente fragmento es esquemático; no lo envíes
sin completar todos los nodos de `api-workflow.json`:

```json
{
  "workflow": {
    "78": {
      "class_type": "LoadImage",
      "inputs": {"image": "example.png"}
    }
  },
  "images": [
    {"name": "example.png", "image": "BASE64_SIN_PREFIJO"}
  ]
}
```

El nombre de `images[].name` debe coincidir con `LoadImage.inputs.image`. Usa
`api-workflow.json`; `workflow.json` es el formato canvas y no es un payload API
válido. Para múltiples imágenes usa `image_node_map`.

## Subir resultados a Filebin

Solo si el usuario lo solicita, Hermes puede publicar un resultado:

```bash
BIN="hermes-krea2-$(python3 -c 'import secrets; print(secrets.token_hex(6))')"
FILE="/tmp/output.png"
SHA=$(sha256sum "$FILE" | cut -d' ' -f1)

curl --fail -X POST \
  -H "Content-Type: image/png" \
  -H "Content-SHA256: $SHA" \
  --data-binary "@$FILE" \
  "https://filebin.net/$BIN/output.png"

echo "https://filebin.net/$BIN"
```

Filebin es público y los bins expiran aproximadamente en seis días. No subas
credenciales, payloads ni imágenes que el usuario no haya autorizado.

## Checklist de Hermes

```text
Sin imagen                 -> FLUX text-to-image; verificar schema.
Con imagen, edición común  -> Krea2 gateway o FLUX Kontext; verificar schema.
Misma persona, nueva pose  -> Krea2 Identity Edit.
URL remota                 -> descargar con HTTPS, límites y timeout; luego Base64.
Resultado                  -> esperar estado terminal y validar el archivo.
Compartir                  -> Filebin solo si el usuario lo pide.
```

## Referencias

- `api-workflow.json`: workflow API probado.
- `README.md`: contrato de despliegue y assets del worker.
- `https://docs.runpod.io/serverless/endpoints/send-requests`: contrato común
  de RunPod Serverless.
- `https://docs.runpod.io/serverless/endpoints/operation-reference`: estados,
  polling y operaciones.
