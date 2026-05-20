"""
Análise de Despesas por Conta Contábil
Aplicação Streamlit para consolidação e análise de despesas contábeis via DB2.
"""

from datetime import date
import html
import os
import re

import pandas as pd
import streamlit as st
import plotly.express as px

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
    page_title="Análise de Despesas por Conta Contábil",
    page_icon="📊",
    layout="wide",
)

if "tema_visual" not in st.session_state:
    st.session_state.tema_visual = "claro"

PLOTLY_TEMPLATE = "plotly_dark" if st.session_state.tema_visual == "escuro" else "plotly_white"

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
    .validation-error {
        color:#dc2626;
        font-size:16px;
        font-weight:700;
        margin:1rem 0;
    }
    .alert-info    { background:#eff6ff; border-left:4px solid #3b82f6;
                     padding:.8rem 1rem; border-radius:6px; margin:.5rem 0;
                     font-size:.88rem; color:#1e40af; }

    .section-title { font-size:1.1rem; font-weight:600; color:#1e3a5f;
                     border-bottom:2px solid #2d6a9f; padding-bottom:.4rem; margin-bottom:1rem; }

    div[data-testid="stTabs"] button[role="tab"] {
        background:#deb297;
        color:#1f2937;
        border:1px solid #c79071;
        border-radius:8px 8px 0 0;
        margin-right:2ch;
        padding:.7rem 1.4rem;
        font-weight:700;
    }
    div[data-testid="stTabs"] button[role="tab"] * {
        color:inherit;
    }
    div[data-testid="stTabs"] button[role="tab"][aria-selected="true"] {
        background:#c79071;
        color:#111827;
        border-color:#9f684b;
    }
    div[data-testid="stTabs"] div[data-baseweb="tab-highlight"] {
        background:#9f684b;
    }

    div[data-testid="stDialog"] div[role="dialog"] {
        width: min(92vw, 560px);
        max-width: 92vw;
    }

    div[data-testid="stDialog"] div[role="dialog"]:has(div[data-testid="stDataFrame"]) {
        width: min(96vw, 1400px);
        max-width: 96vw;
    }

    .stButton>button,
    div[data-testid="stButton"] button,
    div[data-testid="stDialog"] div[data-testid="stButton"] button,
    div[data-testid="stFormSubmitButton"] button,
    div[data-testid="stDownloadButton"] button {
        background:#2d6a9f; color:white; border:none;
        padding:.6rem 2rem; border-radius:8px; font-weight:600; transition:background .2s;
    }
    .stButton>button:hover,
    div[data-testid="stButton"] button:hover,
    div[data-testid="stDialog"] div[data-testid="stButton"] button:hover,
    div[data-testid="stFormSubmitButton"] button:hover,
    div[data-testid="stDownloadButton"] button:hover { background:#1e3a5f; color:white; }

    .stButton>button *,
    div[data-testid="stButton"] button *,
    div[data-testid="stDialog"] div[data-testid="stButton"] button *,
    div[data-testid="stFormSubmitButton"] button *,
    div[data-testid="stDownloadButton"] button *,
    .stButton>button:hover *,
    div[data-testid="stButton"] button:hover *,
    div[data-testid="stDialog"] div[data-testid="stButton"] button:hover *,
    div[data-testid="stFormSubmitButton"] button:hover *,
    div[data-testid="stDownloadButton"] button:hover * {
        color:inherit;
    }

    .stButton>button:disabled,
    .stButton>button:disabled:hover,
    div[data-testid="stButton"] button:disabled,
    div[data-testid="stButton"] button:disabled:hover,
    div[data-testid="stDialog"] div[data-testid="stButton"] button:disabled,
    div[data-testid="stDialog"] div[data-testid="stButton"] button:disabled:hover,
    div[data-testid="stFormSubmitButton"] button:disabled,
    div[data-testid="stFormSubmitButton"] button:disabled:hover,
    div[data-testid="stDownloadButton"] button:disabled,
    div[data-testid="stDownloadButton"] button:disabled:hover {
        background:#e2e8f0;
        color:#475569;
        border:1px solid #cbd5e1;
        opacity:1;
    }
    
    .empty-state {
        text-align: center;
        padding: 4rem 2rem;
        color: #64748b;
    }
    .empty-state h2 { color: #1e3a5f; }
    .empty-state p { font-size: 1.1rem; }

    .pending-row {
        display:grid;
        grid-template-columns: minmax(0, 1fr) 180px;
        gap: 1rem;
        align-items:center;
        padding:.7rem .9rem;
        border:1px solid #d1d5db;
        border-radius:8px;
        margin:.35rem 0 .15rem;
        color:#111827;
    }
    .pending-row strong { display:block; font-size:.78rem; color:#374151; margin-bottom:.15rem; }
    .pending-row .pending-account { font-weight:600; overflow-wrap:anywhere; }
    .pending-row .pending-value { text-align:right; font-weight:700; }
</style>
""", unsafe_allow_html=True)

if st.session_state.tema_visual == "escuro":
    st.markdown("""
    <style>
        [data-testid="stAppViewContainer"] {
            background: #111827;
            color: #e5e7eb;
        }
        [data-testid="stSidebar"] {
            background: #0f172a;
            color: #e5e7eb;
        }
        [data-testid="stHeader"] {
            background: rgba(17, 24, 39, .92);
        }
        .main-header {
            background: linear-gradient(135deg, #0f172a 0%, #1f6f8b 100%);
        }
        .card {
            background: #1f2937;
            border-color: #374151;
            box-shadow: 0 1px 4px rgba(0,0,0,.35);
        }
        .card-label,
        .card-sub,
        .empty-state {
            color: #9ca3af;
        }
        .card-value,
        .empty-state h2,
        .section-title {
            color: #e5e7eb;
        }
        .card-pct {
            color: #38bdf8;
        }
        .section-title {
            border-bottom-color: #38bdf8;
        }
        .alert-info {
            background: #172554;
            color: #dbeafe;
            border-left-color: #38bdf8;
        }
        .alert-warning {
            background: #422006;
            color: #fef3c7;
            border-left-color: #f59e0b;
        }
        .alert-success {
            background: #052e16;
            color: #dcfce7;
            border-left-color: #22c55e;
        }
        .alert-error {
            background: #450a0a;
            color: #fee2e2;
            border-left-color: #ef4444;
        }
        .validation-error {
            color:#f87171;
        }
        .pending-row {
            border-color:#475569;
            color:#0f172a;
        }
        .pending-row strong {
            color:#1f2937;
        }
        div[data-testid="stTabs"] button[role="tab"] {
            background:#e8d826;
            color:#111827;
            border-color:#f3e85f;
        }
        div[data-testid="stTabs"] button[role="tab"] * {
            color:inherit;
        }
        div[data-testid="stTabs"] button[role="tab"][aria-selected="true"] {
            background:#fff176;
            color:#111827;
            border-color:#facc15;
        }
        div[data-testid="stTabs"] div[data-baseweb="tab-highlight"] {
            background:#facc15;
        }
        .stButton>button,
        div[data-testid="stButton"] button,
        div[data-testid="stDialog"] div[data-testid="stButton"] button,
        div[data-testid="stFormSubmitButton"] button,
        div[data-testid="stDownloadButton"] button {
            background:#38bdf8;
            color:#082f49;
            border:1px solid #7dd3fc;
        }
        .stButton>button:hover,
        div[data-testid="stButton"] button:hover,
        div[data-testid="stDialog"] div[data-testid="stButton"] button:hover,
        div[data-testid="stFormSubmitButton"] button:hover,
        div[data-testid="stDownloadButton"] button:hover {
            background:#7dd3fc;
            color:#082f49;
            border-color:#bae6fd;
        }
        .stButton>button *,
        div[data-testid="stButton"] button *,
        div[data-testid="stDialog"] div[data-testid="stButton"] button *,
        div[data-testid="stFormSubmitButton"] button *,
        div[data-testid="stDownloadButton"] button *,
        .stButton>button:hover *,
        div[data-testid="stButton"] button:hover *,
        div[data-testid="stDialog"] div[data-testid="stButton"] button:hover *,
        div[data-testid="stFormSubmitButton"] button:hover *,
        div[data-testid="stDownloadButton"] button:hover * {
            color:inherit;
        }
        .stButton>button:disabled,
        .stButton>button:disabled:hover,
        div[data-testid="stButton"] button:disabled,
        div[data-testid="stButton"] button:disabled:hover,
        div[data-testid="stDialog"] div[data-testid="stButton"] button:disabled,
        div[data-testid="stDialog"] div[data-testid="stButton"] button:disabled:hover,
        div[data-testid="stFormSubmitButton"] button:disabled,
        div[data-testid="stFormSubmitButton"] button:disabled:hover,
        div[data-testid="stDownloadButton"] button:disabled,
        div[data-testid="stDownloadButton"] button:disabled:hover {
            background:#334155;
            color:#cbd5e1;
            border:1px solid #64748b;
            opacity:1;
        }
        .stButton>button:disabled *,
        div[data-testid="stButton"] button:disabled *,
        div[data-testid="stDialog"] div[data-testid="stButton"] button:disabled *,
        div[data-testid="stFormSubmitButton"] button:disabled *,
        div[data-testid="stDownloadButton"] button:disabled * {
            color:inherit;
        }
    </style>
    """, unsafe_allow_html=True)

col_tema_spacer, col_tema_claro, col_tema_escuro = st.columns([8, 1, 1])
with col_tema_claro:
    if st.button(
        "☀️ Claro",
        key="btn_tema_claro",
        use_container_width=True,
        disabled=st.session_state.tema_visual == "claro",
    ):
        st.session_state.tema_visual = "claro"
        st.rerun()
with col_tema_escuro:
    if st.button(
        "🌙 Escuro",
        key="btn_tema_escuro",
        use_container_width=True,
        disabled=st.session_state.tema_visual == "escuro",
    ):
        st.session_state.tema_visual = "escuro"
        st.rerun()

st.markdown("""
<div class="main-header">
    <h1>📊 Análise de Despesas por Conta Contábil</h1>
    <p>Executa Análise a Agrupamento por Contas Contábeis,  Classificação e cálculo do  Custo Operacional</p>
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


@st.dialog("Base de classificação não encontrada", width="small")
def _abrir_aviso_base_ausente(nome_base):
    st.warning(
        f"A base de classificação `{nome_base}` não foi encontrada na pasta do sistema."
    )
    st.markdown(
        "Sem essa base, as contas contábeis serão marcadas como "
        "**PENDENTE DE CLASSIFICAÇÃO** após o processamento."
    )
    st.markdown(
        "Será necessário revisar e classificar as contas manualmente na aba "
        "**Pendências de Classificação**."
    )
    if st.button("Entendi", key="btn_confirmar_base_ausente", use_container_width=True):
        st.session_state.base_ausente_popup_exibido = True
        st.rerun()


@st.dialog("Contas de salários agrupadas")
def _abrir_aviso_agrupamento_salarios(agrupamento):
    conta_destino = agrupamento["conta_destino"]
    st.info(
        f"As contas abaixo foram agrupadas automaticamente na conta **{conta_destino}**."
    )
    for item in agrupamento["detalhes"]:
        st.markdown(f"- **{item['DESCRDEB']}**: {_fmt_brl(item['VALPAGAMENTOTITULO'])}")
    st.markdown(f"**Novo valor final em {conta_destino}: {_fmt_brl(agrupamento['valor_total'])}**")
    if st.button("Entendi", key="btn_confirmar_agrupamento_salarios", use_container_width=True):
        st.session_state.agrupamento_salarios_popup_exibido = True
        st.rerun()


def _ler_base_classificacao_bytes():
    with open(BASE_CLASSIFICACAO_ARQUIVO, "rb") as arquivo:
        return arquivo.read()


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
    ("base_ausente_popup_exibido", False),
    ("agrupamento_salarios", None),
    ("agrupamento_salarios_popup_exibido", False),
]:
    if chave not in st.session_state:
        st.session_state[chave] = padrao

base_local_encontrada = os.path.isfile(BASE_CLASSIFICACAO_ARQUIVO)
base_nome_exibicao = os.path.basename(BASE_CLASSIFICACAO_ARQUIVO)

if base_local_encontrada:
    st.session_state.base_ausente_popup_exibido = False
elif not st.session_state.base_ausente_popup_exibido:
    _abrir_aviso_base_ausente(base_nome_exibicao)

# --- SIDEBAR: Filtros ---
with st.sidebar:
    st.header("🔎 Filtros da Consulta")
    with st.form("form_consulta_db2"):
        data_inicio = st.date_input("Data Inicial", value=date.today().replace(day=1), format="DD/MM/YYYY")
        data_fim = st.date_input("Data Final", value=date.today(), format="DD/MM/YYYY")
        empresas = st.multiselect(
            "Empresas",
            EMPRESAS_DISPONIVEIS,
            default=[1],
            help="Selecione um ou mais IDs de empresa. Códigos válidos: 1 a 20.",
        )
        processar = st.form_submit_button("▶ Processar")
        
    if base_local_encontrada:
        st.markdown(
            f'<div class="alert-info">✅ Base Local para Classificação de CUSTO OPERACIONAL'
            f'<br><strong>{base_nome_exibicao}</strong></div>',
            unsafe_allow_html=True,
        )
        if st.button("ⓘ Ver contas", help="Ver contas existentes na base oficial", key="btn_base_classificacao", use_container_width=True):
            _abrir_base_classificacao()
    else:
        st.markdown(
            f'<div class="alert-warning">⚠️ Base local não encontrada: <strong>{base_nome_exibicao}</strong>. '
            'Contas serão marcadas como pendentes.</div>',
            unsafe_allow_html=True,
        )

# --- PROCESSAMENTO ---
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
            st.error(erro)
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
            df_consolidado, agrupamento_salarios = consolidar(df_raw, retornar_agrupamentos=True)
            df_classificado, alertas_dup = classificar(
                df_consolidado,
                df_base,
                st.session_state.classificacoes_manuais,
            )
            indicadores = calcular_indicadores(df_classificado, faturamento)
            ods_bytes, ods_pend_bytes = exportar_ods(df_classificado, indicadores, faturamento)

            progress.progress(100, text="✅ Concluído!")
            progress.empty()

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
            st.session_state.agrupamento_salarios = agrupamento_salarios
            st.session_state.agrupamento_salarios_popup_exibido = False
            st.session_state.pop("perguntar_salvar_base", None)

            if aviso_vazio:
                st.session_state.alertas_resultado.append(
                    "Nenhuma linha válida retornada após remover contas ignoradas."
                )

            st.toast("Consulta processada com sucesso!", icon="✅")
            st.balloons()
        except ValueError as e:
            progress.empty()
            st.session_state.processado = False
            st.markdown(
                f'<div class="validation-error">{html.escape(str(e))}</div>',
                unsafe_allow_html=True,
            )
        except Exception as e:
            progress.empty()
            st.session_state.processado = False
            st.error(f"Falha no processamento: {e}")

if (
    st.session_state.get("agrupamento_salarios")
    and not st.session_state.get("agrupamento_salarios_popup_exibido")
):
    _abrir_aviso_agrupamento_salarios(st.session_state.agrupamento_salarios)

# --- INTERFACE PRINCIPAL ---
if not st.session_state.processado:
    st.markdown("""
    <div class="empty-state">
        <h2>👋 Bem-vindo ao Painel de Análise!</h2>
        <p>Utilize a barra lateral à esquerda para selecionar as datas e empresas desejadas,<br>
        em seguida clique em "Processar" para visualizar os dados.</p>
    </div>
    """, unsafe_allow_html=True)
else:
    df = st.session_state.df_classificado
    ind = st.session_state.indicadores

    for alerta in st.session_state.get("alertas_resultado", []):
        st.warning(f"⚠️ {alerta}")

    df_pend = df[df["TIPO DE CUSTO"] == "PENDENTE DE CLASSIFICAÇÃO"].copy()
    pendentes_count = len(df_pend)
    precisa_classificar_para_dashboard = not base_local_encontrada and pendentes_count > 0
    
    # Determina as abas baseadas na existência de pendências
    nomes_abas = ["📊  Dashboard Geral ", "📋  Tabela de Despesas ", "⬇️   Downloads & Base "]
    if pendentes_count > 0:
        nomes_abas.insert(2, "🏷️   Pendências de Classificação ")
        
    abas = st.tabs(nomes_abas)

    def fmt_brl_style(v):
        if pd.isna(v):
            return ""
        return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        
    def fmt_pct_style(v):
        if pd.isna(v):
            return ""
        return f"{v:.2f}%".replace(".", ",")

    # ABA 1: Dashboard Geral
    with abas[0]:
        st.markdown('<p class="section-title">📈 Indicadores</p>', unsafe_allow_html=True)
        _exibir_cards_indicadores(ind, pendentes_count)
        
        st.markdown("<br>", unsafe_allow_html=True)

        if precisa_classificar_para_dashboard:
            st.warning(
                "Para exibir os gráficos, primeiro é necessário efetuar a classificação "
                "dos Custos Operacionais na aba **Pendências de Classificação**."
            )
        else:
            col_grafico1, col_grafico2 = st.columns(2)
            
            with col_grafico1:
                st.markdown('<p class="section-title">🍕 Composição de Despesas</p>', unsafe_allow_html=True)
                # Montar DataFrame simplificado para o gráfico
                custo_op = ind['custo_operacional']
                outras_despesas = ind['total_despesas'] - custo_op
                
                df_grafico1 = pd.DataFrame({
                    "Categoria": ["Custo Operacional", "Outras Despesas"],
                    "Valor": [custo_op, outras_despesas]
                })
                
                fig1 = px.pie(
                    df_grafico1,
                    values="Valor",
                    names="Categoria",
                    hole=0.4,
                    color_discrete_sequence=["#2d6a9f", "#e2e8f0"],
                    template=PLOTLY_TEMPLATE,
                )
                fig1.update_traces(textposition='inside', textinfo='percent+label')
                fig1.update_layout(margin=dict(t=0, b=0, l=0, r=0), showlegend=False)
                st.plotly_chart(fig1, use_container_width=True)
                
            with col_grafico2:
                st.markdown('<p class="section-title">🏆 Top 10 Maiores Despesas</p>', unsafe_allow_html=True)
                # Ordenar por valor da despesa
                df_top10 = df[df["TIPO DE CUSTO"] != "IGNORAR"].nlargest(10, "VALPAGAMENTOTITULO")
                fig2 = px.bar(
                    df_top10,
                    x="VALPAGAMENTOTITULO",
                    y="DESCRDEB",
                    orientation='h',
                    labels={"VALPAGAMENTOTITULO": "Valor (R$)", "DESCRDEB": "Conta"},
                    color_discrete_sequence=["#1e3a5f"],
                    template=PLOTLY_TEMPLATE,
                )
                fig2.update_layout(yaxis={'categoryorder':'total ascending'}, margin=dict(t=0, b=0, l=0, r=0))
                st.plotly_chart(fig2, use_container_width=True)

            st.markdown("<br>", unsafe_allow_html=True)
            st.markdown('<p class="section-title">🏭 Todos os Custos Operacionais</p>', unsafe_allow_html=True)
            df_operacional = df[df["TIPO DE CUSTO"] == "C.OPERACIONAL"].sort_values("VALPAGAMENTOTITULO", ascending=False)
            if not df_operacional.empty:
                fig3 = px.bar(
                    df_operacional,
                    x="VALPAGAMENTOTITULO",
                    y="DESCRDEB",
                    orientation='h',
                    labels={"VALPAGAMENTOTITULO": "Valor (R$)", "DESCRDEB": "Conta"},
                    color_discrete_sequence=["#16a34a"],
                    template=PLOTLY_TEMPLATE,
                )
                fig3.update_layout(yaxis={'categoryorder':'total ascending'}, margin=dict(t=0, b=0, l=0, r=0))
                st.plotly_chart(fig3, use_container_width=True)
            else:
                st.info("Nenhum custo operacional encontrado.")


    # ABA 2: Tabela de Despesas
    with abas[1]:
        st.markdown('<p class="section-title">📋 Detalhamento Consolidado</p>', unsafe_allow_html=True)
        df_exibir = df.copy()

        col_configs = {col: st.column_config.Column(alignment="center") for col in df_exibir.columns}
        col_configs.update({
            "VALPAGAMENTOTITULO": st.column_config.Column("Valor (R$)", alignment="center"),
            "% SOBRE FATURAMENTO": st.column_config.Column("% Fat.", alignment="center"),
            "DATA INICIO": st.column_config.DateColumn("Início", format="DD/MM/YYYY", alignment="center"),
            "DATA FIM": st.column_config.DateColumn("Fim", format="DD/MM/YYYY", alignment="center"),
        })
        
        st.dataframe(
            df_exibir.style
            .apply(_colorir_linha, axis=1)
            .format({
                "VALPAGAMENTOTITULO": fmt_brl_style,
                "% SOBRE FATURAMENTO": fmt_pct_style
            }),
            use_container_width=True,
            height=600,
            column_config=col_configs
        )

    # ABA 3: Pendências (Opcional) ou Downloads
    idx_prox_aba = 2
    if pendentes_count > 0:
        with abas[idx_prox_aba]:
            st.markdown('<p class="section-title">🏷️ Classificação Manual de Pendências</p>', unsafe_allow_html=True)
            st.info("⚠️ Existem contas sem classificação. Selecione o tipo de custo em cada linha e salve para recalcular.")
            
            df_edit = df_pend[["DESCRDEB", "VALPAGAMENTOTITULO"]].copy()
            df_edit.rename(columns={"DESCRDEB": "Conta", "VALPAGAMENTOTITULO": "Valor (R$)"}, inplace=True)
            df_edit = df_edit.sort_values("Valor (R$)", ascending=False).reset_index(drop=True)

            escolhas = {}
            opcoes_classificacao = ["Selecionar...", "C.OPERACIONAL", "NÃO OPERACIONAL"]

            with st.form("form_classificacao_pendencias"):
                st.markdown("**Conta contábil** &nbsp;&nbsp;&nbsp;&nbsp; **Valor**", unsafe_allow_html=True)

                for idx, row in df_edit.iterrows():
                    conta = str(row["Conta"])
                    valor = row["Valor (R$)"]
                    classificacao_atual = st.session_state.classificacoes_manuais.get(conta, "Selecionar...")
                    if classificacao_atual not in opcoes_classificacao:
                        classificacao_atual = "Selecionar..."
                    cor_linha = "#ffffff" if idx % 2 == 0 else "#a9baae"
                    chave_conta = re.sub(r"[^A-Za-z0-9_-]+", "_", conta)

                    st.markdown(
                        f"""
                        <div class="pending-row" style="background:{cor_linha};">
                            <div>
                                <strong>Conta contábil</strong>
                                <div class="pending-account">{html.escape(conta)}</div>
                            </div>
                            <div class="pending-value">
                                <strong>Valor</strong>
                                {_fmt_brl(valor)}
                            </div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )
                    escolha = st.radio(
                        "Tipo de custo",
                        opcoes_classificacao,
                        index=opcoes_classificacao.index(classificacao_atual),
                        key=f"radio_pendente_{chave_conta}_{idx}",
                        horizontal=True,
                        label_visibility="collapsed",
                    )
                    escolhas[conta] = escolha

                salvar_pendencias = st.form_submit_button("✅ Salvar e Recalcular Pendências", type="primary")
            
            if salvar_pendencias:
                novas_classificacoes = {}
                falhas = []
                for conta, cls in escolhas.items():
                    if cls in ["C.OPERACIONAL", "NÃO OPERACIONAL"]:
                        novas_classificacoes[conta] = cls
                    else:
                        falhas.append(conta)
                        
                if falhas:
                    st.error(f"Faltam {len(falhas)} conta(s) a classificar. Finalize todas as contas na tabela acima.")
                else:
                    st.session_state.classificacoes_manuais.update(novas_classificacoes)
                    _recalcular_resultado()
                    st.session_state.perguntar_salvar_base = True
                    st.rerun()

        idx_prox_aba += 1
            
    # ABA Downloads & Base
    with abas[idx_prox_aba]:
        st.markdown('<p class="section-title">⬇️ Downloads de Relatórios</p>', unsafe_allow_html=True)
        col_d1, col_d2 = st.columns(2)

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
                st.info("Nenhuma pendência neste período")

        st.markdown("<hr>", unsafe_allow_html=True)
        st.markdown('<p class="section-title">📚 Base Oficial Atual do Sistema</p>', unsafe_allow_html=True)
        if base_local_encontrada:
            st.info(
                f"Esta é a base atual usada pelo sistema para classificar as contas contábeis: "
                f"{base_nome_exibicao}"
            )
            col_base_atual_preview, col_base_atual_download = st.columns(2)
            with col_base_atual_preview:
                if st.button(
                    "👁️ Visualizar Base Atual",
                    help="Pré-visualizar as contas e classificações da base oficial atual",
                    key="btn_base_classificacao_downloads",
                    use_container_width=True,
                ):
                    _abrir_base_classificacao()
            with col_base_atual_download:
                st.download_button(
                    "📥 Baixar Base Atual do Sistema",
                    data=_ler_base_classificacao_bytes(),
                    file_name=base_nome_exibicao,
                    mime="application/vnd.oasis.opendocument.spreadsheet",
                    key="download_base_classificacao_atual",
                    use_container_width=True,
                )
        else:
            st.warning(
                f"A base oficial atual não foi encontrada: {base_nome_exibicao}. "
                "O download ficará disponível quando o arquivo estiver na pasta do sistema."
            )

        # Bloco da revisão da base
        st.markdown("<hr>", unsafe_allow_html=True)
        st.markdown('<p class="section-title">💾 Atualizar Base de Classificação</p>', unsafe_allow_html=True)
        if st.session_state.get("perguntar_salvar_base"):
            st.warning("⚠️ Este arquivo não substitui automaticamente a base oficial. Alguém deve revisar as novas classificações antes de substituir a base oficial.")
            
            col_save1, col_save2 = st.columns(2)
            with col_save1:
                if st.button("🔄 Gerar nova Base para Revisão"):
                    st.session_state.ods_base_bytes = gerar_base_atualizada(
                        st.session_state.get("df_base_original"),
                        st.session_state.classificacoes_manuais,
                    )
                    st.session_state.perguntar_salvar_base = False
                    st.rerun()
            
        if st.session_state.ods_base_bytes:
            st.download_button(
                "💾 Baixar Base para Revisão",
                data=st.session_state.ods_base_bytes,
                file_name=NOME_BASE_REVISAO,
                mime="application/vnd.oasis.opendocument.spreadsheet",
                use_container_width=True,
                type="primary"
            )
        elif not st.session_state.get("perguntar_salvar_base"):
             st.info("Faça classificações manuais para habilitar a geração de uma nova base de revisão.")
