"""Descarga los pesos de los LLM con revisión fijada (commit de Hugging Face) en $LLM_DIR (modelos/).

Uso:  python -m src.download_models            (todos)
      python -m src.download_models qwen2.5-1.5b-q4
"""
import os
import sys
from pathlib import Path

from huggingface_hub import hf_hub_download, snapshot_download

LLM_DIR = Path(os.environ.get("LLM_DIR", "modelos"))

# id -> (repositorio, revisión, archivo GGUF o None para un modelo transformers completo)
MODELS = {
    "qwen2.5-1.5b-q4": ("Qwen/Qwen2.5-1.5B-Instruct-GGUF", "91cad51170dc346986eccefdc2dd33a9da36ead9",
                        "qwen2.5-1.5b-instruct-q4_k_m.gguf"),
    "qwen2.5-3b-q4": ("Qwen/Qwen2.5-3B-Instruct-GGUF", "7dabda4d13d513e3e842b20f0d435c732f172cbe",
                      "qwen2.5-3b-instruct-q4_k_m.gguf"),
    "qwen2.5-1.5b-hf": ("Qwen/Qwen2.5-1.5B-Instruct", "989aa7980e4cf806f80c7fef2b1adb7bc71aa306", None),
}


def model_path(model_id: str) -> Path:
    filename = MODELS[model_id][2]
    return LLM_DIR / model_id / (filename or "")


def download(model_id: str) -> Path:
    repo, rev, filename = MODELS[model_id]
    target = LLM_DIR / model_id
    if filename:
        hf_hub_download(repo, filename, revision=rev, local_dir=target)
    else:
        snapshot_download(repo, revision=rev, local_dir=target,
                          allow_patterns=["*.json", "*.safetensors", "*.txt", "tokenizer*", "merges.txt", "vocab.json"])
    return model_path(model_id)


if __name__ == "__main__":
    for mid in sys.argv[1:] or MODELS:
        print(mid, "->", download(mid))
