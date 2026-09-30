# HGI — Hand Gesture Interface

Projeto local de visão computacional para interpretar gestos da mão.
**Fase concluída: geometria e smoothing.** O comando abaixo apenas identifica o projeto;
webcam, detecção, gestos e controle do mouse serão implementados nas próximas fases.

Requer Python **3.11 ou superior**. O bootstrap usa somente a biblioteca padrão.
Os módulos matemáticos também usam apenas Python, com dimensões fornecidas pelo chamador.

## Instalação e execução

Em um ambiente virtual novo, na raiz do repositório:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
python -m hgi
```

No Windows, ative com `.venv\Scripts\Activate.ps1` no PowerShell.
O comando imprime `HGI — Hand Gesture Interface` e encerra.

Se pytest, pytest-cov, Ruff e setuptools já estiverem disponíveis no ambiente
(como no Conda `hgi` inspecionado), registre somente este projeto, sem downloads
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
sobreposição antes da integração de visão; o bootstrap não importa essas bibliotecas.

## Matemática disponível

`hgi.geometry` contém pontos/regiões tipados, distância, clamp, conversões,
espelhamento e mapeamento de uma área útil para dimensões de tela fornecidas.
`hgi.smoothing.ExponentialSmoother(alpha)` aplica EMA em X/Y e permite reset.

Nas conversões, `0.0` corresponde ao primeiro pixel e `1.0` ao último (`dimensão - 1`).
O centro de 1920×1080 é `(959.5, 539.5)`; coordenadas fracionárias são preservadas.

Veja [os contratos matemáticos](docs/ARCHITECTURE.md) e
[o plano com evidências TDD](docs/IMPLEMENTATION_PLAN.md). A Fase 3 não foi iniciada.
