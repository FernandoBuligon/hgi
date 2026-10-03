# HGI — Hand Gesture Interface

Interface local de visão computacional que interpreta gestos capturados por uma
webcam para mover o cursor com **POINT** (☝), clicar/segurar/arrastar com
**PINCH** (🤏) e produzir intenções de sistema para volume, screenshot e Spotify.
MediaPipe fornece os landmarks; regras geométricas e filtros temporais
interpretam a mão. PyAutoGUI e backends locais executam ações reais somente no
modo opcional.

**Dry-run é o modo padrão. Controle real exige `--real-control` + E.**

O repositório não inclui gravações de tela. A demo deve ser executada localmente
com webcam e, se desejado, gravada fora do fluxo normal do HGI.

## Funcionalidades

- Captura OpenCV, 21 landmarks e lateralidade quando disponível.
- Movimento com região ativa, mapeamento de coordenadas e suavização EMA.
- Pinça normalizada, confirmação temporal, histerese e cooldown.
- PINCH como botão físico: `MOUSE_DOWN`, movimento durante drag e `MOUSE_UP`.
- Ações avançadas: volume, screenshot e ROCK para Spotify em camada separada.
- Dry-run com intenções inspecionáveis; backend real isolado e opcional.
- Overlay com gesto bruto/estável, candidato, armamento, cursor, modo e FPS.
- Inferência IMAGE, VIDEO ou LIVE_STREAM; CPU padrão e GPU opcional explícita.
- Feedback do último CLICK por 500 ms e contador de intenções da sessão.
- Testes sintéticos sem webcam e sem movimentar o mouse real.

## Gestos

| Gesto | Resultado quando a sessão está habilitada |
|---|---|
| ☝ POINT | Move o cursor virtual ou real pela ponta do indicador |
| 🤏 PINCH | Pressiona o botão primário; soltar a pinça libera o botão |
| PINCH + movimento | Arrasta usando a ponta do indicador com a EMA existente |
| 👍 THUMBS_UP | Intenção `VOLUME_UP`; em real-control aumenta 5% até 100% |
| 👎 THUMBS_DOWN | Intenção `VOLUME_DOWN`; em real-control diminui 5% até 0% |
| ✌️ PEACE | Intenção `SCREENSHOT`; salva uma captura por ativação em real-control |
| 🤘 ROCK | Intenção `PLAY_SPOTIFY_TRACK`; abre/toca Highway to Hell — AC/DC |
| Sem mão ou outros estados | Nenhuma ação; tracking prolongadamente perdido limpa a interação |

POINT exige indicador estendido e médio, anelar e mindinho recolhidos, sem pinça.
PEACE exige indicador e médio estendidos, com anelar, mindinho e polegar
recolhidos. ROCK exige indicador e mindinho estendidos, com médio, anelar e
polegar recolhidos. THUMBS_UP/DOWN exigem polegar vertical e os outros dedos
fechados; rotações fortes da mão podem impedir a classificação. OPEN_HAND, FIST
e UNKNOWN são estados reconhecidos para neutralidade; não executam ações.

## Como funciona

O frame BGR da webcam é espelhado e convertido explicitamente para RGB. O
HandTracker adapta os resultados do MediaPipe a tipos internos. O detector
geométrico identifica a pose e a razão de pinça. O filtro temporal confirma os
estados. Gestos de cursor seguem para o `CursorController`; gestos de sistema
seguem para o `GestureActionController`. O cursor mapeia o indicador da região
ativa para a tela e aplica EMA antes de produzir MOVE, MOUSE_DOWN, MOUSE_UP ou
NONE.

A seleção usa o maior `handedness_score`, com a primeira mão em empate ou ausência
de score. Esse valor mede a classificação Left/Right, não confiança de detecção.
Não há identidade persistente entre mãos.

## Arquitetura

```mermaid
flowchart TD
    A[Webcam / Camera] --> B[OpenCV: espelhar BGR e converter RGB]
    B --> C[HandTracker / MediaPipe HandLandmarker]
    C --> D[DetectedHand: landmarks internos]
    D --> E[GestureDetector]
    E --> F[TemporalGestureFilter]
    F --> G[CursorController: mapeamento e EMA]
    F --> M[GestureActionController]
    G --> H[CursorCommand]
    H --> I[DryRunCursorSink]
    H --> J[RealCursorSink / PyAutoGUI opcional]
    M --> N[ActionIntent]
    N --> O[DryRunActionSink]
    N --> P[RealActionSink: volume / screenshot / Spotify]
    B --> K[Overlay: frame BGR]
    D --> K
    G --> K
    M --> K
    K --> L[Janela OpenCV]
```

A orquestração está em `src/hgi/webcam.py`; o desenho em `overlay.py` e os efeitos
reais em `real_cursor.py` e `system_actions.py`. Contratos, matemática e estados estão em
[ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Modelo de segurança

A sessão começa **DISABLED**, em ambos os modos. A flag seleciona o backend;
somente E, com foco na janela OpenCV, habilita a sessão.

| Modo | E pressionado | Resultado |
|---|---|---|
| Sem flag | Sim | Apenas intenções dry-run |
| `--real-control` | Não | Nenhum movimento, clique, volume, screenshot ou Spotify |
| `--real-control` | Sim | Cursor e ações reais após os filtros temporais |

D desabilita; R reseta e desabilita; Q/Esc encerra. Ctrl+C no terminal também
encerra com limpeza. Câmera, tracker e janelas são liberados inclusive em falhas.
Perda de tracking interrompe comandos; após perda longa é necessária nova
confirmação e abertura da pinça. Se o botão foi pressionado por PINCH, D/R/Q/Esc,
Ctrl+C, exceções, perda longa de tracking, fechamento da janela e saída normal
tentam liberar o botão antes da limpeza. Uma mão nunca habilita a sessão
automaticamente.

O **fail-safe do PyAutoGUI permanece habilitado**: leve fisicamente o mouse a
um canto da tela primária para interromper a próxima chamada do backend.
Falha em MOVE/MOUSE_DOWN/MOUSE_UP trava o sink, desabilita a sessão e propaga a
exceção original, sem retry; reinicie a demo para tentar novamente. Falhas de
volume, screenshot ou Spotify aparecem no overlay como erro e não derrubam a
visão. A pausa nativa do PyAutoGUI é preservada.

As teclas D/R/Q/Esc dependem do foco da janela; comandos nativos bloqueados podem
atrasar sua leitura. Antes de uma demo real, salve trabalhos, use uma área
inofensiva e comece com movimentos pequenos. Consulte o
[roteiro manual](docs/RELEASE_CHECKLIST.md#teste-manual-final).

HGI não grava nem transmite frames, não envia teclas, não usa clipboard e não
exige OpenAI. Em real-control, volume usa `wpctl` ou `pactl`, screenshot usa
PyAutoGUI e Spotify usa MPRIS/URI local quando disponível; todos ficam atrás de
interfaces testáveis e não rodam em dry-run. MediaPipe informa coleta de métricas
pela biblioteca; veja [origem do modelo e privacidade](docs/MODELS.md).

## Instalação

Requer **Python >= 3.11**; o ambiente validado é Python 3.11 em Linux/X11 x86_64.
Disponibilidade de wheels nativas varia por sistema e arquitetura.
Na raiz de uma cópia local do repositório, usando Python 3.11:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev,vision]"
python -m hgi
```

No PowerShell, ative com `.venv\Scripts\Activate.ps1`. `python -m hgi` imprime
a identificação do projeto e encerra; a demo é o script descrito abaixo.
A instalação foi reproduzida num venv novo, sem aproveitar os pacotes do Conda.
Uma sessão gráfica e webcam acessível são necessárias para a janela.

| Instalação | Finalidade |
|---|---|
| `python -m pip install -e .` | Núcleo e identificação, sem bibliotecas de hardware |
| `python -m pip install -e ".[vision]"` | Demo visual em dry-run |
| `python -m pip install -e ".[dev,vision]"` | Demo e ferramentas de desenvolvimento |
| `python -m pip install -e ".[vision,control]"` | Demo com backend real disponível |

`pyproject.toml` é a fonte das dependências. MediaPipe, OpenCV e PyAutoGUI têm
versões fixadas; NumPy e ferramentas de desenvolvimento têm intervalos aceitos.
Isso não é um lock completo das dependências transitivas. Não instale variantes
simultâneas de OpenCV: usamos somente **opencv-contrib-python com GUI**, exigido
também pelo MediaPipe, sem opencv-python ou headless.

## Preparação do modelo

O modelo não acompanha o repositório nem é baixado automaticamente. Siga
[MODELS.md](docs/MODELS.md) para criar `models/`, obter o bundle oficial versionado
`hand_landmarker.task` e verificar seu SHA-256 antes da primeira execução.
O caminho pode ser externo ao repositório; arquivos `.task` são ignorados pelo Git.

## Execução

Execute na raiz do repositório, com o ambiente ativado e o modelo preparado.
Os índices de câmera variam por sistema; o padrão é 0. Se 1 não abrir, tente 0.

### Dry-run

```bash
python scripts/demo_webcam.py \
  --model models/hand_landmarker.task \
  --camera 1
```

### Controle real

Instale o extra `control` pela tabela acima e execute:

```bash
python scripts/demo_webcam.py \
  --model models/hand_landmarker.task \
  --camera 1 \
  --real-control
```

O overlay diferencia **HGI | DRY-RUN** de **HGI | REAL CONTROL**, com cabeçalho
vermelho no modo real. Ambos começam DISABLED; pressione E somente quando pronto.

### Opções

```bash
python scripts/demo_webcam.py --help
```

| Opção | Significado |
|---|---|
| `--model` | Bundle local; padrão `models/hand_landmarker.task` |
| `--camera` | Índice da webcam; padrão 0 |
| `--width`, `--height` | Resolução solicitada; padrão 640×480, sujeita à câmera |
| `--screen-width`, `--screen-height` | Devem ser fornecidas juntas; tela lógica ou override real |
| `--real-control` | Seleciona backend real, sem habilitar a sessão |
| `--screenshot-dir` | Diretório para screenshots reais de PEACE; padrão `~/Pictures/HGI/` |
| `--spotify-track-uri` | URI `spotify:track:` usada por ROCK |
| `--running-mode` | `image` (padrão síncrono), `video` (tracking síncrono), `live-stream` (assíncrono) |
| `--delegate` | `cpu` (padrão) ou `gpu` (opt-in; falha clara se indisponível) |

O frame efetivamente entregue determina proporção e desenho. Mudança dessas
dimensões reseta e desabilita a sessão. Dry-run usa tela lógica 1920×1080 sem
consultar monitor. Em modo real, o backend detecta as dimensões; overrides
positivos não podem exceder a área detectada e usam origem (0,0). Reinicie após
alterar monitores. Modelo ausente gera orientação para MODELS.md.

Screenshots reais são salvos fora do repositório por padrão, com nomes como
`HGI_2026-10-02_23-30-15.png`. ROCK usa
`spotify:track:2zYzyRzz6pRmhPzyfMEC8s` por padrão. Se Spotify estiver fechado, o
backend tenta abrir a URI localmente; se o cliente exigir login ou não iniciar a
reprodução sozinho, o overlay informa a falha/limitação sem usar Web API,
OAuth, senha ou token.

### Controles da janela

| Tecla | Efeito |
|---|---|
| E | Enable: habilita a sessão no backend selecionado |
| D | Disable: interrompe comandos e limpa a interação |
| R | Reset + Disable: também limpa o contador visual |
| Q / Esc | Quit: encerra e libera recursos |

Fechar a janela também encerra. D/E preservam o contador de intenções CLICK.
O destaque de 500 ms existe somente na UI; não repete nem armazena comandos CLICK.

Uma demonstração finita, sem modelo, câmera ou mouse real:

```bash
python scripts/demo_cursor.py
```

### Performance e aceleração

Para avaliar tracking entre frames, mantendo dry-run e início DISABLED:

```bash
python scripts/demo_webcam.py --model models/hand_landmarker.task \
  --camera 1 --running-mode video --delegate cpu
```

Troque para `--running-mode live-stream` para inferência assíncrona ou use
`--delegate gpu` para solicitar GPU. Essas opções não habilitam o mouse.
GPU não exige instalação automática de CUDA ou drivers; suporte depende do
pacote MediaPipe e da sessão gráfica. Uma falha indica como retornar à CPU.

O overlay distingue **Loop FPS** de **Inference FPS**. Em LIVE_STREAM, somente
resultados recentes e consumidos uma vez alimentam o controller; callbacks
nunca executam ações. Frames ocupados são descartados, sem fila ilimitada.

Benchmark explícito, sem janela, gravação ou backend de cursor:

```bash
python scripts/benchmark_hand_tracker.py --model models/hand_landmarker.task \
  --camera 1 --delegate cpu --running-mode video --duration 15
python scripts/benchmark_hand_tracker.py --running-mode image --duration 15
```

Sem `--camera`, o segundo comando reutiliza um frame preto sintético; o modelo
local continua obrigatório. `--image caminho.png` usa uma imagem local
pré-carregada; `--json` fornece dados para comparação. Não versionamos frames.
Metodologia, matriz medida, limitações da GPU e roteiro de aceite estão em
[PERFORMANCE.md](docs/PERFORMANCE.md). Os ensaios sem mão ficaram próximos de
12,5 FPS na webcam; a captura dominou o tempo. Não há evidência para trocar
automaticamente os defaults IMAGE/CPU ou alterar a pausa do PyAutoGUI.

## Testes e build

Com o extra `dev` instalado:

```bash
python -m pytest -q
python -m pytest --cov=hgi --cov-report=term-missing
python -m ruff check .
python -m ruff format --check .
python -m compileall src
python -m pip check
python -m pip wheel --no-deps --no-build-isolation --wheel-dir dist .
```

A build acima usa o `setuptools>=68` já instalado no ambiente de build;
`--no-build-isolation` não instala esse requisito por você. Os testes e a wheel
foram verificados em ambientes separados. Uma build com isolamento requer acesso
ao índice de pacotes; nesta sessão essa tentativa foi bloqueada por falha de DNS.

Pytest usa mãos sintéticas, clocks injetáveis e backends falsos; não abre webcam
real nem controla mouse. Cobertura não substitui o teste manual de ergonomia.
Resultados datados e checkpoints estão no
[plano de implementação](docs/IMPLEMENTATION_PLAN.md#19-fase-11--advanced-gesture-actions--system-integration).

## Decisões técnicas

- **MediaPipe Tasks Vision:** IMAGE/CPU preservados como baseline; VIDEO usa
  tracking e LIVE_STREAM expõe resultados assíncronos com consumo único.
- **Tipos internos:** gestos e geometria independem das utilities do MediaPipe.
- **Geometria:** pinça dividida pela referência wrist→middle MCP, com correção
  da proporção do frame; não depende de uma distância fixa em pixels.
- **EMA:** reduz jitter após o mapeamento; alpha menor aumenta o atraso.
- **Temporalidade:** confirmação de 80 ms, histerese 0.25/0.32, PINCH como
  press/release, cooldown de ações discretas e tracking grace de 150 ms.
- **Sinks separados:** lógica produz intenções; somente o backend real realiza
  efeitos. Arredondamento ocorre nessa fronteira, sem duplicar filtros.
- **Ações de sistema:** `GestureActionController` produz `ActionIntent`; volume
  usa `wpctl` com fallback `pactl`, screenshot usa backend PyAutoGUI isolado e
  Spotify usa MPRIS/URI local sem credenciais.

Parâmetros como smoothing e thresholds podem precisar de ajuste conforme a câmera,
a iluminação e o usuário.

## Limitações

- Linux/X11 é o ambiente das verificações atuais. Captura/inferência foram
  medidas com webcam e o smoke manual da Fase 11 foi reportado como funcional.
  Windows/macOS ainda precisam de validação local e permissões próprias.
- GPU inicializou na RTX 5060, mas emitiu aviso nativo sobre reutilização de
  tensores. Isso exige investigação/aceite antes de recomendar GPU para controle.
- Wayland, inclusive via XWayland, é rejeitado pelo backend real; use dry-run.
- Iluminação, oclusão, rotações fora do plano e câmera afetam landmarks.
  Heurísticas não são reconhecimento universal de linguagem de sinais.
- Não há identidade persistente de múltiplas mãos nem suporte avançado a múltiplos
  monitores.
- Spotify depende do cliente desktop local. Abertura de URI funciona melhor com
  o app instalado e sessão logada; o HGI não automatiza login nem usa Web API.
- `PyAutoGUI.PAUSE=0.1` foi preservado: ações frequentes podem limitar o FPS.
  Os benchmarks documentados medem cenários controlados; não há tabela manual
  versionada de FPS por gesto.

## Roadmap

Após o aceite do MVP: calibração guiada, avaliação de filtros de movimento,
gestos configuráveis, ações adicionais de cursor e melhor suporte a monitores.
Esses itens não estão implementados nesta versão.

## Release e licença

A preparação para `v0.1.0` está em [RELEASE_CHECKLIST.md](docs/RELEASE_CHECKLIST.md).
O manifesto declara `0.1.0`; publicação/tag continuam dependendo de autorização futura.
O código do HGI é distribuído sob a [licença MIT](LICENSE).
Modelos e dependências mantêm seus próprios termos, descritos em MODELS.md.
