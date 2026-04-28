"""
Processador de Despesas Contábeis
Aplicação Streamlit para consolidação e análise de despesas contábeis.
"""

import streamlit as st
import pandas as pd
import io
from processamento import (
    ler_arquivo,
    consolidar,
    classificar,
    calcular_indicadores,
    exportar_ods,
    resetar_sessao,
)

# ─── Configuração da página ───────────────────────────────────────────────────
st.set_page_config(
    page_title="Processador de Despesas Contábeis",
    page_icon="📊",
    layout="wide",
)

# ─── CSS customizado ──────────────────────────────────────────────────────────
st.markdown("""
<style>
    .main-header {
        background: linear-gradient(135deg, #1e3a5f 0%, #2d6a9f 100%);
        padding: 2rem;
        border-radius: 12px;
        margin-bottom: 2rem;
        color: white;
        text-align: center;
    }
    .main-header h1 { margin: 0; font-size: 2.2rem; }
    .main-header p  { margin: 0.5rem 0 0 0; opacity: 0.85; font-size: 1rem; }

    .card {
        background: #f8fafc;
        border: 1px solid #e2e8f0;
        border-radius: 10px;
        padding: 1.2rem 1rem;
        text-align: center;
        box-shadow: 0 1px 4px rgba(0,0,0,.06);
    }
    .card-label { font-size: .8rem; color: #64748b; text-transform: uppercase; letter-spacing:.05em; margin-bottom:.3rem; }
    .card-value { font-size: 1.4rem; font-weight: 700; color: #1e3a5f; }
    .card-sub   { font-size: .78rem; color: #94a3b8; margin-top:.2rem; }

    .card-danger  .card-value { color: #dc2626; }
    .card-warning .card-value { color: #d97706; }
    .card-success .card-value { color: #16a34a; }

    .alert-warning {
        background: #fef9c3; border-left: 4px solid #eab308;
        padding: .8rem 1rem; border-radius: 6px; margin: 1rem 0;
    }
    .alert-success {
        background: #dcfce7; border-left: 4px solid #16a34a;
        padding: .8rem 1rem; border-radius: 6px; margin: 1rem 0;
    }
    .alert-error {
        background: #fee2e2; border-left: 4px solid #dc2626;
        padding: .8rem 1rem; border-radius: 6px; margin: 1rem 0;
    }

    .section-title {
        font-size: 1.1rem; font-weight: 600; color: #1e3a5f;
        border-bottom: 2px solid #2d6a9f; padding-bottom: .4rem; margin-bottom: 1rem;
    }
    .stButton>button {
        background: #2d6a9f; color: white; border: none;
        padding: .6rem 2rem; border-radius: 8px; font-weight: 600;
        transition: background .2s;
    }
    .stButton>button:hover { background: #1e3a5f; }
</style>
""", unsafe_allow_html=True)

# ─── Cabeçalho ────────────────────────────────────────────────────────────────
st.markdown("""
<div class="main-header">
    <h1>📊 Processador de Despesas Contábeis</h1>
    <p>Consolide, classifique e analise despesas contábeis com geração automática de relatório ODS</p>
</div>
""", unsafe_allow_html=True)

# ─── Inicialização de estado da sessão ────────────────────────────────────────
if "classificacoes_manuais" not in st.session_state:
    st.session_state.classificacoes_manuais = {}
if "ultimo_arquivo_id" not in st.session_state:
    st.session_state.ultimo_arquivo_id = None
if "df_consolidado" not in st.session_state:
    st.session_state.df_consolidado = None
if "indicadores" not in st.session_state:
    st.session_state.indicadores = None
if "processado" not in st.session_state:
    st.session_state.processado = False
if "ods_bytes" not in st.session_state:
    st.session_state.ods_bytes = None
if "ods_pendencias_bytes" not in st.session_state:
    st.session_state.ods_pendencias_bytes = None
if "ods_base_bytes" not in st.session_state:
    st.session_state.ods_base_bytes = None

# ─── Área de upload ───────────────────────────────────────────────────────────
st.markdown('<p class="section-title">📁 Upload de Arquivos</p>', unsafe_allow_html=True)

col_up1, col_up2 = st.columns(2)
with col_up1:
    arquivo_principal = st.file_uploader(
        "Planilha financeira *",
        type=["ods", "xlsx", "csv"],
        help="Deve conter as colunas DESCRDEB e VALPAGAMENTOTITULO",
    )
with col_up2:
    arquivo_base = st.file_uploader(
        "Base de classificação (opcional)",
        type=["ods", "xlsx"],
        help="Deve conter as colunas DESCRDEB e TIPO DE CUSTO",
    )

# ─── Detectar troca de arquivo → resetar sessão ───────────────────────────────
if arquivo_principal is not None:
    arquivo_id = (arquivo_principal.name, arquivo_principal.size)
    if arquivo_id != st.session_state.ultimo_arquivo_id:
        resetar_sessao(st.session_state)
        st.session_state.ultimo_arquivo_id = arquivo_id

# ─── Faturamento ──────────────────────────────────────────────────────────────
st.markdown('<p class="section-title">💰 Parâmetros</p>', unsafe_allow_html=True)

faturamento_input = st.number_input(
    "Faturamento total do período (R$) *",
    min_value=0.0,
    value=0.0,
    step=1000.0,
    format="%.2f",
    help="Valor deve ser maior que zero",
)

# ─── Botão processar ──────────────────────────────────────────────────────────
processar = st.button("▶ Processar Planilha", use_container_width=False)

# ─── Processamento principal ──────────────────────────────────────────────────
if processar:
    erros = []
    if arquivo_principal is None:
        erros.append("Nenhum arquivo de planilha foi enviado.")
    if faturamento_input <= 0:
        erros.append("Faturamento total deve ser maior que zero.")

    if erros:
        for e in erros:
            st.markdown(f'<div class="alert-error">❌ {e}</div>', unsafe_allow_html=True)
    else:
        progress = st.progress(0, text="Iniciando...")

        try:
            # 10% — arquivo recebido
            progress.progress(10, text="📥 Arquivo recebido...")

            # 30% — leitura
            progress.progress(30, text="📖 Lendo planilha...")
            df_raw, aviso_vazio = ler_arquivo(arquivo_principal)

            if aviso_vazio:
                st.markdown(
                    '<div class="alert-warning">⚠️ Nenhuma linha válida após remover contas ignoradas. '
                    "O processamento continuará, mas os resultados podem estar vazios.</div>",
                    unsafe_allow_html=True,
                )

            # 50% — consolidação
            progress.progress(50, text="🔄 Consolidando contas...")
            df_consolidado = consolidar(df_raw)

            # 70% — classificação
            progress.progress(70, text="🏷️ Classificando contas...")
            df_base = None
            if arquivo_base is not None:
                df_base, alertas_base = ler_arquivo(arquivo_base, modo_base=True)
                for alerta in alertas_base:
                    st.markdown(f'<div class="alert-warning">⚠️ {alerta}</div>', unsafe_allow_html=True)

            df_classificado, alertas_dup = classificar(
                df_consolidado,
                df_base,
                st.session_state.classificacoes_manuais,
            )
            for alerta in alertas_dup:
                st.markdown(f'<div class="alert-warning">⚠️ {alerta}</div>', unsafe_allow_html=True)

            # 90% — geração
            progress.progress(90, text="📄 Gerando arquivo ODS...")
            indicadores = calcular_indicadores(df_classificado, faturamento_input)
            ods_bytes, ods_pendencias_bytes = exportar_ods(df_classificado, indicadores, faturamento_input)

            # 100%
            progress.progress(100, text="✅ Concluído!")

            # Salvar no estado
            st.session_state.df_consolidado = df_classificado
            st.session_state.indicadores = indicadores
            st.session_state.processado = True
            st.session_state.ods_bytes = ods_bytes
            st.session_state.ods_pendencias_bytes = ods_pendencias_bytes
            st.session_state.ods_base_bytes = None
            st.session_state.faturamento = faturamento_input
            st.session_state.df_base_original = df_base

            st.markdown('<div class="alert-success">✅ Processamento concluído com sucesso!</div>', unsafe_allow_html=True)

        except ValueError as e:
            progress.empty()
            st.markdown(f'<div class="alert-error">❌ Falha no processamento: {e}</div>', unsafe_allow_html=True)
        except Exception as e:
            progress.empty()
            st.markdown(f'<div class="alert-error">❌ Falha no processamento: {e}</div>', unsafe_allow_html=True)

# ─── Exibição de resultados ───────────────────────────────────────────────────
if st.session_state.processado and st.session_state.indicadores:
    ind = st.session_state.indicadores
    df = st.session_state.df_consolidado

    # Cards de indicadores
    st.markdown('<p class="section-title">📈 Indicadores</p>', unsafe_allow_html=True)
    c1, c2, c3, c4, c5 = st.columns(5)

    def fmt_brl(v):
        return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

    def fmt_pct(v):
        return f"{v:.1f}%"

    pendentes_count = int((df["TIPO DE CUSTO"] == "PENDENTE DE CLASSIFICAÇÃO").sum())

    with c1:
        st.markdown(f"""<div class="card">
            <div class="card-label">Faturamento</div>
            <div class="card-value">{fmt_brl(ind['faturamento'])}</div>
        </div>""", unsafe_allow_html=True)
    with c2:
        st.markdown(f"""<div class="card">
            <div class="card-label">Total Despesas</div>
            <div class="card-value card-danger">{fmt_brl(ind['total_despesas'])}</div>
            <div class="card-sub">{fmt_pct(ind['pct_despesas'])} do faturamento</div>
        </div>""", unsafe_allow_html=True)
    with c3:
        st.markdown(f"""<div class="card">
            <div class="card-label">Custo Operacional</div>
            <div class="card-value">{fmt_brl(ind['custo_operacional'])}</div>
            <div class="card-sub">{fmt_pct(ind['pct_operacional'])} do faturamento</div>
        </div>""", unsafe_allow_html=True)
    with c4:
        card_class = "card-success" if ind["saldo"] >= 0 else "card-danger"
        st.markdown(f"""<div class="card {card_class}">
            <div class="card-label">Saldo</div>
            <div class="card-value">{fmt_brl(ind['saldo'])}</div>
            <div class="card-sub">{fmt_pct(ind['pct_saldo'])} do faturamento</div>
        </div>""", unsafe_allow_html=True)
    with c5:
        card_class = "card-warning" if pendentes_count > 0 else "card"
        st.markdown(f"""<div class="card {card_class}">
            <div class="card-label">Contas Pendentes</div>
            <div class="card-value">{pendentes_count}</div>
        </div>""", unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # ─── Classificação manual ─────────────────────────────────────────────────
    df_pendentes = df[df["TIPO DE CUSTO"] == "PENDENTE DE CLASSIFICAÇÃO"].copy()

    if not df_pendentes.empty:
        st.markdown('<p class="section-title">🏷️ Classificação Manual</p>', unsafe_allow_html=True)
        st.markdown(
            '<div class="alert-warning">⚠️ Existem contas sem classificação. '
            "Classifique abaixo para continuar.</div>",
            unsafe_allow_html=True,
        )

        df_pendentes_ord = df_pendentes.sort_values("VALPAGAMENTOTITULO", ascending=False)
        opcoes_map = {"SIM → C.OPERACIONAL": "C.OPERACIONAL", "NÃO → NÃO OPERACIONAL": "NÃO OPERACIONAL"}

        escolhas = {}
        for _, row in df_pendentes_ord.iterrows():
            conta = row["DESCRDEB"]
            valor = row["VALPAGAMENTOTITULO"]
            label = f"**{conta}** — {fmt_brl(valor)}"

            valor_atual = st.session_state.classificacoes_manuais.get(conta)
            idx_default = None
            if valor_atual == "C.OPERACIONAL":
                idx_default = 0
            elif valor_atual == "NÃO OPERACIONAL":
                idx_default = 1

            escolha = st.radio(
                f"{label}\n\nEsta conta é custo operacional?",
                options=list(opcoes_map.keys()),
                index=idx_default,
                key=f"radio_{conta}",
                horizontal=True,
            )
            escolhas[conta] = opcoes_map[escolha] if escolha else None

        if st.button("✅ Confirmar Classificações"):
            nao_respondidas = [c for c, v in escolhas.items() if v is None]
            if nao_respondidas:
                st.error(f"Responda todas as contas antes de confirmar: {nao_respondidas}")
            else:
                st.session_state.classificacoes_manuais.update(escolhas)

                # Re-classificar e recalcular
                df_reclassificado, _ = classificar(
                    st.session_state.df_consolidado.copy(),
                    st.session_state.get("df_base_original"),
                    st.session_state.classificacoes_manuais,
                )
                faturamento = st.session_state.faturamento
                indicadores_novo = calcular_indicadores(df_reclassificado, faturamento)
                ods_bytes, ods_pend = exportar_ods(df_reclassificado, indicadores_novo, faturamento)

                st.session_state.df_consolidado = df_reclassificado
                st.session_state.indicadores = indicadores_novo
                st.session_state.ods_bytes = ods_bytes
                st.session_state.ods_pendencias_bytes = ods_pend

                # Pergunta sobre salvar base
                st.session_state.perguntar_salvar_base = True
                st.rerun()

    # ─── Salvar base atualizada ───────────────────────────────────────────────
    if st.session_state.get("perguntar_salvar_base"):
        st.markdown('<p class="section-title">💾 Salvar Base de Classificação</p>', unsafe_allow_html=True)
        salvar = st.radio(
            "Deseja salvar essas classificações para uso futuro?",
            ["Não", "Sim"],
            horizontal=True,
            key="radio_salvar_base",
        )
        if salvar == "Sim" and st.button("Gerar Base Atualizada"):
            from processamento import gerar_base_atualizada
            df_base_orig = st.session_state.get("df_base_original")
            ods_base = gerar_base_atualizada(
                df_base_orig,
                st.session_state.classificacoes_manuais,
            )
            st.session_state.ods_base_bytes = ods_base
            st.session_state.perguntar_salvar_base = False
            st.rerun()

    # ─── Prévia da tabela ─────────────────────────────────────────────────────
    st.markdown('<p class="section-title">📋 Prévia da Tabela Consolidada</p>', unsafe_allow_html=True)

    def colorir_linha(row):
        if row["TIPO DE CUSTO"] == "IGNORAR":
            return ["color: gray; font-style: italic"] * len(row)
        elif row["TIPO DE CUSTO"] == "PENDENTE DE CLASSIFICAÇÃO":
            return ["color: #d97706; font-weight: bold"] * len(row)
        return [""] * len(row)

    df_exibir = st.session_state.df_consolidado.copy()
    df_exibir["VALPAGAMENTOTITULO"] = df_exibir["VALPAGAMENTOTITULO"].apply(fmt_brl)
    df_exibir["% SOBRE FATURAMENTO"] = df_exibir["% SOBRE FATURAMENTO"].apply(
        lambda x: f"{x:.2f}%" if pd.notna(x) else ""
    )

    st.dataframe(
        df_exibir.style.apply(colorir_linha, axis=1),
        use_container_width=True,
        height=400,
    )

    # ─── Downloads ────────────────────────────────────────────────────────────
    st.markdown('<p class="section-title">⬇️ Downloads</p>', unsafe_allow_html=True)
    col_d1, col_d2, col_d3 = st.columns(3)

    with col_d1:
        if st.session_state.ods_bytes:
            st.download_button(
                label="📥 Baixar ODS Consolidado",
                data=st.session_state.ods_bytes,
                file_name="consolidado.ods",
                mime="application/vnd.oasis.opendocument.spreadsheet",
                use_container_width=True,
            )

    with col_d2:
        if st.session_state.ods_pendencias_bytes:
            st.download_button(
                label="⚠️ Baixar ODS Pendências",
                data=st.session_state.ods_pendencias_bytes,
                file_name="pendencias.ods",
                mime="application/vnd.oasis.opendocument.spreadsheet",
                use_container_width=True,
            )
        else:
            st.info("Sem pendências")

    with col_d3:
        if st.session_state.ods_base_bytes:
            st.download_button(
                label="💾 Baixar Base Atualizada",
                data=st.session_state.ods_base_bytes,
                file_name="base_classificacao_atualizada.ods",
                mime="application/vnd.oasis.opendocument.spreadsheet",
                use_container_width=True,
            )
