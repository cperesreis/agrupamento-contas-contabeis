"""
Processador de Despesas Contábeis
Aplicação Streamlit para consolidação e análise de despesas contábeis via DB2.
"""

from datetime import date
import os
import re

import pandas as pd
import streamlit as st

from db import buscar_dados_financeiros
from processamento import (
    BASE_CLASSIFICACAO_ARQUIVO,
    calcular_indicadores,
    classificar,
    consolidar,
    exportar_ods,
    gerar_base_atualizada,
    ler_base_local,
    preparar_dataframe_despesas,
    resetar_sessao,
)


NOME_BASE_REVISAO = "base_classificacao_para_revisao.ods"
EMPRESAS_DISPONIVEIS = list(range(1, 21))


st.set_page_config(
    page_title="Processador de Despesas Contábeis",
    page_icon="📊",
    layout="wide",
)

st.markdown("""
<style>
    .main-header {
        background: linear-gradient(135deg, #1e3a5f 0%, #2d6a9f 100%);
        padding: 2rem; border-radius: 12px; margin-bottom: 2rem;
        color: white; text-align: center;
    }
    .main-header h1 { margin: 0; font-size: 2.2rem; }
    .main-header p  { margin: .5rem 0 0; opacity: .85; font-size: 1rem; }

    .card {
        background: #f8fafc; border: 1px solid #e2e8f0;
        border-radius: 8px; padding: 1.2rem 1rem;
        text-align: center; box-shadow: 0 1px 4px rgba(0,0,0,.06);
    }
    .card-label { font-size:.8rem; color:#64748b; text-transform:uppercase;
                  letter-spacing:.05em; margin-bottom:.3rem; }
    .card-value { font-size:1.35rem; font-weight:700; color:#1e3a5f; }
    .card-sub   { font-size:.78rem; color:#64748b; margin-top:.2rem; }
    .card-pct   { font-size:.9rem; font-weight:600; color:#2d6a9f; margin-top:.2rem; }

    .alert-warning { background:#fef9c3; border-left:4px solid #eab308;
                     padding:.8rem 1rem; border-radius:6px; margin:1rem 0; }
    .alert-success { background:#dcfce7; border-left:4px solid #16a34a;
                     padding:.8rem 1rem; border-radius:6px; margin:1rem 0; }
    .alert-error   { background:#fee2e2; border-left:4px solid #dc2626;
                     padding:.8rem 1rem; border-radius:6px; margin:1rem 0; }
    .alert-info    { background:#eff6ff; border-left:4px solid #3b82f6;
                     padding:.8rem 1rem; border-radius:6px; margin:.5rem 0;
                     font-size:.88rem; color:#1e40af; }

    .section-title { font-size:1.1rem; font-weight:600; color:#1e3a5f;
                     border-bottom:2px solid #2d6a9f; padding-bottom:.4rem; margin-bottom:1rem; }

    div[data-testid="stDialog"] div[role="dialog"] {
        width: min(96vw, 1400px);
        max-width: 96vw;
    }

    .stButton>button {
        background:#2d6a9f; color:white; border:none;
        padding:.6rem 2rem; border-radius:8px; font-weight:600; transition:background .2s;
    }
    .stButton>button:hover { background:#1e3a5f; }
</style>
""", unsafe_allow_html=True)

st.markdown("""
<div class="main-header">
    <h1>📊 Processador de Despesas Contábeis</h1>
    <p>Consulte o DB2, consolide, classifique e gere relatórios ODS automaticamente</p>
</div>
""", unsafe_allow_html=True)


def _fmt_brl(v):
    return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _fmt_pct(v):
    return f"{v:.1f}%"


def _nome_relatorio(data_inicio, data_fim, empresas, sufixo):
    empresas_txt = "-".join(str(empresa) for empresa in empresas)
    return f"empresas_{empresas_txt}_{data_inicio:%Y%m%d}_{data_fim:%Y%m%d}_{sufixo}.ods"


def _colorir_linha(row):
    if row["TIPO DE CUSTO"] == "IGNORAR":
        return ["color:gray;font-style:italic"] * len(row)
    if row["TIPO DE CUSTO"] == "PENDENTE DE CLASSIFICAÇÃO":
        return ["color:#d97706;font-weight:bold"] * len(row)
    return [""] * len(row)


def _exibir_cards_indicadores(ind, pendentes_count):
    st.markdown('<p class="section-title">📈 Indicadores</p>', unsafe_allow_html=True)
    c1, c2, c3, c4, c5 = st.columns(5)

    with c1:
        st.markdown(f"""<div class="card">
            <div class="card-label">Faturamento</div>
            <div class="card-value">{_fmt_brl(ind['faturamento'])}</div>
        </div>""", unsafe_allow_html=True)

    with c2:
        st.markdown(f"""<div class="card">
            <div class="card-label">Total Despesas</div>
            <div class="card-value" style="color:#dc2626">{_fmt_brl(ind['total_despesas'])}</div>
            <div class="card-sub">{_fmt_pct(ind['pct_despesas'])} do faturamento</div>
        </div>""", unsafe_allow_html=True)

    with c3:
        st.markdown(f"""<div class="card">
            <div class="card-label">Custo Operacional</div>
            <div class="card-value">{_fmt_brl(ind['custo_operacional'])}</div>
            <div class="card-pct">{_fmt_pct(ind['pct_operacional'])} do faturamento</div>
        </div>""", unsafe_allow_html=True)

    with c4:
        cor = "#16a34a" if ind["saldo"] >= 0 else "#dc2626"
        st.markdown(f"""<div class="card">
            <div class="card-label">Saldo</div>
            <div class="card-value" style="color:{cor}">{_fmt_brl(ind['saldo'])}</div>
            <div class="card-sub">{_fmt_pct(ind['pct_saldo'])} do faturamento</div>
        </div>""", unsafe_allow_html=True)

    with c5:
        cor_p = "#d97706" if pendentes_count > 0 else "#16a34a"
        st.markdown(f"""<div class="card">
            <div class="card-label">Contas Pendentes</div>
            <div class="card-value" style="color:{cor_p}">{pendentes_count}</div>
        </div>""", unsafe_allow_html=True)


@st.dialog("Contas existentes na base oficial", width="large")
def _abrir_base_classificacao():
    try:
        df_base_preview, _ = ler_base_local(BASE_CLASSIFICACAO_ARQUIVO)
        df_base_preview = df_base_preview.sort_values("DESCRDEB").reset_index(drop=True)
        st.dataframe(df_base_preview, use_container_width=True, height=560)
    except Exception as e:
        st.error(f"Não foi possível carregar a base: {e}")


def _recalcular_resultado():
    df_base = st.session_state.get("df_base_original")
    df_reclassificado, alertas_dup = classificar(
        st.session_state.df_consolidado.copy(),
        df_base,
        st.session_state.classificacoes_manuais,
    )
    indicadores = calcular_indicadores(df_reclassificado, st.session_state.faturamento)
    ods_bytes, ods_pend_bytes = exportar_ods(
        df_reclassificado,
        indicadores,
        st.session_state.faturamento,
    )

    st.session_state.df_classificado = df_reclassificado
    st.session_state.indicadores = indicadores
    st.session_state.ods_bytes = ods_bytes
    st.session_state.ods_pendencias_bytes = ods_pend_bytes
    st.session_state.alertas_resultado = alertas_dup


for chave, padrao in [
    ("classificacoes_manuais", {}),
    ("ultimo_filtro", None),
    ("df_consolidado", None),
    ("df_classificado", None),
    ("indicadores", None),
    ("processado", False),
    ("ods_bytes", None),
    ("ods_pendencias_bytes", None),
    ("ods_base_bytes", None),
    ("alertas_resultado", []),
    ("faturamento", 0.0),
]:
    if chave not in st.session_state:
        st.session_state[chave] = padrao


st.markdown('<p class="section-title">🔎 Filtros da Consulta</p>', unsafe_allow_html=True)

base_local_encontrada = os.path.isfile(BASE_CLASSIFICACAO_ARQUIVO)
base_nome_exibicao = os.path.basename(BASE_CLASSIFICACAO_ARQUIVO)

with st.form("form_consulta_db2"):
    col_data_ini, col_data_fim, col_empresas = st.columns([1, 1, 2])

    with col_data_ini:
        data_inicio = st.date_input("Data Inicial", value=date.today().replace(day=1), format="DD/MM/YYYY")
    with col_data_fim:
        data_fim = st.date_input("Data Final", value=date.today(), format="DD/MM/YYYY")
    with col_empresas:
        empresas = st.multiselect(
            "Empresas",
            EMPRESAS_DISPONIVEIS,
            default=[1],
            help="Selecione um ou mais IDs de empresa. Códigos válidos: 1 a 20.",
        )

    processar = st.form_submit_button("▶ Consultar e Processar")

if base_local_encontrada:
    col_base_msg, col_base_info, _ = st.columns([8, 1, 4])
    with col_base_msg:
        st.markdown(
            f'<div class="alert-info">✅ Base local encontrada: <strong>{base_nome_exibicao}</strong>'
            '<br>Ela será usada automaticamente na classificação das despesas.</div>',
            unsafe_allow_html=True,
        )
    with col_base_info:
        st.markdown("<div style='height:.55rem'></div>", unsafe_allow_html=True)
        if st.button("ⓘ", help="Ver contas existentes na base oficial", key="btn_base_classificacao"):
            _abrir_base_classificacao()
else:
    st.markdown(
        f'<div class="alert-warning">⚠️ Base local não encontrada: <strong>{base_nome_exibicao}</strong>. '
        'As contas serão marcadas como pendentes até que a base exista na pasta do projeto.</div>',
        unsafe_allow_html=True,
    )

filtro_atual = (
    tuple(empresas),
    data_inicio.isoformat() if data_inicio else None,
    data_fim.isoformat() if data_fim else None,
)
if filtro_atual != st.session_state.ultimo_filtro:
    resetar_sessao(st.session_state)
    st.session_state.ultimo_filtro = filtro_atual


if processar:
    erros = []
    if not empresas:
        erros.append("Selecione ao menos uma empresa.")
    if data_inicio and data_fim and data_inicio > data_fim:
        erros.append("A data inicial não pode ser maior que a data final.")

    if erros:
        for erro in erros:
            st.markdown(f'<div class="alert-error">❌ {erro}</div>', unsafe_allow_html=True)
    else:
        progress = st.progress(0, text="Conectando ao DB2...")
        try:
            progress.progress(20, text="Consultando despesas e faturamento...")
            df_despesas_db, faturamento = buscar_dados_financeiros(empresas, data_inicio, data_fim)

            progress.progress(45, text="Normalizando despesas...")
            df_raw, aviso_vazio = preparar_dataframe_despesas(df_despesas_db)

            progress.progress(60, text="Carregando base de classificação...")
            df_base = None
            alertas_base = []
            if base_local_encontrada:
                df_base, alertas_base = ler_base_local(BASE_CLASSIFICACAO_ARQUIVO)

            progress.progress(75, text="Consolidando e classificando...")
            df_consolidado = consolidar(df_raw)
            df_classificado, alertas_dup = classificar(
                df_consolidado,
                df_base,
                st.session_state.classificacoes_manuais,
            )
            indicadores = calcular_indicadores(df_classificado, faturamento)
            ods_bytes, ods_pend_bytes = exportar_ods(df_classificado, indicadores, faturamento)

            progress.progress(100, text="✅ Concluído!")

            st.session_state.df_base_original = df_base
            st.session_state.df_consolidado = df_consolidado
            st.session_state.df_classificado = df_classificado
            st.session_state.faturamento = faturamento
            st.session_state.indicadores = indicadores
            st.session_state.ods_bytes = ods_bytes
            st.session_state.ods_pendencias_bytes = ods_pend_bytes
            st.session_state.alertas_resultado = alertas_base + alertas_dup
            st.session_state.processado = True
            st.session_state.ods_base_bytes = None
            st.session_state.pop("perguntar_salvar_base", None)

            if aviso_vazio:
                st.session_state.alertas_resultado.append(
                    "Nenhuma linha válida retornada após remover contas ignoradas."
                )

            st.markdown(
                '<div class="alert-success">✅ Consulta processada com sucesso.</div>',
                unsafe_allow_html=True,
            )
        except Exception as e:
            progress.empty()
            st.session_state.processado = False
            st.markdown(f'<div class="alert-error">❌ Falha no processamento: {e}</div>', unsafe_allow_html=True)


if st.session_state.processado and st.session_state.df_classificado is not None:
    df = st.session_state.df_classificado
    ind = st.session_state.indicadores

    for alerta in st.session_state.get("alertas_resultado", []):
        st.markdown(f'<div class="alert-warning">⚠️ {alerta}</div>', unsafe_allow_html=True)

    df_pend = df[df["TIPO DE CUSTO"] == "PENDENTE DE CLASSIFICAÇÃO"].copy()
    if not df_pend.empty:
        st.markdown('<p class="section-title">🏷️ Classificação Manual</p>', unsafe_allow_html=True)
        st.markdown(
            '<div class="alert-warning">⚠️ Existem contas sem classificação. '
            'Classifique-as abaixo para recalcular os indicadores e relatórios.</div>',
            unsafe_allow_html=True,
        )

        opcoes_map = {"SIM → C.OPERACIONAL": "C.OPERACIONAL", "NÃO → NÃO OPERACIONAL": "NÃO OPERACIONAL"}
        escolhas = {}

        for _, row in df_pend.sort_values("VALPAGAMENTOTITULO", ascending=False).iterrows():
            conta = row["DESCRDEB"]
            valor_atual = st.session_state.classificacoes_manuais.get(conta)
            idx = 0 if valor_atual == "C.OPERACIONAL" else (1 if valor_atual == "NÃO OPERACIONAL" else None)
            chave_conta = re.sub(r"[^A-Za-z0-9_-]+", "_", conta)
            escolha = st.radio(
                f"**{conta}** — valor: {_fmt_brl(row['VALPAGAMENTOTITULO'])}\n\nEsta conta é custo operacional?",
                options=list(opcoes_map.keys()),
                index=idx,
                key=f"radio_pendente_{chave_conta}",
                horizontal=True,
            )
            escolhas[conta] = opcoes_map.get(escolha)

        if st.button("✅ Confirmar Classificações"):
            nao_resp = [conta for conta, valor in escolhas.items() if valor is None]
            if nao_resp:
                st.error(f"Responda todas as contas antes de confirmar: {nao_resp}")
            else:
                st.session_state.classificacoes_manuais.update(escolhas)
                _recalcular_resultado()
                st.session_state.perguntar_salvar_base = True
                st.rerun()

    if st.session_state.get("perguntar_salvar_base"):
        st.markdown('<p class="section-title">💾 Base de Classificação para Revisão</p>', unsafe_allow_html=True)
        st.markdown(
            '<div class="alert-warning">⚠️ Este arquivo não substitui automaticamente a base oficial. '
            'Alguém deve revisar as novas classificações antes de substituir a base oficial.</div>',
            unsafe_allow_html=True,
        )
        salvar = st.radio(
            "Deseja gerar uma base atualizada para revisão?",
            ["Não", "Sim"],
            horizontal=True,
            key="radio_salvar_base",
        )
        if salvar == "Sim" and st.button("Gerar Base Atualizada para Revisão"):
            st.session_state.ods_base_bytes = gerar_base_atualizada(
                st.session_state.get("df_base_original"),
                st.session_state.classificacoes_manuais,
            )
            st.session_state.perguntar_salvar_base = False
            st.rerun()

    pendentes_count = int((df["TIPO DE CUSTO"] == "PENDENTE DE CLASSIFICAÇÃO").sum())
    _exibir_cards_indicadores(ind, pendentes_count)

    st.markdown('<p class="section-title">📋 Prévia da Tabela Consolidada</p>', unsafe_allow_html=True)
    df_exibir = df.copy()
    df_exibir["VALPAGAMENTOTITULO"] = df_exibir["VALPAGAMENTOTITULO"].apply(_fmt_brl)
    df_exibir["% SOBRE FATURAMENTO"] = df_exibir["% SOBRE FATURAMENTO"].apply(
        lambda x: f"{x:.2f}%" if pd.notna(x) else ""
    )
    st.dataframe(
        df_exibir.style.apply(_colorir_linha, axis=1),
        use_container_width=True,
        height=420,
    )

    st.markdown('<p class="section-title">⬇️ Downloads</p>', unsafe_allow_html=True)
    col_d1, col_d2, col_d3 = st.columns(3)

    with col_d1:
        st.download_button(
            "📥 Baixar ODS Consolidado",
            data=st.session_state.ods_bytes,
            file_name=_nome_relatorio(data_inicio, data_fim, empresas, "consolidado"),
            mime="application/vnd.oasis.opendocument.spreadsheet",
            use_container_width=True,
        )

    with col_d2:
        if st.session_state.ods_pendencias_bytes:
            st.download_button(
                "⚠️ Baixar ODS Pendências",
                data=st.session_state.ods_pendencias_bytes,
                file_name=_nome_relatorio(data_inicio, data_fim, empresas, "pendencias"),
                mime="application/vnd.oasis.opendocument.spreadsheet",
                use_container_width=True,
            )
        else:
            st.info("Sem pendências")

    with col_d3:
        if st.session_state.ods_base_bytes:
            st.download_button(
                "💾 Baixar Base para Revisão",
                data=st.session_state.ods_base_bytes,
                file_name=NOME_BASE_REVISAO,
                mime="application/vnd.oasis.opendocument.spreadsheet",
                use_container_width=True,
            )
        else:
            st.info("Base de revisão ainda não gerada")
