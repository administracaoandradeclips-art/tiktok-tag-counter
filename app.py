import os
import time
import requests
import pandas as pd
import streamlit as st
from datetime import datetime, timezone

# TikTok Tag Counter — dashboard visual + coleta assíncrona via Apify
st.set_page_config(page_title="TikTok Tag Counter", page_icon="🎵", layout="wide")

APIFY_BASE = "https://api.apify.com/v2"
ACTOR_ID = "poidata~tiktok-scraper"

# ---------- Visual ----------
st.markdown("""
<style>
:root { color-scheme: dark; }
.stApp {
  background: radial-gradient(ellipse at 15% 0%, #111c4a 0%, #050d1c 42%, #020712 100%);
  color: #eaf1ff;
}
[data-testid="stSidebar"] {
  background: linear-gradient(180deg,#061426 0%,#071022 100%);
  border-right: 1px solid #17335a;
}
.block-container { padding-top: 1.2rem; max-width: 1600px; }
h1,h2,h3 { color:#f3f7ff !important; }
p, label, .stMarkdown { color:#d7e4ff; }
.hero {
  padding: 1.5rem 1.7rem; border-radius: 18px;
  background: linear-gradient(110deg,rgba(91,48,210,.42),rgba(12,75,135,.26));
  border: 1px solid #3457a6; box-shadow: 0 0 30px rgba(66,94,255,.12);
  margin-bottom: 1rem;
}
.pill { display:inline-block; border:1px solid #3b78b8; background:#112b49;
  color:#55f0c2; border-radius:30px; padding:4px 12px; font-size:.82rem; font-weight:700; }
.metric-card {
  background: linear-gradient(145deg,#0b1a31,#071225);
  border:1px solid #1a3760; border-radius:15px; padding:15px 17px;
  min-height:110px; box-shadow:0 8px 24px rgba(0,0,0,.12);
}
.metric-label { color:#9eb7dc; font-size:.85rem; }
.metric-value { font-size:1.65rem; font-weight:800; color:#f3f7ff; margin-top:5px; }
.section-card { background:rgba(5,17,34,.84); border:1px solid #18365d;
  border-radius:16px; padding:16px; margin-bottom:14px; }
div[data-testid="stDataFrame"] { border:1px solid #1b3a62; border-radius:12px; overflow:hidden; }
.stButton > button {
  border-radius:10px; font-weight:700; border:1px solid #3b65ba;
  background:linear-gradient(100deg,#623bfa,#168fd6); color:white;
}
.stButton > button:hover { border-color:#64d8ff; color:white; }
small { color:#8ca9d3 !important; }
</style>
""", unsafe_allow_html=True)

def apify_token():
    try:
        return st.secrets["APIFY_TOKEN"]
    except Exception:
        return os.getenv("APIFY_TOKEN", "")

def fmt_num(n):
    try:
        return f"{int(float(n)):,}".replace(",", ".")
    except Exception:
        return "—"

def api_headers(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

def start_run(token, username, hashtag, max_items):
    # Mantém um payload comum para o actor. Se o actor mudar de schema, a mensagem da API será exibida.
    payload = {
        "profiles": [username] if username else [],
        "hashtags": [hashtag.lstrip("#")] if hashtag else [],
        "maxItems": int(max_items),
        "maxItemsPerQuery": int(max_items),
        "sortBy": "latest",
    }
    r = requests.post(f"{APIFY_BASE}/acts/{ACTOR_ID}/runs",
                      headers=api_headers(token), json=payload, timeout=30)
    if not r.ok:
        raise RuntimeError(f"Apify respondeu HTTP {r.status_code}: {r.text[:700]}")
    data = r.json().get("data", {})
    run_id = data.get("id")
    if not run_id:
        raise RuntimeError("A API não retornou o ID da coleta.")
    return run_id

def get_run(token, run_id):
    r = requests.get(f"{APIFY_BASE}/actor-runs/{run_id}",
                     headers=api_headers(token), timeout=20)
    if not r.ok:
        raise RuntimeError(f"Erro ao consultar coleta (HTTP {r.status_code}): {r.text[:400]}")
    return r.json().get("data", {})

def get_dataset(token, dataset_id):
    r = requests.get(f"{APIFY_BASE}/datasets/{dataset_id}/items",
                     headers=api_headers(token), params={"format":"json","clean":"true"},
                     timeout=45)
    if not r.ok:
        raise RuntimeError(f"Erro ao baixar resultados (HTTP {r.status_code}): {r.text[:400]}")
    return r.json()

def first_value(row, keys, default=None):
    for key in keys:
        value = row.get(key)
        if value is not None and value != "":
            return value
    return default

def normalize_items(items):
    rows = []
    for item in items or []:
        author = item.get("authorMeta") or item.get("author") or item.get("authorInfo") or {}
        if not isinstance(author, dict):
            author = {}
        stats = item.get("stats") or {}
        if not isinstance(stats, dict):
            stats = {}
        username = first_value(author, ["name","uniqueId","username","userName"],
                               first_value(item, ["authorName","username","uniqueId"], "desconhecido"))
        views = first_value(item, ["playCount","viewCount","views"], first_value(stats, ["playCount","viewCount","views"], 0))
        likes = first_value(item, ["diggCount","likeCount","likes"], first_value(stats, ["diggCount","likeCount","likes"], 0))
        comments = first_value(item, ["commentCount","comments"], first_value(stats, ["commentCount","comments"], 0))
        shares = first_value(item, ["shareCount","shares"], first_value(stats, ["shareCount","shares"], 0))
        created = first_value(author, ["createdAt","createTime","accountCreatedAt","created_at","userCreateTime"])
        caption = first_value(item, ["text","desc","description","caption"], "")
        url = first_value(item, ["webVideoUrl","url","videoUrl"], "")
        try: views = int(views or 0)
        except Exception: views = 0
        try: likes = int(likes or 0)
        except Exception: likes = 0
        try: comments = int(comments or 0)
        except Exception: comments = 0
        try: shares = int(shares or 0)
        except Exception: shares = 0
        engagement = (likes + comments + shares) / views * 100 if views > 0 else 0
        created_days = None
        if created:
            try:
                if isinstance(created, (int, float)):
                    ts = float(created)
                    if ts > 10**12: ts /= 1000
                    dt = datetime.fromtimestamp(ts, tz=timezone.utc)
                else:
                    dt = datetime.fromisoformat(str(created).replace("Z","+00:00"))
                    if dt.tzinfo is None: dt = dt.replace(tzinfo=timezone.utc)
                created_days = max(0, (datetime.now(timezone.utc)-dt.astimezone(timezone.utc)).days)
            except Exception:
                created_days = None
        rows.append({
            "Perfil": str(username).lstrip("@"),
            "Legenda": str(caption),
            "Visualizações": views,
            "Curtidas": likes,
            "Comentários": comments,
            "Compartilhamentos": shares,
            "Engajamento (%)": round(engagement, 2),
            "Dias da conta": created_days,
            "Link": url,
        })
    return pd.DataFrame(rows)

def detect_suspicious(df, age_days, min_views, max_engagement):
    if df.empty:
        return df
    result = df.copy()
    result["Conta recente"] = result["Dias da conta"].apply(
        lambda x: pd.notna(x) and x <= age_days)
    result["Views altas + engajamento baixo"] = (
        (result["Visualizações"] >= min_views) &
        (result["Engajamento (%)"] <= max_engagement)
    )
    result["Sinais suspeitos"] = result[["Conta recente","Views altas + engajamento baixo"]].sum(axis=1)
    result["Classificação"] = result["Sinais suspeitos"].map(
        {2:"Alto — 2 sinais",1:"Atenção — 1 sinal",0:"Sem sinal detectado"})
    return result

if "items" not in st.session_state: st.session_state.items = []
if "run_id" not in st.session_state: st.session_state.run_id = None
if "monitoring" not in st.session_state: st.session_state.monitoring = False
if "last_started" not in st.session_state: st.session_state.last_started = 0.0
if "last_collection" not in st.session_state: st.session_state.last_collection = 0.0
if "status" not in st.session_state: st.session_state.status = "Pronto para iniciar"
if "error" not in st.session_state: st.session_state.error = ""

with st.sidebar:
    st.markdown("## 🎵 TikTok Tag Counter")
    st.caption("Monitoramento inteligente de vídeos")
    st.divider()
    st.markdown("### 🔎 Configurações da busca")
    username = st.text_input("Perfil do TikTok (@)", value="cortesbatalhasdosfamosos").strip().lstrip("@")
    hashtag = st.text_input("Hashtag", value="Casalcheck2Clips5K").strip().lstrip("#")
    max_items = st.selectbox("Máximo de itens por coleta", [100, 250, 500, 1000], index=2)
    st.markdown("### 🕵️ Filtros de análise")
    age_days = st.selectbox("Considerar conta recente até", [7,14,30,60,90], index=1, format_func=lambda x:f"{x} dias")
    min_views = st.number_input("Visualizações mínimas", min_value=1000, max_value=10000000, value=50000, step=5000)
    max_engagement = st.slider("Engajamento máximo suspeito (%)", 0.1, 10.0, 5.0, 0.1)
    st.caption("A criação da conta só pode ser avaliada se o actor devolver essa informação.")
    st.divider()
    token = apify_token()
    if token:
        st.success("Token Apify configurado")
    else:
        st.warning("Configure APIFY_TOKEN em Streamlit Secrets.")
    if st.button("▶ Iniciar monitoramento", use_container_width=True, disabled=not bool(token)):
        st.session_state.monitoring = True
        st.session_state.error = ""
        st.session_state.status = "Iniciando coleta…"
        st.session_state.last_started = 0.0
        st.rerun()
    if st.button("■ Parar monitoramento", use_container_width=True):
        st.session_state.monitoring = False
        st.session_state.status = "Monitoramento parado pelo usuário"
        st.rerun()
    st.caption("A coleta seguinte só começa quando a anterior termina e respeita um intervalo mínimo de 60 segundos.")

st.markdown("""
<div class="hero">
  <span class="pill">● PAINEL DE MONITORAMENTO</span>
  <h1 style="margin:.7rem 0 .25rem 0;">TikTok Tag Counter</h1>
  <p style="margin:0;">Acompanhe vídeos, analise engajamento e encontre sinais que merecem uma segunda olhada.</p>
</div>
""", unsafe_allow_html=True)

# Async start/poll: UI remains responsive; status is checked every 5 seconds.
if st.session_state.monitoring and token:
    now = time.time()
    if not st.session_state.run_id and (now - st.session_state.last_started >= 60):
        try:
            st.session_state.run_id = start_run(token, username, hashtag, max_items)
            st.session_state.last_started = now
            st.session_state.status = "Coleta iniciada no Apify"
            st.session_state.error = ""
        except Exception as e:
            st.session_state.error = str(e)
            st.session_state.status = "Falha ao iniciar coleta"
            st.session_state.monitoring = False
    if st.session_state.run_id:
        try:
            run_data = get_run(token, st.session_state.run_id)
            run_status = run_data.get("status", "UNKNOWN")
            st.session_state.status = f"Coleta: {run_status}"
            if run_status in ("SUCCEEDED",):
                dataset_id = run_data.get("defaultDatasetId")
                if dataset_id:
                    st.session_state.items = get_dataset(token, dataset_id)
                    st.session_state.last_collection = time.time()
                st.session_state.run_id = None
                st.session_state.status = f"Última coleta concluída às {datetime.now().strftime('%H:%M:%S')}"
            elif run_status in ("FAILED","ABORTED","TIMED-OUT"):
                st.session_state.error = f"A coleta terminou com status {run_status}."
                st.session_state.run_id = None
                st.session_state.status = "Coleta não concluída"
        except Exception as e:
            st.session_state.error = str(e)

# Render fragment for status refresh without full page refresh (Streamlit >=1.37)
@st.fragment(run_every="5s" if st.session_state.monitoring else None)
def status_panel():
    active = st.session_state.monitoring
    color = "#39e6b0" if active else "#91a9ca"
    col1, col2, col3 = st.columns([1.2, 2.2, 1])
    with col1:
        st.markdown(f'<div class="metric-card"><div class="metric-label">Status</div><div class="metric-value" style="font-size:1.15rem;color:{color}">{"● Ativo" if active else "○ Parado"}</div></div>', unsafe_allow_html=True)
    with col2:
        st.markdown(f'<div class="metric-card"><div class="metric-label">Última atualização</div><div class="metric-value" style="font-size:1.15rem">{st.session_state.status}</div></div>', unsafe_allow_html=True)
    with col3:
        st.markdown(f'<div class="metric-card"><div class="metric-label">Intervalo</div><div class="metric-value" style="font-size:1.15rem">5 s / 60 s</div><small>Status / nova coleta</small></div>', unsafe_allow_html=True)
    if st.session_state.error:
        st.error(st.session_state.error)
status_panel()

raw_df = normalize_items(st.session_state.items)
df = detect_suspicious(raw_df, age_days, int(min_views), float(max_engagement))

total_videos = len(raw_df)
views_total = int(raw_df["Visualizações"].sum()) if not raw_df.empty else 0
likes_total = int(raw_df["Curtidas"].sum()) if not raw_df.empty else 0
comments_total = int(raw_df["Comentários"].sum()) if not raw_df.empty else 0
shares_total = int(raw_df["Compartilhamentos"].sum()) if not raw_df.empty else 0
suspicious_count = int((df["Sinais suspeitos"] > 0).sum()) if not df.empty and "Sinais suspeitos" in df else 0

metrics = [
    ("🎬 Vídeos encontrados", fmt_num(total_videos)),
    ("👁 Visualizações totais", fmt_num(views_total)),
    ("💜 Curtidas totais", fmt_num(likes_total)),
    ("💬 Comentários totais", fmt_num(comments_total)),
    ("⚠️ Itens com sinais", fmt_num(suspicious_count)),
]
cols = st.columns(5)
for col, (label, value) in zip(cols, metrics):
    with col:
        st.markdown(f'<div class="metric-card"><div class="metric-label">{label}</div><div class="metric-value">{value}</div></div>', unsafe_allow_html=True)

st.markdown("")
left, right = st.columns([1.2, 1])
with left:
    st.markdown('<div class="section-card">', unsafe_allow_html=True)
    st.subheader("🕵️ Análise de sinais suspeitos")
    if df.empty:
        st.info("Inicie uma coleta para visualizar a análise. Os indicadores são heurísticos e não comprovam compra de views ou bots.")
    else:
        counts = df["Classificação"].value_counts().rename_axis("Sinal").reset_index(name="Quantidade")
        st.bar_chart(counts.set_index("Sinal"), height=220)
        st.caption(f"{suspicious_count} item(ns) com pelo menos um sinal entre {total_videos} vídeos retornados.")
    st.markdown('</div>', unsafe_allow_html=True)
with right:
    st.markdown('<div class="section-card">', unsafe_allow_html=True)
    st.subheader("📈 Resumo do engajamento")
    if df.empty:
        st.info("As métricas aparecerão depois da primeira coleta.")
    else:
        avg_eng = float(df["Engajamento (%)"].mean())
        st.metric("Engajamento médio observado", f"{avg_eng:.2f}%")
        st.metric("Contas com data de criação disponível", f"{int(df['Dias da conta'].notna().sum())} / {len(df)}")
        st.caption("Taxa calculada como (curtidas + comentários + compartilhamentos) ÷ visualizações. Não é uma prova definitiva de autenticidade.")
    st.markdown('</div>', unsafe_allow_html=True)

st.markdown('<div class="section-card">', unsafe_allow_html=True)
st.subheader("🚨 Resultados com sinais suspeitos")
if df.empty:
    st.info("Nenhum resultado carregado ainda. Use **Iniciar monitoramento** na lateral.")
else:
    suspicious_df = df[df["Sinais suspeitos"] > 0].copy()
    display_cols = ["Perfil","Dias da conta","Visualizações","Curtidas","Comentários","Compartilhamentos","Engajamento (%)","Classificação"]
    display_cols = [c for c in display_cols if c in suspicious_df.columns]
    if suspicious_df.empty:
        st.success("Nenhum item corresponde aos filtros atuais. Isso não garante que todos os perfis sejam autênticos.")
    else:
        st.dataframe(suspicious_df[display_cols], use_container_width=True, hide_index=True)
st.markdown('</div>', unsafe_allow_html=True)

st.markdown('<div class="section-card">', unsafe_allow_html=True)
st.subheader("🎬 Vídeos encontrados")
if df.empty:
    st.info("A tabela de vídeos será preenchida após uma coleta bem-sucedida.")
else:
    st.dataframe(df, use_container_width=True, hide_index=True, column_config={
        "Link": st.column_config.LinkColumn("Abrir vídeo", display_text="Abrir")
    })
    csv = df.to_csv(index=False).encode("utf-8-sig")
    st.download_button("⬇ Exportar CSV", data=csv, file_name="tiktok_tag_counter.csv", mime="text/csv")
st.markdown('</div>', unsafe_allow_html=True)

st.caption("Nota: resultados dependem do schema e dos dados retornados pelo actor do Apify. Sinais suspeitos são estimativas para triagem, não confirmação de fraude.")
