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
Set-Location "D:\Feira Tecnológica\Machine Learning"
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
