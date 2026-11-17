# Preparação da publicação e transporte

Estado em 10/11/2026: os comandos locais de fotos foram implementados e testados com Storage em memória. Nenhum serviço foi contratado ou provisionado e nenhum banco foi exportado por esta etapa. A publicação permanece pendente de infraestrutura, configuração e ensaio.

## Armazenamento de fotos

Proposta para avaliação: armazenamento de objetos compatível com S3, separado do processo de deploy. Provedor, região, custos, endpoint, bucket, domínio HTTPS e política de retenção ainda precisam ser confirmados por Matheus. A configuração S3 e as dependências de produção não fazem parte desta entrega dos comandos. Não considerar o Storage remoto operacional antes de testar a integração com o provedor escolhido.

As fotos públicas precisam manter as chaves `produtos/...` e URLs HTTPS estáveis. A aplicação deve receber credenciais restritas ao prefixo de fotos, para consultar, ler e gravar objetos; a remoção só é necessária para as operações de edição/exclusão já oferecidas pelo sistema. Nunca permitir escrita ou listagem públicas. Liberar leitura pública de objetos apenas conforme a política do provedor; se houver CDN, configurar a origem privada conforme sua documentação. Configurar o backend para **não sobrescrever objetos existentes** (`file_overwrite=False` no backend S3) e confirmar isso em ensaio. Não salvar credenciais, URLs assinadas ou conteúdo do banco no Git ou em logs.

O importador usa `default_storage`, sem depender de `Storage.path()` ou de `MEDIA_ROOT` para o destino. Downloads são lidos em blocos de 64 KiB, com buffer temporário limitado a 1 MiB em memória antes de usar disco temporário. Fotos já associadas a um produto são preservadas; se o backend renomear um novo arquivo, o nome realmente devolvido é salvo no produto. Falhas mantêm a URL externa de fallback.

## Inventário e pacote operacional

Conferência local somente de contagens em 10/11/2026: **68 nomes de imagem distintos referenciados no banco; 68 arquivos em `media/produtos`; nenhuma referência sem arquivo local; nenhum produto com foto exclusivamente externa**. Isso não substitui uma nova conferência imediatamente antes do transporte. Não foi executado download remoto nesta etapa.

Guardar fora do Git uma cópia independente de `media/produtos`, o manifesto, o arquivo de dados necessário à estratégia escolhida e `../dados/cardapio-2026-11-05.json` (que fica fora deste repositório). Verificar se todas as fotos necessárias estão locais antes de 17/12/2026, quando termina o acesso informado ao OlaClick. Não excluir fotos locais depois do envio; guardar a cópia para restauração.

Antes de transferir, interromper edições de fotos e mudanças de referências no banco durante a janela de cópia. Usar uma cópia da pasta como origem, conferir nomes/arquivos e validar o destino configurado. O comando consulta os nomes de `Produto.imagem` do banco selecionado; copia somente os arquivos referenciados, sem alterar o banco. O backup completo da pasta deve preservar também arquivos não referenciados para revisão posterior.

```powershell
python manage.py transferir_fotos --origem 'CAMINHO_FORA_DO_GIT/media' --manifesto 'CAMINHO_FORA_DO_GIT/fotos-manifesto.json'
```

`--origem` é a pasta que contém `produtos/`. `--manifesto` é **saída na primeira execução e entrada de conferência nas retomadas**. A primeira execução examina todas as origens e registra `arquivos`, cada um com `nome`, `tamanho` em bytes e `sha256`. O manifesto contém apenas metadados, sem credenciais, e descreve o conjunto esperado; **não é recibo de conclusão nem marca progresso**.

Toda retomada compara as referências atuais do banco e os hashes locais com o manifesto. Se houve mudança, o comando recusa: revisar a alteração e preparar um novo manifesto em outro caminho após decidir qual conjunto será transportado. Um manifesto incompleto ou inválido após interrupção também exige revisão; não editar hashes para forçar sucesso. O comando recusa backends que declaram `file_overwrite=True` antes de criar o manifesto ou enviar fotos. Isso não certifica um backend arbitrário: antes do uso remoto, verificar a política real de criação sem sobrescrita e testar uma corrida entre existência e gravação no provedor escolhido. O padrão S3 com sobrescrita habilitada não é adequado para esse transporte.

No destino, um objeto com o mesmo tamanho e SHA-256 é conferido e pulado. Um objeto diferente causa erro sem sobrescrita. Cada arquivo novo é enviado em blocos e relido para conferir tamanho e SHA-256. Arquivo ausente, conflito, renomeação do backend ou falha de verificação encerram o comando com erro. Cópias anteriores podem já ter sido concluídas: executar novamente com a mesma origem e manifesto permite retomá-las. Se o backend renomear um arquivo durante uma corrida, o comando recusa declarar sucesso e deixa o objeto para revisão manual; não apaga objetos automaticamente. Não executar cópias concorrentes para o mesmo conjunto.

Somente a saída final `Fotos verificadas: ...` com código de saída zero confirma que o conjunto inteiro foi conferido nessa execução. Depois do envio, conferir também as URLs HTTPS produzidas pelo backend, a exibição no cardápio e a permanência dos mesmos objetos após redeploy.

## Escolha e transporte do banco

Primeiro decidir com a loja se o banco local contém dados reais ou demonstração. Há dois caminhos: transportar a base existente preservando usuários, grupos e todos os modelos de negócio, ou iniciar uma base vazia pelo JSON do cardápio. Não reimportar o JSON por cima de edições já migradas.

Para uma base nova pelo JSON, fornecer o caminho explicitamente e somente após preparar o ambiente e confirmar a estratégia:

```powershell
python manage.py importar_cardapio 'CAMINHO_FORA_DO_GIT/cardapio-2026-11-05.json'
```

`--baixar-fotos` pode ser acrescentado quando houver fotos exclusivamente externas e a operação estiver autorizada. Não depende de pasta local de destino: grava no `default_storage` configurado. Não substituir nomes de imagens ou URLs de fallback manualmente para apontar ao bucket.

Para transportar a base existente, tirar snapshot anterior e escolher arquivos protegidos fora do Git. O comando abaixo é documentação; não foi executado nesta etapa:

```powershell
python manage.py dumpdata --natural-foreign --natural-primary --exclude contenttypes --exclude auth.permission --exclude sessions.session --output 'CAMINHO_FORA_DO_GIT/banco.json'
```

Tratar o arquivo como dado privado: acesso restrito, armazenamento protegido e retenção acordada. No PostgreSQL de ensaio vazio, executar `migrate --noinput` antes de `loaddata 'CAMINHO_FORA_DO_GIT/banco.json'`. Fazer a carga de maneira controlada, sem servir tráfego durante a restauração; em erro, restaurar o snapshot ou recriar o banco de ensaio em vez de continuar sobre uma carga parcial. Não excluir usuários/grupos nem modelos de negócio da exportação; o dump já exclui sessões e permissões geradas pelas migrations.

Depois da carga, conferir contagens e valores de produtos, grupos, opções, bairros, configurações, usuários/grupos, clientes, pedidos e contador diário. Gerar o SQL de reset das sequences dos apps importados e executá-lo no PostgreSQL de destino antes de aceitar novas gravações:

```powershell
python manage.py sqlsequencereset auth loja cardapio clientes pedidos > 'CAMINHO_FORA_DO_GIT/sequences.sql'
```

Usar o cliente PostgreSQL do ambiente para executar esse SQL; confirmar antes a lista de apps/modelos efetivamente importados. Verificar a próxima criação de usuário/produto e um pedido identificado de ensaio: IDs sem colisão, numeração diária correta, totais e referências preservados. Restaurar também as fotos com o manifesto e conferir todas as chaves referenciadas.

## Verificações ainda pendentes

- Escolher e contratar infraestrutura, confirmar custos, permissões mínimas e políticas reais do provedor.
- Instalar/fixar dependências e configurar backend S3, variáveis e credenciais no ambiente de ensaio.
- Executar envio real, conferir URLs HTTPS persistentes e preservação após redeploy.
- Ensaiar migração/restauração em PostgreSQL e armazenamento separados, incluindo sequences e próximo pedido.
- Confirmar backup diário, retenção e restauração documentada, com cópia independente das fotos e manifesto.
- Executar verificações Linux/deploy e aceite de DNS/HTTPS e fluxo completo no domínio final.

Os testes com Storage em memória verificam o contrato dos comandos; não comprovam acesso, consistência, políticas ou disponibilidade de um serviço remoto.
