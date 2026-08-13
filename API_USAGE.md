# API usage

Replace `ENDPOINT_ID` with the deployed endpoint ID. Store the token in
`RUNPOD_API_KEY`; never put a real token in scripts or documentation.

## Shorthand input

The minimal payload is either:

```json
{"prompt":"a portrait in soft light","image":"data:image/png;base64,..."}
```

or:

```json
{"prompt":"a portrait in soft light","image_url":"https://example.com/reference.png"}
```

## Optional generation parameters (shorthand)

Every parameter except `prompt` and `image`/`image_url` is optional. When
omitted, the bundled workflow defaults are used. When present, the value
overrides the default for that job only:

| Parameter | Type | Default | Range / options |
|---|---|---|---|
| `steps` | int | 8 | 1–100 (Turbo: 8–12; 10 balanced, 12 more face detail) |
| `cfg` | float | 1.0 | 0–20 (keep 1.0 for Turbo edits; >1 only for removals on raw) |
| `ref_boost` | float | 4.0 | 0–1000 (fidelity dial; ~4 strong likeness, >10 over-copies, <1 creative freedom) |
| `ref_boost_a` | float | 1.0 | 0–1000 (scene dial, only matters in two-reference workflows) |
| `fit_mode` | str | `fit` | `fit` (v1.2, recommended) or `crop (legacy)` (v1/v1.1 weights) |
| `grounding_px` | int | 1024 | 256–2048 (trained range 384–768; higher = stronger identity, lower if doubled compositions) |
| `resolution` | int | 1344 | 256–8192 (longest side, px; keep ≤2 MP, ~1024–1344) |
| `seed` | int | fixed per workflow | 0–2⁶³−1 (omit to keep the template seed) |

`grounding_px` is applied to both the positive and the negative grounded-encode
nodes. `resolution` sets the longest side of the source before encoding (the
aspect ratio is preserved; output follows the source AR).

Example with overrides:

```json
{
  "prompt": "a portrait in soft light",
  "image": "data:image/png;base64,...",
  "steps": 12,
  "ref_boost": 4.0,
  "grounding_px": 768,
  "resolution": 1344
}
```

Invalid values are rejected with a per-field error before the job is queued.
These overrides apply only in shorthand mode; when a full `workflow` is
supplied, the workflow is the source of truth and these keys are ignored.

`image` may also be a base64 string or `{ "name": "reference.png", "image": "..." }`.
The optional object name is used only as an extension hint. The worker generates
a unique job-scoped filename and injects that same name into the bundled
workflow, so concurrent jobs do not overwrite one another.
Remote images must use HTTP(S), resolve to public addresses, and be no larger
than 20 MB. Redirects are rejected. Inline decoded image data is also limited
to 20 MB.

## Synchronous request

```bash
curl -X POST "https://api.runpod.ai/v2/ENDPOINT_ID/runsync" \
  -H "Authorization: Bearer $RUNPOD_API_KEY" -H "Content-Type: application/json" \
  -d '{"input":{"prompt":"a portrait","image":"..."}}'
```

## Asynchronous request and status

```bash
curl -X POST "https://api.runpod.ai/v2/ENDPOINT_ID/run" \
  -H "Authorization: Bearer $RUNPOD_API_KEY" -H "Content-Type: application/json" \
  -d '{"input":{"prompt":"a portrait","image_url":"https://example.com/reference.png"}}'
curl "https://api.runpod.ai/v2/ENDPOINT_ID/status/JOB_ID" \
  -H "Authorization: Bearer $RUNPOD_API_KEY"
```

Responses use the RunPod envelope: `{ "id", "status", "output" }` (and an
`error` field when applicable). Successful output contains generated images as
objects with `type`, `data` (base64), and `filename`.

If `workflow` is supplied, the existing full workflow API remains available;
otherwise all workflow parameters are fixed by the bundled template. Fixed
shorthand defaults include node `317` prompt injection, node `78` image
injection, the configured samplers/LoRAs/seeds, a 15-second HTTP download
timeout, and 20 MB decoded-image limits.
