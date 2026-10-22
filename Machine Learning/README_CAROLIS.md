# AETHER / Machine Feira — execução no Windows

## Preparar o ambiente (PowerShell, dentro da pasta do projeto)

```powershell
Set-Location "D:\Feira Tecnológica\Machine Learning"
py -3.11 --version
if (-not (Test-Path .\.venv\Scripts\python.exe)) { py -3.11 -m venv .venv }
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
python -m pip check
```

## Comando 1 — testes automatizados

```powershell
SSet-Location "D:\Feira Tecnológica\Machine Learning"
.\.venv\Scripts\Activate.ps1
python -m pytest -v
```

## Comando 2 — iniciar a câmera com controle ativo

```powershell
Set-Location "D:\Feira Tecnológica\Machine Learning"
.\.venv\Scripts\Activate.ps1
python -m machine_feira.main --control
```

Para iniciar sem controlar mouse/teclado de verdade (modo seguro):

```powershell
python -m machine_feira.main
```

Pressione `q` na janela da câmera para encerrar. O controle ativo envia ações reais ao computador; feche o programa se algum gesto não estiver sendo reconhecido como esperado.

## Observações
- O modelo MediaPipe está incluído em `models/hand_landmarker.task`.
- Backups originais foram preservados na pasta `backups/`.
- Testes automatizados validam a lógica simulada, não substituem o teste físico com webcam e Windows.





tests\test_hand_gestures.py:193: AttributeError
=========================================== short test summary info ============================================
FAILED tests/test_automation.py::test_cursor_mapping - TypeError: DesktopAutomation.__init__() got an unexpected keyword argument 'windows'
FAILED tests/test_automation.py::test_drag_and_release - TypeError: DesktopAutomation.__init__() got an unexpected keyword argument 'windows'
FAILED tests/test_automation.py::test_navigation_and_clicks - TypeError: DesktopAutomation.__init__() got an unexpected keyword argument 'windows'
FAILED tests/test_automation.py::test_windows_window_actions - TypeError: DesktopAutomation.__init__() got an unexpected keyword argument 'windows'
FAILED tests/test_hand_gestures.py::test_closed_fist_does_not_minimize - AttributeError: 'HandGestureRecognizer' object has no attribute 'calibrated'
FAILED tests/test_hand_gestures.py::test_open_palm_down_does_not_minimize - AttributeError: 'HandGestureRecognizer' object has no attribute 'calibrated'
FAILED tests/test_hand_gestures.py::test_detects_scroll_with_only_index_extended - AttributeError: 'HandGestureRecognizer' object has no attribute 'calibrated'
FAILED tests/test_hand_gestures.py::test_scroll_return_movement_does_not_trigger_second_scroll - AttributeError: 'HandGestureRecognizer' object has no attribute 'calibrated'
FAILED tests/test_hand_gestures.py::test_detects_dwell_click_with_index_only - AttributeError: 'HandGestureRecognizer' object has no attribute 'calibrated'
FAILED tests/test_hand_gestures.py::test_detects_thumbs_up_confirm - AttributeError: 'HandGestureRecognizer' object has no attribute 'calibrated'
FAILED tests/test_hand_gestures.py::test_detects_pinch_with_all_other_fingers_extended - AttributeError: 'HandGestureRecognizer' object has no attribute 'calibrated'
FAILED tests/test_hand_gestures.py::test_detects_ok_sign_as_voice_activation - AttributeError: 'HandGestureRecognizer' object has no attribute 'calibrated'
FAILED tests/test_hand_gestures.py::test_detects_open_palm_swipe_left_and_right - AttributeError: 'HandGestureRecognizer' object has no attribute 'calibrated'
FAILED tests/test_hand_gestures.py::test_detects_multiple_consecutive_swipes_with_same_hand - AttributeError: 'HandGestureRecognizer' object has no attribute 'calibrated'
FAILED tests/test_hand_gestures.py::test_detects_two_hand_maximize_and_minimize - AttributeError: 'HandGestureRecognizer' object has no attribute 'calibrated'
FAILED tests/test_hand_gestures.py::test_two_hands_stationary_do_not_fallback_to_confirm - AttributeError: 'HandGestureRecognizer' object has no attribute 'calibrated'
FAILED tests/test_hand_gestures.py::test_circle_in_hand_recognizer_triggers_page_forward - AttributeError: 'HandGestureRecognizer' object has no attribute 'calibrated'
FAILED tests/test_hand_gestures.py::test_fist_does_not_trigger_pinch - AttributeError: 'HandGestureRecognizer' object has no attribute 'calibrated'
FAILED tests/test_hand_gestures.py::test_detects_zoom_with_one_open_hand_and_one_pinch_hand - AttributeError: 'HandGestureRecognizer' object has no attribute 'calibrated'
======================================== 19 failed, 6 passed in 30.40s =========================================
Traceback (most recent call last):
  File "<frozen runpy>", line 198, in _run_module_as_main
  File "<frozen runpy>", line 88, in _run_code
  File "D:\Feira Tecnológica\Machine Learning\src\machine_feira\main.py", line 23, in <module>
    Gesture.CLICK_LEFT: "Clique esquerdo",
    ^^^^^^^^^^^^^^^^^^
  File "C:\Users\etec\AppData\Local\Programs\Python\Python311\Lib\enum.py", line 786, in __getattr__
    raise AttributeError(name) from None
AttributeError: CLICK_LEFT
(.venv) PS D:\Feira Tecnológica\Machine Learning> 