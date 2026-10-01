# Preparação da release v0.1.0

Atualizado em 30/09/2026. Este documento prepara o aceite; não cria tag nem publica
release. A versão permanece `0.1.0.dev0`. Evidências datadas ficam na
[Fase 9 do plano](IMPLEMENTATION_PLAN.md#17-fase-9--polimento-e-preparação-para-portfólio).
Os itens marcados registram a verificação da Fase 9. Reexecute os checks se
mudar código, dependências, versão ou ambiente depois desse registro.

## Gates automatizados e documentação

- [x] Suíte completa passa: `python -m pytest -q`.
- [x] Cobertura verificada: `python -m pytest --cov=hgi --cov-report=term-missing`.
- [x] Ruff passa: `python -m ruff check .` e `python -m ruff format --check .`.
- [x] Compilação passa: `python -m compileall src`.
- [x] Wheel construída: `python -m pip wheel --no-deps --no-build-isolation --wheel-dir dist .`, com setuptools>=68 instalado.
- [x] Instalação limpa e `python -m hgi` verificados.
- [x] `python -m pip check` passa no ambiente da demo.
- [x] README, links e `python scripts/demo_webcam.py --help` revisados.
- [x] Origem, checksum e preparação do modelo documentados em MODELS.md.
- [x] Revisões Python, code review e segurança sem achados CRITICAL/HIGH.

## Gates manuais e decisão do autor

- [ ] Smoke dry-run com webcam aprovado e registrado.
- [ ] Smoke real DISABLED aprovado sem movimento/clique.
- [ ] Movimento e clique real aprovados nas etapas abaixo.
- [ ] FPS dry-run/real, latência, jitter e confiabilidade registrados.
- [ ] GIF real em `assets/demo.gif`, revisado e referenciado no README.
- [ ] Licença decidida pelo autor; LICENSE e metadados coerentes adicionados.
- [ ] Versão alterada para `0.1.0` após os gates; wheel e testes revalidados.
- [ ] `git diff --check` passa e `git status --short` está limpo.
- [ ] Tag `v0.1.0` pronta para criação **com autorização futura**.

## Teste manual final

Prepare o modelo conforme [MODELS.md](MODELS.md), use webcam acessível e uma
sessão gráfica compatível. Para controle real, salve trabalhos importantes,
evite botões destrutivos/terminais com comandos e mantenha a janela HGI acessível.
Conheça D, R, Q/Esc, Ctrl+C e o fail-safe físico antes de habilitar.

### A — Dry-run de regressão

Execute o comando dry-run do README, sem `--real-control`.

- [ ] Inicia DISABLED; imagem, landmarks e handedness aparecem.
- [ ] E habilita somente intenções virtuais; POINT acompanha o indicador.
- [ ] PINCH produz um CLICK visual e incrementa o contador uma vez.
- [ ] PINCH sustentado não repete; abertura confirmada rearma.
- [ ] D desabilita; R reseta, desabilita e limpa o contador.
- [ ] Perda de tracking suspende intenções; perda longa exige nova confirmação.
- [ ] Q/Esc, fechar janela e Ctrl+C liberam recursos em execuções separadas.
- [ ] Nenhuma ação real ocorre.

### B — Real control ainda DISABLED

Execute o comando com `--real-control`, **sem pressionar E**.

- [ ] Overlay mostra REAL CONTROL e CONTROL DISABLED.
- [ ] POINT/PINCH são observáveis sem mover mouse ou clicar.

### C — Movimento real

Pressione E; teste somente POINT primeiro, com movimentos pequenos.

- [ ] Direita/esquerda/cima/baixo da mão correspondem ao cursor.
- [ ] D interrompe novos comandos imediatamente após ser lido.
- [ ] R reseta e desabilita sem emitir movimento ou clique adicional.
- [ ] Fail-safe físico desabilita e encerra, preservando a causa do erro.
  Reinicie para a próxima etapa; não desative FAILSAFE para completar o teste.

### D — Clique único

Reative com E, posicione numa área inofensiva e abra a pinça para armar.

- [ ] Um PINCH confirmado gera um CLICK visual e um clique real.
- [ ] Manter PINCH fechado não produz outros cliques.
- [ ] Abrir, aguardar confirmação/cooldown e fechar produz um segundo clique único.
- [ ] D interrompe; Q/Esc encerra e libera recursos.
- [ ] Foco da janela e alternativa Ctrl+C foram compreendidos.

Registre resultados e limitações, incluindo FPS dos dois modos.
Não marque os gates de hardware como PASS usando testes
sintéticos. Wayland não é aceito pelo backend real atual; use dry-run.
