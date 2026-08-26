"""Reconhecimento determinístico e suavizado de gestos a partir dos landmarks da mão."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
import math
from time import monotonic
from typing import Deque, Sequence

from .filter import OneEuroFilter, PointFilter
from .trajectory import CircleConfig, CircleTrajectoryRecognizer
from .types import Gesture, GestureEvent, Point

# Índices oficiais dos landmarks MediaPipe Hands
WRIST = 0
THUMB_CMC = 1
THUMB_MCP = 2
THUMB_IP = 3
THUMB_TIP = 4
INDEX_MCP = 5
INDEX_PIP = 6
INDEX_DIP = 7
INDEX_TIP = 8
MIDDLE_MCP = 9
MIDDLE_PIP = 10
MIDDLE_DIP = 11
MIDDLE_TIP = 12
RING_MCP = 13
RING_PIP = 14
RING_DIP = 15
RING_TIP = 16
PINKY_MCP = 17
PINKY_PIP = 18
PINKY_DIP = 19
PINKY_TIP = 20


@dataclass(frozen=True)
class GestureConfig:
    # Distância para iniciar e soltar pinça (com histerese)
    pinch_distance_start: float = 0.055
    pinch_distance_release: float = 0.075
    # Zoom
    zoom_step_distance: float = 0.035
    max_zoom_interaction_dist: float = 0.28
    # Dwell Click (raio estável e tempo)
    stable_distance: float = 0.030
    dwell_seconds: float = 0.50
    # Scroll (acumulador e limiar)
    scroll_threshold: float = 0.022
    # Swipes de palma aberta
    swipe_threshold: float = 0.070
    swipe_window_seconds: float = 0.35
    # Gestos de duas mãos (abertura e fechamento)
    two_hand_spread_threshold: float = 0.080
    two_hand_window_seconds: float = 0.45
    # Cooldown para ações discretas
    cooldown_seconds: float = 0.35
    # Configuração de círculos
    circle_config: CircleConfig = CircleConfig()


@dataclass
class _TimedVal:
    val: float
    time: float


@dataclass
class _TimedPoint:
    p: Point
    time: float


class HandGestureRecognizer:
    """Mantém o estado temporal, filtros de suavização e reconhecimento de gestos."""

    def __init__(self, config: GestureConfig | None = None) -> None:
        self.config = config or GestureConfig()
        self._circle_tracker = CircleTrajectoryRecognizer(self.config.circle_config)

        # Filtros One-Euro para estabilização do cursor e distâncias
        self._cursor_filter = PointFilter(min_cutoff=1.2, beta=0.008)
        self._pinch_filter = OneEuroFilter(min_cutoff=1.5, beta=0.01)
        self._two_hand_filter = OneEuroFilter(min_cutoff=1.0, beta=0.005)

        # Estado de pinça / arrasto (histerese)
        self._is_pinching = False

        # Estado de Dwell Click
        self._dwell_anchor: Point | None = None
        self._dwell_start_time: float | None = None
        self._dwell_fired = False

        # Estado de Scroll e Zoom
        self._scroll_accumulator = 0.0
        self._zoom_anchor_dist: float | None = None
        self._previous_filtered_index: Point | None = None

        # Históricos temporais
        self._palm_history: Deque[_TimedPoint] = deque(maxlen=30)
        self._two_hand_history: Deque[_TimedVal] = deque(maxlen=30)
        self._last_two_hand_seen = 0.0

        # Debounce para gestos estáticos (OK e Joinha)
        self._ok_counter = 0
        self._thumbs_up_counter = 0
        self._last_discrete_action = 0.0

    def update(
        self,
        hands: Sequence[object] | Sequence[Sequence[object]],
        now: float | None = None,
    ) -> GestureEvent:
        """Processa um quadro de detecção com 1 ou 2 mãos."""
        timestamp = monotonic() if now is None else now

        if not hands:
            self._reset_all()
            return GestureEvent(Gesture.NONE, Point(0.5, 0.5))

        # Normaliza formato da entrada de mãos
        first_elem = hands[0]
        if hasattr(first_elem, "x") and hasattr(first_elem, "y"):
            hands_list = [hands]
        else:
            hands_list = list(hands)

        # 1. GESTOS DE DUAS MÃOS (Maximizar / Restaurar)
        if len(hands_list) >= 2:
            self._last_two_hand_seen = timestamp
            two_hand_event = self._check_two_hand_gestures(hands_list[0], hands_list[1], timestamp)
            if two_hand_event:
                return two_hand_event
        else:
            # Mantém histórico por pequena tolerância (250ms) caso 1 mão suma brevemente
            if timestamp - self._last_two_hand_seen > 0.25:
                self._two_hand_history.clear()
                self._two_hand_filter.reset()

        # 2. GESTOS DE UMA MÃO (Mão primária)
        primary_hand = hands_list[0]
        return self._process_single_hand(primary_hand, timestamp)

    def _check_two_hand_gestures(
        self, hand1: Sequence[object], hand2: Sequence[object], now: float
    ) -> GestureEvent | None:
        p1 = self._point(hand1[WRIST])
        p2 = self._point(hand2[WRIST])
        raw_dist = math.hypot(p1.x - p2.x, p1.y - p2.y)
        dist = self._two_hand_filter.filter(raw_dist, now)
        mid_point = Point((p1.x + p2.x) / 2, (p1.y + p2.y) / 2)

        # Limpa pontos fora da janela
        while self._two_hand_history and (now - self._two_hand_history[0].time > self.config.two_hand_window_seconds):
            self._two_hand_history.popleft()

        self._two_hand_history.append(_TimedVal(dist, now))

        if len(self._two_hand_history) >= 4 and self._can_fire(now):
            start_dist = self._two_hand_history[0].val
            delta_dist = dist - start_dist

            # Afastamento de mãos -> MAXIMIZE
            if delta_dist >= self.config.two_hand_spread_threshold:
                self._last_discrete_action = now
                self._two_hand_history.clear()
                return GestureEvent(Gesture.MAXIMIZE, mid_point)
            # Aproximação de mãos -> RESTORE
            elif delta_dist <= -self.config.two_hand_spread_threshold:
                self._last_discrete_action = now
                self._two_hand_history.clear()
                return GestureEvent(Gesture.RESTORE, mid_point)

        return None

    def _process_single_hand(self, landmarks: Sequence[object], now: float) -> GestureEvent:
        wrist = self._point(landmarks[WRIST])
        raw_index = self._point(landmarks[INDEX_TIP])
        raw_thumb = self._point(landmarks[THUMB_TIP])

        # Suaviza o cursor para eliminar tremores de mira
        index = self._cursor_filter.filter(raw_index, now)
        raw_pinch_dist = self._distance(raw_index, raw_thumb)
        pinch_dist = self._pinch_filter.filter(raw_pinch_dist, now)

        index_ext = self._is_finger_extended(landmarks, INDEX_TIP, INDEX_PIP, INDEX_MCP)
        middle_ext = self._is_finger_extended(landmarks, MIDDLE_TIP, MIDDLE_PIP, MIDDLE_MCP)
        ring_ext = self._is_finger_extended(landmarks, RING_TIP, RING_PIP, RING_MCP)
        pinky_ext = self._is_finger_extended(landmarks, PINKY_TIP, PINKY_PIP, PINKY_MCP)

        # 1. Gesto: JOINHA 👍 (Ativar Voz/Digitação)
        if self._is_thumbs_up(landmarks, index_ext, middle_ext, ring_ext, pinky_ext):
            self._thumbs_up_counter += 1
            self._ok_counter = 0
            self._reset_dwell()
            self._circle_tracker.clear()
            self._is_pinching = False

            if self._thumbs_up_counter >= 2 and self._can_fire(now):
                self._last_discrete_action = now
                return GestureEvent(Gesture.VOICE_ACTIVATE, raw_thumb)
            return GestureEvent(Gesture.NONE, raw_thumb)
        else:
            self._thumbs_up_counter = 0

        # 2. Gesto: CONFIRMAR (Sinal de OK 👌)
        if self._is_ok_sign(landmarks, pinch_dist, middle_ext, ring_ext, pinky_ext):
            self._ok_counter += 1
            self._thumbs_up_counter = 0
            self._reset_dwell()
            self._circle_tracker.clear()
            self._is_pinching = False

            if self._ok_counter >= 2 and self._can_fire(now):
                self._last_discrete_action = now
                return GestureEvent(Gesture.CONFIRM, index)
            return GestureEvent(Gesture.NONE, index)
        else:
            self._ok_counter = 0

        # 3. Gesto: PALMA ABERTA (Minimizar / Trocar Área de Trabalho por Swipe)
        is_open_palm = index_ext and middle_ext and ring_ext and pinky_ext
        if is_open_palm:
            palm_event = self._check_open_palm_swipe(wrist, now)
            if palm_event:
                self._reset_dwell()
                self._circle_tracker.clear()
                self._is_pinching = False
                return palm_event

        # 4. Gesto: ZOOM IN / ZOOM OUT (Variação da pinça com outros dedos fechados)
        if not middle_ext and not ring_ext and not pinky_ext and pinch_dist <= self.config.max_zoom_interaction_dist:
            zoom_event = self._check_zoom(index, pinch_dist, now)
            if zoom_event:
                self._reset_dwell()
                self._circle_tracker.clear()
                return zoom_event
        else:
            self._zoom_anchor_dist = None

        # 5. Gesto: PINÇA COM HISTERESE (Mover Janela / Arrastar)
        if not self._is_pinching and pinch_dist <= self.config.pinch_distance_start:
            self._is_pinching = True
        elif self._is_pinching and pinch_dist > self.config.pinch_distance_release:
            self._is_pinching = False

        if self._is_pinching:
            self._reset_dwell()
            self._circle_tracker.clear()
            self._remember(index)
            return GestureEvent(Gesture.PINCH, index)

        # 6. Gesto: APENAS INDICADOR ESTENDIDO (Círculos, Scroll ou Dwell Click)
        if index_ext and not middle_ext and not ring_ext and not pinky_ext:
            # A. Trajetória Circular (Avançar/Voltar Página)
            self._circle_tracker.add_point(index, now)
            circle_gesture = self._circle_tracker.evaluate(now)
            if circle_gesture is not Gesture.NONE:
                self._reset_dwell()
                self._last_discrete_action = now
                self._remember(index)
                return GestureEvent(circle_gesture, index, trail=self._circle_tracker.get_trail())

            # B. Rolar Página (Scroll vertical dominante)
            scroll_event = self._check_scroll(index)
            if scroll_event:
                self._reset_dwell()
                self._remember(index)
                return scroll_event

            # C. Dwell Click (Pousar o indicador parado)
            dwell_event, dwell_prog = self._check_dwell(index, now)
            self._remember(index)
            if dwell_event:
                return dwell_event

            return GestureEvent(
                Gesture.NONE,
                index,
                dwell_progress=dwell_prog,
                trail=self._circle_tracker.get_trail(),
            )

        # Nenhum gesto específico ativo
        self._remember(index)
        return GestureEvent(Gesture.NONE, index)

    def _is_thumbs_up(
        self,
        landmarks: Sequence[object],
        index_ext: bool,
        middle_ext: bool,
        ring_ext: bool,
        pinky_ext: bool,
    ) -> bool:
        """Joinha 👍: 4 dedos recolhidos e polegar apontando para cima."""
        if index_ext or middle_ext or ring_ext or pinky_ext:
            return False

        thumb_tip = self._point(landmarks[THUMB_TIP])
        thumb_mcp = self._point(landmarks[THUMB_MCP])
        index_mcp = self._point(landmarks[INDEX_MCP])
        wrist = self._point(landmarks[WRIST])

        is_up = thumb_tip.y < thumb_mcp.y - 0.02 and thumb_tip.y < index_mcp.y
        is_extended = self._distance(thumb_tip, wrist) > self._distance(thumb_mcp, wrist) * 1.10
        return is_up and is_extended

    def _is_ok_sign(
        self,
        landmarks: Sequence[object],
        pinch_dist: float,
        middle_ext: bool,
        ring_ext: bool,
        pinky_ext: bool,
    ) -> bool:
        """Sinal de OK 👌: polegar e indicador juntos, pelo menos 2 dedos estendidos."""
        if pinch_dist > self.config.pinch_distance_start * 1.15:
            return False
        # Permite se ao menos 2 dos 3 outros dedos estiverem estendidos (tolerância prática)
        extended_count = sum([middle_ext, ring_ext, pinky_ext])
        return extended_count >= 2

    def _check_open_palm_swipe(self, wrist: Point, now: float) -> GestureEvent | None:
        """Identifica varreduras direcionais rápidas com a palma aberta."""
        while self._palm_history and (now - self._palm_history[0].time > self.config.swipe_window_seconds):
            self._palm_history.popleft()

        self._palm_history.append(_TimedPoint(wrist, now))

        if len(self._palm_history) >= 4 and self._can_fire(now):
            start_p = self._palm_history[0].p
            dx = wrist.x - start_p.x
            dy = wrist.y - start_p.y

            # Empurrar para baixo -> MINIMIZE
            if dy >= self.config.swipe_threshold and dy > abs(dx) * 1.25:
                self._last_discrete_action = now
                self._palm_history.clear()
                return GestureEvent(Gesture.MINIMIZE, wrist)

            # Varrer para esquerda -> SWIPE_LEFT
            if dx <= -self.config.swipe_threshold and abs(dx) > abs(dy) * 1.25:
                self._last_discrete_action = now
                self._palm_history.clear()
                return GestureEvent(Gesture.SWIPE_LEFT, wrist)

            # Varrer para direita -> SWIPE_RIGHT
            if dx >= self.config.swipe_threshold and abs(dx) > abs(dy) * 1.25:
                self._last_discrete_action = now
                self._palm_history.clear()
                return GestureEvent(Gesture.SWIPE_RIGHT, wrist)

        return None

    def _check_zoom(self, cursor: Point, pinch_dist: float, now: float) -> GestureEvent | None:
        """Zoom estável por passos acumulados."""
        if self._zoom_anchor_dist is None:
            self._zoom_anchor_dist = pinch_dist
            return None

        delta = pinch_dist - self._zoom_anchor_dist

        if delta >= self.config.zoom_step_distance and self._can_fire(now):
            self._last_discrete_action = now
            self._zoom_anchor_dist = pinch_dist
            return GestureEvent(Gesture.ZOOM_IN, cursor)
        elif delta <= -self.config.zoom_step_distance and self._can_fire(now):
            self._last_discrete_action = now
            self._zoom_anchor_dist = pinch_dist
            return GestureEvent(Gesture.ZOOM_OUT, cursor)

        return None

    def _check_scroll(self, index: Point) -> GestureEvent | None:
        """Scroll vertical apenas quando o movimento é puramente vertical."""
        if self._previous_filtered_index is None:
            return None

        dx = index.x - self._previous_filtered_index.x
        dy = index.y - self._previous_filtered_index.y

        # Se houver movimento horizontal relevante, é movimento de mira, não scroll
        if abs(dx) > abs(dy) * 0.7:
            self._scroll_accumulator = 0.0
            return None

        self._scroll_accumulator += dy

        if self._scroll_accumulator <= -self.config.scroll_threshold:
            self._scroll_accumulator = 0.0
            return GestureEvent(Gesture.SCROLL, index, amount=6)
        elif self._scroll_accumulator >= self.config.scroll_threshold:
            self._scroll_accumulator = 0.0
            return GestureEvent(Gesture.SCROLL, index, amount=-6)

        return None

    def _check_dwell(self, index: Point, now: float) -> tuple[GestureEvent | None, float]:
        """Detecta parada do cursor dentro de uma bolha de estabilidade."""
        if self._dwell_anchor is None:
            self._dwell_anchor = index
            self._dwell_start_time = now
            self._dwell_fired = False
            return None, 0.0

        dist_from_anchor = self._distance(index, self._dwell_anchor)

        # Se o cursor saiu da bolha estável, redefine âncora
        if dist_from_anchor > self.config.stable_distance:
            self._dwell_anchor = index
            self._dwell_start_time = now
            self._dwell_fired = False
            return None, 0.0

        # Dentro da bolha estável: calcula progresso
        elapsed = now - (self._dwell_start_time or now)
        progress = min(1.0, elapsed / self.config.dwell_seconds)

        if progress >= 1.0 and not self._dwell_fired:
            self._dwell_fired = True
            return GestureEvent(Gesture.DWELL_CLICK, index, dwell_progress=1.0), 1.0

        return None, progress if not self._dwell_fired else 1.0

    def _is_finger_extended(
        self, landmarks: Sequence[object], tip_idx: int, pip_idx: int, mcp_idx: int
    ) -> bool:
        """Verifica se um dedo está estendido."""
        wrist = self._point(landmarks[WRIST])
        tip = self._point(landmarks[tip_idx])
        pip = self._point(landmarks[pip_idx])
        mcp = self._point(landmarks[mcp_idx])

        dist_tip_wrist = self._distance(tip, wrist)
        dist_pip_wrist = self._distance(pip, wrist)
        dist_tip_mcp = self._distance(tip, mcp)
        dist_pip_mcp = self._distance(pip, mcp)

        return dist_tip_wrist > dist_pip_wrist * 1.05 and dist_tip_mcp > dist_pip_mcp

    def _remember(self, index: Point) -> None:
        self._previous_filtered_index = index

    def _reset_dwell(self) -> None:
        self._dwell_anchor = None
        self._dwell_start_time = None
        self._dwell_fired = False

    def _reset_all(self) -> None:
        self._cursor_filter.reset()
        self._pinch_filter.reset()
        self._two_hand_filter.reset()
        self._is_pinching = False
        self._reset_dwell()
        self._scroll_accumulator = 0.0
        self._zoom_anchor_dist = None
        self._previous_filtered_index = None
        self._palm_history.clear()
        self._two_hand_history.clear()
        self._circle_tracker.clear()
        self._ok_counter = 0
        self._thumbs_up_counter = 0

    def _can_fire(self, now: float) -> bool:
        return now - self._last_discrete_action >= self.config.cooldown_seconds

    @staticmethod
    def _point(landmark: object) -> Point:
        z_val = float(getattr(landmark, "z", 0.0))
        return Point(
            x=float(getattr(landmark, "x")),
            y=float(getattr(landmark, "y")),
            z=z_val,
        )

    @staticmethod
    def _distance(first: Point, second: Point) -> float:
        return math.hypot(first.x - second.x, first.y - second.y)
