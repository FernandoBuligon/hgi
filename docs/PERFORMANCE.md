# Performance e GPU — Fase 10

Medições de 30/09/2026. Defaults preservados: **IMAGE, CPU, dry-run, DISABLED**.
Não foram alterados gestos, thresholds, EMA, debounce, cooldown, PyAutoGUI.PAUSE,
fail-safe, modelo, dependências ou drivers.

## Ambiente e API

| Item | Observação |
|---|---|
| Python | 3.11.16, Conda `hgi` |
| Sistema | Linux Mint 22.1, base Ubuntu noble; kernel 6.8.0-90-generic, x86_64 |
| Sessão | X11, DISPLAY=:0, sem WAYLAND_DISPLAY |
| CPU | Intel Core i5-14600K, 20 CPUs lógicas disponíveis |
| GPU | NVIDIA GeForce RTX 5060, 8151 MiB; driver 580.126.09 |
| MediaPipe | 1.0.1 |
| OpenCV | contrib 5.0.0.93; `cv2.__version__` 5.0.0 |
| NumPy / PyAutoGUI | 2.4.6 / 0.9.54 |
| Webcam | video0/1/2 acessíveis fora do sandbox; ensaios em camera 1, 640×480 |
| FPS do driver | 25, consultado no último ensaio CPU/LIVE_STREAM; não é throughput |
| Modelo | Bundle float16 v1 e SHA-256 de [MODELS.md](MODELS.md) |

O sandbox inicialmente ocultou dispositivos. Consulta NVIDIA e ensaios de
hardware exigiram execução autorizada fora dele. Nenhuma imagem foi salva.

Assinaturas/enums locais confirmaram IMAGE/VIDEO/LIVE_STREAM e CPU/GPU,
`detect(image)`, `detect_for_video(image, timestamp_ms)` e
`detect_async(image, timestamp_ms)`. Options expõe confidences de detecção,
presença/tracking, num_hands e callback. BaseOptions local informa suporte GPU
limitado a Ubuntu; a presença do enum não garante funcionamento em outro sistema.

O [guia oficial Python](https://developers.google.com/edge/mediapipe/solutions/vision/hand_landmarker/python)
descreve tracking em VIDEO/LIVE_STREAM, timestamps em ms e descarte quando async
está ocupado, compatíveis com a API instalada. Porém, AsyncResultDispatcher do
1.0.1 apenas loga certos erros nativos, sem entregá-los ao callback do usuário.
HGI propaga seus erros de adaptação e detecta falta de callback por timeout;
não intercepta internals da biblioteca.

## Metodologia reproduzível

Modelo reutilizado, 10 frames de warmup, 15 s medidos com perf_counter.
Imports/inicialização/warmup ficam fora dos tempos. O benchmark não abre janela,
não constrói sink e não possui flag de controle real.

```bash
python scripts/benchmark_hand_tracker.py --model models/hand_landmarker.task \
  --camera 1 --delegate cpu --running-mode image --duration 15 --json
python scripts/benchmark_hand_tracker.py --model models/hand_landmarker.task \
  --camera 1 --delegate cpu --running-mode video --duration 15 --json
python scripts/benchmark_hand_tracker.py --model models/hand_landmarker.task \
  --camera 1 --delegate cpu --running-mode live-stream --duration 15 --json
```

Repita com gpu. Sem --camera, reutiliza frame preto pré-carregado; --image aceita
imagem local carregada uma vez, com dimensões preservadas. Nenhum download ocorre.
Para comparar, mantenha mão, resolução, iluminação e outras cargas constantes;
não rode ensaios concorrentes, repita e observe frames_with_hands.

- captured/processed: leituras e conclusões bem-sucedidas do ensaio serial.
- capture_fps/inference_fps: contagens/tempo total. Coincidem neste script serial;
  fonte estática mede alimentação, não FPS de uma webcam.
- mean_inference_ms: chamada/adaptação do tracker. Async espera cada callback
  com polling de 1 ms, incluindo esse overhead e scheduling; não é tempo exclusivo
  de kernels GPU. A demo, por sua vez, permite render durante inferência.
- mean_latency_ms: leitura→resultado convertido; exclui exposição/buffers
  anteriores do driver, janela e mouse físico. Não é latência ponta a ponta.
- min_frame_fps: inverso da maior duração leitura→resultado, aproximação do pior
  frame; p95 usa nearest rank. render_fps é null: janela não foi medida.

## Baseline anterior à migração

O relato inicial era ~12 FPS. O tracker IMAGE original mediu camera 1:
188 frames/15,078 s = **12,47 FPS**, captura 71,979 ms, conversão 0,113 ms,
inferência 8,103 ms, latência aproximada 80,195 ms, p95 12,079 ms e pior frame
~6,42 FPS. Essa primeira versão ainda não contava frames com mão.

Frame preto 640×480: 1847 frames/15,008 s, **123,07 FPS**, inferência 8,082 ms.
Sem mão não se comprova tracking ou gestos. O gargalo demonstrado com webcam
foi captura (~90% do tempo), não conversão/overlay.

## Matriz medida com webcam

Camera 1, 640×480, 15 s; **zero frames com mão** em todas as linhas abaixo.
Capturados = processados. A cena não teve controle humano rigoroso; pequenas
diferenças não comprovam ganho causal. Todos os números são medidos.

| Delegate | Mode | Frames | Inference FPS | Inferência média | Captura média | Latência aproximada | P95 inferência | Pior frame FPS |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| CPU | IMAGE | 187 | 12,46 | 7,929 ms | 72,183 ms | 80,228 ms | 9,670 ms | 6,25 |
| CPU | VIDEO | 188 | 12,47 | 8,247 ms | 71,824 ms | 80,187 ms | 11,676 ms | 6,26 |
| CPU | LIVE_STREAM | 189 | 12,53 | 8,485 ms | 71,234 ms | 79,826 ms | 11,920 ms | 11,02 |
| GPU | IMAGE | 189 | 12,53 | 7,938 ms | 71,714 ms | 79,773 ms | 9,316 ms | 11,74 |
| GPU | VIDEO | 185 | 12,33 | 8,010 ms | 72,979 ms | 81,098 ms | 9,397 ms | 6,20 |
| GPU | LIVE_STREAM | 189 | 12,54 | 4,990 ms | 74,555 ms | 79,754 ms | 9,802 ms | 11,28 |

Exploratório anterior CPU/LIVE_STREAM: 312 frames/15,023 s, **20,77 FPS**, 267
frames com mão; captura 39,098 ms, inferência 8,935 ms, latência 48,144 ms.
A cena mudou: a queda da captura impede atribuir o ganho somente ao modo.
Iluminação/exposição/driver são hipóteses para investigar, não causas confirmadas.

## Fonte fixa sintética, sem mão

| Delegate | Mode | Duração | Frames | FPS | Inferência média | Notas |
|---|---|---:|---:|---:|---:|---|
| CPU | IMAGE | 15 s | 1847 | 123,07 | 8,082 ms | Baseline original |
| CPU | VIDEO | 15 s | 1854 | 123,59 | 8,046 ms | Não demonstra tracking sem mão |
| CPU | LIVE_STREAM | 15 s | 1665 | 110,99 | 8,954 ms | Serial, inclui polling |
| GPU | IMAGE | | | | | Não medido com fonte fixa |
| GPU | VIDEO | 3 s | 294 | 97,66 | 10,200 ms | Probe inicial de duração diferente |
| GPU | LIVE_STREAM | 15 s | 1468 | 97,84 | 10,178 ms | Serial, inclui polling |

## GPU e profiling

EGL 1.5/OpenGL ES 3.2 inicializaram na RTX 5060; os três modos produziram
resultados sem mão e fecharam. **Não homologa landmarks humanos ou controle GPU.**
`tensor.cc:411` alertou sobre múltiplas escritas em Tensor e possível ausência
de sincronização nos três modos GPU, também no probe sintético. Sem exceção
Python, mas permanece limitação de correção nativa. CPU manteve os avisos
anteriores de feedback tensors/NORM_RECT. Não ocultamos avisos nem mudamos drivers.
Falha de criação GPU preserva a causa e indica --delegate cpu, sem fallback silencioso.

Perfil sintético IMAGE/CPU, dry-run DISABLED, 300 frames após 10 de warmup:
inferência 10,279 ms, conversão 0,065 ms, controller/observação 0,011 ms e
snapshot/desenho 0,248 ms. Sem janela/mão. O perfil ocorreu junto de um ensaio
GPU: não é comparação controlada de regressão da inferência. Desenho não se
mostrou gargalo; nenhuma otimização gráfica foi aplicada.

PipelineMetrics expõe estágios sem instrumentar o núcleo. Loop FPS inclui
captura, inferência, sink e trabalho anterior da janela. Inference FPS conta
resultados novos/recentes entregues numa janela de 1 s; redraws não contam.
Há uma captura/render por iteração, sem produtores independentes. Async reporta
submissão→callback; sync reporta duração de process().

Resultado antigo (>tracking grace, 150 ms), de outra resolução ou anterior ao
opt-in não autoriza ações. Stall completa o caminho de ausência do filtro
existente antes da retomada e exige abertura para rearmar. NONE pendente não
repete MOVE/CLICK nem EMA. Erro de adaptação chega ao owner; sem callback por 5 s
há erro claro. Não há lock durante detect_async/close ou backend de cursor.

**PyAutoGUI.PAUSE=0.1 preservada.** Não medimos FPS real-control nem movemos mouse
nesta fase. 100 ms/ação sugerem teto ~10 ações/s antes dos demais custos; é
estimativa matemática, não medição real. Anote inference_ms/FPS separadamente
de Loop FPS/controller_ms no aceite real; nenhuma alteração de PAUSE é default.
A pausa junto de captura lenta pode fazer amostras async ultrapassarem 150 ms
e serem rejeitadas. Validar esse comportamento antes de recomendar LIVE_STREAM
com mouse real; IMAGE/VIDEO continuam disponíveis.

Captura/close nativos podem bloquear; o timeout não mata drivers/threads.
D/R/Q/Esc dependem de foco/leitura entre frames; Ctrl+C continua disponível.
Termos/aviso de métricas da dependência estão em MODELS.md.

## Recomendação

Manter **IMAGE/CPU** como default por compatibilidade e pela ausência de ganho
comprovado na cena comparável. **VIDEO/CPU** é o próximo candidato para uso
interativo quando o usuário quiser menor custo temporal de tracking.
LIVE_STREAM permanece experimental/opt-in; GPU não é default diante dos avisos
nativos e da falta de ganho consistente no throughput medido.

Não há tabela manual versionada de FPS/latência por gesto. Os dados de
desempenho deste documento são os benchmarks reproduzíveis registrados durante
o desenvolvimento; novas medições manuais podem ser feitas sob demanda com o
script de benchmark, sem virar requisito de release.
