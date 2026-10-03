# Preparação da release v0.1.0

Atualizado em 03/10/2026. Este documento prepara o aceite; não cria tag nem publica
release. A versão declarada é `0.1.0`. Evidências datadas ficam na
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

- [x] Smoke manual da Fase 11 reportado pelo usuário como funcional.
- [x] Licença MIT presente e coerente com README/metadados.
- [x] Versão `0.1.0` declarada no manifesto; wheel e testes revalidados.
- [x] `git diff --check` passa antes da organização dos commits.
- [ ] Tag `v0.1.0` e release **somente com autorização futura específica**.

## Teste manual final

O smoke manual mais recente foi reportado pelo usuário como funcional após a
Fase 11: novos gestos, drag por PINCH e ações de sistema operam no ambiente
local. Este documento não mantém mais uma tabela manual de FPS nem exige GIF de
demonstração para considerar o repositório apresentável.

Para uma nova máquina, repita os comandos do README em dry-run primeiro. Use
`--real-control` somente em sessão gráfica compatível, salve trabalhos abertos e
confirme que D, R, Q/Esc, Ctrl+C e o fail-safe físico são compreendidos antes de
habilitar a sessão com E. Wayland continua sem suporte para controle real.
