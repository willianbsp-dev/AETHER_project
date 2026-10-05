# Feira Tecnológica - Projeto AETHER

Sistema de controle de computador por gestos aéreos em tempo real, utilizando webcam, MediaPipe Tasks, PyAutoGUI, integrado à aplicação Mobile desenvolvida com Flutter e inteligência artificial.

---

## 👥 Integrantes e Informações Acadêmicas

**Disciplina:** Desenvolvimento Mobile / Inteligência Artificial  
**Professora:** Joelma Sartori  
**Integrantes da Dupla/Grupo:**
- Aluno 1 (Ana Carolina Lopes Reis / 25096)
- Aluno 2 (Julia Cavalcante Leão / 25230)
- Aluno 3 (Maria Rita Barbosa Lima Albuquerque dos Santos / 25021)
- Aluno 4 (Mayara Teles / 25122)
- Aluno 5 (Willian Bernardo Soares Pereira / 25018)

---

## 🎪 Proposta para a Feira Tecnológica / de Ciências

**Tema / Nome do Projeto:**  Gerenciamento de janelas com movimentos das mãos para facilitar o uso de computadores para pessoas com deficiências / AETHER((Adaptativo Environment for Tracking, Help, Execution, and Recognition) 
<!-- Exemplo: Identificador de Expressões e Humor com IA Mobile -->

**Problema que busca resolver / Proposta de Valor:**  O projeto busca facilitar o uso de computadores para pessoas com deficiências motores, que dificultam o uso do teclado e mouse do computador, sendo assim foi desenvolvido um método onde o usuário utiliza as mãos para movimentar as janelas.
<!-- Qual necessidade ou ideia o projeto atende? -->

**Público-Alvo:** Pessoas com dificuldades motoras. 
<!-- A quem se destina a solução? -->

**Como será a demonstração prática na feira:**  A demonstração será feita com os computadores através da câmera onde o avaliador usará a câmera para testar os movimentos possíveis e conseguir visualizar como o projeto funciona.
<!-- Descreva como os visitantes irão interagir com o app no estande -->

---

## 🖐️ Catálogo Completo de Gestos

### Contrato atual de gestos

| Gesto | Ação |
| :--- | :--- |
| 1 dwell | Clique esquerdo |
| 2 dwells | Clique direito |
| 🤏 Pinça | Arrastar janela |
| 🖐️ + 🤏 / pinça dinâmica | Zoom; afastar = zoom in, aproximar = zoom out |
| 👐 juntas, sobem e afastam | Maximizar |
| 👐 afastadas, descem e aproximam | Minimizar |
| ☝️ movimento vertical | Scroll |
| Círculo horário | Avançar |
| Círculo anti-horário | Desfazer (`Ctrl+Z`) |
| Swipe de palma | Trocar área de trabalho |
| 👐 posição de digitação | Abrir teclado virtual disponível |
| ⌨️ indicador parado | Clique esquerdo na tecla |
| 👌 OK | Ativar voz/digitação |
| 👍 Joinha | Enter/confirmar |
| ✊ punho mantido | Pausar; repetir retoma |
| 🖐️ inicial | Calibração automática |

Todas as mãos são validadas pelos 21 landmarks antes do processamento e passam
por filtros temporais/tolerâncias para reduzir tremores.

---

## 🛠️ Tecnologias Utilizadas

- [Flutter](https://flutter.dev/)
- [Google Teachable Machine](https://teachablemachine.withgoogle.com/)
- [TensorFlow Lite](https://www.tensorflow.org/lite)
- [Git & GitHub](https://github.com/)

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

O cursor funciona como um trackpad: o primeiro quadro fixa a posição atual e os
movimentos seguintes deslocam o mouse continuamente, sem saltos absolutos.

O gesto de joinha ativa diretamente o ditado offline AETHER. O atalho
`Super + Alt + V` no Hyprland também alterna o mesmo serviço. Se necessário,
um atalho externo ainda pode ser usado com `--voice-hotkey tecla1,tecla2,...`.

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

---

## 📋 Histórico de Commits e Atualizações

- `[25/08/2026]` - Criação do repositório e estrutura inicial.
- `[06/09/2026]` - Resumo da pesquisa sobre Machine Learning e Teachable Machine.
- `[06/09/2026]` - Adição da proposta e tema para a Feira Tecnológica.
- `[07/09/2026]` - Finalização do README e envio para avaliação.
