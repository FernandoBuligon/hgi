# HGI — Hand Gesture Interface

Projeto local de visão computacional para interpretar gestos da mão.
**Fase concluída: adaptador HandTracker / MediaPipe.** O comando abaixo apenas
identifica o projeto. O tracker processa frames RGB fornecidos pelo chamador;
captura de webcam, gestos e controle do mouse ainda não estão integrados.

Requer Python **3.11 ou superior**. O bootstrap usa somente a biblioteca padrão.
Os módulos matemáticos também usam apenas Python, com dimensões fornecidas pelo chamador.
O extra `vision` declara MediaPipe 1.0.1 e NumPy; o ambiente validado usa Python 3.11.16.

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

O ambiente inspecionado contém `opencv-python` e `opencv-contrib-python`, ambos
5.0.0.93, sem variantes headless. Os dois compartilham `cv2`; o MediaPipe 1.0.1
instalado requer a variante contrib. Nenhum pacote foi removido. Resolver a
sobreposição em uma manutenção posterior: ela não bloqueou a inferência IMAGE
desta fase. Preferir somente contrib, requerido pelo MediaPipe, reparando seus
arquivos após a remoção da outra distribuição. Nenhuma alteração foi realizada.
`pip check` não detecta sobreposição de arquivos; o bootstrap continua sem imports de visão.

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
automaticamente pelo formato. Não há loop de webcam nem teste real de mão nesta sessão.

Veja [os contratos e a arquitetura](docs/ARCHITECTURE.md) e
[o plano com evidências TDD](docs/IMPLEMENTATION_PLAN.md). A Fase 4 não foi iniciada.
