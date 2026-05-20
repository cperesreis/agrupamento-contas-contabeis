"""
db.py
Camada de acesso ao DB2.

As credenciais são carregadas exclusivamente de variáveis de ambiente,
preferencialmente a partir de um arquivo .env local.
"""

from __future__ import annotations

from datetime import date
import os
from urllib.parse import quote_plus

import pandas as pd
from dotenv import load_dotenv
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import create_engine, text, bindparam
from sqlalchemy.engine import Engine


load_dotenv()


def _validar_empresas(empresas: list[int]) -> list[int]:
    if not empresas:
        raise ValueError("Selecione ao menos uma empresa.")

    empresas_int = sorted({int(empresa) for empresa in empresas})
    invalidas = [empresa for empresa in empresas_int if empresa < 1 or empresa > 20]
    if invalidas:
        raise ValueError(f"Empresas inválidas: {invalidas}. Use IDs entre 1 e 20.")

    return empresas_int


def _validar_periodo(data_inicio: date, data_fim: date) -> None:
    if data_inicio is None or data_fim is None:
        raise ValueError("Informe data inicial e data final.")
    if data_inicio > data_fim:
        raise ValueError("A data inicial não pode ser maior que a data final.")


def criar_engine_db2() -> Engine:
    """
    Cria a conexão SQLAlchemy com DB2 usando variáveis de ambiente.

    Opções aceitas:
      1. DB2_SQLALCHEMY_URL pronto.
      2. DB2_USER, DB2_PASSWORD, DB2_HOST, DB2_PORT e DB2_DATABASE.
    """
    url_pronta = os.getenv("DB2_SQLALCHEMY_URL")
    if url_pronta:
        return create_engine(url_pronta)

    usuario = os.getenv("DB2_USER")
    senha = os.getenv("DB2_PASSWORD")
    host = os.getenv("DB2_HOST")
    porta = os.getenv("DB2_PORT", "50000")
    database = os.getenv("DB2_DATABASE")

    faltando = [
        nome
        for nome, valor in {
            "DB2_USER": usuario,
            "DB2_PASSWORD": senha,
            "DB2_HOST": host,
            "DB2_DATABASE": database,
        }.items()
        if not valor
    ]
    if faltando:
        raise ValueError(
            "Credenciais do DB2 incompletas no .env. "
            f"Variáveis ausentes: {', '.join(faltando)}."
        )

    url = (
        "ibm_db_sa://"
        f"{quote_plus(usuario)}:{quote_plus(senha)}@"
        f"{host}:{porta}/{database}"
    )
    return create_engine(url)


def buscar_faturamento_bruto(
    empresas: list[int],
    data_inicio: date,
    data_fim: date,
    engine: Engine | None = None,
) -> float:
    empresas = _validar_empresas(empresas)
    _validar_periodo(data_inicio, data_fim)
    engine = engine or criar_engine_db2()

    query = (
        text(
            """
            SELECT DECIMAL(COALESCE(SUM(EA.VALTOTLIQUIDO), 0), 16, 2) AS FATURAMENTO_BRUTO
            FROM DBA.NOTAS N
            INNER JOIN DBA.ESTOQUE_ANALITICO EA
                ON EA.IDEMPRESA = N.IDEMPRESA
               AND EA.IDPLANILHA = N.IDPLANILHA
            INNER JOIN DBA.NOTAS_ENTRADA_SAIDA NES
                ON NES.IDEMPRESA = N.IDEMPRESA
               AND NES.IDPLANILHA = N.IDPLANILHA
               AND NES.IDOPERACAO = EA.IDOPERACAO
            INNER JOIN DBA.OPERACAO_INTERNA COI
                ON COI.IDOPERACAO = NES.IDOPERACAO
            WHERE COI.TIPOMOVIMENTO = 'V'
              AND N.IDEMPRESA IN :empresas
              AND N.FLAGNOTACANCEL = 'F'
              AND EA.DTMOVIMENTO >= :data_inicio
              AND EA.DTMOVIMENTO <= :data_fim
            """
        )
        .bindparams(bindparam("empresas", expanding=True))
    )

    df = pd.read_sql(
        query,
        engine,
        params={
            "empresas": empresas,
            "data_inicio": data_inicio,
            "data_fim": data_fim,
        },
    )
    df.columns = [str(coluna).strip().upper() for coluna in df.columns]
    if df.empty:
        return 0.0

    return float(df.iloc[0]["FATURAMENTO_BRUTO"] or 0)


def buscar_despesas(
    empresas: list[int],
    data_inicio: date,
    data_fim: date,
    engine: Engine | None = None,
) -> pd.DataFrame:
    """
    Busca os pagamentos efetuados no DB2.

    O DataFrame retornado preserva os nomes exigidos pelo processamento:
    DESCRDEB e VALPAGAMENTOTITULO.
    """
    empresas = _validar_empresas(empresas)
    _validar_periodo(data_inicio, data_fim)
    engine = engine or criar_engine_db2()

    query = (
        text(
            """
            SELECT
                CBEB.DESCRCTACONTABIL AS DESCRDEB,
                TMP.VALPAGAMENTOTITULO AS VALPAGAMENTOTITULO
            FROM (
                SELECT
                    CONTAS_PAGAR_BAIXAS.VALPAGAMENTOTITULO,
                    COALESCE(
                        CONTAS_PAGAR.IDCTACONTABILCONTRAPARTIDA,
                        DBA.UF_FRST_CPAG_PESQ(
                            CONTAS_PAGAR.IDEMPRESA,
                            CONTAS_PAGAR.IDPLANILHA,
                            'D',
                            CONTAS_PAGAR.ORIGEMMOVIMENTO
                        )
                    ) AS IDCTADEBITO
                FROM DBA.CLIENTE_FORNECEDOR CLIENTE_FORNECEDOR,
                     DBA.CONTAS_PAGAR_BAIXAS CONTAS_PAGAR_BAIXAS,
                     DBA.CONTAS_PAGAR CONTAS_PAGAR
                        JOIN DBA.CONTABIL_PLANO_CONTAS AS CTA
                          ON CONTAS_PAGAR.IDCTACONTABIL = CTA.IDCTACONTABIL,
                     DBA.FORMA_PAGREC FORMA_PAGREC
                WHERE CLIENTE_FORNECEDOR.IDCLIFOR = CONTAS_PAGAR_BAIXAS.IDCLIFOR
                  AND FORMA_PAGREC.IDRECEBIMENTO = CONTAS_PAGAR.IDPAGAMENTO
                  AND CONTAS_PAGAR_BAIXAS.IDEMPRESA = CONTAS_PAGAR.IDEMPRESA
                  AND CONTAS_PAGAR_BAIXAS.IDCLIFOR = CONTAS_PAGAR.IDCLIFOR
                  AND CONTAS_PAGAR_BAIXAS.IDTITULO = CONTAS_PAGAR.IDTITULO
                  AND CONTAS_PAGAR_BAIXAS.DIGITOTITULO = CONTAS_PAGAR.DIGITOTITULO
                  AND CONTAS_PAGAR_BAIXAS.SERIENOTA = CONTAS_PAGAR.SERIENOTA
                  AND CONTAS_PAGAR_BAIXAS.IDEMPRESA IN :empresas
                  AND CONTAS_PAGAR_BAIXAS.DTPAGAMENTO >= :data_inicio
                  AND CONTAS_PAGAR_BAIXAS.DTPAGAMENTO <= :data_fim
                  AND NOT EXISTS (
                      SELECT 0
                      FROM DBA.CONTAS_PAGAR_BAIXAS AS CPB
                      JOIN DBA.CONTAS_PAGAR AS CP
                        ON CPB.IDEMPRESABAIXA = CP.IDEMPRESA
                       AND CPB.IDPLANILHA = CP.IDPLANILHA
                      WHERE CONTAS_PAGAR_BAIXAS.IDEMPRESA = CPB.IDEMPRESA
                        AND CONTAS_PAGAR_BAIXAS.IDCLIFOR = CPB.IDCLIFOR
                        AND CONTAS_PAGAR_BAIXAS.IDTITULO = CPB.IDTITULO
                        AND CONTAS_PAGAR_BAIXAS.DIGITOTITULO = CPB.DIGITOTITULO
                        AND CONTAS_PAGAR_BAIXAS.SERIENOTA = CPB.SERIENOTA
                  )
            ) AS TMP
            JOIN DBA.CONTABIL_PLANO_CONTAS AS CBEB
              ON CBEB.IDCTACONTABIL = TMP.IDCTADEBITO
            """
        )
        .bindparams(bindparam("empresas", expanding=True))
    )

    try:
        return pd.read_sql(
            query,
            engine,
            params={
                "empresas": empresas,
                "data_inicio": data_inicio,
                "data_fim": data_fim,
            },
        )
    except SQLAlchemyError as exc:
        mensagem = str(exc)
        if "UF_FRST_CPAG_PESQ" in mensagem and ("SQL0440N" in mensagem or "SQLCODE=-440" in mensagem):
            raise ValueError(
                "O DB2 não encontrou a função DBA.UF_FRST_CPAG_PESQ usada pela query de despesas. "
                "Confirme com o DBA se essa função existe nesse banco/schema e se o usuário do .env tem permissão de execução."
            ) from exc
        raise


def validar_empresas_no_banco(empresas: list[int], engine: Engine | None = None) -> None:
    """Confirma se os IDs selecionados existem no cadastro de empresas do DB2."""
    empresas = _validar_empresas(empresas)
    engine = engine or criar_engine_db2()

    query = (
        text(
            """
            SELECT IDEMPRESA
            FROM DBA.EMPRESA
            WHERE IDEMPRESA IN :empresas
            """
        )
        .bindparams(bindparam("empresas", expanding=True))
    )

    df = pd.read_sql(query, engine, params={"empresas": empresas})
    df.columns = [str(coluna).strip().upper() for coluna in df.columns]
    encontradas = set()
    if not df.empty and "IDEMPRESA" in df.columns:
        encontradas = {int(empresa) for empresa in df["IDEMPRESA"].dropna().tolist()}

    nao_encontradas = [empresa for empresa in empresas if empresa not in encontradas]
    if nao_encontradas:
        if len(nao_encontradas) == 1:
            raise ValueError(
                f"Empresa {nao_encontradas[0]} não foi encontrada no banco de dados ! Favor Verificar.."
            )
        ids = ", ".join(str(empresa) for empresa in nao_encontradas)
        raise ValueError(f"Empresas {ids} não foram encontradas no banco de dados.")


def buscar_dados_financeiros(
    empresas: list[int],
    data_inicio: date,
    data_fim: date,
) -> tuple[pd.DataFrame, float]:
    """Retorna despesas e faturamento bruto usando uma única engine."""
    engine = criar_engine_db2()
    validar_empresas_no_banco(empresas, engine=engine)
    despesas = buscar_despesas(empresas, data_inicio, data_fim, engine=engine)
    faturamento = buscar_faturamento_bruto(empresas, data_inicio, data_fim, engine=engine)
    return despesas, faturamento
