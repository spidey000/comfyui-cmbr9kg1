# Hermes: cliente Python para Krea2 en RunPod Serverless

La integración primaria para Hermes es la llamada HTTP explicada abajo; el
repositorio también incluye `hermes_runpod_krea2.py` como CLI reutilizable. El
endpoint `5fj6bxupuhijp3` solo edita una fotografía existente o crea una nueva
toma manteniendo la identidad de la persona. Siempre se debe aportar una foto
real: no es text-to-image y no se debe sustituir la referencia por ruido.

## Seguridad y límites

No guardes, imprimas ni registres `RUNPOD_API_KEY`, el header Authorization, el
payload completo ni Base64 de imágenes. Usa el token exclusivamente mediante
la variable de entorno `RUNPOD_API_KEY`. Si un token fue expuesto, revócalo y
genera uno nuevo. El cliente actual admite extensiones `.jpg`, `.jpeg`, `.png`,
`.webp`, `.gif`, `.bmp`, `.tif` y `.tiff`, limita la imagen a 7 MiB y el JSON
aproximadamente a 9,5 MB para mantenerse bajo el límite de `/run`.

## API exacta

Las URL son:

```text
POST https://api.runpod.ai/v2/5fj6bxupuhijp3/run
GET  https://api.runpod.ai/v2/5fj6bxupuhijp3/status/{job_id}
POST https://api.runpod.ai/v2/5fj6bxupuhijp3/cancel/{job_id}  (opcional)
```

En las tres llamadas usa `Authorization: Bearer <valor de RUNPOD_API_KEY>`;
en POST añade `Content-Type: application/json`. El cuerpo de `/run` debe tener
exactamente esta forma conceptual:

```json
{
  "input": {
    "workflow": {"78": {"class_type": "LoadImage", "inputs": {"image": "input.jpg"}}},
    "images": [{"name": "input.jpg", "image": "BASE64_RAW_SIN_PREFIJO_DATA_URL"}]
  }
}
```

El objeto mostrado para `workflow` es abreviado solo para explicar la forma:
en la llamada real debe ser el objeto completo cargado desde `api-workflow.json`,
nunca una cadena JSON y nunca `workflow.json` (que es el formato canvas).
`images[].image` es Base64 crudo, sin `data:image/...;base64,`. Cada nodo cuyo
`class_type` sea `LoadImage` debe tener `inputs.image` exactamente igual a
`images[].name`; el ejemplo Python parchea todos ellos con un nombre seguro
derivado de la extensión.

## Parámetros y nodos

`prompt` y `image` son obligatorios. Los demás son overrides opcionales: si no
se proporcionan, se conservan los valores del fixture `api-workflow.json`.

| Parámetro | Ruta en workflow | Tipo y rango del cliente | Valor del fixture |
|---|---|---|---|
| `prompt` | `317.inputs.prompt` | texto, obligatorio | `Make a new shot...` |
| `negative_prompt` | `318.inputs.prompt` | texto opcional | vacío |
| `steps` | `320.inputs.steps` | entero 1–200 | 12 |
| `seed` | `320.inputs.seed` | entero 0–2⁶⁴−1 | 817020100192714 |
| `cfg` | `321.inputs.value` | número 0–30 | 1 |
| `resolution` | `264.inputs.value` | entero 16–8192 | 1344 |
| `ref_boost` | `319.inputs.ref_boost` | número 0–1000 | 4.0 |
| `ref_boost_a` | `319.inputs.ref_boost_a` | número 0–1000 | 1.0 |
| `fit_mode` | `319.inputs.fit_mode` | `fit` o `crop` | `fit` |
| `grounding_px` | `317.inputs.grounding_px` y `318.inputs.grounding_px` | entero 256–2048 | 1024 |

Si se solicita un override y falta su nodo o campo, el cliente debe fallar con
un error claro, no enviarlo como un campo top-level.

## Cliente Python ejecutable

Instala `requests`, exporta el secreto sin escribir su valor en el código y
ejecuta el archivo. Este ejemplo es autónomo y no depende de funciones ocultas:

```python
import base64, json, os, re, time
from pathlib import Path
import requests

ENDPOINT = "5fj6bxupuhijp3"
TERMINAL = {"COMPLETED", "FAILED", "CANCELLED", "CANCELED", "TIMED_OUT"}
MAX_IMAGE = 7 * 1024 * 1024
MAX_REQUEST = 9_500_000

def set_input(workflow, node, field, value):
    try:
        inputs = workflow[node]["inputs"]
        if field not in inputs:
            raise KeyError
        inputs[field] = value
    except (KeyError, TypeError):
        raise ValueError(f"falta {node}.inputs.{field} para aplicar el control")

def safe_name(source):
    if source.suffix.lower() not in {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".tif", ".tiff"}:
        raise ValueError("extensión de imagen no soportada")
    return "input" + source.suffix.lower()

def safe_output(directory, filename, used):
    name = Path(str(filename or "output.png")).name
    if not re.fullmatch(r"[A-Za-z0-9._-]+", name):
        name = "output.png"
    path = directory / name
    stem, suffix = path.stem, path.suffix
    index = 1
    while path.exists() or path in used:
        path = directory / f"{stem}-{index}{suffix}"
        index += 1
    used.add(path)
    return path

def run(image_path, prompt, output_dir="salidas", timeout=300, poll_interval=3,
        cancel_on_timeout=False, **overrides):
    source = Path(image_path)
    if not source.is_file():
        raise ValueError(f"no existe la imagen: {source}")
    raw = source.read_bytes()
    if len(raw) > MAX_IMAGE:
        raise ValueError("la imagen supera 7 MiB")
    image_name = safe_name(source)
    workflow = json.loads(Path(__file__).with_name("api-workflow.json").read_text())
    for spec in workflow.values():
        if spec.get("class_type") == "LoadImage":
            spec["inputs"]["image"] = image_name
    set_input(workflow, "317", "prompt", prompt)
    mapping = {
        "negative_prompt": ("318", "prompt"), "steps": ("320", "steps"),
        "seed": ("320", "seed"), "cfg": ("321", "value"),
        "resolution": ("264", "value"), "ref_boost": ("319", "ref_boost"),
        "ref_boost_a": ("319", "ref_boost_a"), "fit_mode": ("319", "fit_mode"),
    }
    for name, value in overrides.items():
        if value is not None:
            if name == "grounding_px":
                continue
            node, field = mapping[name]
            set_input(workflow, node, field, value)
    if overrides.get("grounding_px") is not None:
        set_input(workflow, "317", "grounding_px", overrides["grounding_px"])
        set_input(workflow, "318", "grounding_px", overrides["grounding_px"])
    payload = {"input": {"workflow": workflow, "images": [
        {"name": image_name, "image": base64.b64encode(raw).decode("ascii")}
    ]}}
    if len(json.dumps(payload, separators=(",", ":")).encode()) > MAX_REQUEST:
        raise ValueError("el payload supera aproximadamente 9,5 MB")
    key = os.environ.get("RUNPOD_API_KEY")
    if not key:
        raise RuntimeError("falta RUNPOD_API_KEY")
    base = f"https://api.runpod.ai/v2/{ENDPOINT}"
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    response = requests.post(base + "/run", headers=headers, json=payload, timeout=timeout)
    response.raise_for_status()
    job_id = response.json()["id"]
    deadline = time.monotonic() + timeout
    while True:
        if time.monotonic() >= deadline:
            if cancel_on_timeout:
                requests.post(base + f"/cancel/{job_id}", headers=headers, timeout=30)
            raise TimeoutError("se agotó el tiempo de polling")
        result = requests.get(base + f"/status/{job_id}", headers=headers, timeout=30).json()
        status = result.get("status")
        if status in TERMINAL:
            break
        time.sleep(poll_interval)
    if status != "COMPLETED":
        raise RuntimeError(f"RunPod terminó en estado {status}")
    directory, used = Path(output_dir), set()
    directory.mkdir(parents=True, exist_ok=True)
    saved = []
    images = (result.get("output") or {}).get("images", [])
    if isinstance(images, dict):
        images = [images]
    for item in images:
        encoded = item.get("data") or item.get("image")
        if not isinstance(encoded, str) or not encoded:
            raise ValueError("RunPod devolvió una imagen sin Base64 válido")
        if encoded.startswith("data:"):
            encoded = encoded.split(",", 1)[1]
        data = base64.b64decode(encoded, validate=True)
        path = safe_output(directory, item.get("filename"), used)
        path.write_bytes(data)
        saved.append({"path": str(path), "bytes": len(data)})
    return {"job_id": job_id, "status": status, "outputs": saved}

if __name__ == "__main__":
    result = run("persona.jpg", "Create a new photograph of the same person in a cafe; preserve identity.",
                 output_dir="salidas", steps=12, cfg=1, resolution=1344)
    print(json.dumps(result, ensure_ascii=False))  # solo metadatos, nunca Base64
```

La respuesta inicial de `/run` contiene `id`, que es el `job_id`. `IN_QUEUE` y
`IN_PROGRESS` requieren seguir consultando. `COMPLETED` suele contener
`output.images`, con entradas `{data, type: "base64", filename}` o
`{image, data, filename}`; el ejemplo acepta ambas variantes y también elimina
defensivamente un prefijo Data URL. `FAILED`, `CANCELLED`/`CANCELED` y
`TIMED_OUT` son terminales y no deben tratarse como éxito.

Fallos comunes son olvidar `RUNPOD_API_KEY`, enviar `workflow.json`, enviar el
workflow como string, no hacer coincidir el nombre de `LoadImage`, superar los
límites de imagen/payload, solicitar un campo inexistente o enviar una imagen
sin Base64 válido. Los errores HTTP deben registrarse solo truncados y
redactados; nunca muestres la respuesta completa si pudiera contener secretos.
