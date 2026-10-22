from __future__ import annotations

import json
import shutil
from pathlib import Path

ROOT = Path.cwd()
PACKAGE = ROOT / "src" / "machine_feira"
MAIN = PACKAGE / "main.py"
GESTURES = PACKAGE / "hand_gestures.py"
AUTOMATION = PACKAGE / "automation.py"

if not all(p.exists() for p in (MAIN, GESTURES, AUTOMATION)):
    raise SystemExit("Execute este instalador na pasta raiz do projeto Machine Learning, onde existe src/machine_feira.")

for path in (MAIN, GESTURES, AUTOMATION):
    backup = path.with_suffix(path.suffix + ".aether-backup")
    if not backup.exists():
        shutil.copy2(path, backup)

# Corrige o bloqueio do movimento de retorno: ele precisa voltar pelo menos a distância
# do limiar para rearmar o scroll, sem gerar um segundo evento durante a volta.
gesture_text = GESTURES.read_text(encoding="utf-8")
old_scroll = '''    def _check_scroll(self, index: Point) -> GestureEvent | None:
        if self._previous_filtered_index is None:
            return None

        dx = index.x - self._previous_filtered_index.x
        dy = index.y - self._previous_filtered_index.y

        if abs(dx) > abs(dy) * 0.55:
            self._scroll_accumulator = 0.0
            self._scroll_return_direction = 0
            self._scroll_return_accumulator = 0.0
            return None

        if abs(dy) < 0.002:
            return None

        if abs(dy) >= 0.006:
            self._click_pending_time = None
            self._click_bend_started = None

        if self._scroll_return_direction != 0:
            if dy * self._scroll_return_direction > 0:
                self._scroll_return_accumulator += abs(dy)
                return None

            self._scroll_return_direction = 0
            self._scroll_return_accumulator = 0.0
            self._scroll_accumulator = 0.0

        self._scroll_accumulator += dy

        if self._scroll_accumulator <= -self.config.scroll_threshold:
            self._scroll_accumulator = 0.0
            self._scroll_return_direction = 1
            self._scroll_return_accumulator = 0.0
            return GestureEvent(Gesture.SCROLL, index, amount=6)

        if self._scroll_accumulator >= self.config.scroll_threshold:
            self._scroll_accumulator = 0.0
            self._scroll_return_direction = -1
            self._scroll_return_accumulator = 0.0
            return GestureEvent(Gesture.SCROLL, index, amount=-6)

        return None
'''
new_scroll = '''    def _check_scroll(self, index: Point) -> GestureEvent | None:
        if self._previous_filtered_index is None:
            return None

        dx = index.x - self._previous_filtered_index.x
        dy = index.y - self._previous_filtered_index.y

        if abs(dx) > abs(dy) * 0.55:
            self._scroll_accumulator = 0.0
            return None

        if abs(dy) < 0.002:
            return None

        if abs(dy) >= 0.006:
            self._click_pending_time = None
            self._click_bend_started = None

        if self._scroll_return_direction != 0:
            if dy * self._scroll_return_direction > 0:
                self._scroll_return_accumulator += abs(dy)
                if self._scroll_return_accumulator >= self.config.scroll_threshold:
                    self._scroll_return_direction = 0
                    self._scroll_return_accumulator = 0.0
                    self._scroll_accumulator = 0.0
                return None
            return None

        self._scroll_accumulator += dy

        if self._scroll_accumulator <= -self.config.scroll_threshold:
            self._scroll_accumulator = 0.0
            self._scroll_return_direction = 1
            self._scroll_return_accumulator = 0.0
            return GestureEvent(Gesture.SCROLL, index, amount=6)

        if self._scroll_accumulator >= self.config.scroll_threshold:
            self._scroll_accumulator = 0.0
            self._scroll_return_direction = -1
            self._scroll_return_accumulator = 0.0
            return GestureEvent(Gesture.SCROLL, index, amount=-6)

        return None
'''
if old_scroll not in gesture_text:
    raise SystemExit("Não encontrei a versão esperada de _check_scroll. Nenhum arquivo foi alterado; envie seu hand_gestures.py atual.")
gesture_text = gesture_text.replace(old_scroll, new_scroll)
# Filter setting is applied by replacing the point filter when settings change.
if 'def apply_tremor_filter' not in gesture_text:
    anchor = '    @property\n    def calibrated(self) -> bool:\n'
    addition = '''    def apply_tremor_filter(self, enabled: bool) -> None:
        self._cursor_filter = PointFilter(min_cutoff=0.8, beta=0.004) if enabled else PointFilter(min_cutoff=1.2, beta=0.008)
        self._previous_filtered_index = None
        self._scroll_accumulator = 0.0
        self._scroll_return_direction = 0
        self._scroll_return_accumulator = 0.0

'''
    if anchor not in gesture_text:
        raise SystemExit("Não encontrei o ponto seguro para integrar o filtro de tremor.")
    gesture_text = gesture_text.replace(anchor, addition + anchor, 1)
GESTURES.write_text(gesture_text, encoding="utf-8")

# Intensidade do scroll passa a ser configurável, sem mudar o gesto reconhecido.
auto_text = AUTOMATION.read_text(encoding="utf-8")
if 'self.scroll_amount = 6' not in auto_text:
    anchor = '        self.enabled = enabled\n'
    if anchor not in auto_text:
        raise SystemExit("Não encontrei o ponto seguro em automation.py.")
    auto_text = auto_text.replace(anchor, anchor + '        self.scroll_amount = 6\n', 1)
auto_text = auto_text.replace('self._pyautogui.scroll(event.amount)', 'self._pyautogui.scroll(self.scroll_amount if event.amount > 0 else -self.scroll_amount)')
AUTOMATION.write_text(auto_text, encoding="utf-8")

# Instala a janela de configurações como módulo do pacote.
source_settings = Path(__file__).with_name("settings_window.py")
shutil.copy2(source_settings, PACKAGE / "settings_window.py")

main_text = MAIN.read_text(encoding="utf-8")
if 'aether_settings.json' not in main_text:
    main_text = main_text.replace('import argparse\n', 'import argparse\nimport json\nimport subprocess\nimport sys\nfrom dataclasses import replace\nfrom pathlib import Path\n', 1)
    main_text = main_text.replace('    recognizer = HandGestureRecognizer()\n    automation = DesktopAutomation(enabled=args.control)\n', '''    recognizer = HandGestureRecognizer()
    automation = DesktopAutomation(enabled=args.control)
    config_path = Path(__file__).resolve().parents[2] / "aether_settings.json"
    settings_process = None
    if not args.no_settings:
        settings_process = subprocess.Popen([sys.executable, "-m", "machine_feira.settings_window"])
    last_config_mtime = None
    active_config = {"scroll_threshold": recognizer.config.scroll_threshold, "scroll_intensity": 6, "tremor_filter": True}
''', 1)
    main_text = main_text.replace('    parser.add_argument("--control", action="store_true", help="habilita automação real do computador")\n', '    parser.add_argument("--control", action="store_true", help="habilita automação real do computador")\n    parser.add_argument("--no-settings", action="store_true", help="não abrir a janela de configurações")\n', 1)
    main_text = main_text.replace('                result = detector.detect_for_video(image, timestamp_ms)\n', '''                result = detector.detect_for_video(image, timestamp_ms)
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
''', 1)
    main_text = main_text.replace('        automation.release()\n        camera.release()\n', '''        automation.release()
        if settings_process is not None and settings_process.poll() is None:
            settings_process.terminate()
        camera.release()
''', 1)
MAIN.write_text(main_text, encoding="utf-8")

config = ROOT / "aether_settings.json"
if not config.exists():
    config.write_text(json.dumps({"scroll_threshold": 0.012, "scroll_intensity": 6, "tremor_filter": True}, indent=2), encoding="utf-8")

print("Integração aplicada. Backups .aether-backup criados para main.py, hand_gestures.py e automation.py.")
print("Agora execute: $env:PYTHONPATH = 'src'; .\\.venv\\Scripts\\python.exe -m machine_feira.main --control")
