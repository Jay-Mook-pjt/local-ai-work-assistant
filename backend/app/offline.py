"""Keep model libraries off the network.

Imported first by the API (app.main) and the worker (worker.main). Hugging Face
reads HF_HUB_OFFLINE when huggingface_hub is first imported, so this must run
before mlx_whisper / pyannote are imported anywhere. Models are already in the
local cache; only the explicit one-time download command goes online.
"""

import os

for key, value in {
    "HF_HUB_OFFLINE": "1",  # no "latest revision" checks against huggingface.co
    "HF_HUB_DISABLE_TELEMETRY": "1",
    "PYANNOTE_METRICS_ENABLED": "false",  # pyannote.audio 4.x usage telemetry
    "TOKENIZERS_PARALLELISM": "false",
}.items():
    os.environ[key] = value
