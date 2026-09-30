# Arquitetura do HGI — estado após a Fase 3

O núcleo matemático usa somente a biblioteca padrão Python. O entrypoint identifica o
projeto e encerra. Geometria e smoothing não fazem I/O, não consultam relógio/FPS,
não obtêm dimensões reais e não importam bibliotecas de visão ou automação.
O adaptador de visão usa NumPy e importa MediaPipe somente ao construir o tracker.
O modelo interno de mão não depende dessas bibliotecas. Gestos e ações permanecem
propostos no [plano de implementação](IMPLEMENTATION_PLAN.md).

## API atual

| API | Contrato |
|---|---|
| `Point2D(x, y)` | Dataclass imutável de duas coordenadas finitas; aceita negativos |
| `Region2D(left, top, right, bottom)` | Dataclass imutável; limites inclusivos e spans positivos, finitos |
| `distance(first, second)` | Distância euclidiana via hypot, na unidade compartilhada pelos pontos |
| `normalized_distance(first, second, reference_distance)` | Distância dividida por referência positiva e finita na mesma unidade |
| `clamp(value, minimum, maximum)` | Intervalo inclusivo; bounds iguais são válidos; valores não finitos e bounds invertidos são rejeitados |
| `normalized_to_pixels(point, width, height)` | Clip 0..1, multiplicação por dimensão−1 e clamp final; sem arredondamento para inteiro |
| `pixels_to_normalized(point, width, height)` | Conversão inversa com clipping; um eixo de um pixel retorna 0 |
| `mirror_horizontal(point)` | Reflexão `1-x`, preservando Y; não aplica clipping por conta própria |
| `map_camera_to_screen(point, camera_region, screen_width, screen_height, *, mirror_x=False)` | Clip na área útil → normalização relativa → espelhamento opcional → pixels seguros |
| `ExponentialSmoother(alpha)` | EMA com alpha validado e somente o último ponto como estado |
| `smoother.update(point)` | Primeiro ponto passa intacto; seguintes são suavizados nos dois eixos |
| `smoother.reset()` | Descarta o estado; próxima entrada passa intacta |
| `smoother.alpha` | Propriedade somente leitura; `0 < alpha <= 1` |

Não há hierarquia de unidades: usar nomes como `camera_point`, `screen_point` e
`normalized_point` e converter explicitamente. Um ponto e sua região devem usar
a mesma unidade. Distância entre coordenadas normalizadas de um frame retangular
não equivale à distância em pixels; converter os dois eixos usando as dimensões
fornecidas antes de comparar distâncias físicas no plano da imagem.

## Bordas, margens e precisão

Largura/altura são inteiros positivos, excluindo booleanos. Na convenção atual,
`0.0 → 0` e `1.0 → dimensão−1`. Para 1920×1080, o centro é `(959.5, 539.5)`.
Isso mantém os pixels extremos dentro da resolução. O clamp também é aplicado
após multiplicar, para conter arredondamentos na borda. Um eixo de um pixel só
tem posição 0; sua inversa escolhe 0 como valor canônico. Clipping e eixos de um
pixel perdem informação, portanto não permitem um round-trip geral.

A região representa diretamente as margens. Por exemplo, para um frame numérico
640×480, `Region2D(64, 48, 575, 431)` define uma área interna. Seus cantos mapeiam
para os extremos da tela fornecida. O espelhamento ocorre **depois** de normalizar
essa região; inverter o frame inteiro e inverter novamente o ponto seria duplicar
o espelhamento. Essa coerência deverá ser validada na integração futura.

Não há arredondamento antecipado nem consulta ao monitor. A conversão em posições
inteiras do backend será responsabilidade do controlador futuro. Coordenadas não
finitas, regiões vazias e referências de distância não positivas geram ValueError;
resultados de distância além da capacidade dos floats também são rejeitados.
Os tipos documentados devem ser respeitados pelos chamadores.

## EMA

Após inicialização, a regra por eixo é:

```text
novo = (1 - alpha) * anterior + alpha * atual
```

É equivalente a `anterior + alpha * (atual - anterior)`, mas evita overflow na
subtração de valores grandes de sinais opostos. Eixos com entrada igual ao valor
anterior são preservados exatamente, evitando deriva por arredondamento.
Alpha baixo responde mais lentamente; alpha 1 acompanha a entrada sem atraso.
O fator é validado na construção, sem configuração global nem defaults dispersos.

Não há compensação temporal: a mesma sequência de pontos produz a mesma saída,
mas a resposta em segundos pode variar com a frequência de chamadas. Nenhuma
medição de FPS ou filtro adicional pertence a esta fase. Na integração futura,
resetar após perda/troca de tracking evita reaproveitar posições antigas.

## Verificação

Os testes usam somente pontos e dimensões sintéticos: distância, escalas, bordas,
clipping, margens, espelhamento, parâmetros inválidos, overflow e sequências EMA.
Os resultados e checkpoints RED/GREEN estão registrados no plano. Gestos e
controle real continuam sem implementação; hardware ainda não foi validado.

## Fronteira de visão

```mermaid
flowchart LR
    A[Array RGB uint8] --> B[HandTracker]
    B --> C[MediaPipe HandLandmarker IMAGE]
    C --> D[Conversão no adaptador]
    D --> E[tuple de DetectedHand do HGI]
```

`hand_tracker.py` é o único módulo de produção que conhece tipos MediaPipe.
`process(frame)` recebe `numpy.ndarray`, RGB, `uint8`, H×W×3, com eixos positivos.
Entradas inválidas geram TypeError/ValueError antes da inferência. Arrays strided
são tornados contíguos; RGB e entrada são preservados. Não se pode inferir RGB
versus BGR apenas por dtype/shape: a conversão pertence ao futuro módulo de captura.

`HandTracker(model_path, *, num_hands=1, min_hand_detection_confidence=0.5,
min_hand_presence_confidence=0.5)` configura CPU e **IMAGE** síncrono. Modelo
local obrigatório; detector criado uma vez e reutilizado. Veja [MODELS.md](MODELS.md).
A mudança da proposta VIDEO para IMAGE simplifica esta fase de um frame: não há
timestamps ou estado temporal. VIDEO/LIVE_STREAM poderão ser avaliados depois;
o IMAGE não usa o tracking temporal que reduz a latência nesses modos.

Retorno: `tuple[DetectedHand, ...]`, com `()` significando ausência normal de mão.
Não há identidade persistente ou garantia de ordem entre frames. Se houver
múltiplas categorias de handedness, o adaptador escolhe a de maior score disponível.
Handedness ausente permanece None. Não há confiança de detecção inventada.
Resultados malformados não são convertidos em ausência: são rejeitados.

| Tipo/API interna | Contrato |
|---|---|
| `HandLandmark` | IntEnum dos 21 índices oficiais, WRIST=0 até PINKY_TIP=20; INDEX_FINGER_TIP=8 |
| `NormalizedLandmark(x, y, z)` | Dataclass imutável; XYZ finitos; mantém a previsão sem clipping |
| `DetectedHand(landmarks, handedness=None, handedness_score=None)` | Tuple imutável com exatamente 21 pontos; lateralidade Left/Right opcional; score finito em 0..1 quando disponível |
| `HandTracker.process(frame)` | Converte todos os resultados para tipos HGI; nunca expõe objetos MediaPipe |
| `HandTracker.close()` / `with HandTracker(...)` | Fechamento explícito ou automático, inclusive sob exceção; close bem-sucedido é idempotente |

X/Y são normalizados pelas dimensões da imagem; Z é profundidade relativa ao
punho, aproximadamente na escala de X, **não metros**. Predições extrapoladas
fora de 0..1 são preservadas. `handedness_score` mede confiança de Left/Right,
não confiança por landmark. World landmarks e scores não expostos pela API não
são fabricados. Espelhamento deve ser coerente com a imagem processada; o tracker
não inverte coordenadas ou rótulos automaticamente.

Falhas de importação, criação, inferência e fechamento conhecidas geram
`HandTrackerError` com `__cause__` original. Erros inesperados propagam.
Um tracker fechado rejeita processamento e reentrada; um close que falhar pode
ser tentado novamente. Não há supressão de exceções no context manager, captura,
desenho, callbacks, gestos, smoothing no pipeline ou automação. O tracker não é
thread-safe; neste incremento deve ser usado sequencialmente.

Os testes substituem somente a fronteira MediaPipe, processando arrays sintéticos
e resultados externos falsos através da conversão real. O smoke com modelo real
é separado da suíte e não depende de webcam. Qualidade de tracking humano,
renderização e permissões de captura continuam exigindo teste manual futuro.
