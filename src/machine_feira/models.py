"""Disponibiliza os modelos locais necessários para as tarefas do MediaPipe."""

from __future__ import annotations

from pathlib import Path
from urllib.request import urlretrieve

HAND_LANDMARKER_URL = (
    "https://storage.googleapis.com/mediapipe-models/hand_landmarker/"
    "hand_landmarker/float16/latest/hand_landmarker.task"
)


def ensure_hand_landmarker_model() -> Path:
    """Retorna o modelo de mãos, baixando-o da fonte oficial quando necessário."""
    model_path = Path(__file__).resolve().parents[2] / "models" / "hand_landmarker.task"
    if model_path.is_file() and model_path.stat().st_size > 1_000_000:
        return model_path

    model_path.parent.mkdir(parents=True, exist_ok=True)
    print("Baixando o modelo oficial de reconhecimento de mãos (primeira execução)...")
    try:
        urlretrieve(HAND_LANDMARKER_URL, model_path)
    except OSError as error:
        raise RuntimeError(
            "Não foi possível baixar o modelo do MediaPipe. Verifique sua conexão e tente novamente."
        ) from error
    return model_path
