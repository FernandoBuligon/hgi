# HGI — Hand Gesture Interface

Projeto local de visão computacional para interpretar gestos da mão.
**Fase 7 implementada: webcam, overlay e pipeline completo em dry-run.**
A demo visual interpreta a mão e mostra intenções virtuais. A validação com
webcam humana permanece pendente nesta sessão, pois não há `/dev/video*`.
`python -m hgi` continua sendo o entrypoint mínimo que identifica o projeto.

Requer Python **3.11 ou superior**. O bootstrap usa somente a biblioteca padrão.
Os módulos matemáticos também usam apenas Python, com dimensões fornecidas pelo chamador.
O extra `vision` declara MediaPipe 1.0.1, NumPy e opencv-contrib-python 5.0.0.93
com GUI; o ambiente validado usa Python 3.11.16.

## Instalação e execução

Em um ambiente virtual novo, na raiz do repositório:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev,vision]"
python -m hgi
```

No Windows, ative com `.venv\Scripts\Activate.ps1` no PowerShell.
O comando imprime `HGI — Hand Gesture Interface` e encerra.

No ambiente Conda existente desta máquina, use `conda activate hgi` antes dos
comandos: o Python padrão do shell pertence ao ambiente base, não ao HGI.

Se pytest, pytest-cov, Ruff e setuptools já estiverem disponíveis no ambiente
(como no Conda `hgi` inspecionado, incluindo NumPy e MediaPipe), registre somente
este projeto, sem downloads
ou instalação de dependências:

```bash
python -m pip install --no-deps --no-build-isolation --no-index -e .
python -m hgi
```

## Verificações

```bash
python -m pytest -q
python -m pytest --cov=hgi --cov-report=term-missing
python -m ruff check .
python -m ruff format --check .
python -m compileall src
python -m pip check
```

O ambiente HGI agora contém somente **opencv-contrib-python 5.0.0.93**, sem
variantes headless, com `cv2.__version__ == "5.0.0"` e GUI QT5. Não instale
opencv-python junto: compartilham arquivos e o namespace cv2. MediaPipe exige
contrib, que já contém os módulos principais. Na manutenção desta fase, a
remoção inicial apagou arquivos compartilhados; foi revertida, e contrib foi
reparado na mesma versão após nova remoção de python. Nenhuma outra dependência
foi alterada. `pip check` e o import final passaram; detalhes no plano.

## Demo visual com webcam — somente dry-run

Prepare explicitamente o modelo conforme [MODELS.md](docs/MODELS.md). Na raiz,
com o ambiente ativado e HGI instalado:

```bash
python scripts/demo_webcam.py
```

O caminho padrão é `models/hand_landmarker.task`. Para outro caminho/câmera ou
dimensões solicitadas e tela lógica diferentes:

```bash
python scripts/demo_webcam.py --model /caminho/hand_landmarker.task --camera 0 \
  --width 640 --height 480 --screen-width 1920 --screen-height 1080
```

Não há download automático. Modelo ausente encerra com mensagem apontando para
MODELS.md. As dimensões da tela são lógicas; nenhum monitor real é consultado.
A câmera pode ignorar a resolução pedida: a integração usa `frame.shape` para
desenho e correção de proporção das medidas. Se as dimensões entregues mudarem,
a sessão é reiniciada DISABLED; habilite novamente com E.

| Tecla com foco na janela OpenCV | Efeito |
|---|---|
| E | Habilita apenas intenções virtuais |
| D | Desabilita e limpa a interação |
| R | Reset da interação e contador visual, permanecendo DISABLED |
| Q / Esc | Encerra e libera câmera, tracker e janelas |

Também é possível fechar a janela. A sessão começa **DISABLED**; nenhuma mão
a habilita automaticamente. `CONTROL: ENABLED` significa exclusivamente
autorizar a saída dry-run. A demo não aceita `--control` e não importa PyAutoGUI.
MOVE/CLICK são dataclasses em memória; nenhum mouse, clique ou tecla do sistema
é acionado. Teclas são lidas somente por `cv2.waitKey`, na janela da demo.
Não são gravados nem transmitidos frames pelo código HGI.

O overlay mostra modo, handedness/confiança Left/Right, RAW/STABLE, candidato,
armamento/cooldown, razão de pinça, cursor virtual/ação e FPS. Desenha os 21
landmarks com conexões, realça o indicador e marca a região ativa de 10% a 90%.
`Index normalized` é a posição no frame espelhado; `screen target` é o alvo
mapeado antes da suavização; `Cursor` é a posição virtual retida pelo controller.
`Action` mostra somente o comando do frame atual. `Last CLICK: RECENT` e uma
borda amarela permanecem por 500 ms após uma intenção CLICK. `Session CLICKs`
conta as intenções desde a abertura da demo ou o último R; D/E preservam o total.
Essa memória é somente visual: guarda contador/timestamp, sem reemitir ou reter
um comando CLICK. O relógio da UI é separado dos gates de gesto/cooldown.
FPS é a frequência do loop, mostrada
com uma amostra de atraso; não é uma medição isolada de latência do modelo.

O frame é espelhado **antes** da inferência; o controller usa `mirror_x=False`.
Seleção: maior `handedness_score`, primeira mão em empate/ausência; esse score
mede classificação Left/Right, não confiança de detecção. O tracker usa uma mão
por padrão. Não há identidade persistente; ao trocar de mão, use R e depois E.
As regras e thresholds das fases anteriores foram preservados.

| Gesto/estado | Saída virtual quando ENABLED |
|---|---|
| POINT confirmado, pinça aberta | MOVE com margem e EMA |
| PINCH confirmado, armado e fora do cooldown | Um CLICK no último alvo virtual |
| PINCH mantido / cooldown bloqueado | NONE, sem clique pendente |
| Sem mão / DISABLED | NONE |
| OPEN_HAND, FIST ou UNKNOWN confirmados | NONE e limpeza do movimento |

Exige webcam acessível e sessão gráfica funcional com OpenCV GUI. No Linux,
ausência de DISPLAY/WAYLAND_DISPLAY produz erro claro antes da captura. Variável
presente não garante conexão/driver/plugin gráfico funcional; a wheel QT5 deste
ambiente usa X11/XWayland conforme suporte local. Windows/macOS podem exigir
permissão de câmera. Esta demo não precisa de permissão para automação de entrada.
Falhas de captura/inferência/desenho encerram com limpeza; geometria degenerada
gera erro explícito, em vez de inventar um gesto. Q/Esc são processados entre
frames; captura ou inferência nativa bloqueada pode atrasar a resposta.

Validação automatizada: **360 testes**, **99% de cobertura total**, Ruff check e
format aprovados. Testes de câmera/janela usam fakes; o overlay usa OpenCV real
sobre arrays sintéticos sem display. POINT/PINCH foram validados sinteticamente.
FPS real, lateralidade, ergonomia, jitter e qualidade de detecção humana ainda
exigem webcam. IMAGE continua síncrono, sem otimização temporal do modo VIDEO.
Veja o roteiro manual e evidências em [IMPLEMENTATION_PLAN.md](docs/IMPLEMENTATION_PLAN.md).

## Matemática disponível

`hgi.geometry` contém pontos/regiões tipados, distância, clamp, conversões,
espelhamento e mapeamento de uma área útil para dimensões de tela fornecidas.
`hgi.smoothing.ExponentialSmoother(alpha)` aplica EMA em X/Y e permite reset.

Nas conversões, `0.0` corresponde ao primeiro pixel e `1.0` ao último (`dimensão - 1`).
O centro de 1920×1080 é `(959.5, 539.5)`; coordenadas fracionárias são preservadas.

## HandTracker disponível

Prepare um modelo local seguindo [MODELS.md](docs/MODELS.md). Não há download em runtime.

```python
import numpy as np

from hgi.hand_landmarks import HandLandmark
from hgi.hand_tracker import HandTracker

frame_rgb = np.zeros((240, 320, 3), dtype=np.uint8)  # Imagem sintética sem mão.
with HandTracker("models/hand_landmarker.task") as tracker:
    hands = tracker.process(frame_rgb)
    if hands:
        hand = hands[0]
        index_tip = hand.landmarks[HandLandmark.INDEX_FINGER_TIP]
        print(hand.handedness, hand.handedness_score, index_tip)
```

A entrada é RGB, `uint8`, `H × W × 3`; retorno vazio é `()`. O modo IMAGE é
síncrono e não exige timestamps. Os resultados contêm 21 pontos XYZ próprios do
HGI. A ordem de cores depende do chamador; um array BGR não pode ser identificado
automaticamente pelo formato. A conversão BGR→RGB ocorre explicitamente na demo;
nenhum teste de mão humana foi realizado nesta sessão.

## Reconhecimento geométrico disponível

Com uma variável `hand` contendo um `DetectedHand` interno, sem importar
bibliotecas de visão:

```python
from hgi.finger_state import GestureConfig, detect_fingers, pinch_ratio
from hgi.gesture_detector import GestureDetector

config = GestureConfig(pinch_threshold=0.25, image_aspect_ratio=640 / 480)
detector = GestureDetector(config)
state = detect_fingers(hand, config)
ratio = pinch_ratio(hand, config)
gesture = detector.detect(hand)
```

São reconhecidos UNKNOWN, POINT, PINCH, OPEN_HAND e FIST. PINCH tem prioridade,
com distância polegar→indicador dividida pela referência wrist→middle MCP.
As heurísticas são determinísticas por mão, sem debounce, histerese ou ações.
O limiar inicial precisa de calibração com mãos reais; não é reconhecimento de
linguagem de sinais. Proporção da imagem e limites geométricos estão documentados
em [ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Cursor virtual disponível

Com `hand` contendo um DetectedHand interno (ou None), a saída é uma intenção
inspecionável em memória, sem controlar o computador:

```python
from hgi.cursor import DryRunCursorSink
from hgi.cursor_controller import CursorConfig, CursorController

sink = DryRunCursorSink()
controller = CursorController(CursorConfig(1920, 1080), sink=sink)
controller.enable()  # Opt-in de intenções virtuais; não habilita mouse real.
command = controller.update(hand)
print(command, sink.commands)
controller.reset()
```

O controller começa DISABLED; update retorna NONE até enable explícito.
POINT confirmado gera MOVE após área ativa, espelhamento e EMA. PINCH confirmado
gera CLICK lógico somente após abertura/armamento e fora do cooldown. A área
padrão vai de 0.1 a 0.9 nos dois eixos, com alpha 0.25. As dimensões são virtuais,
fornecidas pelo chamador. `mirror_x=True` espera imagem não espelhada;
desative-o se a entrada já foi espelhada. Reset/disable desabilitam, limpam a
interação e preservam o log. Defaults: confirmação de 80 ms, histerese 0.25/0.32,
cooldown de 300 ms e grace period de 150 ms. Perda breve preserva EMA e não
rearma pinça; perda longa exige confirmação/abertura novas. Não há backend de
mouse ou consulta ao monitor. A demo abaixo usa tempo simulado.

Para configurar ou testar tempo, injete
`TemporalGestureFilter(TemporalConfig(...), clock=seu_clock)` no parâmetro
`temporal` do controller; os tipos residem em `hgi.temporal`.

Demo finita sem webcam, depois de instalar o HGI:

```bash
python scripts/demo_cursor.py
```

Veja os contratos e limitações em [ARCHITECTURE.md](docs/ARCHITECTURE.md)
e [o plano com evidências TDD](docs/IMPLEMENTATION_PLAN.md).
A implementação da Fase 7 termina nesta integração dry-run; o controle real
continua adiado e exige autorização própria. Próximo passo: smoke com webcam
e observação exploratória dos defaults, antes de qualquer backend real ou extras.
