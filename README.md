# Processador de Despesas Contábeis

Aplicação web em Python/Streamlit para consolidação, classificação e análise de despesas contábeis, com processamento em lote e geração de relatórios ODS/ZIP.

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

### 1. Upload das planilhas financeiras
Formatos aceitos: **ODS, XLSX, XLS, CSV**

Cada planilha deve conter obrigatoriamente as colunas:
- `DESCRDEB` — descrição da conta contábil
- `VALPAGAMENTOTITULO` — valor do pagamento

Formatos de valor aceitos: `R$ 1.234,56` · `1234,56` · `1.234,56` · `1234.56`

Limite: até **20 planilhas** por processamento.

### 2. Upload da base de classificação (opcional)
Formatos aceitos: **ODS, XLSX, XLS**

Se existir um arquivo `base_classificacao_atualizada.ods` na pasta do projeto, ele será carregado automaticamente e usado para todas as planilhas. Se esse arquivo não existir, o upload manual de base fica disponível.

Colunas necessárias:
- `DESCRDEB`
- `TIPO DE CUSTO` → valores: `C.OPERACIONAL`, `NÃO OPERACIONAL`, `IGNORAR`

### 3. Informe o faturamento de cada planilha
Cada arquivo enviado precisa ter um faturamento próprio, obrigatório e maior que zero.

### 4. Clique em "Processar Planilhas"

### 5. Classifique as pendências (se houver)
Contas sem classificação na base serão apresentadas para classificação manual.
No processamento em lote, cada conta pendente aparece uma única vez, mesmo quando existir em várias planilhas.

Você pode optar por gerar uma base revisada com as novas classificações para uso futuro.

### 6. Faça o download dos relatórios
O app gera:
- um relatório consolidado ODS por planilha;
- um ODS de pendências por planilha, quando houver contas pendentes;
- uma base de classificação revisada, quando novas classificações manuais forem salvas;
- um ZIP com todos os arquivos gerados no lote.

---

## Regras de negócio

| Regra | Detalhe |
|---|---|
| Pré-filtro | `DEVOLUCAO DE VENDAS` e `MERCAD. EMITIDA P/ CONSERTO` são removidas antes de qualquer processamento |
| Correspondência | EXATA — sem normalização, sem fuzzy matching |
| Contas IGNORAR | Entram nos totais, sinalizadas em cinza itálico no ODS |
| Duplicata na base | Conta com tipos divergentes → PENDENTE + alerta |
| Reset de sessão | Troca do conjunto de arquivos limpa resultados e classificações manuais anteriores |
| Base local | `base_classificacao_atualizada.ods` é usada automaticamente para todas as planilhas quando existir |
| Lote | Até 20 planilhas por processamento, com faturamento individual por arquivo |
| Pendências | Classificação manual deduplicada por conta no lote |
| Exportação | Valores monetários e percentuais são gravados como números, com máscara visual aplicada |
| Download | Relatórios individuais e pacote ZIP com todos os ODS gerados |

---

## Estrutura do projeto

```
app.py             # Interface Streamlit (dashboard)
processamento.py   # Lógica de negócio (leitura, consolidação, classificação, exportação)
inicia.sh          # Atalho para ativar venv e iniciar o Streamlit
salvar_github.sh   # Atalho para adicionar, commitar e enviar alterações ao GitHub
requirements.txt   # Dependências
README.md          # Este arquivo
```
