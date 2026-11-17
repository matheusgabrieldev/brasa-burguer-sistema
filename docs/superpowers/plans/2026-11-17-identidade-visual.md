# Identidade visual Brasa Burguer — plano de implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** trocar logo, favicon, ícones e fonte de títulos do sistema pela nova marca Brasa Burguer (preto/amarelo/creme, sombra vazada).

**Architecture:** os arquivos de imagem são gerados por um script Python (`docs/marca/gerar_marca.py`, Pillow + fontTools) a partir das fontes TTF, para serem reproduzíveis. O CSS ganha a fonte Dela Gothic One auto-hospedada (woff2, igual às outras) e o token `--creme`.

**Tech Stack:** Python 3.13, Pillow, fontTools, Django static, CSS.

**Spec:** `docs/superpowers/specs/2026-11-17-identidade-visual-design.md`

## Global Constraints
- Cores: preto `#111111`, amarelo `#F2B705`, creme `#F6EAD7`. Sem vermelho na marca.
- Fontes: Dela Gothic One (logo e títulos), Space Grotesk Bold (BURGUER).
- Sombra vazada: letra amarela, vão preto, contorno creme deslocado para baixo/direita.
- Favicon e ícones pequenos: "B" preto chapado em círculo amarelo, sem contorno.

## Review Focus
- Ícone em 40 px (topo do site) precisa ser legível: conferir no navegador.
- Fonte Dela Gothic One tem só peso 400: títulos com `font-weight: 800` gerariam negrito falso. Zerar para 400.
- `.loja-nome` com nome longo da loja em Dela (mais larga) não pode estourar no celular (375 px).
- Cache do navegador/WhiteNoise: os nomes de arquivo continuam os mesmos; `collectstatic` com manifest resolve em produção.

---

### Task 1: Gerar os arquivos da marca
**Files:** Create `docs/marca/gerar_marca.py`, `docs/marca/fontes/*.ttf`; Modify `static/img/logo.png`, `favicon.png`, `icon-192.png`, `icon-512.png`; Create `static/img/logo-horizontal.svg`, `static/fonts/dela-gothic-one-latin-400-normal.woff2`.
- [ ] Baixar Dela Gothic One e Space Grotesk (TTF, Google Fonts) e o woff2 da Dela (fontsource).
- [ ] Script gera: `logo.png` 512 px (círculo preto, B vazado, estalo), `icon-512/192.png` (mesmo emblema, fundo preto quadrado para o app), `favicon.png` 64 px (B preto no círculo amarelo), `logo-horizontal.svg` (letras em curvas).
- [ ] Conferir as imagens visualmente.

### Task 2: Fonte e cores no CSS
**Files:** Modify `static/css/base.css:3-33`, `static/css/cliente.css:231-232`, `static/css/gerenciar.css:15,24,28`; Test `config/tests/test_marca.py`.
- [ ] Teste `test_marca.py`: `base.css` declara `@font-face` "Dela Gothic One" apontando para um woff2 que existe; `--display` começa com "Dela Gothic One"; `--creme: #F6EAD7`; os arquivos de imagem de Task 1 existem.
- [ ] Rodar: falha.
- [ ] `--display: "Dela Gothic One", ...`; `--creme`; `.loja-nome, .secao h2` com `font-family: var(--display); font-weight: 400`; títulos da Área do Dono com `var(--display)`.
- [ ] Rodar `python -m pytest`: tudo passa.

### Task 3: Conferir e entregar
- [ ] Subir o servidor, abrir cardápio (desktop e 375 px) e Área do Dono, ver logo, favicon e títulos.
- [ ] Commit e push.
