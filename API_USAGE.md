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
