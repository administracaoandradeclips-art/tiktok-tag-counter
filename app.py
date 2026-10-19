import asyncio
import time
from datetime import datetime, timezone
import pandas as pd
import streamlit as st

st.set_page_config(page_title="TikTok Tag Counter", page_icon="🎵", layout="wide")

st.markdown("""
<style>
:root { color-scheme: dark; }
.stApp { background: radial-gradient(ellipse at 15% 0%, #111c4a 0%, #050d1c 42%, #020712 100%); color:#eaf1ff; }
[data-testid="stSidebar"] { background:linear-gradient(180deg,#061426 0%,#071022 100%); border-right:1px solid #17335a; }
.block-container { padding-top:1.2rem; max-width:1600px; }
h1,h2,h3 { color:#f3f7ff !important; }
p,label,.stMarkdown { color:#d7e4ff; }
.hero { padding:1.5rem 1.7rem; border-radius:18px; background:linear-gradient(110deg,rgba(91,48,210,.42),rgba(12,75,135,.26)); border:1px solid #3457a6; margin-bottom:1rem; }
.pill { display:inline-block; border:1px solid #3b78b8; background:#112b49; color:#55f0c2; border-radius:30px; padding:4px 12px; font-size:.82rem; font-weight:700; }
.metric-card { background:linear-gradient(145deg,#0b1a31,#071225); border:1px solid #1a3760; border-radius:15px; padding:15px 17px; min-height:100px; }
.metric-label { color:#9eb7dc; font-size:.85rem; }
.metric-value { font-size:1.6rem; font-weight:800; color:#f3f7ff; margin-top:5px; }
.stButton>button { border-radius:10px; font-weight:700; border:1px solid #3b65ba; background:linear-gradient(100deg,#623bfa,#168fd6); color:white; }
</style>
""", unsafe_allow_html=True)

st.markdown("""
<div class="hero"><span class="pill">● MODO GRATUITO / EXPERIMENTAL</span>
<h1 style="margin:.7rem 0 .25rem 0;">TikTok Tag Counter</h1>
<p style="margin:0;">Monitoramento de perfil e hashtag, com análise de engajamento e filtros heurísticos.</p></div>
""", unsafe_allow_html=True)

def fmt_num(value):
    try: return f"{int(value):,}".replace(",", ".")
    except Exception: return "—"

def get_video_field(video, *keys, default=None):
    for key in keys:
        value = video.get(key) if isinstance(video, dict) else None
        if value not in (None, ""):
            return value
    return default

def normalize_video(video, source):
    author = video.get("author") or {}
    stats = video.get("stats") or {}
    username = author.get("unique_id") or author.get("username") or author.get("nickname") or "desconhecido"
    views = get_video_field(stats, "play_count", "playCount", default=0)
    likes = get_video_field(stats, "digg_count", "diggCount", default=0)
    comments = get_video_field(stats, "comment_count", "commentCount", default=0)
    shares = get_video_field(stats, "share_count", "shareCount", default=0)
    desc = get_video_field(video, "desc", "description", default="")
    vid = str(get_video_field(video, "id", "aweme_id", default=""))
    created = get_video_field(video, "create_time", "createTime")
    try: views = int(views or 0)
    except (ValueError, TypeError): views = 0
    try: likes = int(likes or 0)
    except (ValueError, TypeError): likes = 0
    try: comments = int(comments or 0)
    except (ValueError, TypeError): comments = 0
    try: shares = int(shares or 0)
    except (ValueError, TypeError): shares = 0
    created_at = ""
    if created:
        try:
            stamp = float(created)
            if stamp > 10**12: stamp /= 1000
            created_at = datetime.fromtimestamp(stamp, tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        except Exception:
            pass
    engagement = (likes + comments + shares) / views * 100 if views else 0
    return {
        "Origem": source, "Perfil": str(username).lstrip("@"), "Legenda": str(desc),
        "Data do vídeo": created_at, "Visualizações": views, "Curtidas": likes,
        "Comentários": comments, "Compartilhamentos": shares,
        "Engajamento (%)": round(engagement, 2),
        "Link": f"https://www.tiktok.com/@{username}/video/{vid}" if vid else ""
    }

async def collect_tiktok(username, hashtag, max_items, ms_token):
    # TikTokApi é uma biblioteca não oficial. Pode falhar se o TikTok mudar o site,
    # exigir verificação, bloquear o IP ou não houver uma sessão válida.
    from TikTokApi import TikTokApi
    api = TikTokApi()
    kwargs = {"num_sessions": 1, "sleep_after": 2, "browser": "chromium"}
    if ms_token:
        kwargs["cookies"] = [{"name": "msToken", "value": ms_token, "domain": ".tiktok.com", "path": "/"}]
    await api.create_sessions(**kwargs)
    results = []
    errors = []
    try:
        if username:
            try:
                user = api.user(username=username)
                count = 0
                async for video in user.videos(count=max_items):
                    results.append(normalize_video(video.as_dict, "Perfil"))
                    count += 1
                    if count >= max_items: break
            except Exception as exc:
                errors.append(f"Perfil @{username}: {type(exc).__name__}: {exc}")
        if hashtag:
            try:
                tag = api.hashtag(name=hashtag.lstrip("#"))
                count = 0
                async for video in tag.videos(count=max_items):
                    results.append(normalize_video(video.as_dict, f"#{hashtag.lstrip('#')}"))
                    count += 1
                    if count >= max_items: break
            except Exception as exc:
                errors.append(f"Hashtag #{hashtag.lstrip('#')}: {type(exc).__name__}: {exc}")
    finally:
        try: await api.close_sessions()
        except Exception: pass
    return results, errors

def run_collection(username, hashtag, max_items, ms_token):
    return asyncio.run(collect_tiktok(username, hashtag, max_items, ms_token))

if "items" not in st.session_state: st.session_state.items = []
if "monitoring" not in st.session_state: st.session_state.monitoring = False
if "last_collection" not in st.session_state: st.session_state.last_collection = 0.0
if "status" not in st.session_state: st.session_state.status = "Pronto para iniciar"
if "error" not in st.session_state: st.session_state.error = ""
if "seen" not in st.session_state: st.session_state.seen = set()

with st.sidebar:
    st.markdown("## 🎵 Configurações")
    username = st.text_input("Perfil do TikTok (@)", value="cortesbatalhasdosfamosos").strip().lstrip("@")
    hashtag = st.text_input("Hashtag", value="Casalcheck2Clips5K").strip().lstrip("#")
    max_items = st.selectbox("Máximo por fonte", [10, 20, 30, 50], index=1)
    interval = st.selectbox("Intervalo entre coletas", [300, 600, 900, 1800], index=1,
                            format_func=lambda s: f"{s//60} minutos")
    ms_token = st.text_input("msToken (opcional)", type="password",
        help="Cookie opcional do TikTok. Não cole sua senha. Sem token, a coleta pode falhar ou ser limitada.")
    st.caption("O monitoramento é manual. Nenhuma coleta começa até você apertar Iniciar.")
    c1, c2 = st.columns(2)
    with c1:
        if st.button("▶ Iniciar", use_container_width=True):
            st.session_state.monitoring = True
            st.session_state.error = ""
            st.session_state.status = "Monitoramento iniciado"
            st.session_state.last_collection = 0
            st.rerun()
    with c2:
        if st.button("■ Parar", use_container_width=True):
            st.session_state.monitoring = False
            st.session_state.status = "Parado pelo usuário"
            st.rerun()
    st.divider()
    st.markdown("### 🕵️ Filtros")
    age_days = st.selectbox("Conta recente até", [7, 14, 30, 60, 90], index=1, format_func=lambda x: f"{x} dias")
    min_views = st.number_input("Visualizações mínimas", min_value=0, max_value=10000000, value=50000, step=5000)
    max_engagement = st.slider("Engajamento máximo suspeito (%)", 0.1, 10.0, 5.0, 0.1)

if st.session_state.monitoring:
    now = time.time()
    if now - st.session_state.last_collection >= interval:
        with st.spinner("Consultando dados públicos do TikTok…"):
            try:
                new_items, errors = run_collection(username, hashtag, max_items, ms_token)
                existing = st.session_state.items
                keyed = {item.get("Link") or (item["Perfil"], item["Legenda"], item["Origem"]): item for item in existing}
                for item in new_items:
                    key = item.get("Link") or (item["Perfil"], item["Legenda"], item["Origem"])
                    keyed[key] = item
                st.session_state.items = list(keyed.values())
                st.session_state.last_collection = time.time()
                st.session_state.status = f"Última coleta: {datetime.now().strftime('%H:%M:%S')} — {len(new_items)} resultado(s)"
                st.session_state.error = "\n".join(errors)
                if not new_items and not errors:
                    st.session_state.status += " (nenhum resultado novo)"
            except Exception as exc:
                st.session_state.error = (
                    f"{type(exc).__name__}: {exc}\n\n"
                    "A coleta gratuita depende do acesso público do TikTok e pode falhar por bloqueio, "
                    "mudança no site ou necessidade de sessão. Confira o README."
                )
                st.session_state.status = "Falha na coleta gratuita"
                st.session_state.last_collection = time.time()
        st.rerun()

st.caption("Status: " + st.session_state.status)
if st.session_state.monitoring:
    st.info(f"Monitoramento ligado. Próxima tentativa em aproximadamente {interval//60} minuto(s), quando o app estiver ativo. O Streamlit pode suspender o app por inatividade.")
if st.session_state.error:
    st.warning(st.session_state.error)

items = st.session_state.items
# Defensive normalization: session_state may contain None or a non-list value
# after a Streamlit rerun / upgrade. Only pass a list of row dictionaries to pandas.
if not isinstance(items, list):
    items = []
    st.session_state.items = items
items = [item for item in items if isinstance(item, dict)]
st.session_state.items = items
df = pd.DataFrame.from_records(items) if items else pd.DataFrame()
if not df.empty:
    for col in ["Visualizações", "Curtidas", "Comentários", "Compartilhamentos", "Engajamento (%)"]:
        if col not in df: df[col] = 0
    df["Conta recente"] = False
    df["Views altas + engajamento baixo"] = (df["Visualizações"] >= int(min_views)) & (df["Engajamento (%)"] <= float(max_engagement))
    df["Sinais suspeitos"] = df[["Conta recente", "Views altas + engajamento baixo"]].sum(axis=1)
    df["Classificação"] = df["Sinais suspeitos"].map({2:"Alto — 2 sinais", 1:"Atenção — 1 sinal", 0:"Sem sinal detectado"})
else:
    df = pd.DataFrame(columns=["Origem","Perfil","Legenda","Data do vídeo","Visualizações","Curtidas","Comentários","Compartilhamentos","Engajamento (%)","Link","Conta recente","Views altas + engajamento baixo","Sinais suspeitos","Classificação"])

total = len(df)
views = int(df["Visualizações"].sum()) if total else 0
likes = int(df["Curtidas"].sum()) if total else 0
comments = int(df["Comentários"].sum()) if total else 0
suspicious = int((df["Sinais suspeitos"] > 0).sum()) if total else 0
metrics = [("🎬 Vídeos", fmt_num(total)), ("👁 Visualizações", fmt_num(views)),
           ("💜 Curtidas", fmt_num(likes)), ("💬 Comentários", fmt_num(comments)),
           ("⚠️ Sinais", fmt_num(suspicious))]
cols = st.columns(5)
for col, (label, value) in zip(cols, metrics):
    with col:
        st.markdown(f'<div class="metric-card"><div class="metric-label">{label}</div><div class="metric-value">{value}</div></div>', unsafe_allow_html=True)

left, right = st.columns([1.2, 1])
with left:
    st.subheader("🕵️ Análise de sinais")
    if total:
        st.bar_chart(df["Classificação"].value_counts())
        st.caption("Os sinais são heurísticos; não comprovam bots, compra de visualizações ou fraude.")
    else:
        st.info("Os resultados aparecerão aqui depois da primeira coleta bem-sucedida.")
with right:
    st.subheader("📈 Engajamento")
    if total:
        st.metric("Engajamento médio", f"{df['Engajamento (%)'].mean():.2f}%")
        st.metric("Vídeos com link", int(df["Link"].astype(bool).sum()))
    else:
        st.info("Sem dados carregados.")

st.subheader("🚨 Resultados com sinais")
if total:
    suspicious_df = df[df["Sinais suspeitos"] > 0]
    st.dataframe(suspicious_df, use_container_width=True, hide_index=True,
                 column_config={"Link": st.column_config.LinkColumn("Abrir vídeo", display_text="Abrir")})
else:
    st.info("Ainda não há resultados para exibir.")

st.subheader("🎬 Todos os vídeos")
if total:
    st.dataframe(df, use_container_width=True, hide_index=True,
                 column_config={"Link": st.column_config.LinkColumn("Abrir vídeo", display_text="Abrir")})
    st.download_button("⬇ Exportar CSV", data=df.to_csv(index=False).encode("utf-8-sig"),
                       file_name="tiktok_tag_counter.csv", mime="text/csv")
st.caption("Modo gratuito experimental: usa biblioteca não oficial e não depende do Apify. Disponibilidade, cobertura e frequência não são garantidas. Data de criação da conta não é obtida nesta versão.")
