# Feira tecnológia - Projeto AETHER

Sistema de controle de computador por gestos aéreos em tempo real, utilizando webcam, MediaPipe Tasks, PyAutoGUI e integração nativa com o compositor **Hyprland** (Wayland / Arch Linux).

---

## 🖐️ Catálogo Completo de Gestos

### 1. Gerenciamento de Janelas e Telas (Hyprland)
| Gesto | Como Fazer | Ação Executada |
| :--- | :--- | :--- |
| **Mover Janela / Arrastar** | Unir polegar e indicador (**pinça**) na barra da janela e mover a mão. Abrir os dedos para soltar. | Mouse Drag & Drop (`mouseDown` / `mouseUp`) |
| **Maximizar Janela** | Abrir os dois braços/mãos simultaneamente para os lados (afastamento). | `hyprctl dispatch fullscreen 1` |
| **Restaurar (Flutuante)** | Aproximar os dois braços/mãos em direção ao centro. | `hyprctl dispatch togglefloating` |
| **Minimizar** | Palma da mão aberta empurrando para baixo. | `hyprctl dispatch movetoworkspacesilent special:minimized` |
| **Trocar Área de Trabalho** | Palma aberta varrendo para a esquerda ou para a direita. | `hyprctl dispatch workspace e-1` / `e+1` |

### 2. Navegação e Zoom
| Gesto | Como Fazer | Ação Executada |
| :--- | :--- | :--- |
| **Rolar Página (Scroll)** | Manter **apenas o indicador estendido** e movê-lo para cima ou para baixo. | Rolagem vertical (`pyautogui.scroll`) |
| **Zoom In (Ampliar)** | Fazer pinça e afastar o polegar do indicador. | `Ctrl` + `+` |
| **Zoom Out (Reduzir)** | Fazer pinça e aproximar o polegar do indicador. | `Ctrl` + `-` |
| **Avançar Página** | Desenhar um **círculo no ar no sentido horário** com o indicador. | `Alt` + `Right` (Avançar no navegador) |
| **Voltar Página** | Desenhar um **círculo no ar no sentido anti-horário** com o indicador. | `Alt` + `Left` (Voltar no navegador) |

### 3. Cliques e Digitação
| Gesto | Como Fazer | Ação Executada |
| :--- | :--- | :--- |
| **Clicar (Links/Botões)** | Apontar com o indicador e segurar a mão parada por 0,5s (*Dwell Time*). | Clique do mouse com gauge visual de progresso |
| **Ativar Voz/Digitação** | Fazer o sinal de joinha 👍 (polegar para cima e outros dedos fechados). | Dispara gancho / atalho de ditado por voz |
| **Confirmar / Enviar** | Fazer o sinal de OK 👌 (polegar e indicador unidos, outros 3 estendidos). | `Enter` |

---

## 🚀 Como Executar

### 1. Instalação do Ambiente

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

### 2. Execução em Modo Seguro (Visualização e Treino)

Permite testar e visualizar o reconhecimento dos gestos na webcam sem interagir com o desktop:

```bash
machine-feira
```

### 3. Execução com Automação Real Ativa

Habilita o controle real do cursor, cliques e comandos do Hyprland:

```bash
machine-feira --control
```

*Dica*: Pressione a tecla `q` na janela da câmera para encerrar a qualquer momento.

---

## 🧪 Testes Automatizados

Para rodar a suíte completa de testes unitários:

```bash
pytest
```

---

## 📁 Estrutura do Projeto

- `src/machine_feira/types.py`: Definições puras de dados, enums de gestos e eventos com metadados.
- `src/machine_feira/hand_gestures.py`: Algoritmo determinístico de detecção postural, temporização e gestos com 1 ou 2 mãos.
- `src/machine_feira/trajectory.py`: Rastreador de trajetórias para identificação de círculos horários e anti-horários.
- `src/machine_feira/hyprland.py`: Módulo de integração e despacho de comandos `hyprctl` para o compositor Hyprland.
- `src/machine_feira/automation.py`: Ponte de automação do desktop com PyAutoGUI e Hyprland.
- `src/machine_feira/main.py`: Loop principal de captura da webcam, detecção com MediaPipe Tasks e HUD visual.
