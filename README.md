# Processador de Despesas Contábeis

Aplicação web em Python/Streamlit para consolidação, classificação e análise de despesas contábeis, com geração de relatório ODS.

---

## Instalação

```bash
pip install -r requirements.txt
```

## Execução

```bash
streamlit run app.py
```

Acesse em: http://localhost:8501

---

## Como usar

### 1. Upload da planilha financeira
Formatos aceitos: **ODS, XLSX, XLS, CSV**

A planilha deve conter obrigatoriamente as colunas:
- `DESCRDEB` — descrição da conta contábil
- `VALPAGAMENTOTITULO` — valor do pagamento

Formatos de valor aceitos: `R$ 1.234,56` · `1234,56` · `1.234,56` · `1234.56`

### 2. Upload da base de classificação (opcional)
Formatos aceitos: **ODS, XLSX, XLS**

Se existir um arquivo `base_classificacao_atualizada.ods` na pasta do projeto, ele será carregado automaticamente. Se esse arquivo não existir, o upload manual de base fica disponível.

Colunas necessárias:
- `DESCRDEB`
- `TIPO DE CUSTO` → valores: `C.OPERACIONAL`, `NÃO OPERACIONAL`, `IGNORAR`

### 3. Informe o faturamento do período
Valor obrigatório, maior que zero.

### 4. Clique em "Processar Planilha"

### 5. Classifique as pendências (se houver)
Contas sem classificação na base serão apresentadas para classificação manual.
Você pode optar por salvar as novas classificações para uso futuro.

### 6. Faça o download do ODS gerado

---

## Regras de negócio

| Regra | Detalhe |
|---|---|
| Pré-filtro | `DEVOLUCAO DE VENDAS` e `MERCAD. EMITIDA P/ CONSERTO` são removidas antes de qualquer processamento |
| Correspondência | EXATA — sem normalização, sem fuzzy matching |
| Contas IGNORAR | Entram nos totais, sinalizadas em cinza itálico no ODS |
| Duplicata na base | Conta com tipos divergentes → PENDENTE + alerta |
| Reset de sessão | Novo upload limpa todas as classificações manuais anteriores |
| Base local | `base_classificacao_atualizada.ods` é usada automaticamente quando existir |
| Exportação | Valores monetários e percentuais são gravados como números, com máscara visual aplicada |

---

## Estrutura do projeto

```
app.py             # Interface Streamlit (dashboard)
processamento.py   # Lógica de negócio (leitura, consolidação, classificação, exportação)
requirements.txt   # Dependências
README.md          # Este arquivo
```
