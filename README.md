# HGI — Hand Gesture Interface

Projeto local de visão computacional para interpretar gestos da mão.
**Fase 8 implementada: backend real com duplo opt-in e fail-safe.**
**Dry-run é o modo padrão.** A demo visual interpreta a mão e mostra intenções.
Mouse real exige `--real-control` e depois E na janela. A validação com
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
python scripts/demo_webcam.py --model models/hand_landmarker.task --camera 1
```

O caminho padrão é `models/hand_landmarker.task`. Para outro caminho/câmera ou
dimensões solicitadas e tela lógica diferentes:

```bash
python scripts/demo_webcam.py --model /caminho/hand_landmarker.task --camera 0 \
  --width 640 --height 480 --screen-width 1920 --screen-height 1080
```

Não há download automático. Modelo ausente encerra com mensagem apontando para
MODELS.md. Em dry-run as dimensões são lógicas (1920×1080 por padrão);
nenhum monitor real é consultado. Forneça largura e altura juntas ao sobrescrever.
A câmera pode ignorar a resolução pedida: a integração usa `frame.shape` para
desenho e correção de proporção das medidas. Se as dimensões entregues mudarem,
a sessão é reiniciada DISABLED; habilite novamente com E.

| Tecla com foco na janela OpenCV | Efeito |
|---|---|
| E | Habilita a sessão no backend selecionado |
| D | Desabilita e limpa a interação |
| R | Reset da interação e contador visual, permanecendo DISABLED |
| Q / Esc | Encerra e libera câmera, tracker e janelas |

Também é possível fechar a janela. A sessão começa **DISABLED**; nenhuma mão
a habilita automaticamente. Sem `--real-control`, E autoriza somente intenções
em memória: nenhum mouse ou clique real ocorre e PyAutoGUI não é carregado.
A flag antiga `--control` não é aceita. Teclas são lidas somente por
`cv2.waitKey`, na janela da demo; HGI não envia teclas ao sistema.
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
permissão de câmera. Dry-run não precisa de permissão para automação de entrada.
Falhas de captura/inferência/desenho encerram com limpeza; geometria degenerada
gera erro explícito, em vez de inventar um gesto. Q/Esc são processados entre
frames; captura ou inferência nativa bloqueada pode atrasar a resposta.

Validação automatizada: **403 testes**, **99% de cobertura total**, Ruff check e
format aprovados. Testes de câmera/janela usam fakes; o overlay usa OpenCV real
sobre arrays sintéticos sem display. POINT/PINCH foram validados sinteticamente.
FPS real, lateralidade, ergonomia, jitter e qualidade de detecção humana ainda
exigem webcam. IMAGE continua síncrono, sem otimização temporal do modo VIDEO.
Veja o roteiro manual e evidências em [IMPLEMENTATION_PLAN.md](docs/IMPLEMENTATION_PLAN.md).

## Controle real — opt-in explícito

O extra opcional `control` declara PyAutoGUI **0.9.54**. No ambiente HGI atual
ele já está instalado; nenhuma dependência foi alterada. Em ambiente novo:

```bash
python -m pip install -e ".[vision,control]"
python scripts/demo_webcam.py \
  --model models/hand_landmarker.task \
  --camera 1 \
  --real-control
```

| Execução | E na janela | Resultado |
|---|---|---|
| Padrão, sem flag | Sim | Apenas dry-run |
| `--real-control` | Não | Sessão DISABLED, nenhum input |
| `--real-control` | Sim | MOVE e CLICK reais após os gates temporais |

O overlay e o título mostram **HGI | REAL CONTROL**, com cabeçalho vermelho,
ou **HGI | DRY-RUN**; CONTROL ENABLED/DISABLED é um estado separado. A flag
nunca habilita a sessão sozinha. D desabilita, R reseta e desabilita, Q/Esc
encerra. Ctrl+C no terminal também encerra com limpeza. Disable/reset não
emitem movimento nem clique. As teclas da janela exigem foco; clicar em outra
aplicação pode retirar esse foco. O fail-safe físico continua disponível.

Somente o backend consulta a resolução em modo real, uma vez ao iniciar.
`--screen-width` **e** `--screen-height`, quando fornecidos juntos, sobrescrevem
essa resolução com um retângulo cuja origem é (0,0); devem ser positivos e não
exceder as dimensões detectadas. O pipeline continua recebendo somente números.
Reinicie a demo após alterar a configuração dos monitores. Não há seleção ou
mapeamento avançado de múltiplos monitores. Neste X11, PyAutoGUI informa
**4480×1440**, que pode representar a superfície combinada do servidor X.

`RealCursorSink(backend=None, screen_width=None, screen_height=None).emit(command)`
implementa CursorSink. O backend pode ser injetado (`size`, `move_to`, `click`).
MOVE encaminha as coordenadas existentes, arredondadas uma vez por `round`
(empates para o inteiro par), sem novo smoothing, clipping ou aceleração.
Coordenadas fora dos limites, inclusive após round, são rejeitadas antes do input.
CLICK chama uma vez `click` primário no alvo do comando, sem MOVE adicional do
HGI; PyAutoGUI pode reposicionar para clicar nesse alvo. NONE não chama o mouse.
Debounce, histerese, armamento e cooldown continuam exclusivamente no filtro
temporal. Um comando CLICK corresponde a um clique; a UI não repete comandos.

`FAILSAFE=True` é garantido na construção e antes de cada ação. Mover fisicamente
o mouse a um canto dispara o fail-safe na próxima chamada do PyAutoGUI. Uma
falha em MOVE/CLICK, incluindo fail-safe, trava o sink, desabilita a sessão e
propaga a exceção original, sem retry. A demo encerra e libera recursos;
falhas simultâneas de fechamento são anexadas à exceção original como notas.
Para tentar novamente é necessário reiniciar a demo. Não há rollback de uma
ação que o SO já tenha recebido antes da falha.

A pausa nativa `PAUSE=0.1` foi preservada, assim como outras proteções do
fornecedor. Cada MOVE/CLICK pode acrescentar 100 ms; durante movimento contínuo
isso limita o loop a aproximadamente 10 FPS ou menos, considerando também a
visão. É uma estimativa pelo custo configurado, **não FPS observado**. Não foi
reduzida a pausa para otimizar desempenho. Referência: [fail-safe e pausa do
PyAutoGUI](https://pyautogui.readthedocs.io/en/latest/index.html#fail-safes).

No Linux, o backend real usa X11 e exige acesso autorizado ao display. Wayland
é rejeitado explicitamente, inclusive quando há XWayland; use dry-run. Variáveis
de ambiente não garantem permissão de input. macOS pode exigir Acessibilidade;
Windows/macOS precisam de validação manual. Não há contorno de permissões.

Antes do smoke real, salve trabalhos, mantenha a janela HGI acessível e conheça
D/R/Q/Esc/Ctrl+C e o fail-safe. Evite botões destrutivos e terminais com comandos.
Teste nesta ordem: dry-run; real DISABLED sem E; POINT com movimentos pequenos
nas quatro direções e D; depois dois PINCH em área inofensiva, confirmando um
clique por pinça e nenhuma repetição ao mantê-la fechada. Registre FPS dos dois
modos e latência percebida. Sem webcam nesta sessão, essas etapas e movimento/
clique reais não foram testados. A consulta somente leitura ao X11 funcionou.

Pytest usa backends falsos e bloqueia o carregamento do PyAutoGUI real; nenhum
teste controla o mouse. Revisões Python/segurança e verification-loop estão
registrados no plano. Drag, scroll, teclado, volume e extras não foram implementados.

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
rearma pinça; perda longa exige confirmação/abertura novas. Esse exemplo e a
demo abaixo usam somente o sink virtual; o controller não consulta hardware.

Para configurar ou testar tempo, injete
`TemporalGestureFilter(TemporalConfig(...), clock=seu_clock)` no parâmetro
`temporal` do controller; os tipos residem em `hgi.temporal`.

Demo finita sem webcam, depois de instalar o HGI:

```bash
python scripts/demo_cursor.py
```

Veja os contratos e limitações em [ARCHITECTURE.md](docs/ARCHITECTURE.md)
e [o plano com evidências TDD](docs/IMPLEMENTATION_PLAN.md).
O próximo passo é o aceite manual da própria Fase 8 com webcam e movimentos
pequenos, incluindo fail-safe e foco da janela. Nenhuma fase posterior foi iniciada.
