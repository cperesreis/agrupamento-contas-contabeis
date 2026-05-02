"""
Processador de Despesas Contábeis
Aplicação Streamlit para consolidação e análise de despesas contábeis.
"""

import os
import re
import io
import zipfile

import pandas as pd
import streamlit as st

from processamento import (
    BASE_CLASSIFICACAO_ARQUIVO,
    calcular_indicadores,
    classificar,
    consolidar,
    exportar_ods,
    gerar_base_atualizada,
    ler_arquivo,
    ler_base_local,
    resetar_sessao,
)

MAX_ARQUIVOS = 20
NOME_BASE_REVISAO = "base_classificacao_para_revisao.ods"


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

    div[data-testid="stDialog"] div[role="dialog"] {
        width: min(96vw, 1400px);
        max-width: 96vw;
    }

    div[data-testid="stTabs"] [role="tablist"] {
        gap: .35rem;
        background:#f1f5f9;
        border:1px solid #e2e8f0;
        border-radius:8px;
        padding:.35rem;
    }
    div[data-testid="stTabs"] button[role="tab"] {
        background:#e5e7eb;
        border-radius:6px;
        padding:.55rem .9rem;
        min-height:2.7rem;
    }
    div[data-testid="stTabs"] button[role="tab"] p {
        font-size:1rem;
        font-weight:700;
        color:#1e3a5f;
    }
    div[data-testid="stTabs"] button[role="tab"][aria-selected="true"] {
        background:#ffffff;
        border:1px solid #2d6a9f;
    }
    div[data-testid="stTabs"] button[role="tab"][aria-selected="true"] p {
        color:#1e3a5f;
    }

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


# ─── Helpers ─────────────────────────────────────────────────────────────────
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


def _fmt_brl(v):
    return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _fmt_pct(v):
    return f"{v:.1f}%"


def _formatar_faturamento_digitado(chave: str):
    valor = st.session_state.get(chave, "").strip()
    if not valor:
        return

    somente_digitos = re.sub(r"\D", "", valor)
    try:
        if re.fullmatch(r"(R\$\s*)?\d+", valor.replace(" ", "")) and somente_digitos:
            numero = int(somente_digitos) / 100
        else:
            numero = _parse_moeda(valor)
        st.session_state[chave] = _fmt_brl(numero)
    except Exception:
        pass


def _arquivo_id(arquivo):
    return f"{arquivo.name}|{arquivo.size}"


def _arquivo_key(arquivo):
    base = re.sub(r"[^A-Za-z0-9_-]+", "_", _arquivo_id(arquivo))
    return base.strip("_") or "arquivo"


def _nome_seguro(nome: str, sufixo: str) -> str:
    base = os.path.splitext(os.path.basename(nome))[0]
    base = re.sub(r"[^A-Za-z0-9_-]+", "_", base).strip("_") or "relatorio"
    return f"{base}_{sufixo}.ods"


def _nomes_zip_unicos(nome_arquivo: str, usados: set) -> str:
    if nome_arquivo not in usados:
        usados.add(nome_arquivo)
        return nome_arquivo

    base, ext = os.path.splitext(nome_arquivo)
    contador = 2
    while True:
        candidato = f"{base}_{contador}{ext}"
        if candidato not in usados:
            usados.add(candidato)
            return candidato
        contador += 1


def _gerar_zip_relatorios(resultados, ods_base_bytes=None) -> bytes:
    buffer = io.BytesIO()
    nomes_usados = set()

    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as zipf:
        for item in resultados:
            nome_consolidado = _nomes_zip_unicos(
                _nome_seguro(item["nome"], "consolidado"),
                nomes_usados,
            )
            zipf.writestr(nome_consolidado, item["ods_bytes"])

            if item["ods_pendencias_bytes"]:
                nome_pendencias = _nomes_zip_unicos(
                    _nome_seguro(item["nome"], "pendencias"),
                    nomes_usados,
                )
                zipf.writestr(nome_pendencias, item["ods_pendencias_bytes"])

        if ods_base_bytes:
            zipf.writestr(
                _nomes_zip_unicos(NOME_BASE_REVISAO, nomes_usados),
                ods_base_bytes,
            )

    return buffer.getvalue()


def _resetar_lote():
    resetar_sessao(st.session_state)
    st.session_state.resultados_lote = []
    st.session_state.erros_lote = []
    st.session_state.alertas_lote = []
    st.session_state.ods_base_bytes = None
    st.session_state.pop("perguntar_salvar_base", None)


def _carregar_base_classificacao(base_local_encontrada, arquivo_base):
    df_base = None
    alertas_base = []

    if base_local_encontrada:
        df_base, alertas_base = ler_base_local(BASE_CLASSIFICACAO_ARQUIVO)
    elif arquivo_base is not None:
        df_base, alertas_base = ler_arquivo(arquivo_base, modo_base=True)

    return df_base, alertas_base


def _processar_arquivo(arquivo, faturamento, df_base):
    df_raw, aviso_vazio = ler_arquivo(arquivo)
    df_consolidado = consolidar(df_raw)
    df_classificado, alertas_dup = classificar(
        df_consolidado,
        df_base,
        st.session_state.classificacoes_manuais,
    )
    indicadores = calcular_indicadores(df_classificado, faturamento)
    ods_bytes, ods_pend_bytes = exportar_ods(df_classificado, indicadores, faturamento)

    return {
        "id": _arquivo_id(arquivo),
        "nome": arquivo.name,
        "faturamento": faturamento,
        "df_consolidado": df_consolidado,
        "df": df_classificado,
        "indicadores": indicadores,
        "ods_bytes": ods_bytes,
        "ods_pendencias_bytes": ods_pend_bytes,
        "aviso_vazio": aviso_vazio,
        "alertas": alertas_dup,
    }


def _recalcular_resultados_lote():
    novos = []
    df_base = st.session_state.get("df_base_original")

    for item in st.session_state.resultados_lote:
        df_reclassificado, alertas_dup = classificar(
            item["df_consolidado"].copy(),
            df_base,
            st.session_state.classificacoes_manuais,
        )
        indicadores = calcular_indicadores(df_reclassificado, item["faturamento"])
        ods_bytes, ods_pend_bytes = exportar_ods(
            df_reclassificado,
            indicadores,
            item["faturamento"],
        )
        novo = item.copy()
        novo.update({
            "df": df_reclassificado,
            "indicadores": indicadores,
            "ods_bytes": ods_bytes,
            "ods_pendencias_bytes": ods_pend_bytes,
            "alertas": alertas_dup,
        })
        novos.append(novo)

    st.session_state.resultados_lote = novos


def _pendencias_unicas(resultados):
    linhas = []
    for item in resultados:
        df_pend = item["df"][item["df"]["TIPO DE CUSTO"] == "PENDENTE DE CLASSIFICAÇÃO"]
        for _, row in df_pend.iterrows():
            linhas.append({
                "DESCRDEB": row["DESCRDEB"],
                "VALPAGAMENTOTITULO": row["VALPAGAMENTOTITULO"],
                "ARQUIVO": item["nome"],
            })

    if not linhas:
        return pd.DataFrame(columns=["DESCRDEB", "VALOR TOTAL", "PLANILHAS"])

    df = pd.DataFrame(linhas)
    return (
        df.groupby("DESCRDEB", as_index=False)
        .agg(
            **{
                "VALOR TOTAL": ("VALPAGAMENTOTITULO", "sum"),
                "PLANILHAS": ("ARQUIVO", lambda x: ", ".join(sorted(set(x)))),
            }
        )
        .sort_values("VALOR TOTAL", ascending=False)
        .reset_index(drop=True)
    )


def _colorir_linha(row):
    if row["TIPO DE CUSTO"] == "IGNORAR":
        return ["color:gray;font-style:italic"] * len(row)
    if row["TIPO DE CUSTO"] == "PENDENTE DE CLASSIFICAÇÃO":
        return ["color:#d97706;font-weight:bold"] * len(row)
    return [""] * len(row)


def _exibir_cards_indicadores(ind, pendentes_count, titulo="📈 Indicadores"):
    st.markdown(f'<p class="section-title">{titulo}</p>', unsafe_allow_html=True)
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
            <div class="card-value">{_fmt_brl(ind['custo_operacional'])} <span class="card-pct">({_fmt_pct(ind['pct_operacional'])})</span></div>
            <div class="card-sub">do faturamento</div>
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
    ("resultados_lote", []),
    ("erros_lote", []),
    ("alertas_lote", []),
]:
    if chave not in st.session_state:
        st.session_state[chave] = padrao

# ─── Upload de arquivos ───────────────────────────────────────────────────────
st.markdown('<p class="section-title">📁 Upload de Arquivos</p>', unsafe_allow_html=True)

base_local_encontrada = os.path.isfile(BASE_CLASSIFICACAO_ARQUIVO)
base_nome_exibicao = os.path.basename(BASE_CLASSIFICACAO_ARQUIVO)

arquivos_principais = st.file_uploader(
    "1. Planilhas financeiras *",
    type=["ods", "xlsx", "xls", "csv"],
    accept_multiple_files=True,
    help="Cada planilha deve conter as colunas DESCRDEB e VALPAGAMENTOTITULO. Limite máximo: 20 arquivos.",
)
st.markdown(
    '<div class="upload-hint">📂 <strong>Arraste e solte seus arquivos aqui</strong> '
    'ou clique no botão acima — formatos aceitos: ODS, XLSX, XLS, CSV. Limite: 20 planilhas.</div>',
    unsafe_allow_html=True,
)

arquivo_base = None
st.markdown("<br>", unsafe_allow_html=True)

if base_local_encontrada:
    col_base_msg, col_base_info, _ = st.columns([8, 1, 4])
    with col_base_msg:
        st.markdown(
            f'<div class="alert-info">✅ Base local encontrada: <strong>{base_nome_exibicao}</strong>'
            '<br>Ela será usada automaticamente para todas as planilhas. '
            'Remova ou renomeie esse arquivo para usar uma base via upload.</div>',
            unsafe_allow_html=True,
        )
    with col_base_info:
        st.markdown("<div style='height:.55rem'></div>", unsafe_allow_html=True)
        if st.button("ⓘ", help="Ver contas existentes na base oficial", key="btn_base_classificacao"):
            _abrir_base_classificacao()
else:
    arquivo_base = st.file_uploader(
        "2. Base de classificação (opcional)",
        type=["ods", "xlsx", "xls"],
        help="Deve conter as colunas DESCRDEB e TIPO DE CUSTO. Será usada para todas as planilhas.",
    )
    st.markdown(
        '<div class="upload-hint">📂 <strong>Arraste e solte sua base aqui</strong> '
        'ou clique — formatos aceitos: ODS, XLSX, XLS</div>',
        unsafe_allow_html=True,
    )

# ─── Resetar sessão ao trocar conjunto de arquivos ────────────────────────────
arquivo_ids = tuple(_arquivo_id(a) for a in arquivos_principais)
if arquivo_ids != st.session_state.ultimo_arquivo_id:
    _resetar_lote()
    st.session_state.ultimo_arquivo_id = arquivo_ids

# ─── Faturamentos ─────────────────────────────────────────────────────────────
st.markdown('<p class="section-title">💰 Faturamento por Planilha</p>', unsafe_allow_html=True)

if len(arquivos_principais) > MAX_ARQUIVOS:
    st.markdown(
        f'<div class="alert-error">❌ Envio Máximo de {MAX_ARQUIVOS} arquivos.</div>',
        unsafe_allow_html=True,
    )
elif arquivos_principais:
    faturamentos = {}
    faturamentos_validos = {}

    for arquivo in arquivos_principais:
        arquivo_id = _arquivo_id(arquivo)
        chave = f"faturamento_{_arquivo_key(arquivo)}"
        col_nome, col_valor, col_ok = st.columns([3, 2, 2])
        with col_nome:
            st.markdown(f"**{arquivo.name}**")
        with col_valor:
            valor_digitado = st.text_input(
                "Faturamento",
                key=chave,
                placeholder="R$ 150.000,00",
                help="Digite apenas números ou informe o valor completo. Ex: 15000000 ou R$ 150.000,00.",
                label_visibility="collapsed",
                on_change=_formatar_faturamento_digitado,
                args=(chave,),
            )
        with col_ok:
            if valor_digitado.strip():
                try:
                    valor = _parse_moeda(valor_digitado)
                    faturamentos[arquivo_id] = valor
                    faturamentos_validos[arquivo_id] = valor > 0
                    if valor > 0:
                        st.markdown(
                            f'<div style="padding-top:.45rem;color:#16a34a;font-weight:600;">✔ {_fmt_brl(valor)}</div>',
                            unsafe_allow_html=True,
                        )
                    else:
                        st.markdown(
                            '<div style="padding-top:.45rem;color:#dc2626;">⚠ Deve ser maior que zero</div>',
                            unsafe_allow_html=True,
                        )
                except Exception:
                    faturamentos[arquivo_id] = 0.0
                    faturamentos_validos[arquivo_id] = False
                    st.markdown(
                        '<div style="padding-top:.45rem;color:#dc2626;">⚠ Formato inválido</div>',
                        unsafe_allow_html=True,
                    )
            else:
                faturamentos[arquivo_id] = 0.0
                faturamentos_validos[arquivo_id] = False
else:
    faturamentos = {}
    faturamentos_validos = {}
    st.info("Envie uma ou mais planilhas para informar o faturamento de cada uma.")

# ─── Botão processar ──────────────────────────────────────────────────────────
processar = st.button("▶ Processar Planilhas")

# ─── Processamento ────────────────────────────────────────────────────────────
if processar:
    erros = []
    if not arquivos_principais:
        erros.append("Nenhum arquivo de planilha foi enviado.")
    if len(arquivos_principais) > MAX_ARQUIVOS:
        erros.append(f"Envio Máximo de {MAX_ARQUIVOS} arquivos.")

    for arquivo in arquivos_principais:
        if not faturamentos_validos.get(_arquivo_id(arquivo)):
            erros.append(f"Faturamento inválido para {arquivo.name}. Digite um valor maior que zero.")

    if erros:
        for e in erros:
            st.markdown(f'<div class="alert-error">❌ {e}</div>', unsafe_allow_html=True)
    else:
        progress = st.progress(0, text="Iniciando processamento em lote...")
        resultados = []
        erros_lote = []
        alertas_lote = []
        df_base = None

        try:
            progress.progress(10, text="📂 Carregando base de classificação...")
            df_base, alertas_base = _carregar_base_classificacao(base_local_encontrada, arquivo_base)
            st.session_state.df_base_original = df_base
            alertas_lote.extend(alertas_base)

            total = len(arquivos_principais)
            for idx, arquivo in enumerate(arquivos_principais, start=1):
                pct = 10 + int((idx / total) * 80)
                progress.progress(pct, text=f"Processando {idx}/{total}: {arquivo.name}")
                try:
                    resultado = _processar_arquivo(arquivo, faturamentos[_arquivo_id(arquivo)], df_base)
                    resultados.append(resultado)
                    if resultado["aviso_vazio"]:
                        alertas_lote.append(
                            f"{arquivo.name}: nenhuma linha válida após remover contas ignoradas."
                        )
                    for alerta in resultado["alertas"]:
                        alertas_lote.append(f"{arquivo.name}: {alerta}")
                except Exception as e:
                    erros_lote.append(f"{arquivo.name}: {e}")

            progress.progress(100, text="✅ Concluído!")

            st.session_state.resultados_lote = resultados
            st.session_state.erros_lote = erros_lote
            st.session_state.alertas_lote = alertas_lote
            st.session_state.processado = bool(resultados)
            st.session_state.ods_base_bytes = None
            st.session_state.pop("perguntar_salvar_base", None)

            if resultados:
                st.markdown(
                    f'<div class="alert-success">✅ {len(resultados)} planilha(s) processada(s) com sucesso.</div>',
                    unsafe_allow_html=True,
                )
            if erros_lote:
                st.markdown(
                    '<div class="alert-warning">⚠️ Algumas planilhas não foram processadas. '
                    'Veja os detalhes no resumo geral.</div>',
                    unsafe_allow_html=True,
                )
                for erro in erros_lote:
                    st.markdown(f'<div class="alert-error">❌ {erro}</div>', unsafe_allow_html=True)
        except ValueError as e:
            progress.empty()
            st.markdown(f'<div class="alert-error">❌ Falha: {e}</div>', unsafe_allow_html=True)
        except Exception as e:
            progress.empty()
            st.markdown(f'<div class="alert-error">❌ Erro inesperado: {e}</div>', unsafe_allow_html=True)

# ─── Resultados ───────────────────────────────────────────────────────────────
resultados_lote = st.session_state.get("resultados_lote", [])

if st.session_state.processado and resultados_lote:
    for alerta in st.session_state.get("alertas_lote", []):
        st.markdown(f'<div class="alert-warning">⚠️ {alerta}</div>', unsafe_allow_html=True)

    # ── Classificação manual deduplicada ──────────────────────────────────────
    df_pend_unicas = _pendencias_unicas(resultados_lote)
    if not df_pend_unicas.empty:
        st.markdown('<p class="section-title">🏷️ Classificação Manual</p>', unsafe_allow_html=True)
        st.markdown(
            '<div class="alert-warning">⚠️ Existem contas sem classificação. '
            'Cada conta aparece uma única vez abaixo, mesmo quando existe em várias planilhas.</div>',
            unsafe_allow_html=True,
        )

        opcoes_map = {"SIM → C.OPERACIONAL": "C.OPERACIONAL", "NÃO → NÃO OPERACIONAL": "NÃO OPERACIONAL"}
        escolhas = {}

        for _, row in df_pend_unicas.iterrows():
            conta = row["DESCRDEB"]
            va = st.session_state.classificacoes_manuais.get(conta)
            idx = 0 if va == "C.OPERACIONAL" else (1 if va == "NÃO OPERACIONAL" else None)

            st.caption(f"Planilhas: {row['PLANILHAS']}")
            escolha = st.radio(
                f"**{conta}** — valor total no lote: {_fmt_brl(row['VALOR TOTAL'])}\n\nEsta conta é custo operacional?",
                options=list(opcoes_map.keys()),
                index=idx,
                key=f"radio_pendente_{re.sub(r'[^A-Za-z0-9_-]+', '_', conta)}",
                horizontal=True,
            )
            escolhas[conta] = opcoes_map.get(escolha)

        if st.button("✅ Confirmar Classificações"):
            nao_resp = [c for c, v in escolhas.items() if v is None]
            if nao_resp:
                st.error(f"Responda todas as contas antes de confirmar: {nao_resp}")
            else:
                st.session_state.classificacoes_manuais.update(escolhas)
                _recalcular_resultados_lote()
                st.session_state.perguntar_salvar_base = True
                st.rerun()

    # ── Salvar base para revisão ──────────────────────────────────────────────
    if st.session_state.get("perguntar_salvar_base"):
        st.markdown('<p class="section-title">💾 Base de Classificação para Revisão</p>', unsafe_allow_html=True)
        st.markdown(
            '<div class="alert-warning">⚠️ Este arquivo não substitui automaticamente a base oficial do servidor. '
            'Alguém deve revisar as novas classificações antes de substituir a base oficial.</div>',
            unsafe_allow_html=True,
        )
        salvar = st.radio(
            "Deseja gerar uma base atualizada para revisão?",
            ["Não", "Sim"], horizontal=True, key="radio_salvar_base",
        )
        if salvar == "Sim" and st.button("Gerar Base Atualizada para Revisão"):
            ods_base = gerar_base_atualizada(
                st.session_state.get("df_base_original"),
                st.session_state.classificacoes_manuais,
            )
            st.session_state.ods_base_bytes = ods_base
            st.session_state.perguntar_salvar_base = False
            st.rerun()

    # ── Abas ─────────────────────────────────────────────────────────────────
    nomes_abas = ["Resumo Geral"] + [item["nome"][:35] for item in resultados_lote]
    abas = st.tabs(nomes_abas)

    with abas[0]:
        faturamento_total = sum(item["indicadores"]["faturamento"] for item in resultados_lote)
        despesas_total = sum(item["indicadores"]["total_despesas"] for item in resultados_lote)
        custo_op_total = sum(item["indicadores"]["custo_operacional"] for item in resultados_lote)
        saldo_total = faturamento_total - despesas_total
        pendentes_total = sum(
            int((item["df"]["TIPO DE CUSTO"] == "PENDENTE DE CLASSIFICAÇÃO").sum())
            for item in resultados_lote
        )

        indicadores_gerais = {
            "faturamento": faturamento_total,
            "total_despesas": despesas_total,
            "custo_operacional": custo_op_total,
            "saldo": saldo_total,
            "pct_despesas": (despesas_total / faturamento_total) * 100 if faturamento_total else 0,
            "pct_operacional": (custo_op_total / faturamento_total) * 100 if faturamento_total else 0,
            "pct_saldo": (saldo_total / faturamento_total) * 100 if faturamento_total else 0,
        }

        _exibir_cards_indicadores(indicadores_gerais, pendentes_total, "📈 Resumo Geral")

        c_qtd, c_pend = st.columns(2)
        with c_qtd:
            st.markdown(f"""<div class="card">
                <div class="card-label">Planilhas Processadas</div>
                <div class="card-value">{len(resultados_lote)}</div>
            </div>""", unsafe_allow_html=True)
        with c_pend:
            st.markdown(f"""<div class="card">
                <div class="card-label">Contas Pendentes Únicas</div>
                <div class="card-value" style="color:#d97706">{len(df_pend_unicas)}</div>
            </div>""", unsafe_allow_html=True)

        if st.session_state.get("erros_lote"):
            st.markdown('<p class="section-title">⚠️ Planilhas com Erro</p>', unsafe_allow_html=True)
            for erro in st.session_state.erros_lote:
                st.markdown(f'<div class="alert-error">❌ {erro}</div>', unsafe_allow_html=True)

        st.markdown('<p class="section-title">📋 Resumo por Planilha</p>', unsafe_allow_html=True)
        df_resumo = pd.DataFrame([
            {
                "Planilha": item["nome"],
                "Faturamento": item["indicadores"]["faturamento"],
                "Total Despesas": item["indicadores"]["total_despesas"],
                "% Despesas/Faturamento": item["indicadores"]["pct_despesas"],
                "Custo Operacional": item["indicadores"]["custo_operacional"],
                "% Custo Operacional/Faturamento": item["indicadores"]["pct_operacional"],
                "Saldo": item["indicadores"]["saldo"],
                "% Saldo/Faturamento": item["indicadores"]["pct_saldo"],
                "Pendências": int((item["df"]["TIPO DE CUSTO"] == "PENDENTE DE CLASSIFICAÇÃO").sum()),
            }
            for item in resultados_lote
        ])
        st.dataframe(
            df_resumo.style.format({
                "Faturamento": _fmt_brl,
                "Total Despesas": _fmt_brl,
                "Custo Operacional": _fmt_brl,
                "Saldo": _fmt_brl,
                "% Despesas/Faturamento": lambda v: f"{v:.2f}%",
                "% Custo Operacional/Faturamento": lambda v: f"{v:.2f}%",
                "% Saldo/Faturamento": lambda v: f"{v:.2f}%",
            }),
            use_container_width=True,
            height=320,
        )

        col_rank_1, col_rank_2 = st.columns(2)
        with col_rank_1:
            st.markdown('<p class="section-title">🏆 Maior Despesa Total</p>', unsafe_allow_html=True)
            df_rank_despesa = (
                df_resumo.sort_values("Total Despesas", ascending=False)
                [["Planilha", "Total Despesas", "Faturamento", "Pendências"]]
                .head(10)
                .reset_index(drop=True)
            )
            st.dataframe(
                df_rank_despesa.style.format({
                    "Total Despesas": _fmt_brl,
                    "Faturamento": _fmt_brl,
                }),
                use_container_width=True,
                height=300,
            )

        with col_rank_2:
            st.markdown('<p class="section-title">📊 Maior % de Despesa</p>', unsafe_allow_html=True)
            df_rank_pct = (
                df_resumo.sort_values("% Despesas/Faturamento", ascending=False)
                [["Planilha", "% Despesas/Faturamento", "Total Despesas", "Faturamento"]]
                .head(10)
                .reset_index(drop=True)
            )
            st.dataframe(
                df_rank_pct.style.format({
                    "% Despesas/Faturamento": lambda v: f"{v:.2f}%",
                    "Total Despesas": _fmt_brl,
                    "Faturamento": _fmt_brl,
                }),
                use_container_width=True,
                height=300,
            )

        st.markdown('<p class="section-title">⬇️ Download Completo</p>', unsafe_allow_html=True)
        zip_bytes = _gerar_zip_relatorios(
            resultados_lote,
            st.session_state.get("ods_base_bytes"),
        )
        st.download_button(
            "📦 Baixar Todos os Relatórios em ZIP",
            data=zip_bytes,
            file_name="relatorios_processamento_lote.zip",
            mime="application/zip",
            use_container_width=True,
        )

        if st.session_state.ods_base_bytes:
            st.markdown(
                '<div class="alert-info">ℹ️ Base gerada apenas para revisão. '
                'Ela não substitui automaticamente a base oficial do servidor.</div>',
                unsafe_allow_html=True,
            )
            st.download_button(
                "💾 Baixar Base Atualizada para Revisão",
                data=st.session_state.ods_base_bytes,
                file_name=NOME_BASE_REVISAO,
                mime="application/vnd.oasis.opendocument.spreadsheet",
                use_container_width=True,
            )

    for aba, item in zip(abas[1:], resultados_lote):
        with aba:
            df = item["df"]
            ind = item["indicadores"]
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
                height=400,
            )

            st.markdown('<p class="section-title">⬇️ Downloads</p>', unsafe_allow_html=True)
            col_d1, col_d2 = st.columns(2)
            with col_d1:
                st.download_button(
                    "📥 Baixar ODS Consolidado",
                    data=item["ods_bytes"],
                    file_name=_nome_seguro(item["nome"], "consolidado"),
                    mime="application/vnd.oasis.opendocument.spreadsheet",
                    use_container_width=True,
                )
            with col_d2:
                if item["ods_pendencias_bytes"]:
                    st.download_button(
                        "⚠️ Baixar ODS Pendências",
                        data=item["ods_pendencias_bytes"],
                        file_name=_nome_seguro(item["nome"], "pendencias"),
                        mime="application/vnd.oasis.opendocument.spreadsheet",
                        use_container_width=True,
                    )
                else:
                    st.info("Sem pendências")
