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
    # Limiares relativos ao tamanho da palma (reduzem variação por distância da câmera)
    pinch_ratio_start: float = 0.38
    pinch_ratio_release: float = 0.55
    zoom_step_ratio: float = 0.20
    max_zoom_ratio: float = 1.80
    # Classificação geométrica dos dedos
    finger_extension_angle: float = 150.0
    finger_extension_ratio: float = 1.02
    # Dwell Click (raio estável e tempo)
    stable_distance: float = 0.040
    dwell_seconds: float = 0.40
    double_click_window_seconds: float = 1.20
    # Scroll (acumulador e limiar)
    scroll_threshold: float = 0.015
    # Swipes de palma aberta
    swipe_threshold: float = 0.065
    swipe_window_seconds: float = 0.35
    swipe_same_cooldown_seconds: float = 0.40
    swipe_opposite_lockout_seconds: float = 1.10  # Bloqueia o retorno involuntário da mão
    # Cooldowns específicos para Minimização e Gaveta (Toggle)
    toggle_minimized_cooldown_seconds: float = 1.30  # Delay seguro para o toggle não ficar oscilando
    minimize_cooldown_seconds: float = 1.00
    vertical_opposite_lockout_seconds: float = 1.20  # Bloqueia o retorno vertical involuntário
    # Gestos de duas mãos (abertura e fechamento)
    two_hand_spread_threshold: float = 0.075
    two_hand_window_seconds: float = 0.45
    two_hand_vertical_threshold: float = 0.055
    typing_hold_seconds: float = 0.80
    fist_hold_seconds: float = 0.80
    calibration_frames: int = 0
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

        # Estado de pinça / arrasto (histerese). Zoom só é armado depois
        # que uma pinça estável foi observada; isso evita que uma pinça comum
        # seja interpretada como zoom.
        self._is_pinching = False
        self._pinch_candidate_since: float | None = None
        self._pinch_stable_frames = 0

        # Estado de Dwell Click
        self._dwell_anchor: Point | None = None
        self._dwell_start_time: float | None = None
        self._dwell_fired = False

        # Estado de Scroll e Zoom
        self._scroll_accumulator = 0.0
        self._zoom_anchor_dist: float | None = None
        self._zoom_active = False
        self._previous_filtered_index: Point | None = None
        self._last_click_time: float | None = None

        # Históricos temporais
        self._palm_history: Deque[_TimedPoint] = deque(maxlen=30)
        self._two_hand_history: Deque[_TimedVal] = deque(maxlen=30)
        self._last_two_hand_seen = -999.0
        self._two_hand_mid_history: Deque[_TimedVal] = deque(maxlen=30)
        self._typing_start_time: float | None = None
        self._typing_fired = False
        self._fist_start_time: float | None = None
        self._fist_fired = False
        self._calibration_count = 0
        self._calibrated = self.config.calibration_frames <= 0

        # Debounce e controle de gestos discretos e swipes com anti-recoil
        self._ok_counter = 0
        self._thumbs_up_counter = 0
        self._ok_fired = False
        self._thumbs_up_fired = False
        self._last_action_times: dict[Gesture, float] = {}
        self._last_swipe_time = -999.0
        self._last_swipe_gesture: Gesture | None = None
        self._swipe_opposite_lockout_until = -999.0
        self._last_toggle_minimized_time = -999.0
        self._last_minimize_time = -999.0
        self._vertical_opposite_lockout_until = -999.0

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

        # MediaPipe deve entregar exatamente os 21 landmarks por mão. Uma
        # detecção parcial/corrompida é descartada antes de acessar índices.
        hands_list = [hand for hand in hands_list if self._valid_hand(hand)]
        if not hands_list:
            self._reset_all()
            return GestureEvent(Gesture.NONE, Point(0.5, 0.5))

        if not self._calibrated:
            if any(self._is_open_palm(hand) for hand in hands_list):
                self._calibration_count += 1
            else:
                self._calibration_count = 0
            if self._calibration_count < self.config.calibration_frames:
                return GestureEvent(Gesture.NONE, self._point(hands_list[0][INDEX_TIP]))
            self._calibrated = True

        # 1. GESTOS DE DUAS MÃOS (Maximizar / Restaurar)
        has_multiple_hands = len(hands_list) >= 2
        if has_multiple_hands:
            self._last_two_hand_seen = timestamp
            keyboard_event = self._check_typing_position(hands_list[0], hands_list[1], timestamp)
            if keyboard_event:
                return keyboard_event
            two_hand_event = self._check_two_hand_gestures(hands_list[0], hands_list[1], timestamp)
            if two_hand_event:
                return two_hand_event
        else:
            if timestamp - self._last_two_hand_seen > 0.25:
                self._two_hand_history.clear()
                self._two_hand_mid_history.clear()
                self._two_hand_filter.reset()
                self._typing_start_time = None
                self._typing_fired = False

        # 2. SELEÇÃO DA MÃO ATIVA (Mão esquerda ou direita com base no score de intenção)
        if has_multiple_hands:
            score_0 = self._hand_activity_score(hands_list[0])
            score_1 = self._hand_activity_score(hands_list[1])
            if score_1 > score_0:
                primary_hand = hands_list[1]
            elif score_0 > score_1:
                primary_hand = hands_list[0]
            else:
                if self._previous_filtered_index is not None:
                    dist_0 = self._distance(self._point(hands_list[0][INDEX_TIP]), self._previous_filtered_index)
                    dist_1 = self._distance(self._point(hands_list[1][INDEX_TIP]), self._previous_filtered_index)
                    primary_hand = hands_list[0] if dist_0 <= dist_1 else hands_list[1]
                else:
                    primary_hand = hands_list[0]
        else:
            primary_hand = hands_list[0]

        return self._process_single_hand(primary_hand, timestamp, has_multiple_hands=has_multiple_hands)

    def _hand_activity_score(self, landmarks: Sequence[object]) -> float:
        """Determina o nível de atividade/intenção de uma mão para desempate."""
        raw_index = self._point(landmarks[INDEX_TIP])
        raw_thumb = self._point(landmarks[THUMB_TIP])
        pinch_dist = self._distance(raw_index, raw_thumb)

        index_ext = self._is_finger_extended(landmarks, INDEX_TIP, INDEX_PIP, INDEX_MCP)
        middle_ext = self._is_finger_extended(landmarks, MIDDLE_TIP, MIDDLE_PIP, MIDDLE_MCP)
        ring_ext = self._is_finger_extended(landmarks, RING_TIP, RING_PIP, RING_MCP)
        pinky_ext = self._is_finger_extended(landmarks, PINKY_TIP, PINKY_PIP, PINKY_MCP)

        # 1. Joinha 👍 ou Confirmação 👌 (máxima prioridade)
        if self._is_thumbs_up(landmarks, index_ext, middle_ext, ring_ext, pinky_ext):
            return 100.0
        if self._is_ok_sign(landmarks, pinch_dist, middle_ext, ring_ext, pinky_ext):
            return 95.0

        # 2. Pinça ativa (Arrastar / Zoom)
        if pinch_dist <= self._effective_pinch_start(landmarks) * 1.15:
            return 90.0

        # 3. Indicador estendido isolado (Mira, clique, scroll, círculos)
        if index_ext and not middle_ext and not ring_ext and not pinky_ext:
            return 80.0

        # 4. Palma aberta (Minimizar / Gaveta / Swipes)
        open_fingers = sum([index_ext, middle_ext, ring_ext, pinky_ext])
        if open_fingers >= 3:
            return 70.0

        return 10.0

    def _check_two_hand_gestures(
        self, hand1: Sequence[object], hand2: Sequence[object], now: float
    ) -> GestureEvent | None:
        p1 = self._point(hand1[WRIST])
        p2 = self._point(hand2[WRIST])
        raw_dist = math.hypot(p1.x - p2.x, p1.y - p2.y)
        dist = self._two_hand_filter.filter(raw_dist, now)
        mid_point = Point((p1.x + p2.x) / 2, (p1.y + p2.y) / 2)

        while self._two_hand_history and (now - self._two_hand_history[0].time > self.config.two_hand_window_seconds):
            self._two_hand_history.popleft()
        self._two_hand_history.append(_TimedVal(dist, now))
        while self._two_hand_mid_history and (now - self._two_hand_mid_history[0].time > self.config.two_hand_window_seconds):
            self._two_hand_mid_history.popleft()
        self._two_hand_mid_history.append(_TimedVal(mid_point.y, now))

        # Este histórico é exclusivo das mãos; o teclado virtual não usa mais
        # o primeiro timestamp do histórico de movimento.
        if len(self._two_hand_history) >= 4:
            start_dist = self._two_hand_history[0].val
            delta_dist = dist - start_dist
            # Usa o deslocamento vertical medido dentro da mesma janela.
            first_y = self._two_hand_mid_history[0].val if self._two_hand_mid_history else mid_point.y
            delta_y = mid_point.y - first_y

            if delta_dist >= self.config.two_hand_spread_threshold and (
                delta_y <= -self.config.two_hand_vertical_threshold or abs(delta_y) < 0.01
            ) and self._can_fire(Gesture.MAXIMIZE, now):
                self._mark_fired(Gesture.MAXIMIZE, now)
                self._two_hand_history.clear()
                self._two_hand_mid_history.clear()
                return GestureEvent(Gesture.MAXIMIZE, mid_point)

            if delta_dist <= -self.config.two_hand_spread_threshold and (
                delta_y >= self.config.two_hand_vertical_threshold or abs(delta_y) < 0.01
            ):
                gesture = Gesture.MINIMIZE if delta_y >= self.config.two_hand_vertical_threshold else Gesture.RESTORE
                if self._can_fire(gesture, now):
                    self._mark_fired(gesture, now)
                    self._two_hand_history.clear()
                    self._two_hand_mid_history.clear()
                    return GestureEvent(gesture, mid_point)

        return None

    def _check_typing_position(
        self, hand1: Sequence[object], hand2: Sequence[object], now: float
    ) -> GestureEvent | None:
        """Detecta duas palmas abertas mantidas na posição de digitação."""
        is_open = self._is_open_palm(hand1) and self._is_open_palm(hand2)
        y = (self._point(hand1[WRIST]).y + self._point(hand2[WRIST]).y) / 2

        # A postura precisa permanecer válida continuamente; sair dela reseta
        # o cronômetro em vez de reaproveitar histórico de outro gesto.
        if not is_open or y < 0.45:
            self._typing_start_time = None
            self._typing_fired = False
            return None

        if self._typing_start_time is None:
            self._typing_start_time = now
            return None

        elapsed = now - self._typing_start_time
        if elapsed >= self.config.typing_hold_seconds and not self._typing_fired:
            self._typing_fired = True
            self._mark_fired(Gesture.VIRTUAL_KEYBOARD, now)
            return GestureEvent(Gesture.VIRTUAL_KEYBOARD, Point(0.5, y))
        return None

    def _process_single_hand(
        self, landmarks: Sequence[object], now: float, has_multiple_hands: bool = False
    ) -> GestureEvent:
        wrist = self._point(landmarks[WRIST])
        raw_index = self._point(landmarks[INDEX_TIP])
        raw_thumb = self._point(landmarks[THUMB_TIP])

        if self._previous_filtered_index is not None:
            if self._distance(raw_index, self._previous_filtered_index) > 0.30:
                self._cursor_filter.reset()
                self._reset_dwell()

        index = self._cursor_filter.filter(raw_index, now)
        raw_pinch_dist = self._distance(raw_index, raw_thumb)
        # A decisão PINCH/ZOOM usa a distância instantânea. O filtro anterior
        # introduzia atraso suficiente para perder pinças curtas nos testes e
        # também atrasava a transição PINCH -> ZOOM.
        pinch_dist = raw_pinch_dist
        self._pinch_filter.filter(raw_pinch_dist, now)

        index_ext = self._is_finger_extended(landmarks, INDEX_TIP, INDEX_PIP, INDEX_MCP)
        middle_ext = self._is_finger_extended(landmarks, MIDDLE_TIP, MIDDLE_PIP, MIDDLE_MCP)
        ring_ext = self._is_finger_extended(landmarks, RING_TIP, RING_PIP, RING_MCP)
        pinky_ext = self._is_finger_extended(landmarks, PINKY_TIP, PINKY_PIP, PINKY_MCP)

        # ---------------------------------------------------------------
        # PINCH: prioridade máxima entre gestos de uma mão.
        # Uma pinça fechada não pode virar JOINHA/PUNHO por acidente.
        # Mantemos OK acima da pinça apenas quando há dedos adicionais
        # claramente estendidos.
        # ---------------------------------------------------------------
        pinch_start = self._effective_pinch_start(landmarks)
        pinch_release = self._effective_pinch_release(landmarks)
        zoom_max = self._effective_zoom_max(landmarks)

        closed_pinch = (
            pinch_dist <= pinch_start
            and not middle_ext
            and not ring_ext
            and not pinky_ext
        )

        if closed_pinch:
            self._is_pinching = True
            self._pinch_candidate_since = now
            self._pinch_stable_frames += 1
            self._fist_start_time = None
            self._fist_fired = False
            self._reset_dwell()
            self._circle_tracker.clear()
            # Mantém a distância da pinça fechada como âncora. Ao abrir a
            # pinça, a própria abertura pode ser o primeiro passo de ZOOM.
            # A postura fechada continua retornando exclusivamente PINCH.
            self._zoom_anchor_dist = pinch_dist
            self._zoom_anchor_ratio = None
            self._zoom_active = False
            self._remember(index)
            return GestureEvent(Gesture.PINCH, index)

        just_released_pinch = False
        if self._is_pinching:
            # A pinça só termina quando a abertura ultrapassa a histerese.
            # A partir daí o próprio frame de abertura pode produzir ZOOM.
            if pinch_dist <= pinch_release:
                self._reset_dwell()
                self._remember(index)
                return GestureEvent(Gesture.PINCH, index)
            self._is_pinching = False
            self._pinch_candidate_since = None
            self._pinch_stable_frames = 0
            just_released_pinch = True
            # Não apaga _zoom_anchor_dist aqui: o frame de abertura deve
            # ser comparado diretamente com a distância da pinça fechada.

        # ---------------------------------------------------------------
        # ZOOM ABERTO
        # Uma "pinça aberta" usada para zoom pode ter a mesma geometria
        # básica de um joinha (os outros dedos estão dobrados). O teste e
        # o uso do gesto definem a distância polegar-indicador como a pista
        # principal: dentro do limite de interação, o zoom tem prioridade.
        # Uma distância maior (como no joinha) continua indo para CONFIRM.
        # ---------------------------------------------------------------
        zoom_posture_pre = (
            not index_ext
            and not middle_ext
            and not ring_ext
            and not pinky_ext
            and pinch_dist > pinch_release
            and pinch_dist <= self.config.max_zoom_interaction_dist
        )
        if zoom_posture_pre:
            if self._zoom_anchor_dist is None:
                self._zoom_anchor_dist = pinch_dist
                self._zoom_anchor_ratio = None
                self._zoom_active = False

            zoom_event = self._check_zoom(index, pinch_dist, now, landmarks)
            if zoom_event:
                self._reset_dwell()
                self._circle_tracker.clear()
                self._zoom_active = True
                return zoom_event
        else:
            # Uma postura que não pode ser zoom encerra a âncora, exceto
            # durante a transição recém-liberada de PINCH.
            if not just_released_pinch:
                self._zoom_anchor_dist = None
                self._zoom_anchor_ratio = None
                self._zoom_active = False

        # ---------------------------------------------------------------
        # JOINHA
        # ---------------------------------------------------------------
        if self._is_thumbs_up(landmarks, index_ext, middle_ext, ring_ext, pinky_ext):
            self._thumbs_up_counter += 1
            self._ok_counter = 0
            self._ok_fired = False
            self._reset_dwell()
            self._circle_tracker.clear()

            if (
                self._thumbs_up_counter >= 2
                and not self._thumbs_up_fired
                and self._can_fire(Gesture.CONFIRM, now)
            ):
                self._mark_fired(Gesture.CONFIRM, now)
                self._thumbs_up_fired = True
                return GestureEvent(Gesture.CONFIRM, raw_thumb)
            return GestureEvent(Gesture.NONE, raw_thumb)
        else:
            self._thumbs_up_counter = 0
            self._thumbs_up_fired = False

        # ---------------------------------------------------------------
        # OK
        # ---------------------------------------------------------------
        if self._is_ok_sign(landmarks, pinch_dist, middle_ext, ring_ext, pinky_ext):
            self._ok_counter += 1
            self._thumbs_up_counter = 0
            self._thumbs_up_fired = False
            self._reset_dwell()
            self._circle_tracker.clear()

            if (
                self._ok_counter >= 2
                and not self._ok_fired
                and self._can_fire(Gesture.VOICE_ACTIVATE, now)
            ):
                self._mark_fired(Gesture.VOICE_ACTIVATE, now)
                self._ok_fired = True
                return GestureEvent(Gesture.VOICE_ACTIVATE, index)
            return GestureEvent(Gesture.NONE, index)
        else:
            self._ok_counter = 0
            self._ok_fired = False

        # O zoom aberto já foi processado antes de JOINHA para evitar que
        # uma pinça aberta seja confundida com CONFIRM.
        # ---------------------------------------------------------------
        # PUNHO
        # ---------------------------------------------------------------
        if self._is_closed_fist(landmarks, index_ext, middle_ext, ring_ext, pinky_ext):
            if self._fist_start_time is None:
                self._fist_start_time = now
            if (
                not self._fist_fired
                and now - self._fist_start_time >= self.config.fist_hold_seconds
            ):
                self._fist_fired = True
                return GestureEvent(Gesture.PAUSE_TOGGLE, wrist)
            return GestureEvent(Gesture.NONE, wrist)
        self._fist_start_time = None
        self._fist_fired = False

        # ---------------------------------------------------------------
        # PALMA / SWIPE
        # ---------------------------------------------------------------
        open_fingers = sum([index_ext, middle_ext, ring_ext, pinky_ext])
        is_open_palm = open_fingers >= 3
        if is_open_palm:
            if not has_multiple_hands:
                palm_event = self._check_open_palm_swipe(wrist, now)
                if palm_event:
                    self._reset_dwell()
                    self._circle_tracker.clear()
                    return palm_event
        elif self._palm_history and (now - self._palm_history[-1].time > 0.10):
            self._palm_history.clear()

        # ---------------------------------------------------------------
        # INDICADOR: círculo, scroll ou dwell
        # ---------------------------------------------------------------
        if index_ext and not middle_ext and not ring_ext and not pinky_ext:
            # Círculo e zoom são mutuamente exclusivos. Ao entrar no modo
            # indicador isolado, a âncora de zoom deixa de ser válida.
            self._zoom_anchor_dist = None
            self._zoom_anchor_ratio = None
            self._zoom_active = False
            self._circle_tracker.add_point(index, now)
            circle_gesture = self._circle_tracker.evaluate(now)
            if circle_gesture is not Gesture.NONE:
                self._reset_dwell()
                self._mark_fired(circle_gesture, now)
                self._remember(index)
                return GestureEvent(
                    circle_gesture, index, trail=self._circle_tracker.get_trail()
                )

            scroll_event = self._check_scroll(index)
            if scroll_event:
                self._reset_dwell()
                self._remember(index)
                return scroll_event

            dwell_event, dwell_prog = self._check_dwell(index, now)
            self._remember(index)
            if dwell_event:
                if (
                    self._last_click_time is not None
                    and now - self._last_click_time <= self.config.double_click_window_seconds
                ):
                    self._last_click_time = None
                    return GestureEvent(Gesture.DOUBLE_CLICK, index, dwell_progress=1.0)
                self._last_click_time = now
                return dwell_event

            return GestureEvent(
                Gesture.NONE,
                index,
                dwell_progress=dwell_prog,
                trail=self._circle_tracker.get_trail(),
            )

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
        is_extended = self._distance(thumb_tip, wrist) > self._distance(thumb_mcp, wrist) * 1.08
        return is_up and is_extended

    def _is_ok_sign(
        self,
        landmarks: Sequence[object],
        pinch_dist: float,
        middle_ext: bool,
        ring_ext: bool,
        pinky_ext: bool,
    ) -> bool:
        """Sinal de OK 👌: polegar e indicador unidos, pelo menos 2 dedos estendidos."""
        if pinch_dist > self.config.pinch_distance_start * 1.20:
            return False
        extended_count = sum([middle_ext, ring_ext, pinky_ext])
        return extended_count >= 2

    def _is_closed_fist(
        self,
        landmarks: Sequence[object],
        index_ext: bool,
        middle_ext: bool,
        ring_ext: bool,
        pinky_ext: bool,
    ) -> bool:
        """Punho: dedos fechados e polegar recolhido, sem confundir joinha."""
        if index_ext or middle_ext or ring_ext or pinky_ext:
            return False
        thumb_tip = self._point(landmarks[THUMB_TIP])
        thumb_mcp = self._point(landmarks[THUMB_MCP])
        wrist = self._point(landmarks[WRIST])
        return self._distance(thumb_tip, wrist) <= self._distance(thumb_mcp, wrist) * 1.10

    def _is_open_palm(self, landmarks: Sequence[object]) -> bool:
        flags = [
            self._is_finger_extended(landmarks, INDEX_TIP, INDEX_PIP, INDEX_MCP),
            self._is_finger_extended(landmarks, MIDDLE_TIP, MIDDLE_PIP, MIDDLE_MCP),
            self._is_finger_extended(landmarks, RING_TIP, RING_PIP, RING_MCP),
            self._is_finger_extended(landmarks, PINKY_TIP, PINKY_PIP, PINKY_MCP),
        ]
        return sum(flags) >= 3

    @staticmethod
    def _valid_hand(landmarks: Sequence[object]) -> bool:
        if len(landmarks) < 21:
            return False
        for landmark in landmarks[:21]:
            try:
                x = float(getattr(landmark, "x"))
                y = float(getattr(landmark, "y"))
                z = float(getattr(landmark, "z", 0.0))
            except (AttributeError, TypeError, ValueError):
                return False
            if not all(math.isfinite(value) for value in (x, y, z)):
                return False
            if not (-0.10 <= x <= 1.10 and -0.10 <= y <= 1.10):
                return False
        return True

    def _check_open_palm_swipe(self, wrist: Point, now: float) -> GestureEvent | None:
        """Identifica varreduras direcionais rápidas com bloqueio anti-recoil do retorno da mão."""
        # Se estiver em período de lockout para a direção oposta, limpa histórico e descarta
        while self._palm_history and (now - self._palm_history[0].time > self.config.swipe_window_seconds):
            self._palm_history.popleft()

        self._palm_history.append(_TimedPoint(wrist, now))

        if len(self._palm_history) >= 3:
            start_p = self._palm_history[0].p
            dx = wrist.x - start_p.x
            dy = wrist.y - start_p.y
            abs_dx = abs(dx)
            abs_dy = abs(dy)

            # 1. Empurrar para baixo -> MINIMIZE
            if dy >= self.config.swipe_threshold and abs_dy > abs_dx * 1.25:
                # Se veio de um TOGGLE_MINIMIZED recente, bloqueia o retorno involuntário da mão para baixo
                if self._last_swipe_gesture == Gesture.TOGGLE_MINIMIZED and now < self._vertical_opposite_lockout_until:
                    return None

                if now - self._last_minimize_time >= self.config.minimize_cooldown_seconds and self._can_fire(Gesture.MINIMIZE, now):
                    self._mark_fired(Gesture.MINIMIZE, now)
                    self._last_swipe_time = now
                    self._last_minimize_time = now
                    self._last_swipe_gesture = Gesture.MINIMIZE
                    self._vertical_opposite_lockout_until = now + self.config.vertical_opposite_lockout_seconds
                    self._palm_history.clear()
                    return GestureEvent(Gesture.MINIMIZE, wrist)

            # 2. Puxar para cima -> TOGGLE_MINIMIZED (Abrir / Fechar gaveta de minimizadas)
            if dy <= -self.config.swipe_threshold and abs_dy > abs_dx * 1.25:
                # Se veio de um MINIMIZE recente, bloqueia o retorno involuntário da mão para cima
                if self._last_swipe_gesture == Gesture.MINIMIZE and now < self._vertical_opposite_lockout_until:
                    return None

                if now - self._last_toggle_minimized_time >= self.config.toggle_minimized_cooldown_seconds and self._can_fire(Gesture.TOGGLE_MINIMIZED, now):
                    self._mark_fired(Gesture.TOGGLE_MINIMIZED, now)
                    self._last_swipe_time = now
                    self._last_toggle_minimized_time = now
                    self._last_swipe_gesture = Gesture.TOGGLE_MINIMIZED
                    self._vertical_opposite_lockout_until = now + self.config.vertical_opposite_lockout_seconds
                    self._palm_history.clear()
                    return GestureEvent(Gesture.TOGGLE_MINIMIZED, wrist)

            # 3. Varrer para a esquerda -> SWIPE_LEFT
            if dx <= -self.config.swipe_threshold and abs_dx > abs_dy * 1.20:
                # Se o último foi SWIPE_RIGHT, bloqueia o retorno involuntário
                if self._last_swipe_gesture == Gesture.SWIPE_RIGHT and now < self._swipe_opposite_lockout_until:
                    return None

                cooldown = self.config.swipe_same_cooldown_seconds if self._last_swipe_gesture == Gesture.SWIPE_LEFT else 0.40
                if now - self._last_swipe_time >= cooldown:
                    self._mark_fired(Gesture.SWIPE_LEFT, now)
                    self._last_swipe_time = now
                    self._last_swipe_gesture = Gesture.SWIPE_LEFT
                    self._swipe_opposite_lockout_until = now + self.config.swipe_opposite_lockout_seconds
                    self._palm_history.clear()
                    return GestureEvent(Gesture.SWIPE_LEFT, wrist)

            # 4. Varrer para a direita -> SWIPE_RIGHT
            if dx >= self.config.swipe_threshold and abs_dx > abs_dy * 1.20:
                # Se o último foi SWIPE_LEFT, bloqueia o retorno involuntário
                if self._last_swipe_gesture == Gesture.SWIPE_LEFT and now < self._swipe_opposite_lockout_until:
                    return None

                cooldown = self.config.swipe_same_cooldown_seconds if self._last_swipe_gesture == Gesture.SWIPE_RIGHT else 0.40
                if now - self._last_swipe_time >= cooldown:
                    self._mark_fired(Gesture.SWIPE_RIGHT, now)
                    self._last_swipe_time = now
                    self._last_swipe_gesture = Gesture.SWIPE_RIGHT
                    self._swipe_opposite_lockout_until = now + self.config.swipe_opposite_lockout_seconds
                    self._palm_history.clear()
                    return GestureEvent(Gesture.SWIPE_RIGHT, wrist)

        return None

    def _check_zoom(
        self, cursor: Point, pinch_dist: float, now: float, landmarks: Sequence[object]
    ) -> GestureEvent | None:
        """Detecta zoom por variação absoluta ou relativa da abertura da pinça.

        A distância absoluta mantém um limiar previsível para pequenas mãos/testes,
        enquanto a medida relativa ajuda quando a mão muda de distância da câmera.
        """
        scale = max(self._hand_scale(landmarks), 1e-4)
        normalized = pinch_dist / scale

        if self._zoom_anchor_dist is None:
            # O estado guarda a distância bruta; a versão normalizada é calculada
            # contra a escala atual para não misturar unidades.
            self._zoom_anchor_dist = pinch_dist
            return None

        absolute_delta = pinch_dist - self._zoom_anchor_dist
        anchor_normalized = self._zoom_anchor_dist / scale
        normalized_delta = normalized - anchor_normalized

        absolute_step = self.config.zoom_step_distance
        relative_step = self.config.zoom_step_ratio

        if (
            absolute_delta >= absolute_step
            or normalized_delta >= relative_step
        ) and self._can_fire(Gesture.ZOOM_IN, now):
            self._mark_fired(Gesture.ZOOM_IN, now)
            self._zoom_anchor_dist = pinch_dist
            return GestureEvent(Gesture.ZOOM_IN, cursor)

        if (
            absolute_delta <= -absolute_step
            or normalized_delta <= -relative_step
        ) and self._can_fire(Gesture.ZOOM_OUT, now):
            self._mark_fired(Gesture.ZOOM_OUT, now)
            self._zoom_anchor_dist = pinch_dist
            return GestureEvent(Gesture.ZOOM_OUT, cursor)

        return None

    def _check_scroll(self, index: Point) -> GestureEvent | None:
        """Scroll vertical apenas quando o movimento é puramente vertical."""
        if self._previous_filtered_index is None:
            return None

        dx = index.x - self._previous_filtered_index.x
        dy = index.y - self._previous_filtered_index.y

        if abs(dx) > abs(dy) * 0.7:
            self._scroll_accumulator = 0.0
            return None

        self._scroll_accumulator += dy

        if self._scroll_accumulator <= -self.config.scroll_threshold:
            self._scroll_accumulator = 0.0
            return GestureEvent(Gesture.SCROLL, index, amount=5)
        elif self._scroll_accumulator >= self.config.scroll_threshold:
            self._scroll_accumulator = 0.0
            return GestureEvent(Gesture.SCROLL, index, amount=-5)

        return None

    def _check_dwell(self, index: Point, now: float) -> tuple[GestureEvent | None, float]:
        """Detecta parada do cursor dentro de uma bolha de estabilidade."""
        if self._dwell_anchor is None:
            self._dwell_anchor = index
            self._dwell_start_time = now
            self._dwell_fired = False
            return None, 0.0

        dist_from_anchor = self._distance(index, self._dwell_anchor)

        if dist_from_anchor > self.config.stable_distance:
            self._dwell_anchor = index
            self._dwell_start_time = now
            self._dwell_fired = False
            return None, 0.0

        elapsed = now - (self._dwell_start_time or now)
        progress = min(1.0, elapsed / self.config.dwell_seconds)

        if progress >= 1.0 and not self._dwell_fired:
            self._dwell_fired = True
            return GestureEvent(Gesture.DWELL_CLICK, index, dwell_progress=1.0), 1.0

        return None, progress if not self._dwell_fired else 1.0

    def _is_finger_extended(
        self, landmarks: Sequence[object], tip_idx: int, pip_idx: int, mcp_idx: int
    ) -> bool:
        """Classifica extensão usando ângulo articular + distância normalizada."""
        wrist = self._point(landmarks[WRIST])
        tip = self._point(landmarks[tip_idx])
        pip = self._point(landmarks[pip_idx])
        mcp = self._point(landmarks[mcp_idx])

        angle = self._joint_angle(mcp, pip, tip)
        tip_wrist = self._distance_3d(tip, wrist)
        pip_wrist = self._distance_3d(pip, wrist)

        return (
            angle >= self.config.finger_extension_angle
            and tip_wrist >= pip_wrist * self.config.finger_extension_ratio
        )

    def _hand_scale(self, landmarks: Sequence[object]) -> float:
        """Escala aproximada da palma, independente da distância à câmera."""
        wrist = self._point(landmarks[WRIST])
        middle_mcp = self._point(landmarks[MIDDLE_MCP])
        index_mcp = self._point(landmarks[INDEX_MCP])
        pinky_mcp = self._point(landmarks[PINKY_MCP])
        return max(
            self._distance_3d(wrist, middle_mcp),
            self._distance_3d(index_mcp, pinky_mcp),
            1e-4,
        )

    def _effective_pinch_start(self, landmarks: Sequence[object]) -> float:
        scale = self._hand_scale(landmarks)
        return min(self.config.pinch_distance_start, scale * self.config.pinch_ratio_start)

    def _effective_pinch_release(self, landmarks: Sequence[object]) -> float:
        scale = self._hand_scale(landmarks)
        return min(self.config.pinch_distance_release, scale * self.config.pinch_ratio_release)

    def _effective_zoom_max(self, landmarks: Sequence[object]) -> float:
        scale = self._hand_scale(landmarks)
        return min(self.config.max_zoom_interaction_dist, scale * self.config.max_zoom_ratio)

    @staticmethod
    def _joint_angle(first: Point, vertex: Point, last: Point) -> float:
        a = (first.x - vertex.x, first.y - vertex.y, first.z - vertex.z)
        b = (last.x - vertex.x, last.y - vertex.y, last.z - vertex.z)
        norm_a = math.sqrt(sum(value * value for value in a))
        norm_b = math.sqrt(sum(value * value for value in b))
        if norm_a <= 1e-6 or norm_b <= 1e-6:
            return 0.0
        cosine = sum(x * y for x, y in zip(a, b)) / (norm_a * norm_b)
        cosine = max(-1.0, min(1.0, cosine))
        return math.degrees(math.acos(cosine))

    @staticmethod
    def _distance_3d(first: Point, second: Point) -> float:
        return math.sqrt(
            (first.x - second.x) ** 2
            + (first.y - second.y) ** 2
            + (first.z - second.z) ** 2
        )

    def _remember(self, index: Point) -> None:
        self._previous_filtered_index = index

    def _reset_dwell(self) -> None:
        self._dwell_anchor = None
        self._dwell_start_time = None
        self._dwell_fired = False

    def _reset_all(self) -> None:
        was_calibrated = self._calibrated
        self._cursor_filter.reset()
        self._pinch_filter.reset()
        self._two_hand_filter.reset()
        self._is_pinching = False
        self._reset_dwell()
        self._scroll_accumulator = 0.0
        self._zoom_anchor_dist = None
        self._zoom_active = False
        self._previous_filtered_index = None
        self._palm_history.clear()
        self._two_hand_history.clear()
        self._two_hand_mid_history.clear()
        self._circle_tracker.clear()
        self._ok_counter = 0
        self._thumbs_up_counter = 0
        self._ok_fired = False
        self._thumbs_up_fired = False
        self._last_action_times.clear()
        self._last_swipe_time = -999.0
        self._last_swipe_gesture = None
        self._swipe_opposite_lockout_until = -999.0
        self._last_toggle_minimized_time = -999.0
        self._last_minimize_time = -999.0
        self._vertical_opposite_lockout_until = -999.0
        self._last_click_time = None
        self._typing_start_time = None
        self._typing_fired = False
        self._pinch_candidate_since = None
        self._pinch_stable_frames = 0
        self._fist_start_time = None
        self._fist_fired = False
        self._calibration_count = 0
        self._calibrated = was_calibrated or self.config.calibration_frames <= 0

    def _can_fire(self, gesture: Gesture, now: float) -> bool:
        return now - self._last_action_times.get(gesture, -999.0) >= self.config.cooldown_seconds

    def _mark_fired(self, gesture: Gesture, now: float) -> None:
        self._last_action_times[gesture] = now

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
