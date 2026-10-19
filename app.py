
import asyncio
import time
from datetime import datetime, timezone

import pandas as pd
import streamlit as st

st.set_page_config(
    page_title="TikTok Tag Counter",
    page_icon="🎵",
    layout="wide",
)

st.markdown("""
<style>
.stApp {
    background: linear-gradient(135deg, #050816, #0b1530);
    color: #eef4ff;
}
[data-testid="stSidebar"] {
    background: #081326;
    border-right: 1px solid #203b66;
}
.block-container {max-width: 1500px; padding-top: 1.5rem;}
.hero {
    padding: 25px;
    border-radius: 18px;
    background: linear-gradient(110deg, #25135b, #073d61);
    border: 1px solid #3457a6;
    margin-bottom: 20px;
}
.metric {
    background: #0c1930;
    border: 1px solid #203b66;
    border-radius: 14px;
    padding: 16px;
}
.metric-label {color: #a8bddf; font-size: 14px;}
.metric-value {font-size: 27px; font-weight: 800;}
.stButton button {
    border-radius: 10px;
    font-weight: 700;
    min-height: 42px;
}
</style>
""", unsafe_allow_html=True)


st.markdown("""
<div class="hero">
    <h1>🎵 TikTok Tag Counter</h1>
    <p>Monitoramento de perfil e hashtag • Modo gratuito experimental</p>
</div>
""", unsafe_allow_html=True)


# ---------- Estado da aplicação ----------

if not isinstance(st.session_state.get("items"), list):
    st.session_state.items = []

if "monitoring" not in st.session_state:
    st.session_state.monitoring = False

if "last_collection" not in st.session_state:
    st.session_state.last_collection = 0.0

if "status" not in st.session_state:
    st.session_state.status = "Parado"

if "error" not in st.session_state:
    st.session_state.error = ""


# ---------- Coleta gratuita ----------

def normalize_video(video, source):
    author = video.get("author") or {}
    stats = video.get("stats") or {}

    username = (
        author.get("unique_id")
        or author.get("username")
        or author.get("nickname")
        or "desconhecido"
    )

    def number(*keys):
        for key in keys:
            value = stats.get(key)
            if value is not None:
                try:
                    return int(value)
                except (ValueError, TypeError):
                    pass
        return 0

    views = number("play_count", "playCount")
    likes = number("digg_count", "diggCount")
    comments = number("comment_count", "commentCount")
    shares = number("share_count", "shareCount")

    created = video.get("create_time", "")
    date_text = ""

    if created:
        try:
            date_text = datetime.fromtimestamp(
                float(created), tz=timezone.utc
            ).strftime("%Y-%m-%d %H:%M UTC")
        except (ValueError, TypeError, OSError):
            pass

    video_id = str(video.get("id") or video.get("aweme_id") or "")
    engagement = (
        (likes + comments + shares) / views * 100
        if views else 0
    )

    return {
        "Origem": source,
        "Perfil": username.lstrip("@"),
        "Legenda": video.get("desc", ""),
        "Data do vídeo": date_text,
        "Visualizações": views,
        "Curtidas": likes,
        "Comentários": comments,
        "Compartilhamentos": shares,
        "Engajamento (%)": round(engagement, 2),
        "Link": (
            f"https://www.tiktok.com/@{username}/video/{video_id}"
            if video_id else ""
        ),
    }


async def collect_videos(username, hashtag, limit, ms_token):
    from TikTokApi import TikTokApi

    api = TikTokApi()
    options = {
        "num_sessions": 1,
        "sleep_after": 2,
        "browser": "chromium",
    }

    if ms_token:
        options["cookies"] = [{
            "name": "msToken",
            "value": ms_token,
            "domain": ".tiktok.com",
            "path": "/",
        }]

    await api.create_sessions(**options)

    rows = []
    errors = []

    try:
        if username:
            try:
                user = api.user(username=username)
                count = 0

                async for video in user.videos(count=limit):
                    rows.append(
                        normalize_video(video.as_dict, "Perfil")
                    )
                    count += 1
                    if count >= limit:
                        break

            except Exception as exc:
                errors.append(
                    f"Perfil: {type(exc).__name__}: {exc}"
                )

        if hashtag:
            try:
                tag = api.hashtag(name=hashtag.lstrip("#"))
                count = 0

                async for video in tag.videos(count=limit):
                    rows.append(
                        normalize_video(
                            video.as_dict,
                            f"#{hashtag.lstrip('#')}",
                        )
                    )
                    count += 1
                    if count >= limit:
                        break

            except Exception as exc:
                errors.append(
                    f"Hashtag: {type(exc).__name__}: {exc}"
                )

    finally:
        try:
            await api.close_sessions()
        except Exception:
            pass

    return rows, errors


def collect(username, hashtag, limit, ms_token):
    return asyncio.run(
        collect_videos(username, hashtag, limit, ms_token)
    )


# ---------- Configurações ----------

with st.sidebar:
    st.header("⚙️ Configurações")

    username = st.text_input(
        "Perfil do TikTok",
        value="cortesbatalhasdosfamosos",
    ).strip().lstrip("@")

    hashtag = st.text_input(
        "Hashtag",
        value="Casalcheck2Clips5K",
    ).strip().lstrip("#")

    limit = st.selectbox(
        "Vídeos por fonte",
        [10, 20, 30, 50],
        index=1,
    )

    interval = st.selectbox(
        "Intervalo de coleta",
        [300, 600, 900, 1800],
        index=1,
        format_func=lambda x: f"{x // 60} minutos",
    )

    ms_token = st.text_input(
        "msToken opcional",
        type="password",
        help="Cole somente o valor do cookie msToken. Nunca sua senha.",
    )

    st.divider()

    if st.button("▶ Iniciar monitoramento", use_container_width=True):
        st.session_state.monitoring = True
        st.session_state.last_collection = 0
        st.session_state.error = ""
        st.session_state.status = "Monitoramento iniciado"
        st.rerun()

    if st.button("■ Parar monitoramento", use_container_width=True):
        st.session_state.monitoring = False
        st.session_state.status = "Parado pelo usuário"
        st.rerun()

    st.divider()
    st.caption(
        "A coleta só começa após clicar em Iniciar. "
        "O app pode pausar quando estiver inativo."
    )


# ---------- Execução da coleta ----------

if st.session_state.monitoring:
    elapsed = time.time() - st.session_state.last_collection

    if elapsed >= interval:
        with st.spinner("Consultando o TikTok..."):
            try:
                rows, errors = collect(
                    username,
                    hashtag,
                    limit,
                    ms_token,
                )

                existing = st.session_state.items
                combined = {}

                for row in existing:
                    key = row.get("Link") or (
                        row.get("Perfil"),
                        row.get("Legenda"),
                        row.get("Origem"),
                    )
                    combined[key] = row

                for row in rows:
                    key = row.get("Link") or (
                        row.get("Perfil"),
                        row.get("Legenda"),
                        row.get("Origem"),
                    )
                    combined[key] = row

                st.session_state.items = list(combined.values())
                st.session_state.last_collection = time.time()
                st.session_state.status = (
                    f"Coleta às {datetime.now().strftime('%H:%M:%S')} "
                    f"• {len(rows)} resultado(s)"
                )
                st.session_state.error = "\n".join(errors)

            except Exception as exc:
                st.session_state.error = (
                    f"{type(exc).__name__}: {exc}\n\n"
                    "Verifique a instalação do Chromium e os logs "
                    "do Streamlit Cloud."
                )
                st.session_state.status = "Falha na coleta"
                st.session_state.last_collection = time.time()

        st.rerun()


st.caption(f"Status: {st.session_state.status}")

if st.session_state.monitoring:
    st.info(
        "Monitoramento ligado. A próxima tentativa ocorre no "
        "intervalo selecionado, quando o app estiver ativo."
    )

if st.session_state.error:
    st.warning(st.session_state.error)


# ---------- Tabela segura ----------

items = st.session_state.items

if not isinstance(items, list):
    items = []

items = [row for row in items if isinstance(row, dict)]
st.session_state.items = items

df = pd.DataFrame.from_records(items) if items else pd.DataFrame()

if not df.empty:
    for col in [
        "Visualizações", "Curtidas", "Comentários",
        "Compartilhamentos", "Engajamento (%)",
    ]:
        if col not in df.columns:
            df[col] = 0

    df["Sinal suspeito"] = (
        (df["Visualizações"] >= 50000)
        & (df["Engajamento (%)"] <= 5)
    )
else:
    df = pd.DataFrame(columns=[
        "Origem", "Perfil", "Legenda", "Data do vídeo",
        "Visualizações", "Curtidas", "Comentários",
        "Compartilhamentos", "Engajamento (%)",
        "Link", "Sinal suspeito",
    ])


# ---------- Métricas ----------

total = len(df)
views = int(df["Visualizações"].sum()) if total else 0
likes = int(df["Curtidas"].sum()) if total else 0
comments = int(df["Comentários"].sum()) if total else 0
suspicious = (
    int(df["Sinal suspeito"].sum()) if total else 0
)

metrics = [
    ("🎬 Vídeos", total),
    ("👁 Visualizações", f"{views:,}".replace(",", ".")),
    ("💜 Curtidas", f"{likes:,}".replace(",", ".")),
    ("💬 Comentários", f"{comments:,}".replace(",", ".")),
    ("⚠️ Sinais", suspicious),
]

columns = st.columns(5)

for col, (label, value) in zip(columns, metrics):
    with col:
        st.markdown(
            f'<div class="metric">'
            f'<div class="metric-label">{label}</div>'
            f'<div class="metric-value">{value}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )


# ---------- Resultados ----------

st.subheader("🚨 Vídeos com sinais para análise")

if total:
    suspicious_df = df[df["Sinal suspeito"]]
    st.dataframe(
        suspicious_df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Link": st.column_config.LinkColumn(
                "Abrir vídeo",
                display_text="Abrir",
            )
        },
    )

    st.subheader("🎬 Todos os vídeos")

    st.dataframe(
        df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Link": st.column_config.LinkColumn(
                "Abrir vídeo",
                display_text="Abrir",
            )
        },
    )

    st.download_button(
        "⬇ Exportar CSV",
        data=df.to_csv(index=False).encode("utf-8-sig"),
        file_name="tiktok_tag_counter.csv",
        mime="text/csv",
    )

    st.caption(
        "Os sinais são heurísticos e não comprovam fraude ou bots."
    )
else:
    st.info(
        "Nenhum vídeo carregado ainda. Clique em Iniciar "
        "para tentar a primeira coleta."
    )

st.caption(
    "Alternativa gratuita experimental com biblioteca não oficial. "
    "O TikTok pode limitar ou bloquear consultas. "
    "O Chromium deve ser instalado durante o deploy."
)
