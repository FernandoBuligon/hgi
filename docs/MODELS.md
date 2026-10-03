# Modelo do HandTracker

Revisado em 30/09/2026. Requer instalação do extra `vision`, conforme
[README.md](../README.md#instalação), antes do smoke abaixo.

O `HandLandmarker` exige o bundle compatível contendo detector de palma e modelo
de landmarks. HGI recebe um caminho local explícito; não procura, baixa ou atualiza
modelos durante a execução. Sem arquivo, o construtor gera `FileNotFoundError`.
Um arquivo incompatível gera `HandTrackerError`, preservando a causa do MediaPipe.
Separar a preparação da execução torna a versão e o acesso à rede explícitos,
permite conferir o checksum e evita downloads inesperados durante a demo.

## Preparação explícita

Fonte: [modelos oficiais do Hand Landmarker](https://developers.google.cn/edge/mediapipe/solutions/vision/hand_landmarker#models).
Foi validado o bundle **float16, versão 1**, com MediaPipe **1.0.1**, modo IMAGE e CPU.
Use a URL versionada abaixo, evitando o alias mutável `latest`.

```bash
mkdir -p models
curl --fail --location --max-time 60 \
  --output models/hand_landmarker.task \
  https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task
sha256sum models/hand_landmarker.task
```

O comando cria o diretório e baixa somente o bundle. No Windows, crie `models`
e use a mesma URL no navegador ou `curl.exe`; confira com `Get-FileHash` abaixo.

O bundle validado tem **7.819.105 bytes** e SHA-256:

```text
fbc2a30080c3c557093b5ddfc334698132eb341044ccee322ccf8bcf3607cde1
```

Esse checksum foi calculado sobre o download observado, não é uma assinatura do
fornecedor. Compare antes de usar; uma divergência deve ser investigada, não aceita
como atualização automática. No PowerShell: `Get-FileHash -Algorithm SHA256 models/hand_landmarker.task`.
Não coloque o arquivo no Git: `*.task` está no `.gitignore`, inclusive em
subdiretórios e caminhos alternativos dentro do repositório.
Um caminho fora do repositório também é aceito.

A [model card vinculada pelo guia oficial](https://storage.googleapis.com/mediapipe-assets/Model%20Card%20Hand%20Tracking%20%28Lite_Full%29%20with%20Fairness%20Oct%202021.pdf)
informa **Apache License 2.0** para os modelos descritos. Preserve a atribuição e
consulte os termos da fonte ao redistribuir; o binário não integra o repositório HGI.

## Smoke test sem hardware, separado de pytest

Após preparar o modelo, execute na raiz do repositório:

```bash
python - <<'PY'
import numpy as np
from hgi.hand_tracker import HandTracker

with HandTracker("models/hand_landmarker.task") as tracker:
    for shape in ((240, 320, 3), (120, 160, 3)):
        hands = tracker.process(np.zeros(shape, dtype=np.uint8))
        assert hands == (), hands
        print(shape, "hands:", len(hands))
print("Tracker fechado")
PY
```

Esse comando usa o detector real. Não roda no pytest padrão, não abre câmera,
não acessa display e não grava imagens. O modelo fica em memória no detector
reutilizado; a preparação é a única etapa do HGI que requer rede.

Na sessão da Fase 3, o mesmo teste passou usando o modelo em `/tmp`.
O backend emitiu avisos de feedback tensors e `NORM_RECT`/projeção, sem impedir
a execução. Isso confirma inicialização, inferência sem mão e fechamento,
**não** confirma landmarks de uma mão real ou sua estabilidade.

Captura, conversão BGR→RGB e overlay já estão implementados. Execute a demo
documentada no README depois de preparar o bundle; a sessão inicia DISABLED e
em dry-run. HGI não salva nem transmite frames. A Fase 10 mediu captura/inferência
em hardware acessível fora do sandbox; metodologia e limitações em
[PERFORMANCE.md](PERFORMANCE.md). O smoke manual da Fase 11 foi reportado pelo
usuário como funcional.

O [aviso de privacidade do MediaPipe 1.0.1](https://pypi.org/project/mediapipe/1.0.1/)
informa processamento local dos dados de entrada e coleta de métricas de uso e
desempenho pela biblioteca. HGI não implementa envio de frames nem telemetria própria;
isso não equivale a garantir ausência de tráfego da dependência nativa.
