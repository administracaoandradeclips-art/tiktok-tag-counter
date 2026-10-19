import re, time, requests
import pandas as pd
import streamlit as st
from datetime import datetime, timezone

st.set_page_config(page_title="TikTok Tag Counter", page_icon="🎬", layout="wide")
DEFAULT_PROFILE = "cortesbatalhasdosfamosos"
DEFAULT_TAG = "Casalcheck2Clips5K"
ACTOR_ID = "poidata~tiktok-scraper"
UI_REFRESH_SECONDS = 5
COLLECTION_INTERVAL_SECONDS = 60

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
html, body, [class*="css"] {font-family:Inter,sans-serif}
.stApp {background:radial-gradient(ellipse at top left,#171c2e 0%,#0b0d13 48%,#0b0d13 100%)}
[data-testid="stSidebar"] {background:#10131d;border-right:1px solid #252a3a}
.block-container {max-width:1500px;padding-top:2rem}
.hero {padding:1.6rem 1.8rem;border:1px solid #2a3044;border-radius:22px;background:linear-gradient(120deg,rgba(124,58,237,.22),rgba(14,165,233,.10));margin-bottom:1.3rem}
.kicker {color:#a5b4fc;text-transform:uppercase;letter-spacing:.15em;font-size:.72rem;font-weight:800}
.hero-title {color:#f8fafc;font-size:clamp(1.8rem,3vw,2.7rem);font-weight:800;margin:.25rem 0}
.sub {color:#b6bfd2}
.metric {background:linear-gradient(145deg,#171c2b,#111520);border:1px solid #2a3044;border-radius:18px;padding:1rem;min-height:120px}
.metric-label {color:#aab4c8;font-size:.82rem;font-weight:600;margin-bottom:.5rem}
.metric-value {color:#f8fafc;font-size:clamp(1.4rem,2.2vw,2rem);font-weight:800}
.metric-note {color:#8290a8;font-size:.72rem;margin-top:.4rem}
.section {color:#f1f5f9;font-size:1.25rem;font-weight:750;margin:1.5rem 0 .7rem}
div.stButton>button,div.stDownloadButton>button {border-radius:12px;font-weight:700;min-height:2.7rem}
.live-pill {display:inline-block;padding:.3rem .65rem;border-radius:999px;background:rgba(34,197,94,.12);color:#4ade80;border:1px solid rgba(34,197,94,.3);font-weight:700;font-size:.8rem}
</style>""", unsafe_allow_html=True)

def n(v):
    try: return int(float(v.replace(",", "") if isinstance(v,str) else v)) if v not in (None,"") else 0
    except (ValueError,TypeError): return 0

def first(item, keys, default=0):
    return next((item[k] for k in keys if item.get(k) not in (None,"")), default)

def tags_caption(item):
    tags=set()
    raw=item.get("hashtags")
    if isinstance(raw,list):
        for x in raw:
            val=x.get("name","") if isinstance(x,dict) else str(x)
            if val.strip(): tags.add(val.strip().lstrip("#").casefold())
    caption=str(item.get("text") or item.get("description") or item.get("video_description") or item.get("caption") or item.get("title") or "")
    tags.update(m.group(1).casefold() for m in re.finditer(r"(?<!\w)#([\w]+)",caption,flags=re.UNICODE))
    return tags,caption

def author_name(item):
    a=item.get("authorMeta") or item.get("author") or {}
    name=(a.get("name") or a.get("uniqueId") or a.get("username") or "") if isinstance(a,dict) else str(a)
    return str(item.get("author_username") or item.get("uniqueId") or name).lstrip("@").casefold()

def avatar_url(item):
    a=item.get("authorMeta") or item.get("author") or item.get("author_info") or {}
    if not isinstance(a,dict): return ""
    for key in ("avatar","avatarUrl","avatar_url","avatarThumb","avatarLarger","profilePicture","profile_picture","cover"):
        v=a.get(key)
        if isinstance(v,str) and v.startswith("https://"): return v
        if isinstance(v,dict):
            for nk in ("url_list","urlList","urls"):
                arr=v.get(nk)
                if isinstance(arr,list):
                    for u in arr:
                        if isinstance(u,str) and u.startswith("https://"): return u
            for nk in ("url","uri"):
                u=v.get(nk)
                if isinstance(u,str) and u.startswith("https://"): return u
    return ""

def collect(token, username, limit):
    url=f"https://api.apify.com/v2/acts/{ACTOR_ID}/run-sync-get-dataset-items"
    payload={"profiles":[username],"maxItems":int(limit),"maxItemsPerQuery":min(int(limit),1000),
             "sortBy":"latest","downloadVideos":False,"includeComments":False,"includeSubtitles":False}
    r=requests.post(url,headers={"Authorization":f"Bearer {token}","Content-Type":"application/json"},
                    params={"format":"json","clean":"true"},json=payload,timeout=300)
    if not r.ok: raise RuntimeError(f"Apify retornou HTTP {r.status_code}: {r.text[:400]}")
    data=r.json()
    if not isinstance(data,list): raise RuntimeError("Resposta inesperada do Actor da Apify.")
    return data

def parse_items(raw, username, tag):
    out=[]; seen=set()
    for item in raw:
        if not isinstance(item,dict): continue
        author=author_name(item)
        if author and author != username.casefold(): continue
        tags,caption=tags_caption(item)
        if tag.casefold() not in tags: continue
        url=item.get("webVideoUrl") or item.get("video_url") or item.get("share_url") or ""
        vid=item.get("id") or item.get("video_id")
        if not url and vid: url=f"https://www.tiktok.com/@{username}/video/{vid}"
        ident=str(vid or url).strip()
        if not ident or ident in seen: continue
        seen.add(ident)
        created=item.get("createTimeISO") or item.get("published_at") or item.get("createTime") or item.get("create_time") or ""
        if isinstance(created,(int,float)): created=datetime.fromtimestamp(created,tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        out.append({"Data":str(created),"Perfil":"@"+username,"Foto do perfil":avatar_url(item),"Legenda":caption,"Link":url,
                    "Visualizações":n(first(item,["playCount","play_count","plays","viewCount","views"])),
                    "Curtidas":n(first(item,["diggCount","digg_count","likes","likeCount"])),
                    "Comentários":n(first(item,["commentCount","comment_count","comments"])),
                    "Compartilhamentos":n(first(item,["shareCount","share_count","shares"]))})
    return out

def save_collection(username, tag, limit, token):
    raw=collect(token,username,limit)
    st.session_state["results"]=parse_items(raw,username,tag)
    st.session_state["raw_count"]=len(raw)
    st.session_state["profile_avatar"]=next((avatar_url(x) for x in raw if isinstance(x,dict) and avatar_url(x)),"")
    st.session_state["current_profile"]=username
    st.session_state["current_tag"]=tag
    st.session_state["last_collection_at"]=time.time()
    st.session_state["last_collection_label"]=datetime.now().astimezone().strftime("%d/%m/%Y %H:%M:%S")
    st.session_state["collection_error"]=""

def suspicious(rows):
    views=sum(x["Visualizações"] for x in rows); inter=sum(x["Curtidas"]+x["Comentários"]+x["Compartilhamentos"] for x in rows)
    if views<=0: return 0,"Indeterminado",0.0,"Não há visualizações válidas para avaliar."
    rate=inter/views
    if rate<.005:
        fraction=min(.8,max(0,(.005-rate)/.005)); risk="Alto" if rate<.001 else "Médio"
        reason="Taxa de interações baixa; isso pode ter causas legítimas e não comprova fraude."
    else: fraction=0; risk="Baixo"; reason="A regra heurística não acionou alerta; isso não garante autenticidade."
    return round(views*fraction),risk,rate*100,reason

def metric(label,value,note,emoji):
    return f'<div class="metric"><div class="metric-label">{emoji} &nbsp; {label}</div><div class="metric-value">{value:,}</div><div class="metric-note">{note}</div></div>'

with st.sidebar:
    st.markdown("## 🔎 Fazer uma busca")
    profile_input=st.text_input("Perfil do TikTok (@)",value="@"+DEFAULT_PROFILE,placeholder="@seuperfil")
    hashtag_input=st.text_input("Hashtag",value="#"+DEFAULT_TAG,placeholder="#SuaHashtag")
    max_items=st.select_slider("Máximo de itens solicitados",options=[100,200,500,1000,2000,5000],value=1000,
                               format_func=lambda x:f"{x:,}".replace(",","."))
    st.caption("Coletas maiores podem consumir mais créditos da Apify.")
    search=st.button("🔎 Buscar vídeos",type="primary",use_container_width=True)
    st.divider()
    st.caption("Mantenha APIFY_TOKEN nos Secrets do Streamlit; nunca no código.")

st.markdown("""<div class="hero"><div class="kicker">Painel público de desempenho</div>
<div class="hero-title">🎬 TikTok Tag Counter</div>
<div class="sub">Consulte vídeos por perfil e hashtag, acompanhe métricas e exporte resultados.</div></div>""",unsafe_allow_html=True)

for key,default in [("monitoring",False),("results",None),("last_collection_at",0.0),("collection_error","")]:
    if key not in st.session_state: st.session_state[key]=default

if search:
    username=profile_input.strip().lstrip("@").strip(); tag=hashtag_input.strip().lstrip("#").strip()
    if not username or not re.fullmatch(r"[A-Za-z0-9._]{2,24}",username): st.error("Digite um @ válido do TikTok.")
    elif not tag or not re.fullmatch(r"[\w]+",tag,flags=re.UNICODE): st.error("Digite uma hashtag válida, sem espaços.")
    else:
        try: token=str(st.secrets.get("APIFY_TOKEN","")).strip()
        except Exception: token=""
        if not token: st.error("Configure APIFY_TOKEN em Streamlit → Manage app → Settings → Secrets. Não peça o token aos visitantes.")
        else:
            with st.spinner(f"Consultando @{username} e filtrando #{tag}..."):
                try:
                    save_collection(username,tag,max_items,token)
                    st.session_state["active_limit"]=max_items
                    st.session_state["monitoring"]=False
                    st.success("Busca concluída. Agora você pode iniciar o monitoramento.")
                except requests.Timeout: st.error("A coleta excedeu o tempo limite. Tente um limite menor.")
                except Exception as e: st.error(f"Não foi possível concluir a busca: {e}")

if st.session_state["results"] is None:
    st.markdown("### Comece sua consulta")
    st.info("Informe um perfil público e uma hashtag na barra lateral. Depois da busca, você poderá iniciar o monitoramento.")
else:
    controls=st.columns([2,2,4])
    with controls[0]:
        if not st.session_state["monitoring"]:
            if st.button("▶️ Iniciar monitoramento",type="primary",use_container_width=True):
                st.session_state["monitoring"]=True; st.rerun()
        elif st.button("⏸️ Parar monitoramento",use_container_width=True):
            st.session_state["monitoring"]=False; st.rerun()
    with controls[1]:
        if st.button("🔄 Coletar agora",use_container_width=True):
            try: token=str(st.secrets.get("APIFY_TOKEN","")).strip()
            except Exception: token=""
            if not token: st.error("APIFY_TOKEN não está configurado.")
            else:
                with st.spinner("Coletando dados atualizados..."):
                    try: save_collection(st.session_state["current_profile"],st.session_state["current_tag"],max_items,token)
                    except Exception as e:
                        st.session_state["collection_error"]=str(e); st.warning("A coleta falhou; os últimos dados válidos foram mantidos.")

    @st.fragment(run_every="5s" if st.session_state["monitoring"] else None)
    def live_dashboard():
        if st.session_state["monitoring"]:
            elapsed=time.time()-st.session_state.get("last_collection_at",0)
            last_attempt=st.session_state.get("last_collection_attempt",0)
            if elapsed>=COLLECTION_INTERVAL_SECONDS and time.time()-last_attempt>=COLLECTION_INTERVAL_SECONDS:
                try: token=str(st.secrets.get("APIFY_TOKEN","")).strip()
                except Exception: token=""
                if token:
                    st.session_state["last_collection_attempt"]=time.time()
                    try:
                        save_collection(st.session_state["current_profile"],st.session_state["current_tag"],
                                        st.session_state.get("active_limit",1000),token)
                    except Exception as e: st.session_state["collection_error"]=str(e)
        rows=st.session_state.get("results") or []
        avatar=st.session_state.get("profile_avatar","")
        pc,pi=st.columns([1,5],vertical_alignment="center")
        with pc:
            if avatar: st.image(avatar,width=112)
            else: st.markdown("<div style='width:96px;height:96px;border-radius:50%;background:#252a3a;display:flex;align-items:center;justify-content:center;font-size:2.5rem'>🎬</div>",unsafe_allow_html=True)
        with pi:
            st.markdown(f"### @{st.session_state['current_profile']}")
            st.markdown(f"[Abrir perfil no TikTok](https://www.tiktok.com/@{st.session_state['current_profile']})")
            st.caption(f"Hashtag monitorada: #{st.session_state['current_tag']}")
        status=st.columns([1,2,3])
        with status[0]:
            st.markdown('<span class="live-pill">● MONITORAMENTO ATIVO</span>' if st.session_state["monitoring"] else "Monitoramento pausado",unsafe_allow_html=True)
        with status[1]: st.caption("Tela atualiza a cada 5 segundos" if st.session_state["monitoring"] else "Inicie o monitoramento para atualizar automaticamente")
        with status[2]: st.caption("Última coleta: "+st.session_state.get("last_collection_label","não registrada"))
        if st.session_state.get("collection_error"): st.warning("A coleta falhou; mantendo os últimos dados válidos. Detalhe: "+st.session_state["collection_error"][:250])
        totals={k:sum(x[k] for x in rows) for k in ("Visualizações","Curtidas","Comentários","Compartilhamentos")}
        st.markdown('<div class="section">📊 Resumo geral</div>',unsafe_allow_html=True)
        st.caption(f"Itens retornados pelo coletor: {st.session_state.get('raw_count',0)}")
        cols=st.columns(5)
        cards=[("Vídeos encontrados",len(rows),"Vídeos únicos","🎬"),("Visualizações totais",totals["Visualizações"],"Soma das visualizações","👁️"),
               ("Curtidas totais",totals["Curtidas"],"Soma das curtidas","❤️"),("Comentários totais",totals["Comentários"],"Soma dos comentários","💬"),
               ("Compartilhamentos",totals["Compartilhamentos"],"Soma dos compartilhamentos","↗️")]
        for col,(label,val,note,emoji) in zip(cols,cards):
            with col: st.markdown(metric(label,val,note,emoji),unsafe_allow_html=True)
        st.markdown('<div class="section">🕵️ Análise de visualizações suspeitas</div>',unsafe_allow_html=True)
        suspect,risk,rate,reason=suspicious(rows); color={"Baixo":"#22c55e","Médio":"#f59e0b","Alto":"#ef4444"}.get(risk,"#94a3b8")
        a,b,c=st.columns(3)
        with a: st.metric("Estimativa de visualizações suspeitas",f"{suspect:,}".replace(",","."))
        with b: st.markdown(f'<div class="metric"><div class="metric-label">Nível de risco</div><div class="metric-value" style="color:{color}">{risk}</div><div class="metric-note">Sinal heurístico, não confirmação</div></div>',unsafe_allow_html=True)
        with c: st.metric("Interações / visualizações",f"{rate:.2f}%")
        st.info(reason+" Esta regra não identifica bots e não comprova fraude; é apenas uma heurística experimental.")
        st.markdown('<div class="section">📋 Vídeos encontrados</div>',unsafe_allow_html=True)
        if not rows: st.warning("Nenhum vídeo correspondente nos itens retornados. Isso não prova que não existam outros vídeos.")
        else:
            df=pd.DataFrame(rows); shown=df.drop(columns=["Foto do perfil"],errors="ignore")
            st.dataframe(shown,use_container_width=True,hide_index=True,column_config={"Link":st.column_config.LinkColumn("Vídeo",display_text="Abrir no TikTok"),"Legenda":st.column_config.TextColumn("Legenda",width="large")})
            st.download_button("⬇️ Exportar CSV",data=shown.to_csv(index=False).encode("utf-8-sig"),file_name="tiktok_tag_counter.csv",mime="text/csv")
        st.caption("Atualização visual a cada 5 s; nova coleta tentada a cada 60 s. Deixe a página aberta para monitorar.")
    st.session_state["active_limit"]=max_items
    live_dashboard()

st.divider()
st.caption("A frequência real depende da duração e dos limites do Actor da Apify. O esquema de entrada do Actor foi herdado do código anterior e precisa ser validado se ocorrer erro HTTP 400/404. Cada sessão de visitante pode iniciar suas próprias coletas; para compartilhar resultados entre todos, seria necessário armazenamento/cache central.")
