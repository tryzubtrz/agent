from __future__ import annotations

from typing import Any

LOCAL_MODEL_CATALOG: tuple[dict[str, Any], ...] = (
    {
        "id": "qwen3-8b",
        "runtime_ref": "qwen3:8b",
        "display_name": "Qwen3-8B",
        "capabilities": ["chat", "reasoning", "planning", "summarization"],
        "license": "Apache-2.0",
        "requirements": "16 GB RAM recommended; Ollama Q4_K_M download is about 5.2 GB",
        "runtime_backend": "ollama",
        "recommended": True,
    },
    {
        "id": "deepseek-r1-distill-qwen-14b",
        "runtime_ref": "deepseek-r1:14b",
        "display_name": "DeepSeek-R1-Distill-Qwen-14B",
        "capabilities": ["reasoning", "planning"],
        "license": "MIT checkpoint license",
        "requirements": "16–24 GB RAM; Ollama Q4_K_M download is about 9 GB",
        "runtime_backend": "ollama",
        "recommended": False,
    },
    {
        "id": "qwen2.5-coder-7b-instruct",
        "runtime_ref": "qwen2.5-coder:7b",
        "display_name": "Qwen2.5-Coder-7B-Instruct",
        "capabilities": ["coding", "reasoning"],
        "license": "Apache-2.0",
        "requirements": "16 GB RAM recommended; Ollama download is about 4.7 GB",
        "runtime_backend": "ollama",
        "recommended": False,
    },
    {
        "id": "qwen3-vl-8b-instruct",
        "display_name": "Qwen3-VL-8B-Instruct",
        "capabilities": ["vision", "ocr"],
        "license": "Apache-2.0",
        "requirements": "12–16 GB VRAM recommended",
        "runtime_backend": None,
        "recommended": False,
    },
    {
        "id": "bge-m3",
        "display_name": "BGE-M3",
        "capabilities": ["retrieval"],
        "license": "MIT",
        "requirements": "4–8 GB system RAM; GPU optional",
        "runtime_backend": None,
        "recommended": False,
    },
    {
        "id": "flux-1-schnell",
        "display_name": "FLUX.1 [schnell]",
        "capabilities": ["image"],
        "license": "Apache-2.0",
        "requirements": "About 12 GB VRAM comfortable; CPU offload is slower",
        "runtime_backend": None,
        "recommended": False,
    },
    {
        "id": "wan2.1-t2v-1.3b",
        "display_name": "Wan2.1-T2V-1.3B",
        "capabilities": ["video"],
        "license": "Apache-2.0",
        "requirements": "About 8.2 GB VRAM for 480p-class use",
        "runtime_backend": None,
        "recommended": False,
    },
    {
        "id": "whisper-turbo",
        "display_name": "Whisper Turbo",
        "capabilities": ["speech_to_text"],
        "license": "MIT",
        "requirements": "About 6 GB VRAM; CPU supported but slower",
        "runtime_backend": None,
        "recommended": False,
    },
    {
        "id": "kokoro-82m",
        "display_name": "Kokoro-82M",
        "capabilities": ["text_to_speech"],
        "license": "Apache-2.0",
        "requirements": "CPU-capable; Ukrainian voice quality requires validation",
        "runtime_backend": None,
        "recommended": False,
    },
    {
        "id": "paddleocr",
        "display_name": "PaddleOCR / PaddleOCR-VL",
        "capabilities": ["ocr", "vision"],
        "license": "Apache-2.0",
        "requirements": "Base OCR can run on CPU; VL path benefits from 8–12 GB VRAM",
        "runtime_backend": None,
        "recommended": False,
    },
)


def get_local_model(model_id: str) -> dict[str, Any] | None:
    return next((item for item in LOCAL_MODEL_CATALOG if item["id"] == model_id), None)


def installable_model_ids() -> set[str]:
    return {item["id"] for item in LOCAL_MODEL_CATALOG if item.get("runtime_ref")}
