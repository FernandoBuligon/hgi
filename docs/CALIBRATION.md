# Registro de calibração exploratória

Atualizado em 30/09/2026. Preencha uma cópia desta tabela a cada sessão manual.
Não houve medição com webcam nesta sessão; campos vazios não significam aprovação.

| Ambiente e observação | Valor observado |
|---|---|
| Environment: SO, Python, X11/Wayland e commit | |
| Camera: dispositivo e índice | |
| Resolution: solicitada e efetivamente entregue | |
| Screen: lógica/detectada e override, se houver | |
| Lighting: iluminação e fundo | |
| FPS dry-run | |
| FPS real | |
| Latency: percepção e método de medição | |
| POINT stability: confirmação e interrupções | |
| PINCH reliability: clique único, falsos positivos e rearmamento | |
| Cursor jitter: mão parada e movimento lento | |
| pinch_ratio: aberto, fechado e situações de falso PINCH | |

## Parâmetros atuais

Consulte os construtores `CursorConfig` e `TemporalConfig`; esses ajustes não são
flags da CLI nem uma configuração persistente. `pinch_enter`/`pinch_exit` são
nomes deste registro para os thresholds do filtro temporal. A proporção real do
frame é passada automaticamente ao detector, sem calibrar thresholds.

| Parâmetro | Campo no código | Default | Valor usado | Observação / próximo valor sugerido |
|---|---|---|---|---|
| smoothing_alpha | CursorConfig.smoothing_alpha | 0.25 | | |
| pinch_enter | TemporalConfig.enter_pinch_threshold | 0.25 | | |
| pinch_exit | TemporalConfig.exit_pinch_threshold | 0.32 | | |
| stable_time | TemporalConfig.stabilization_seconds | 0.08 s | | |
| tracking_grace | TemporalConfig.tracking_grace_seconds | 0.15 s | | |
| click_cooldown | TemporalConfig.click_cooldown_seconds | 0.30 s | | |
| active_region | CursorConfig.active_region | 0.1–0.9 em X/Y | | |

## Procedimento

1. Comece em dry-run e mantenha câmera, resolução, iluminação e distância constantes.
2. Observe os defaults antes de editar. Registre valor atual, comportamento e
   valor sugerido; uma sugestão ainda não é validação.
3. Altere **somente um parâmetro por vez**, num ajuste local e reversível.
   Não reduza cooldown/limites apenas para produzir um clique na demo.
4. Repita POINT, PINCH sustentado, abertura/rearmamento e perda de tracking.
   Diferencie atraso do filtro, jitter de landmarks e custo do backend.
5. Compare resultados, justifique a mudança e execute testes antes de adotá-la.
   Preserve `pinch_enter < pinch_exit` e todos os mecanismos de segurança.

O FPS exibido mede o loop e não a latência isolada do modelo. A pausa do PyAutoGUI
continua ativa; não altere defaults globais para calibrar desempenho.
Teste controle real somente após o roteiro seguro de
[RELEASE_CHECKLIST.md](RELEASE_CHECKLIST.md#teste-manual-final).
