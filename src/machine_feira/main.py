"""Ponto de entrada do protótipo de reconhecimento por webcam com HUD enriquecido."""

from __future__ import annotations

import argparse

import cv2
import mediapipe as mp

from .automation import DesktopAutomation
from .hand_gestures import HandGestureRecognizer
from .models import ensure_hand_landmarker_model
from .types import Gesture, GestureEvent

# Mapa de nomes amigáveis para exibição na interface
GESTURE_LABELS: dict[Gesture, str] = {
    Gesture.NONE: "Navegando",
    Gesture.PINCH: "Mover Janela (Pinça)",
    Gesture.MAXIMIZE: "Maximizar (2 Mãos)",
    Gesture.RESTORE: "Restaurar (2 Mãos)",
    Gesture.MINIMIZE: "Minimizar (Palma p/ Baixo)",
    Gesture.SWIPE_LEFT: "Área de Trabalho Anterior",
    Gesture.SWIPE_RIGHT: "Próxima Área de Trabalho",
    Gesture.SCROLL: "Rolar Página",
    Gesture.ZOOM_IN: "Zoom In (+)",
    Gesture.ZOOM_OUT: "Zoom Out (-)",
    Gesture.PAGE_FORWARD: "Avançar Página (Círculo Horário)",
    Gesture.PAGE_BACK: "Voltar Página (Círculo Anti-Horário)",
    Gesture.DWELL_CLICK: "Clique Confirmado!",
    Gesture.VOICE_ACTIVATE: "Voz / Ditado (👍)",
    Gesture.CONFIRM: "Confirmar / Enter (👌)",
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
    parser.add_argument("--camera", type=int, default=0, help="índice da webcam a utilizar (padrão: 0)")
    parser.add_argument("--max-frame-width", type=int, default=960, help="largura máxima do quadro processado")
    args = parser.parse_args()

    print(f"Abrindo webcam {args.camera}...")
    camera = cv2.VideoCapture(args.camera)
    if not camera.isOpened():
        raise RuntimeError("Não foi possível acessar a webcam padrão.")

    recognizer = HandGestureRecognizer()
    automation = DesktopAutomation(enabled=args.control)
    model_path = ensure_hand_landmarker_model()
    print("Inicializando reconhecimento de mãos (até 2 mãos com suavização One-Euro)...")
    options = mp.tasks.vision.HandLandmarkerOptions(
        base_options=mp.tasks.BaseOptions(model_asset_path=str(model_path)),
        running_mode=mp.tasks.vision.RunningMode.VIDEO,
        num_hands=2,
        min_hand_detection_confidence=0.60,
        min_hand_presence_confidence=0.60,
        min_tracking_confidence=0.60,
    )

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

                label = "Nenhuma mão"
                hands_count = 0

                if result.hand_landmarks:
                    hands_count = len(result.hand_landmarks)
                    event = recognizer.update(result.hand_landmarks)
                    automation.handle(event)

                    for idx, hand_lms in enumerate(result.hand_landmarks):
                        color = HAND_COLORS[idx % len(HAND_COLORS)]
                        _draw_hand_skeleton(frame, hand_lms, color)

                    _draw_feedback(frame, event)
                    label = GESTURE_LABELS.get(event.gesture, event.gesture.name)
                else:
                    recognizer.update([])

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


def _draw_feedback(frame: object, event: GestureEvent) -> None:
    """Renderiza feedback visual: cursor estabilizado, rastro de círculo e medidor de dwell."""
    height, width = frame.shape[:2]
    cx, cy = int(event.cursor.x * width), int(event.cursor.y * height)

    # 1. Rastro de trajetória circular
    if event.trail and len(event.trail) >= 2:
        for i in range(1, len(event.trail)):
            p1 = event.trail[i - 1]
            p2 = event.trail[i]
            pt1 = (int(p1.x * width), int(p1.y * height))
            pt2 = (int(p2.x * width), int(p2.y * height))
            alpha = i / len(event.trail)
            thickness = max(1, int(3 * alpha))
            cv2.line(frame, pt1, pt2, (255, 80, 255), thickness)

    # 2. Cursor indicador
    cv2.circle(frame, (cx, cy), 6, (0, 255, 255), 2)
    cv2.circle(frame, (cx, cy), 2, (0, 0, 255), -1)

    # 3. Indicador de progresso do Dwell Click
    if event.dwell_progress > 0:
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
