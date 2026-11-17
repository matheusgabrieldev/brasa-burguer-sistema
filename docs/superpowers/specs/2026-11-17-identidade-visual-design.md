# Identidade visual Brasa Burguer no sistema — design (curto)

**Por quê:** o sistema do portfólio é a cópia do sistema da Le Burguer com a marca trocada pela fictícia Brasa Burguer. O logo atual (selo redondo com hambúrguer clip-art) não parece marca de verdade.

**O que foi decidido (com o Matheus, 17/11/2026):**
- Logo tipográfico no padrão da Brasa Burguer do portfólio de design dele: "BRASA" em Dela Gothic One, "BURGUER" em Space Grotesk Bold espaçado entre dois traços, estalo de três traços acima do último A.
- Paleta da Le Burguer, não a vermelha: preto `#111111`, amarelo `#F2B705`, creme `#F6EAD7` (novo). Vermelho continua só para alerta.
- Sombra **vazada**: letra amarela com um vão preto e um contorno creme deslocado (não a sombra chapada da versão vermelha).
- Ícone: "B" com o mesmo tratamento. Em tamanho pequeno (favicon), "B" preto chapado num círculo amarelo, sem contorno.

**Abordagens consideradas:** (A) desenhar logos por código, rejeitada depois de três rodadas; (B) briefing + IA de imagem, abandonada; (C) **reaproveitar o padrão da marca que ele mesmo desenhou, recolorida**, escolhida.

**Escopo desta etapa:**
- Todos os lugares que usam `static/img/logo.png` mostram um círculo (40 a 124 px). Então `logo.png` vira o emblema redondo: fundo preto, "B" amarelo vazado e estalo.
- Novo `static/img/logo-horizontal.svg` (logo completo, letras convertidas em curvas), para uso futuro e para o manual.
- `favicon.png`, `icon-192.png` e `icon-512.png` novos.
- CSS: fonte Dela Gothic One auto-hospedada como `--display`, aplicada nos títulos (nome da loja, títulos de seção, título do hero e títulos da Área do Dono). Token `--creme`. Botões, preços e chips continuam como estão.

**Fora do escopo (próxima etapa):** mascote, estampa de fundo (`--fundo-estampa`), cartela de adesivos e página de manual da marca.

**Não pode:** copiar a versão vermelha do portfólio de design como está; usar vermelho na marca.
