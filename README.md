# Análise de Despesas por Conta Contábil

Aplicação web em Python/Streamlit para consultar despesas e faturamento no DB2, consolidar valores por conta contábil, classificar custos operacionais e gerar relatórios ODS.

O acesso ao painel é validado preferencialmente via authentik/OIDC. O login legado com credenciais CISSPoder via INTEGRIM permanece disponível por configuração, e o cliente INTEGRIM continua preservado para eventual integração técnica futura com serviços CISS.

---

## Instalação

Pré-requisito: Python 3.10 ou superior.

```bash
pip install -r requirements.txt
```

## Configuração

Crie um arquivo `.env` na pasta do projeto ou exporte as variáveis no ambiente.

### Autenticação recomendada: authentik/OIDC

Configure no authentik uma Application/Provider OAuth2/OIDC:

- Application Name: `Analise Contas Contabeis`
- Slug: `contascontabeis`
- Provider: `contascontabeis`
- Policy engine mode: `ANY`
- Redirect URI local: `http://localhost:8501`
- Scopes: `openid profile email`

Discovery endpoint esperado:

```text
https://auth.lojaototal.com.br/application/o/contascontabeis/.well-known/openid-configuration
```

Variáveis:

```env
AUTH_PROVIDER=authentik
AUTHENTIK_BASE_URL=https://auth.lojaototal.com.br
AUTHENTIK_PROVIDER_SLUG=contascontabeis
AUTHENTIK_CLIENT_ID=seu_client_id_authentik
AUTHENTIK_CLIENT_SECRET=seu_client_secret_authentik
AUTHENTIK_REDIRECT_URI=http://localhost:8501
AUTHENTIK_SCOPES=openid profile email
AUTHENTIK_STATE_TTL_SECONDS=600
REQUEST_TIMEOUT_SECONDS=15
```

Em produção, `AUTHENTIK_REDIRECT_URI` deve ser exatamente igual à Redirect URI cadastrada no authentik para o endereço público do painel.

Se o usuário já estiver autenticado no authentik no mesmo navegador, o login pode voltar direto para o painel sem pedir senha novamente. Esse é o comportamento esperado de SSO.

### Modo legado: INTEGRIM / CISSPoder

Use este modo apenas se precisar voltar temporariamente ao login antigo:

```env
AUTH_PROVIDER=integrim
```

Variáveis do INTEGRIM:

```env
CIM_HOST=https://servidor-cim
CISS_CLIENT_ID=seu_client_id
CISS_CLIENT_SECRET=seu_client_secret
REQUEST_TIMEOUT_SECONDS=15
```

### DB2

Use uma URL SQLAlchemy pronta:

```env
DB2_SQLALCHEMY_URL=ibm_db_sa://usuario:senha@host:50000/database
```

Ou informe os componentes separadamente:

```env
DB2_USER=usuario
DB2_PASSWORD=senha
DB2_HOST=host
DB2_PORT=50000
DB2_DATABASE=database
```

## Execução

```bash
streamlit run app.py
```

Acesse em: http://localhost:8501

Também existe o atalho:

```bash
./inicia.sh
```

---

## Como usar

### 1. Faça login

No modo recomendado, clique em **Entrar com authentik**. O app redireciona para o authentik, valida o retorno OIDC e mantém os tokens apenas na sessão do Streamlit.

Se `AUTH_PROVIDER=integrim`, o app volta ao formulário legado de usuário e senha CISSPoder, autenticando diretamente no INTEGRIM.

### 2. Selecione filtros da consulta

Na barra lateral, informe:

- data inicial;
- data final;
- uma ou mais empresas, com IDs de 1 a 20.

### 3. Clique em "Processar"

O app consulta no DB2:

- despesas pagas do período;
- faturamento bruto do período;
- cadastro de empresas selecionadas para validar se existem no banco.

Depois disso, normaliza as despesas, consolida por conta contábil, aplica a base de classificação e calcula os indicadores.

### 4. Revise pendências

Se houver contas sem classificação, elas aparecem na aba **Pendências de Classificação**. Classifique cada conta como:

- `C.OPERACIONAL`;
- `NÃO OPERACIONAL`.

Após salvar, o dashboard e os relatórios são recalculados.

### 5. Faça os downloads

O app pode gerar:

- ODS consolidado do período;
- ODS de pendências, quando houver contas pendentes;
- download da base oficial atual;
- base de classificação para revisão, quando novas classificações manuais forem salvas.

Observação: a exportação principal usa ODS. Se a biblioteca ODS não estiver disponível no ambiente, o módulo de processamento possui fallback interno para XLSX.

---

## Base de classificação

Se existir um arquivo `base_classificacao_atualizada.ods` na pasta do projeto, ele será carregado automaticamente.

Colunas necessárias:

- `DESCRDEB`;
- `TIPO DE CUSTO`.

Valores aceitos para `TIPO DE CUSTO`:

- `C.OPERACIONAL`;
- `NÃO OPERACIONAL`;
- `IGNORAR`.

Quando a base local não existe, todas as contas retornadas pela consulta ficam como **PENDENTE DE CLASSIFICAÇÃO** até revisão manual.

---

## Formatos suportados pelo módulo de processamento

O fluxo principal atual usa DB2, mas o módulo `processamento.py` ainda possui leitura de arquivos para reutilização interna ou manutenção.

Formatos aceitos:

- ODS;
- XLSX;
- XLS;
- CSV.

Colunas esperadas para despesas:

- `DESCRDEB`;
- `VALPAGAMENTOTITULO`.

Formatos de valor aceitos incluem `R$ 1.234,56`, `1234,56`, `1.234,56` e `1234.56`.

---

## Regras de negócio

| Regra | Detalhe |
|---|---|
| Pré-filtro | `DEVOLUCAO DE VENDAS` e `MERCAD. EMITIDA P/ CONSERTO` são removidas antes de qualquer processamento |
| Empresas | IDs válidos entre 1 e 20; o app também valida existência no cadastro do DB2 |
| Período | Data inicial e final são obrigatórias; a data inicial não pode ser maior que a final |
| Salários | Contas de salários configuradas no código são agrupadas em `SALÁRIOS` |
| Correspondência | Exata, sem normalização e sem fuzzy matching |
| Contas `IGNORAR` | Entram nos totais, sinalizadas em cinza itálico no ODS |
| Duplicata na base | Conta com tipos divergentes vira `PENDENTE DE CLASSIFICAÇÃO` |
| Reset de sessão | Troca de empresas ou período limpa resultados e classificações manuais anteriores |
| Base local | `base_classificacao_atualizada.ods` é usada automaticamente quando existir |
| Pendências | Classificação manual é deduplicada por conta |
| Exportação | Valores monetários e percentuais são gravados como números, com máscara visual aplicada |

---

## Estrutura do projeto

```text
app.py                         # Interface Streamlit, login, filtros, dashboard e downloads
authentik_client.py            # Autenticação de usuário via authentik/OIDC
db.py                          # Conexão e consultas DB2
integrim_client.py             # Login legado e consumo técnico de serviços INTEGRIM
processamento.py               # Lógica de negócio, classificação e exportação
base_classificacao_atualizada.ods # Base local oficial de classificação
inicia.sh                      # Atalho para ativar venv e iniciar o Streamlit
salvar_github.sh               # Atalho para adicionar, commitar e enviar alterações ao GitHub
requirements.txt               # Dependências Python
README.md                      # Documentação do projeto
spec-auth-authentik-prompt.md  # Especificação local ignorada pelo Git
```
