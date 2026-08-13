# Hermes + Krea2 mediante RunPod Serverless

El endpoint `5fj6bxupuhijp3` sirve exclusivamente para editar una fotografía o
crear una nueva toma manteniendo la identidad de una persona. Siempre necesita
una foto real de referencia: no es text-to-image y no usa ruido como sustituto.
Si el token fue expuesto, revócalo y crea otro. Guárdalo únicamente en la
variable `RUNPOD_API_KEY`, nunca en archivos, prompts ni logs.

## Instalación y ejecución

En el entorno del agente instala el cliente:

```bash
python -m pip install requests
export RUNPOD_API_KEY=<tu-token-nuevo>
python hermes_runpod_krea2.py --image /ruta/persona.jpg --prompt "Replace the background with a studio; preserve identity, face and clothing." --output-dir ./salidas
```

El script valida la imagen, carga `api-workflow.json` (objeto API) y descarga
los resultados. `workflow.json` es el formato canvas y no sirve como workflow
enviado a Serverless. El modo normal siempre llama al endpoint HTTPS de RunPod;
`--dry-run` solo existe como comprobación opcional del payload y no sustituye una
llamada Serverless.

Ejemplo de nueva toma: `--prompt "Create a new full-body photograph of the same
person standing in side profile on a city street; preserve facial identity and
hairstyle, changing pose and scene."` Se pueden ajustar `--steps`, `--cfg`,
`--seed`, `--resolution`, `--ref-boost`, `--ref-boost-a`, `--fit-mode` y
`--grounding-px`; `--cancel-on-timeout` cancela el trabajo al vencer el tiempo.

## Contrato conceptual

El cliente envía exactamente esta forma. `workflow` es el diccionario completo
cargado desde `api-workflow.json`; no es el nombre del archivo ni una cadena:

```python
workflow = load_json("api-workflow.json")  # dict completo de 17 nodos
payload = {
    "input": {
        "workflow": workflow,
        "images": [{"name": "input.jpg", "image": "BASE64_SIN_PREFIJO"}],
    }
}
```

Internamente parchea todos los `LoadImage.inputs.image` al mismo nombre e
inyecta controles en sus nodos. La API recibe `POST
https://api.runpod.ai/v2/5fj6bxupuhijp3/run` con `Authorization: Bearer
RUNPOD_API_KEY`; luego el cliente hace polling en `/status/{job_id}` hasta
`IN_QUEUE`, `IN_PROGRESS`, `COMPLETED`, `FAILED`, `CANCELLED/CANCELED` o
`TIMED_OUT`. Al completar, valida Base64 y guarda las imágenes localmente sin
imprimirlas.

Filebin puede usarse opcionalmente solo si el usuario lo pide explícitamente y
autoriza compartir la imagen.
