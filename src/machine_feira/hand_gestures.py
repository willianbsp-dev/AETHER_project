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
    stable_distance: float = 0.040
    # Um clique só nasce depois de um segundo completamente parado. O cursor
    # continua sendo atualizado independentemente deste temporizador.
    dwell_seconds: float = 1.0
    double_click_window_seconds: float = 1.20
    # Movimento curto para baixo e retorno: clique no ar no modo mouse.
    air_click_threshold: float = 0.020
    air_click_window_seconds: float = 0.35
    air_click_cooldown_seconds: float = 0.45
    # Scroll: deslocamento maior e intervalo entre passos reduzem tremor.
    scroll_threshold: float = 0.025
    scroll_cooldown_seconds: float = 0.07
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
    typing_motion_threshold: float = 0.018
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

        # Estado de pinça / arrasto (histerese)
        self._is_pinching = False

        # Estado de Dwell Click
        self._dwell_anchor: Point | None = None
        self._dwell_start_time: float | None = None
        self._dwell_fired = False
        # O modo mouse é o estado seguro. Círculo e scroll só são avaliados
        # depois que o indicador permanece parado e a bolinha completa.
        self._gesture_mode = False
        self._air_click_start: Point | None = None
        self._air_click_started_at: float | None = None
        self._air_click_cooldown_until = -999.0
        self._air_click_previous_raw: Point | None = None

        # Estado de Scroll e Zoom
        self._scroll_accumulator = 0.0
        self._last_scroll_time = -999.0
        self._zoom_anchor_dist: float | None = None
        self._previous_filtered_index: Point | None = None
        self._last_click_time: float | None = None

        # Históricos temporais
        self._palm_history: Deque[_TimedPoint] = deque(maxlen=30)
        self._two_hand_history: Deque[_TimedVal] = deque(maxlen=30)
        self._last_two_hand_seen = -999.0
        self._two_hand_mid_history: Deque[_TimedVal] = deque(maxlen=30)
        self._typing_fired = False
        self._typing_motion_history: Deque[_TimedVal] = deque(maxlen=20)
        self._typing_last_finger_y: float | None = None
        self._fist_start_time: float | None = None
        self._fist_fired = False
        self._calibration_count = 0
        self._calibrated = self.config.calibration_frames <= 0

        # Debounce e controle de gestos discretos e swipes com anti-recoil
        self._ok_counter = 0
        self._thumbs_up_counter = 0
        self._ok_fired = False
        self._thumbs_up_fired = False
        self._last_discrete_action = -999.0
        self._last_swipe_time = -999.0
        self._last_swipe_gesture: Gesture | None = None
        self._swipe_opposite_lockout_until = -999.0
        self._last_toggle_minimized_time = -999.0
        self._last_minimize_time = -999.0
        self._vertical_opposite_lockout_until = -999.0
        # Evita que a mão em pinça do zoom seja reinterpretada como arrasto.
        self._two_hand_zoom_active = False

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

            # Zoom é uma interação combinada: uma mão permanece aberta e a
            # outra faz a pinça dinâmica. A distância entre polegar e indicador
            # da mão em pinça determina o zoom. Isso impede que uma única mão
            # dispare ZOOM_IN/ZOOM_OUT ou que uma pinça simples vire zoom.
            zoom_event = self._check_two_hand_zoom(hands_list[0], hands_list[1], timestamp)
            if zoom_event is not None:
                return zoom_event

            two_hand_event = self._check_two_hand_gestures(hands_list[0], hands_list[1], timestamp)
            if two_hand_event:
                return two_hand_event
        else:
            # Zoom só pode existir com a combinação de duas mãos.
            self._zoom_anchor_dist = None
            if timestamp - self._last_two_hand_seen > 0.25:
                self._two_hand_history.clear()
                self._two_hand_filter.reset()

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
        if pinch_dist <= self.config.pinch_distance_start * 1.15:
            return 90.0

        # 3. Indicador estendido isolado (Mira, clique, scroll, círculos)
        if index_ext and not middle_ext and not ring_ext and not pinky_ext:
            return 80.0

        # 4. Palma aberta (Minimizar / Gaveta / Swipes)
        open_fingers = sum([index_ext, middle_ext, ring_ext, pinky_ext])
        if open_fingers >= 3:
            return 70.0

        return 10.0

    def _check_two_hand_zoom(
        self, hand1: Sequence[object], hand2: Sequence[object], now: float
    ) -> GestureEvent | None:
        """Detecta zoom somente com uma palma aberta e a outra mão em pinça dinâmica."""
        open1 = self._is_open_palm(hand1)
        open2 = self._is_open_palm(hand2)

        # Exige exatamente uma mão aberta e uma mão responsável pela pinça.
        if open1 == open2:
            self._zoom_anchor_dist = None
            self._two_hand_zoom_active = False
            return None

        pinch_hand = hand2 if open1 else hand1
        index = self._point(pinch_hand[INDEX_TIP])
        thumb = self._point(pinch_hand[THUMB_TIP])
        pinch_dist = self._distance(index, thumb)

        if pinch_dist > self.config.max_zoom_interaction_dist:
            self._zoom_anchor_dist = None
            self._two_hand_zoom_active = False
            return None

        # Enquanto a combinação de zoom está ativa, não deixe a pinça da mão
        # ativa cair no gesto PINCH de arrastar janela.
        self._reset_dwell()
        self._circle_tracker.clear()
        self._is_pinching = False
        self._two_hand_zoom_active = True
        # Mesmo sem atingir o próximo passo de zoom, consumimos a combinação
        # inteira para que ela nunca caia no gesto PINCH de arrastar.
        return self._check_zoom(index, pinch_dist, now) or GestureEvent(Gesture.NONE, index)

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
        self._two_hand_mid_history.append(_TimedVal(mid_point.y, now))

        if len(self._two_hand_history) >= 4 and self._can_fire(now):
            start_dist = self._two_hand_history[0].val
            delta_dist = dist - start_dist
            start_y = self._two_hand_mid_history[0].val
            delta_y = mid_point.y - start_y

            # Juntas -> sobem e afastam: MAXIMIZE.
            if delta_dist >= self.config.two_hand_spread_threshold and (
                delta_y <= -self.config.two_hand_vertical_threshold or abs(delta_y) < 0.01
            ):
                self._last_discrete_action = now
                self._two_hand_history.clear()
                self._two_hand_mid_history.clear()
                return GestureEvent(Gesture.MAXIMIZE, mid_point)
            # Afastadas -> descem e aproximam: MINIMIZE.
            elif delta_dist <= -self.config.two_hand_spread_threshold and (
                delta_y >= self.config.two_hand_vertical_threshold or abs(delta_y) < 0.01
            ):
                self._last_discrete_action = now
                self._two_hand_history.clear()
                self._two_hand_mid_history.clear()
                return GestureEvent(
                    Gesture.MINIMIZE if delta_y >= self.config.two_hand_vertical_threshold else Gesture.RESTORE,
                    mid_point,
                )

        return None

    def _check_typing_position(
        self, hand1: Sequence[object], hand2: Sequence[object], now: float
    ) -> GestureEvent | None:
        """Detecta mãos baixas fazendo movimento de dedos de digitação.

        Duas palmas abertas paradas são deliberadamente rejeitadas: elas são
        usadas para outros gestos de duas mãos, não para abrir o teclado.
        """
        if self._is_open_palm(hand1) or self._is_open_palm(hand2):
            self._typing_fired = False
            self._typing_motion_history.clear()
            self._typing_last_finger_y = None
            return None
        y = (self._point(hand1[WRIST]).y + self._point(hand2[WRIST]).y) / 2
        if y < 0.45:
            self._typing_fired = False
            self._typing_motion_history.clear()
            self._typing_last_finger_y = None
            return None

        tips = (INDEX_TIP, MIDDLE_TIP, RING_TIP, PINKY_TIP)
        finger_y = sum(
            self._point(hand[idx]).y for hand in (hand1, hand2) for idx in tips
        ) / 8.0
        if self._typing_last_finger_y is not None:
            movement = abs(finger_y - self._typing_last_finger_y)
            if movement >= self.config.typing_motion_threshold:
                self._typing_motion_history.append(_TimedVal(finger_y, now))
        self._typing_last_finger_y = finger_y

        if not self._typing_motion_history:
            return None
        elapsed = now - self._typing_motion_history[0].time
        if elapsed >= self.config.typing_hold_seconds and not self._typing_fired:
            self._typing_fired = True
            return GestureEvent(Gesture.VIRTUAL_KEYBOARD, Point(0.5, y))
        return None

    def _process_single_hand(
        self, landmarks: Sequence[object], now: float, has_multiple_hands: bool = False
    ) -> GestureEvent:
        wrist = self._point(landmarks[WRIST])
        raw_index = self._point(landmarks[INDEX_TIP])
        raw_thumb = self._point(landmarks[THUMB_TIP])

        # Se houver troca brusca de posição (ex: troca de mão ativa), reseta o filtro para evitar arrasto
        if self._previous_filtered_index is not None:
            if self._distance(raw_index, self._previous_filtered_index) > 0.30:
                self._cursor_filter.reset()
                self._reset_dwell()

        # Suaviza o cursor para eliminar tremores de mira
        index = self._cursor_filter.filter(raw_index, now)
        raw_pinch_dist = self._distance(raw_index, raw_thumb)
        pinch_dist = self._pinch_filter.filter(raw_pinch_dist, now)

        index_ext = self._is_finger_extended(landmarks, INDEX_TIP, INDEX_PIP, INDEX_MCP)
        middle_ext = self._is_finger_extended(landmarks, MIDDLE_TIP, MIDDLE_PIP, MIDDLE_MCP)
        ring_ext = self._is_finger_extended(landmarks, RING_TIP, RING_PIP, RING_MCP)
        pinky_ext = self._is_finger_extended(landmarks, PINKY_TIP, PINKY_PIP, PINKY_MCP)

        # 1. Gesto: JOINHA 👍 (Confirmar / Enter)
        if self._is_thumbs_up(landmarks, index_ext, middle_ext, ring_ext, pinky_ext):
            self._thumbs_up_counter += 1
            self._ok_counter = 0
            self._ok_fired = False
            self._reset_dwell()
            self._circle_tracker.clear()
            self._is_pinching = False

            if self._thumbs_up_counter >= 2 and not self._thumbs_up_fired and self._can_fire(now):
                self._last_discrete_action = now
                self._thumbs_up_fired = True
                return GestureEvent(Gesture.CONFIRM, raw_thumb)
            return GestureEvent(Gesture.NONE, raw_thumb)
        else:
            self._thumbs_up_counter = 0
            self._thumbs_up_fired = False

        # 2. Gesto: VOZ (Sinal de OK 👌)
        if self._is_ok_sign(landmarks, pinch_dist, middle_ext, ring_ext, pinky_ext):
            self._ok_counter += 1
            self._thumbs_up_counter = 0
            self._thumbs_up_fired = False
            self._reset_dwell()
            self._circle_tracker.clear()
            self._is_pinching = False

            if self._ok_counter >= 2 and not self._ok_fired and self._can_fire(now):
                self._last_discrete_action = now
                self._ok_fired = True
                return GestureEvent(Gesture.VOICE_ACTIVATE, index)
            return GestureEvent(Gesture.NONE, index)
        else:
            self._ok_counter = 0
            self._ok_fired = False

        # 3. Punho fechado mantido: alterna pausa/retomada.
        if self._is_closed_fist(landmarks, index_ext, middle_ext, ring_ext, pinky_ext):
            if self._fist_start_time is None:
                self._fist_start_time = now
            if not self._fist_fired and now - self._fist_start_time >= self.config.fist_hold_seconds:
                self._fist_fired = True
                return GestureEvent(Gesture.PAUSE_TOGGLE, wrist)
            return GestureEvent(Gesture.NONE, wrist)
        self._fist_start_time = None
        self._fist_fired = False

        # 4. Gesto: PALMA ABERTA (Trocar Workspace por Swipe)
        open_fingers = sum([index_ext, middle_ext, ring_ext, pinky_ext])
        is_open_palm = open_fingers >= 3
        if is_open_palm:
            if not has_multiple_hands:
                palm_event = self._check_open_palm_swipe(wrist, now)
                if palm_event:
                    self._reset_dwell()
                    self._circle_tracker.clear()
                    self._is_pinching = False
                    return palm_event
        else:
            if self._palm_history and (now - self._palm_history[-1].time > 0.10):
                self._palm_history.clear()

        # 5. Gesto: PINÇA COM HISTERESE (Mover Janela / Arrastar)
        # Palma aberta tem prioridade: uma mão totalmente aberta nunca vira
        # pinça só porque a geometria do polegar passou perto do indicador.
        if is_open_palm:
            self._is_pinching = False
        elif not self._is_pinching and pinch_dist <= self.config.pinch_distance_start:
            self._is_pinching = True
        elif self._is_pinching and pinch_dist > self.config.pinch_distance_release:
            self._is_pinching = False

        if self._is_pinching:
            self._reset_dwell()
            self._circle_tracker.clear()
            self._remember(index)
            return GestureEvent(Gesture.PINCH, index)

        # 6. Indicador sozinho: exclusivamente mouse e clique no ar.
        if index_ext and not middle_ext and not ring_ext and not pinky_ext:
            self._gesture_mode = False
            self._reset_dwell()
            self._circle_tracker.clear()
            # O movimento curto usa o landmark bruto, antes do filtro que
            # suaviza o cursor e poderia apagar o clique no ar.
            air_click = self._check_air_click(raw_index, now)
            self._remember(index)
            if air_click:
                return air_click
            # Durante a tentativa de clique, congela o cursor na posição que
            # o usuário escolheu. O movimento de pressionar/soltar não pode
            # deslocar o alvo antes de o botão ser acionado.
            if self._air_click_start is not None:
                return GestureEvent(Gesture.NONE, index, cursor_enabled=False, gesture_mode=False)
            return GestureEvent(Gesture.NONE, index, cursor_enabled=True, gesture_mode=False)

        # 7. Indicador + médio levantados: muda imediatamente para laranja e
        # libera círculos/scroll. Não há mais espera para carregar a bolinha.
        if index_ext and middle_ext and not ring_ext and not pinky_ext:
            if not self._gesture_mode:
                self._gesture_mode = True
                self._circle_tracker.clear()
                self._reset_dwell()
                self._remember(index)
                return GestureEvent(
                    Gesture.NONE,
                    index,
                    dwell_progress=0.0,
                    cursor_enabled=False,
                    gesture_mode=True,
                )

            # Modo gesto: o mouse fica parado e apenas os comandos são avaliados.
            self._circle_tracker.add_point(index, now)
            circle_gesture = self._circle_tracker.evaluate(now)
            if circle_gesture is not Gesture.NONE:
                self._reset_dwell()
                self._last_discrete_action = now
                self._remember(index)
                # O círculo anti-horário volta a ser navegação. Ele nunca
                # envia Ctrl+Z, pois isso pode suspender o terminal do AETHER.
                return GestureEvent(
                    circle_gesture,
                    index,
                    trail=self._circle_tracker.get_trail(),
                    cursor_enabled=False,
                    gesture_mode=True,
                )

            scroll_event = self._check_scroll(index, now)
            if scroll_event:
                self._reset_dwell()
                self._remember(index)
                return GestureEvent(
                    scroll_event.gesture,
                    scroll_event.cursor,
                    amount=scroll_event.amount,
                    cursor_enabled=False,
                    gesture_mode=True,
                )

            self._remember(index)
            return GestureEvent(
                Gesture.NONE,
                index,
                dwell_progress=0.0,
                trail=self._circle_tracker.get_trail(),
                cursor_enabled=False,
                gesture_mode=True,
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

                if now - self._last_minimize_time >= self.config.minimize_cooldown_seconds and self._can_fire(now):
                    self._last_discrete_action = now
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

                if now - self._last_toggle_minimized_time >= self.config.toggle_minimized_cooldown_seconds and self._can_fire(now):
                    self._last_discrete_action = now
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
                    self._last_discrete_action = now
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
                    self._last_discrete_action = now
                    self._last_swipe_time = now
                    self._last_swipe_gesture = Gesture.SWIPE_RIGHT
                    self._swipe_opposite_lockout_until = now + self.config.swipe_opposite_lockout_seconds
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

    def _check_scroll(self, index: Point, now: float) -> GestureEvent | None:
        """Gera passos de scroll somente após deslocamento vertical consistente."""
        if self._previous_filtered_index is None:
            return None

        # Depois de um passo, aguarda alguns frames para que a mesma oscilação
        # não role a página várias vezes seguidas.
        if now - self._last_scroll_time < self.config.scroll_cooldown_seconds:
            return None

        dx = index.x - self._previous_filtered_index.x
        dy = index.y - self._previous_filtered_index.y

        if abs(dy) < 0.004 or abs(dx) > abs(dy) * 0.55:
            self._scroll_accumulator = 0.0
            return None

        self._scroll_accumulator += dy

        if self._scroll_accumulator <= -self.config.scroll_threshold:
            self._scroll_accumulator = 0.0
            self._last_scroll_time = now
            return GestureEvent(Gesture.SCROLL, index, amount=1)
        elif self._scroll_accumulator >= self.config.scroll_threshold:
            self._scroll_accumulator = 0.0
            self._last_scroll_time = now
            return GestureEvent(Gesture.SCROLL, index, amount=-1)

        return None

    def _check_dwell(self, index: Point, now: float) -> tuple[GestureEvent | None, float]:
        """Lógica antiga de dwell, mantida para possível reativação futura.

        Atualmente ela não participa da troca para o modo laranja: a troca é
        imediata ao levantar indicador e médio. O método permanece isolado para
        podermos restaurar o atraso sem reescrever o reconhecedor.
        """
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

        # Não use `or` aqui: timestamp 0.0 é válido nos testes e em relógios
        # simulados. Caso contrário a bolinha nunca completa no primeiro ciclo.
        start_time = self._dwell_start_time if self._dwell_start_time is not None else now
        elapsed = now - start_time
        progress = min(1.0, elapsed / self.config.dwell_seconds)

        if progress >= 1.0 and not self._dwell_fired:
            self._dwell_fired = True
            return GestureEvent(Gesture.DWELL_CLICK, index, dwell_progress=1.0), 1.0

        return None, progress if not self._dwell_fired else 1.0

    def _check_air_click(self, index: Point, now: float) -> GestureEvent | None:
        """Reconhece um toque curto do indicador no ar, no modo mouse."""
        previous = self._air_click_previous_raw
        self._air_click_previous_raw = index
        if now < self._air_click_cooldown_until:
            return None

        # A primeira metade do gesto é um pequeno movimento para baixo.
        if self._air_click_start is None:
            if previous is not None and index.y - previous.y >= self.config.air_click_threshold:
                self._air_click_start = previous
                self._air_click_started_at = now
            return None

        start = self._air_click_start
        started_at = self._air_click_started_at if self._air_click_started_at is not None else now
        if now - started_at > self.config.air_click_window_seconds:
            self._air_click_start = None
            self._air_click_started_at = None
            return None

        # O retorno próximo ao ponto inicial completa o clique.
        if index.y <= start.y + self.config.air_click_threshold * 0.35:
            self._air_click_start = None
            self._air_click_started_at = None
            self._air_click_cooldown_until = now + self.config.air_click_cooldown_seconds
            return GestureEvent(Gesture.DWELL_CLICK, index, cursor_enabled=False, gesture_mode=False)
        return None

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

        return (dist_tip_wrist > dist_pip_wrist * 1.01) and (dist_tip_mcp > dist_pip_mcp * 0.98)

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
        self._last_scroll_time = -999.0
        self._zoom_anchor_dist = None
        self._two_hand_zoom_active = False
        self._gesture_mode = False
        self._air_click_start = None
        self._air_click_started_at = None
        self._air_click_cooldown_until = -999.0
        self._air_click_previous_raw = None
        self._previous_filtered_index = None
        self._palm_history.clear()
        self._two_hand_history.clear()
        self._two_hand_mid_history.clear()
        self._circle_tracker.clear()
        self._ok_counter = 0
        self._thumbs_up_counter = 0
        self._ok_fired = False
        self._thumbs_up_fired = False
        self._last_discrete_action = -999.0
        self._last_swipe_time = -999.0
        self._last_swipe_gesture = None
        self._swipe_opposite_lockout_until = -999.0
        self._last_toggle_minimized_time = -999.0
        self._last_minimize_time = -999.0
        self._vertical_opposite_lockout_until = -999.0
        self._last_click_time = None
        self._typing_fired = False
        self._typing_motion_history.clear()
        self._typing_last_finger_y = None
        self._fist_start_time = None
        self._fist_fired = False
        self._calibration_count = 0
        self._calibrated = was_calibrated or self.config.calibration_frames <= 0

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
