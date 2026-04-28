"""
Processador de Despesas Contábeis
Aplicação Streamlit para consolidação e análise de despesas contábeis.
"""

import os
import re
import streamlit as st
import pandas as pd
from processamento import (
    ler_arquivo,
    ler_base_local,
    consolidar,
    classificar,
    calcular_indicadores,
    exportar_ods,
    resetar_sessao,
    gerar_base_atualizada,
    BASE_CLASSIFICACAO_ARQUIVO,   # item 6: nome configurável vindo do módulo
)

# ─── Configuração da página ───────────────────────────────────────────────────
st.set_page_config(
    page_title="Processador de Despesas Contábeis",
    page_icon="📊",
    layout="wide",
)

# ─── CSS ──────────────────────────────────────────────────────────────────────
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
        border-radius: 10px; padding: 1.2rem 1rem;
        text-align: center; box-shadow: 0 1px 4px rgba(0,0,0,.06);
    }
    .card-label { font-size:.8rem; color:#64748b; text-transform:uppercase;
                  letter-spacing:.05em; margin-bottom:.3rem; }
    .card-value { font-size:1.4rem; font-weight:700; color:#1e3a5f; }
    .card-sub   { font-size:.78rem; color:#94a3b8; margin-top:.2rem; }
    .card-pct   { font-size:.95rem; font-weight:600; color:#2d6a9f; margin-top:.2rem; }

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

    .upload-hint { font-size:.82rem; color:#64748b; margin-top:.3rem; }

    .stButton>button {
        background:#2d6a9f; color:white; border:none;
        padding:.6rem 2rem; border-radius:8px; font-weight:600; transition:background .2s;
    }
    .stButton>button:hover { background:#1e3a5f; }
</style>
""", unsafe_allow_html=True)

# ─── Cabeçalho ────────────────────────────────────────────────────────────────
st.markdown("""
<div class="main-header">
    <h1>📊 Processador de Despesas Contábeis</h1>
    <p>Consolide, classifique e analise despesas contábeis com geração automática de relatório ODS</p>
</div>
""", unsafe_allow_html=True)

# ─── Estado da sessão ─────────────────────────────────────────────────────────
for chave, padrao in [
    ("classificacoes_manuais", {}),
    ("ultimo_arquivo_id", None),
    ("df_consolidado", None),
    ("indicadores", None),
    ("processado", False),
    ("ods_bytes", None),
    ("ods_pendencias_bytes", None),
    ("ods_base_bytes", None),
]:
    if chave not in st.session_state:
        st.session_state[chave] = padrao

# ─── Upload de arquivos ───────────────────────────────────────────────────────
st.markdown('<p class="section-title">📁 Upload de Arquivos</p>', unsafe_allow_html=True)

base_local_encontrada = os.path.isfile(BASE_CLASSIFICACAO_ARQUIVO)
base_nome_exibicao = os.path.basename(BASE_CLASSIFICACAO_ARQUIVO)

arquivo_principal = st.file_uploader(
    "1. Planilha financeira *",
    type=["ods", "xlsx", "xls", "csv"],
    help="Deve conter as colunas DESCRDEB e VALPAGAMENTOTITULO",
)
st.markdown(
    '<div class="upload-hint">📂 <strong>Arraste e solte seu arquivo aqui</strong> '
    'ou clique no botão acima — formatos aceitos: ODS, XLSX, XLS, CSV</div>',
    unsafe_allow_html=True,
)

arquivo_base = None
st.markdown("<br>", unsafe_allow_html=True)

if base_local_encontrada:
    st.markdown(
        f'<div class="alert-info">✅ Base local encontrada: <strong>{base_nome_exibicao}</strong>'
        '<br>Ela será usada automaticamente. Remova ou renomeie esse arquivo para usar uma base via upload.</div>',
        unsafe_allow_html=True,
    )
else:
    arquivo_base = st.file_uploader(
        "2. Base de classificação (opcional)",
        type=["ods", "xlsx", "xls"],
        help="Deve conter as colunas DESCRDEB e TIPO DE CUSTO",
    )
    st.markdown(
        '<div class="upload-hint">📂 <strong>Arraste e solte seu arquivo aqui</strong> '
        'ou clique — formatos aceitos: ODS, XLSX, XLS</div>',
        unsafe_allow_html=True,
    )

# ─── Resetar sessão ao trocar arquivo ─────────────────────────────────────────
if arquivo_principal is not None:
    arquivo_id = (arquivo_principal.name, arquivo_principal.size)
    if arquivo_id != st.session_state.ultimo_arquivo_id:
        resetar_sessao(st.session_state)
        st.session_state.ultimo_arquivo_id = arquivo_id

# ─── Faturamento ──────────────────────────────────────────────────────────────
st.markdown('<p class="section-title">💰 Parâmetros</p>', unsafe_allow_html=True)

col_fat, col_fat_ok = st.columns([2, 3])

faturamento_input = 0.0
faturamento_valido = False

def _parse_moeda(valor: str) -> float:
    s = re.sub(r"R\$\s*", "", valor).strip().replace(" ", "")
    if "," in s and "." in s:
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif re.match(r"^\d+(,\d+)?$", s):
        s = s.replace(",", ".")
    elif re.match(r"^\d{1,3}(,\d{3})+(\.\d+)?$", s):
        s = s.replace(",", "")
    elif re.match(r"^\d{1,3}(\.\d{3})+$", s):
        s = s.replace(".", "")
    return float(s)

def _fmt_brl_input(v):
    return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def _formatar_faturamento_digitado():
    valor = st.session_state.get("faturamento_str", "").strip()
    if not valor:
        return

    somente_digitos = re.sub(r"\D", "", valor)
    try:
        if re.fullmatch(r"(R\$\s*)?\d+", valor.replace(" ", "")) and somente_digitos:
            numero = int(somente_digitos) / 100
        else:
            numero = _parse_moeda(valor)
        st.session_state.faturamento_str = _fmt_brl_input(numero)
    except Exception:
        pass

with col_fat:
    faturamento_str = st.text_input(
        "Faturamento total do período *",
        key="faturamento_str",
        placeholder="Digite por exemplo R$ 150.000,00",
        help="Digite apenas números ou informe o valor completo. Ex: 15000000 ou R$ 150.000,00.",
        on_change=_formatar_faturamento_digitado,
    )

if faturamento_str.strip():
    try:
        faturamento_input = _parse_moeda(faturamento_str)
        faturamento_valido = faturamento_input > 0

        with col_fat_ok:
            if faturamento_valido:
                st.markdown(
                    f'<div style="padding-top:1.9rem;color:#16a34a;font-weight:600;">'
                    f'✔ {_fmt_brl_input(faturamento_input)}</div>',
                    unsafe_allow_html=True,
                )
            else:
                st.markdown(
                    '<div style="padding-top:1.9rem;color:#dc2626;">⚠ Deve ser maior que zero</div>',
                    unsafe_allow_html=True,
                )
    except Exception:
        with col_fat_ok:
            st.markdown(
                '<div style="padding-top:1.9rem;color:#dc2626;">⚠ Formato inválido. '
                'Use: R$ 150.000,00</div>',
                unsafe_allow_html=True,
            )

# ─── Botão processar ──────────────────────────────────────────────────────────
processar = st.button("▶ Processar Planilha")

# ─── Processamento ────────────────────────────────────────────────────────────
if processar:
    erros = []
    if arquivo_principal is None:
        erros.append("Nenhum arquivo de planilha foi enviado.")
    if not faturamento_valido or faturamento_input <= 0:
        erros.append("Faturamento inválido. Digite um valor maior que zero (Ex: R$ 150.000,00).")

    if erros:
        for e in erros:
            st.markdown(f'<div class="alert-error">❌ {e}</div>', unsafe_allow_html=True)
    else:
        progress = st.progress(0, text="Iniciando...")
        try:
            progress.progress(10, text="📥 Arquivo recebido...")

            progress.progress(30, text="📖 Lendo planilha...")
            df_raw, aviso_vazio = ler_arquivo(arquivo_principal)
            if aviso_vazio:
                st.markdown(
                    '<div class="alert-warning">⚠️ Nenhuma linha válida após remover contas ignoradas. '
                    'O processamento continuará com resultado vazio.</div>',
                    unsafe_allow_html=True,
                )

            progress.progress(50, text="🔄 Consolidando contas...")
            df_consolidado = consolidar(df_raw)

            progress.progress(70, text="🏷️ Classificando contas...")

            # Item 6: base local tem prioridade; se não existir, usa upload opcional
            df_base = None
            if base_local_encontrada:
                df_base, alertas_base = ler_base_local(BASE_CLASSIFICACAO_ARQUIVO)
                st.markdown(
                    f'<div class="alert-info">📂 Base local carregada: '
                    f'<strong>{base_nome_exibicao}</strong></div>',
                    unsafe_allow_html=True,
                )
                for a in alertas_base:
                    st.markdown(f'<div class="alert-warning">⚠️ {a}</div>', unsafe_allow_html=True)
            elif arquivo_base is not None:
                df_base, alertas_base = ler_arquivo(arquivo_base, modo_base=True)
                st.markdown(
                    '<div class="alert-info">📂 Usando base de classificação do upload.</div>',
                    unsafe_allow_html=True,
                )
                for a in alertas_base:
                    st.markdown(f'<div class="alert-warning">⚠️ {a}</div>', unsafe_allow_html=True)

            df_classificado, alertas_dup = classificar(
                df_consolidado, df_base, st.session_state.classificacoes_manuais
            )
            for a in alertas_dup:
                st.markdown(f'<div class="alert-warning">⚠️ {a}</div>', unsafe_allow_html=True)

            progress.progress(90, text="📄 Gerando arquivo ODS...")
            indicadores = calcular_indicadores(df_classificado, faturamento_input)
            ods_bytes, ods_pend_bytes = exportar_ods(df_classificado, indicadores, faturamento_input)

            progress.progress(100, text="✅ Concluído!")

            st.session_state.df_consolidado       = df_classificado
            st.session_state.indicadores          = indicadores
            st.session_state.processado           = True
            st.session_state.ods_bytes            = ods_bytes
            st.session_state.ods_pendencias_bytes = ods_pend_bytes
            st.session_state.ods_base_bytes       = None
            st.session_state.faturamento          = faturamento_input
            st.session_state.df_base_original     = df_base

            st.markdown(
                '<div class="alert-success">✅ Processamento concluído com sucesso!</div>',
                unsafe_allow_html=True,
            )

        except ValueError as e:
            progress.empty()
            st.markdown(f'<div class="alert-error">❌ Falha: {e}</div>', unsafe_allow_html=True)
        except Exception as e:
            progress.empty()
            st.markdown(f'<div class="alert-error">❌ Erro inesperado: {e}</div>', unsafe_allow_html=True)

# ─── Resultados ───────────────────────────────────────────────────────────────
if st.session_state.processado and st.session_state.indicadores:
    ind = st.session_state.indicadores
    df  = st.session_state.df_consolidado

    def fmt_brl(v):
        return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

    def fmt_pct(v):
        return f"{v:.1f}%"

    pendentes_count = int((df["TIPO DE CUSTO"] == "PENDENTE DE CLASSIFICAÇÃO").sum())

    # ── Cards de indicadores ──────────────────────────────────────────────────
    st.markdown('<p class="section-title">📈 Indicadores</p>', unsafe_allow_html=True)
    c1, c2, c3, c4, c5 = st.columns(5)

    with c1:
        st.markdown(f"""<div class="card">
            <div class="card-label">Faturamento</div>
            <div class="card-value">{fmt_brl(ind['faturamento'])}</div>
        </div>""", unsafe_allow_html=True)

    with c2:
        st.markdown(f"""<div class="card">
            <div class="card-label">Total Despesas</div>
            <div class="card-value" style="color:#dc2626">{fmt_brl(ind['total_despesas'])}</div>
            <div class="card-sub">{fmt_pct(ind['pct_despesas'])} do faturamento</div>
        </div>""", unsafe_allow_html=True)

    with c3:
        st.markdown(f"""<div class="card">
            <div class="card-label">Custo Operacional</div>
            <div class="card-value">{fmt_brl(ind['custo_operacional'])} <span class="card-pct">({fmt_pct(ind['pct_operacional'])})</span></div>
            <div class="card-sub">do faturamento</div>
        </div>""", unsafe_allow_html=True)

    with c4:
        cor = "#16a34a" if ind["saldo"] >= 0 else "#dc2626"
        st.markdown(f"""<div class="card">
            <div class="card-label">Saldo</div>
            <div class="card-value" style="color:{cor}">{fmt_brl(ind['saldo'])}</div>
            <div class="card-sub">{fmt_pct(ind['pct_saldo'])} do faturamento</div>
        </div>""", unsafe_allow_html=True)

    with c5:
        cor_p = "#d97706" if pendentes_count > 0 else "#16a34a"
        st.markdown(f"""<div class="card">
            <div class="card-label">Contas Pendentes</div>
            <div class="card-value" style="color:{cor_p}">{pendentes_count}</div>
        </div>""", unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # ── Classificação manual ──────────────────────────────────────────────────
    df_pend = df[df["TIPO DE CUSTO"] == "PENDENTE DE CLASSIFICAÇÃO"].copy()

    if not df_pend.empty:
        st.markdown('<p class="section-title">🏷️ Classificação Manual</p>', unsafe_allow_html=True)
        st.markdown(
            '<div class="alert-warning">⚠️ Existem contas sem classificação. '
            'Classifique abaixo para continuar.</div>',
            unsafe_allow_html=True,
        )

        opcoes_map = {"SIM → C.OPERACIONAL": "C.OPERACIONAL", "NÃO → NÃO OPERACIONAL": "NÃO OPERACIONAL"}
        escolhas = {}

        for _, row in df_pend.sort_values("VALPAGAMENTOTITULO", ascending=False).iterrows():
            conta = row["DESCRDEB"]
            valor = row["VALPAGAMENTOTITULO"]
            va = st.session_state.classificacoes_manuais.get(conta)
            idx = 0 if va == "C.OPERACIONAL" else (1 if va == "NÃO OPERACIONAL" else None)

            escolha = st.radio(
                f"**{conta}** — {fmt_brl(valor)}\n\nEsta conta é custo operacional?",
                options=list(opcoes_map.keys()),
                index=idx,
                key=f"radio_{conta}",
                horizontal=True,
            )
            escolhas[conta] = opcoes_map.get(escolha)

        if st.button("✅ Confirmar Classificações"):
            nao_resp = [c for c, v in escolhas.items() if v is None]
            if nao_resp:
                st.error(f"Responda todas as contas antes de confirmar: {nao_resp}")
            else:
                st.session_state.classificacoes_manuais.update(escolhas)
                df_recl, _ = classificar(
                    st.session_state.df_consolidado.copy(),
                    st.session_state.get("df_base_original"),
                    st.session_state.classificacoes_manuais,
                )
                fat = st.session_state.faturamento
                ind_novo = calcular_indicadores(df_recl, fat)
                ob, op = exportar_ods(df_recl, ind_novo, fat)
                st.session_state.df_consolidado       = df_recl
                st.session_state.indicadores          = ind_novo
                st.session_state.ods_bytes            = ob
                st.session_state.ods_pendencias_bytes = op
                st.session_state.perguntar_salvar_base = True
                st.rerun()

    # ── Salvar base ───────────────────────────────────────────────────────────
    if st.session_state.get("perguntar_salvar_base"):
        st.markdown('<p class="section-title">💾 Salvar Base de Classificação</p>', unsafe_allow_html=True)
        salvar = st.radio(
            "Deseja salvar essas classificações para uso futuro?",
            ["Não", "Sim"], horizontal=True, key="radio_salvar_base",
        )
        if salvar == "Sim" and st.button("Gerar Base Atualizada"):
            ods_base = gerar_base_atualizada(
                st.session_state.get("df_base_original"),
                st.session_state.classificacoes_manuais,
            )
            st.session_state.ods_base_bytes = ods_base
            st.session_state.perguntar_salvar_base = False
            st.rerun()

    # ── Prévia da tabela ──────────────────────────────────────────────────────
    st.markdown('<p class="section-title">📋 Prévia da Tabela Consolidada</p>', unsafe_allow_html=True)

    def colorir_linha(row):
        if row["TIPO DE CUSTO"] == "IGNORAR":
            return ["color:gray;font-style:italic"] * len(row)
        if row["TIPO DE CUSTO"] == "PENDENTE DE CLASSIFICAÇÃO":
            return ["color:#d97706;font-weight:bold"] * len(row)
        return [""] * len(row)

    df_exibir = st.session_state.df_consolidado.copy()
    df_exibir["VALPAGAMENTOTITULO"] = df_exibir["VALPAGAMENTOTITULO"].apply(fmt_brl)
    df_exibir["% SOBRE FATURAMENTO"] = df_exibir["% SOBRE FATURAMENTO"].apply(
        lambda x: f"{x:.2f}%" if pd.notna(x) else ""
    )
    st.dataframe(df_exibir.style.apply(colorir_linha, axis=1), use_container_width=True, height=400)

    # ── Downloads ─────────────────────────────────────────────────────────────
    st.markdown('<p class="section-title">⬇️ Downloads</p>', unsafe_allow_html=True)
    col_d1, col_d2, col_d3 = st.columns(3)

    with col_d1:
        if st.session_state.ods_bytes:
            st.download_button(
                "📥 Baixar ODS Consolidado",
                data=st.session_state.ods_bytes,
                file_name="consolidado.ods",
                mime="application/vnd.oasis.opendocument.spreadsheet",
                use_container_width=True,
            )
    with col_d2:
        if st.session_state.ods_pendencias_bytes:
            st.download_button(
                "⚠️ Baixar ODS Pendências",
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
                "💾 Baixar Base Atualizada",
                data=st.session_state.ods_base_bytes,
                file_name=base_nome_exibicao,
                mime="application/vnd.oasis.opendocument.spreadsheet",
                use_container_width=True,
            )
