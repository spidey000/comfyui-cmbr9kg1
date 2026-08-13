#!/usr/bin/env python3
"""Small, redacted RunPod Serverless client for the Krea2 API workflow."""
import argparse, base64, json, re, struct, time
from pathlib import Path

import requests

DEFAULT_ENDPOINT = "5fj6bxupuhijp3"
TERMINAL = {"COMPLETED", "FAILED", "CANCELLED", "CANCELED", "TIMED_OUT"}
EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".tif", ".tiff"}
MAX_IMAGE_BYTES = 7 * 1024 * 1024
MAX_REQUEST_BYTES = 9_500_000

def fail(message): raise SystemExit("Error: " + message)

def set_field(wf, node, field, value, label):
    if node not in wf or not isinstance(wf[node], dict) or "inputs" not in wf[node] or field not in wf[node]["inputs"]:
        fail(f"no se puede aplicar {label}: falta el nodo/campo {node}.inputs.{field}")
    wf[node]["inputs"][field] = value

def validate_controls(args):
    checks = (
        ("steps", args.steps, lambda value: 1 <= value <= 200),
        ("cfg", args.cfg, lambda value: 0 <= value <= 30),
        ("seed", args.seed, lambda value: 0 <= value < 2**64),
        ("resolution", args.resolution, lambda value: 16 <= value <= 8192),
        ("ref-boost", args.ref_boost, lambda value: 0 <= value <= 1000),
        ("ref-boost-a", args.ref_boost_a, lambda value: 0 <= value <= 1000),
        ("grounding-px", args.grounding_px, lambda value: 256 <= value <= 2048),
    )
    for name, value, valid in checks:
        if value is not None and not valid(value):
            fail(f"--{name} tiene un valor fuera de rango")
    if args.fit_mode is not None and args.fit_mode not in {"fit", "crop"}:
        fail("--fit-mode debe ser fit o crop")

def prepare(args):
    validate_controls(args)
    source = Path(args.image).expanduser()
    if not source.is_file(): fail(f"la imagen no existe: {source}")
    if source.stat().st_size > MAX_IMAGE_BYTES: fail("la imagen supera 7 MiB; el endpoint /run tiene un límite de payload cercano a 10 MB")
    if source.suffix.lower() not in EXTENSIONS: fail("extensión de imagen no soportada")
    workflow_path = Path(args.workflow).expanduser()
    try: wf = json.loads(workflow_path.read_text(encoding="utf-8"))
    except Exception as exc: fail(f"no se pudo cargar workflow: {exc}")
    if not isinstance(wf, dict): fail("el workflow debe ser un objeto API")
    safe_name = "input" + source.suffix.lower()
    loads = []
    for node, spec in wf.items():
        if isinstance(spec, dict) and spec.get("class_type") == "LoadImage":
            if "inputs" not in spec or "image" not in spec["inputs"]: fail(f"LoadImage {node} no tiene inputs.image")
            spec["inputs"]["image"] = safe_name; loads.append(node)
    if not loads: fail("el workflow no contiene nodos LoadImage")
    set_field(wf, "317", "prompt", args.prompt, "prompt")
    controls = {}
    for value, node, field, label in [(args.negative_prompt,"318","prompt","negative_prompt"),(args.steps,"320","steps","steps"),(args.seed,"320","seed","seed"),(args.cfg,"321","value","cfg"),(args.resolution,"264","value","resolution"),(args.ref_boost,"319","ref_boost","ref_boost"),(args.ref_boost_a,"319","ref_boost_a","ref_boost_a"),(args.fit_mode,"319","fit_mode","fit_mode"),(args.grounding_px,"317","grounding_px","grounding_px"),(args.grounding_px,"318","grounding_px","grounding_px")]:
        if value is not None: set_field(wf,node,field,value,label); controls[label] = value
    raw = source.read_bytes(); encoded = base64.b64encode(raw).decode("ascii")
    payload = {"input":{"workflow":wf,"images":[{"name":safe_name,"image":encoded}]}}
    request_bytes = len(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    if request_bytes > MAX_REQUEST_BYTES:
        fail("el payload supera el límite seguro de 9.5 MB para /run; usa una imagen más pequeña")
    return payload, {"nodes":len(wf),"load_images":loads,"image_name":safe_name,"image_bytes":len(raw),"request_bytes":request_bytes,"controls":controls}

def safe_output(name, directory, used):
    name = Path(str(name or "output.png")).name
    if not re.fullmatch(r"[A-Za-z0-9._-]+", name): name = "output.png"
    path = directory / name; stem, suffix = path.stem, path.suffix
    i = 1
    while path in used or path.exists(): path = directory / f"{stem}-{i}{suffix}"; i += 1
    used.add(path); return path

def dimensions(data):
    if data[:8] == b"\x89PNG\r\n\x1a\n" and len(data) >= 24: return struct.unpack(">II", data[16:24])
    if data[:2] == b"\xff\xd8":
        i = 2
        while i + 9 < len(data):
            if data[i] != 0xff:
                i += 1
                continue
            while i + 1 < len(data) and data[i + 1] == 0xff: i += 1
            marker = data[i + 1]
            if marker in (0xd8, 0xd9):
                i += 2
                continue
            if i + 4 > len(data): break
            length = struct.unpack(">H", data[i + 2:i + 4])[0]
            if length < 2 or i + 2 + length > len(data): break
            if marker in set(range(0xc0, 0xc4)) | set(range(0xc5, 0xc8)) | set(range(0xc9, 0xcc)) | set(range(0xcd, 0xd0)):
                if i + 9 <= len(data):
                    height, width = struct.unpack(">HH", data[i + 5:i + 9])
                    return width, height
            i += 2 + length
    return None

def main():
    p=argparse.ArgumentParser(); p.add_argument("--image",required=True); p.add_argument("--prompt",required=True); p.add_argument("--endpoint",default=DEFAULT_ENDPOINT); p.add_argument("--workflow",default=str(Path(__file__).with_name("api-workflow.json"))); p.add_argument("--output-dir",default="."); p.add_argument("--timeout",type=float,default=300); p.add_argument("--poll-interval",type=float,default=3); p.add_argument("--steps",type=int); p.add_argument("--cfg",type=float); p.add_argument("--seed",type=int); p.add_argument("--resolution",type=int); p.add_argument("--ref-boost",type=float); p.add_argument("--ref-boost-a",type=float); p.add_argument("--fit-mode"); p.add_argument("--grounding-px",type=int); p.add_argument("--negative-prompt"); p.add_argument("--dry-run",action="store_true"); p.add_argument("--cancel-on-timeout",action="store_true"); args=p.parse_args()
    payload, meta = prepare(args)
    if args.dry_run: print(json.dumps({"endpoint":args.endpoint,**meta},ensure_ascii=False)); return
    key = __import__("os").environ.get("RUNPOD_API_KEY")
    if not key: fail("falta RUNPOD_API_KEY")
    base=f"https://api.runpod.ai/v2/{args.endpoint}"; headers={"Content-Type":"application/json","Authorization":f"Bearer {key}"}
    try:
        r=requests.post(base+"/run",headers=headers,json=payload,timeout=args.timeout); r.raise_for_status(); job=r.json().get("id")
        if not job: fail("RunPod no devolvió job_id")
        deadline=time.monotonic()+args.timeout
        while True:
            if time.monotonic() >= deadline:
                if args.cancel_on_timeout: requests.post(base+f"/cancel/{job}",headers=headers,timeout=30)
                fail("timeout esperando el trabajo")
            r=requests.get(base+f"/status/{job}",headers=headers,timeout=30); r.raise_for_status(); result=r.json(); status=result.get("status")
            if status in TERMINAL: break
            time.sleep(args.poll_interval)
    except requests.RequestException as exc:
        body = str(exc.response.text)[:500] if exc.response is not None else str(exc)
        body = re.sub(r"(?i)(authorization|token|api[_-]?key)\s*[:=]\s*[^,\s}]+", r"\1: [REDACTED]", body)
        fail(f"HTTP {getattr(exc.response,'status_code','?')}: {body}")
    if status != "COMPLETED": fail(f"trabajo {job} terminó en {status}")
    outdir=Path(args.output_dir); outdir.mkdir(parents=True,exist_ok=True); paths=[]; used=set()
    images=(result.get("output") or {}).get("images",[])
    if isinstance(images,dict): images=[images]
    for item in images:
        encoded=item.get("data") or item.get("image"); encoded=encoded.split(",",1)[-1] if isinstance(encoded,str) and encoded.startswith("data:") else encoded
        if not encoded: continue
        try: data=base64.b64decode(encoded,validate=True)
        except Exception: fail("RunPod devolvió Base64 inválido")
        path=safe_output(item.get("filename"),outdir,used); path.write_bytes(data); d=dimensions(data); paths.append({"path":str(path),"bytes":len(data),**({"dimensions":d} if d else {})})
    print(json.dumps({"endpoint":args.endpoint,"job_id":job,"status":status,"outputs":paths},ensure_ascii=False))
if __name__ == "__main__": main()
