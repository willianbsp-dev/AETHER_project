"""Ponto de entrada do protótipo de reconhecimento por webcam com HUD enriquecido."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import cv2
import mediapipe as mp

from .automation import DesktopAutomation
from .hand_gestures import HandGestureRecognizer
from .models import ensure_hand_landmarker_model
from .types import Gesture, GestureEvent

# Mapa de nomes amigáveis para exibição na interface
GESTURE_LABELS: dict[Gesture, str] = {
    Gesture.NONE: "Navegando",
    Gesture.CLICK_LEFT: "Clique esquerdo",
    Gesture.CLICK_RIGHT: "Clique direito",
    Gesture.PINCH: "Arrastar (Pinça)",
    Gesture.MAXIMIZE: "Maximizar (2 Mãos)",
    Gesture.RESTORE: "Restaurar (2 Mãos)",
    Gesture.MINIMIZE: "Minimizar (2 Mãos)",
    Gesture.SWIPE_LEFT: "Área de Trabalho Anterior",
    Gesture.SWIPE_RIGHT: "Próxima Área de Trabalho",
    Gesture.SCROLL: "Rolar Página",
    Gesture.ZOOM_IN: "Zoom In (+)",
    Gesture.ZOOM_OUT: "Zoom Out (-)",
    Gesture.PAGE_FORWARD: "Avançar Página (Círculo Horário)",
    Gesture.PAGE_BACK: "Voltar Página (Círculo Anti-Horário)",
    Gesture.UNDO: "Desfazer (Círculo Anti-Horário)",
    Gesture.DWELL_CLICK: "Clique por Permanência",
    Gesture.VOICE_ACTIVATE: "Ativar Voz (👌)",
    Gesture.CONFIRM: "Confirmar / Enter (👍)",
    Gesture.PAUSE_TOGGLE: "Pausar / Retomar",
    Gesture.KEYBOARD_TOGGLE: "Teclado Virtual",
}

HAND_COLORS = [
    (0, 255, 0),    # Verde (Mão 1)
    (255, 200, 0),  # Ciano/Amarelo (Mão 2)
]

# Conexões dos 21 landmarks da mão para desenhar o esqueleto
HAND_CONNECTIONS = [
    (0, 1), (1, 2), (2, 3), (3, 4),        # Polegar
    (0, 5), (5, 6), (6, 7), (7, 8),        # Indicador
    (5, 9), (9, 10), (10, 11), (11, 12),   # Médio
    (9, 13), (13, 14), (14, 15), (15, 16), # Anelar
    (13, 17), (17, 18), (18, 19), (19, 20),# Mínimo
    (0, 17),                               # Base da palma
]


def main() -> None:
    parser = argparse.ArgumentParser(description="Controle por gestos aéreos")
    parser.add_argument("--control", action="store_true", help="habilita automação real do computador")
    parser.add_argument("--no-settings", action="store_true", help="não abrir a janela de configurações")
    parser.add_argument("--camera", type=int, default=0, help="índice da webcam a utilizar (padrão: 0)")
    parser.add_argument("--max-frame-width", type=int, default=960, help="largura máxima do quadro processado")
    args = parser.parse_args()

    print(f"Abrindo webcam {args.camera}...")
    camera = cv2.VideoCapture(args.camera)
    if not camera.isOpened():
        raise RuntimeError("Não foi possível acessar a webcam padrão.")

    recognizer = HandGestureRecognizer()
    automation = DesktopAutomation(enabled=args.control)
    config_path = Path(__file__).resolve().parents[2] / "aether_settings.json"
    settings_process = None
    if not args.no_settings:
        settings_process = subprocess.Popen([sys.executable, "-m", "machine_feira.settings_window"])
    last_config_mtime = None
    active_config = {"scroll_threshold": recognizer.config.scroll_threshold, "scroll_intensity": 6, "tremor_filter": True}
    model_path = ensure_hand_landmarker_model()
    print("Inicializando reconhecimento de mãos (até 2 mãos com suavização One-Euro)...")
    options = mp.tasks.vision.HandLandmarkerOptions(
    base_options=mp.tasks.BaseOptions(model_asset_buffer=model_path.read_bytes()),
    running_mode=mp.tasks.vision.RunningMode.VIDEO,
    num_hands=2,
    min_hand_detection_confidence=0.60,
    min_hand_presence_confidence=0.60,
    min_tracking_confidence=0.60,
)

    window_name = "Machine Feira - Controle por Gestos"
    cv2.namedWindow(window_name, cv2.WINDOW_AUTOSIZE)
    try:
        cv2.setWindowProperty(window_name, cv2.WND_PROP_TOPMOST, 1)
    except Exception:
        pass

    try:
        with mp.tasks.vision.HandLandmarker.create_from_options(options) as detector:
            while True:
                received, frame = camera.read()
                if not received:
                    break
                frame = cv2.flip(frame, 1)
                frame = _resize_frame(frame, args.max_frame_width)
                rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_frame)
                timestamp_ms = int(cv2.getTickCount() * 1000 / cv2.getTickFrequency())
                result = detector.detect_for_video(image, timestamp_ms)
                try:
                    current_mtime = config_path.stat().st_mtime_ns
                    if current_mtime != last_config_mtime:
                        loaded = json.loads(config_path.read_text(encoding="utf-8"))
                        active_config.update(loaded)
                        threshold = min(0.030, max(0.004, float(active_config["scroll_threshold"])))
                        intensity = min(15, max(1, int(active_config["scroll_intensity"])))
                        tremor = bool(active_config["tremor_filter"])
                        recognizer.config = replace(recognizer.config, scroll_threshold=threshold)
                        automation.scroll_amount = intensity
                        if getattr(recognizer, "_settings_tremor_enabled", None) != tremor:
                            recognizer.apply_tremor_filter(tremor)
                            recognizer._settings_tremor_enabled = tremor
                        last_config_mtime = current_mtime
                except (OSError, ValueError, TypeError, json.JSONDecodeError):
                    pass

                label = "Nenhuma mão"
                hands_count = 0

                if result.hand_landmarks:
                    hands_count = len(result.hand_landmarks)
                    event = recognizer.update(result.hand_landmarks)
                    automation.handle(event)

                    for idx, hand_lms in enumerate(result.hand_landmarks):
                        color = HAND_COLORS[idx % len(HAND_COLORS)]
                        _draw_hand_skeleton(frame, hand_lms, color)

                    _draw_feedback(frame, event, recognizer.is_pointer_pose)
                    label = GESTURE_LABELS.get(event.gesture, event.gesture.name)
                else:
                    recognizer.update([])

                if not recognizer.calibrated:
                    calibration_pct = int(recognizer.calibration_progress * 100)
                    label = f"Calibrando mãos... {calibration_pct}%"
                elif recognizer.paused:
                    label = "AETHER PAUSADO"

                mode = "CONTROLE ATIVO" if args.control else "MODO SEGURO"
                mode_color = (0, 0, 255) if args.control else (0, 200, 0)
                # Painel de status superior
                cv2.rectangle(frame, (10, 10), (frame.shape[1] - 10, 50), (30, 30, 30), -1)
                cv2.rectangle(frame, (10, 10), (frame.shape[1] - 10, 50), (80, 80, 80), 1)
                cv2.putText(
                    frame,
                    f"[{mode}] Mãos: {hands_count} | Gesto: {label}",
                    (20, 37),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.65,
                    mode_color,
                    2,
                )
                cv2.imshow("Machine Feira - Controle por Gestos", frame)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break
    finally:
        automation.release()
        if settings_process is not None and settings_process.poll() is None:
            settings_process.terminate()
        camera.release()
        cv2.destroyAllWindows()


def _draw_hand_skeleton(frame: object, landmarks: list[object], color: tuple[int, int, int]) -> None:
    """Desenha o esqueleto e juntas da mão com cor personalizada."""
    height, width = frame.shape[:2]
    # Conexões
    for start_idx, end_idx in HAND_CONNECTIONS:
        p1 = landmarks[start_idx]
        p2 = landmarks[end_idx]
        pt1 = (int(p1.x * width), int(p1.y * height))
        pt2 = (int(p2.x * width), int(p2.y * height))
        cv2.line(frame, pt1, pt2, (color[0] // 2, color[1] // 2, color[2] // 2), 1)

    # Juntas
    for landmark in landmarks:
        cx, cy = int(landmark.x * width), int(landmark.y * height)
        cv2.circle(frame, (cx, cy), 3, color, -1)



def _draw_feedback(frame: object, event: GestureEvent | None, show_cursor: bool) -> None:
    """Renderiza feedback visual: cursor estabilizado e rastro de círculo."""
    height, width = frame.shape[:2]

    if event is None:
        return

    cursor = event.cursor
    if cursor is not None:
        cx, cy = int(cursor.x * width), int(cursor.y * height)
    else:
        cx, cy = 0, 0

    if event.trail and len(event.trail) >= 2:
        for i in range(1, len(event.trail)):
            p1 = event.trail[i - 1]
            p2 = event.trail[i]
            pt1 = (int(p1.x * width), int(p1.y * height))
            pt2 = (int(p2.x * width), int(p2.y * height))
            alpha = i / len(event.trail)
            thickness = max(1, int(3 * alpha))
            cv2.line(frame, pt1, pt2, (255, 80, 255), thickness)

    if show_cursor and cursor is not None:
        cv2.circle(frame, (cx, cy), 6, (0, 255, 255), 2)
        cv2.circle(frame, (cx, cy), 2, (0, 0, 255), -1)


    # 3. Dwell foi desativado; não desenhamos bolinha de permanência.
    if False and event.dwell_progress > 0:
        radius = 22
        # Círculo base de fundo
        cv2.circle(frame, (cx, cy), radius, (100, 100, 100), 1)
        # Arco de progresso preenchendo
        angle = int(event.dwell_progress * 360)
        prog_color = (0, 255, 0) if event.dwell_progress >= 1.0 else (0, 200, 255)
        cv2.ellipse(frame, (cx, cy), (radius, radius), -90, 0, angle, prog_color, 3)


def _resize_frame(frame: object, max_width: int) -> object:
    """Reduz a carga de CPU e memória, preservando a proporção do quadro."""
    if max_width <= 0 or frame.shape[1] <= max_width:
        return frame
    scale = max_width / frame.shape[1]
    return cv2.resize(frame, (max_width, int(frame.shape[0] * scale)), interpolation=cv2.INTER_AREA)


if __name__ == "__main__":
    main()
