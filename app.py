import re, time, requests
import pandas as pd
import streamlit as st
from datetime import datetime, timezone

st.set_page_config(page_title="TikTok Tag Counter", page_icon="🎬", layout="wide")
DEFAULT_PROFILE = "cortesbatalhasdosfamosos"
DEFAULT_TAG = "Casalcheck2Clips5K"
ACTOR_ID = "poidata~tiktok-scraper"
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

def author_dict(item):
    for key in ("authorMeta","author","author_info","authorInfo","author_meta"):
        val=item.get(key)
        if isinstance(val,dict): return val
    return {}

def author_name(item):
    a=author_dict(item)
    name=(a.get("name") or a.get("uniqueId") or a.get("username") or a.get("unique_id") or "") if a else ""
    return str(item.get("author_username") or item.get("authorUniqueId") or item.get("uniqueId") or name).lstrip("@").casefold()

def avatar_url(item):
    a=author_dict(item)
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

def parse_account_date(item):
    """Tenta ler data de criação se o Actor realmente a devolver."""
    a=author_dict(item)
    keys=("createTime","create_time","createdAt","created_at","accountCreatedAt","account_created_at","registerTime","registration_date")
    raw=next((a.get(k) for k in keys if a.get(k) not in (None,"")),None)
    if raw is None:
        raw=next((item.get(k) for k in keys if item.get(k) not in (None,"")),None)
    if raw in (None,""): return None
    try:
        if isinstance(raw,(int,float)) or (isinstance(raw,str) and raw.strip().isdigit()):
            val=float(raw)
            if val > 10_000_000_000: val/=1000
            return datetime.fromtimestamp(val,tz=timezone.utc)
        s=str(raw).strip().replace("Z","+00:00")
        dt=datetime.fromisoformat(s)
        return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)
    except (ValueError,TypeError,OverflowError,OSError):
        return None

def account_info(item):
    a=author_dict(item)
    followers=n(first(a,["fans","followerCount","followers","followersCount","follower_count"],0))
    following=n(first(a,["following","followingCount","following_count"],0))
    videos=n(first(a,["video","videoCount","video_count","awemeCount"],0))
    friends=n(first(a,["friendCount","friends"],0))
    created=parse_account_date(item)
    age_days=(datetime.now(timezone.utc)-created).total_seconds()/86400 if created else None
    return {"Conta criada em":created.strftime("%Y-%m-%d") if created else "Não informado",
            "Idade da conta (dias)":round(age_days,1) if age_days is not None and age_days>=0 else None,
            "Seguidores":followers,"Seguindo":following,"Vídeos do perfil":videos,"Amigos":friends,
            "_created":created,"_age_days":age_days}

def collect(token, username, limit):
    endpoint=f"https://api.apify.com/v2/acts/{ACTOR_ID}/run-sync-get-dataset-items"
    payload={"profiles":[username],"maxItems":int(limit),"maxItemsPerQuery":min(int(limit),1000),
             "sortBy":"latest","downloadVideos":False,"includeComments":False,"includeSubtitles":False}
    response=requests.post(endpoint,headers={"Authorization":f"Bearer {token}","Content-Type":"application/json"},
        params={"format":"json","clean":"true"},json=payload,timeout=300)
    if not response.ok: raise RuntimeError(f"Apify retornou HTTP {response.status_code}: {response.text[:450]}")
    data=response.json()
    if not isinstance(data,list): raise RuntimeError("Resposta inesperada do Actor. Verifique o Input schema na Apify.")
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
        ai=account_info(item)
        out.append({"Data do vídeo":str(created),"Perfil":"@"+username,"Foto do perfil":avatar_url(item),
            "Legenda":caption,"Link":url,"Visualizações":n(first(item,["playCount","play_count","plays","viewCount","views"])),
            "Curtidas":n(first(item,["diggCount","digg_count","likes","likeCount"])),
            "Comentários":n(first(item,["commentCount","comment_count","comments"])),
            "Compartilhamentos":n(first(item,["shareCount","share_count","shares"])),
            "Conta criada em":ai["Conta criada em"],"Idade da conta (dias)":ai["Idade da conta (dias)"],
            "Seguidores":ai["Seguidores"],"Seguindo":ai["Seguindo"],"Vídeos do perfil":ai["Vídeos do perfil"],
            "Amigos":ai["Amigos"],"_created":ai["_created"],"_age_days":ai["_age_days"]})
    return out

def analyze(rows, new_days, low_engagement_pct, min_views):
    total_views=sum(r["Visualizações"] for r in rows)
    total_inter=sum(r["Curtidas"]+r["Comentários"]+r["Compartilhamentos"] for r in rows)
    rate=(100*total_inter/total_views) if total_views else 0
    new=[]; missing=0
    for r in rows:
        age=r.get("_age_days")
        if age is None: missing+=1
        elif 0 <= age <= new_days: new.append(r)
    low_engagement=[]
    for r in rows:
        v=r["Visualizações"]
        interactions=r["Curtidas"]+r["Comentários"]+r["Compartilhamentos"]
        if v >= min_views and v > 0 and 100*interactions/v < low_engagement_pct:
            low_engagement.append(r)
    # Risk is a transparent indicator based on available signals, not a fraud verdict.
    high_signal=[]
    for r in rows:
        age=r.get("_age_days"); views=r["Visualizações"]
        interactions=r["Curtidas"]+r["Comentários"]+r["Compartilhamentos"]
        er=100*interactions/views if views else 0
        signals=0
        if age is not None and 0 <= age <= new_days: signals+=1
        if views>=min_views and er<low_engagement_pct: signals+=1
        if r.get("Seguidores",0)==0 and r.get("Vídeos do perfil",0)<=1: signals+=1
        if signals>=2: high_signal.append(r)
    return {"views":total_views,"interactions":total_inter,"rate":rate,"new":new,"missing":missing,
            "low_engagement":low_engagement,"high_signal":high_signal}

def metric(label,value,note,emoji):
    return f'<div class="metric"><div class="metric-label">{emoji} &nbsp; {label}</div><div class="metric-value">{value:,}</div><div class="metric-note">{note}</div></div>'

with st.sidebar:
    st.markdown("## 🔎 Fazer uma busca")
    profile_input=st.text_input("Perfil do TikTok (@)",value="@"+DEFAULT_PROFILE,placeholder="@seuperfil")
    hashtag_input=st.text_input("Hashtag",value="#"+DEFAULT_TAG,placeholder="#SuaHashtag")
    max_items=st.select_slider("Máximo de itens solicitados",options=[100,200,500,1000,2000,5000],value=1000,
        format_func=lambda x:f"{x:,}".replace(",","."))
    st.caption("Coletas grandes podem consumir mais créditos da Apify.")
    search=st.button("🔎 Buscar vídeos",type="primary",use_container_width=True)
    st.divider()
    st.caption("O token fica nos Secrets do Streamlit; não o coloque no código.")

st.markdown("""<div class="hero"><div class="kicker">Painel de desempenho e sinais de qualidade</div>
<div class="hero-title">🎬 TikTok Tag Counter</div><div class="sub">Métricas, monitoramento e filtros experimentais de contas suspeitas.</div></div>""",unsafe_allow_html=True)

for key,default in [("monitoring",False),("results",None),("last_collection_at",0.0),("collection_error","")]:
    if key not in st.session_state: st.session_state[key]=default

if search:
    username=profile_input.strip().lstrip("@").strip(); tag=hashtag_input.strip().lstrip("#").strip()
    if not username or not re.fullmatch(r"[A-Za-z0-9._]{2,24}",username): st.error("Digite um @ válido do TikTok.")
    elif not tag or not re.fullmatch(r"[\w]+",tag,flags=re.UNICODE): st.error("Digite uma hashtag válida, sem espaços.")
    else:
        try: token=str(st.secrets.get("APIFY_TOKEN","")).strip()
        except Exception: token=""
        if not token: st.error("Configure APIFY_TOKEN em Streamlit → Manage app → Settings → Secrets.")
        else:
            with st.spinner(f"Consultando @{username} e filtrando #{tag}..."):
                try:
                    raw=collect(token,username,max_items)
                    st.session_state["results"]=parse_items(raw,username,tag)
                    st.session_state["raw_count"]=len(raw)
                    st.session_state["profile_avatar"]=next((avatar_url(x) for x in raw if isinstance(x,dict) and avatar_url(x)),"")
                    st.session_state["current_profile"]=username; st.session_state["current_tag"]=tag
                    st.session_state["last_collection_at"]=time.time()
                    st.session_state["last_collection_label"]=datetime.now().astimezone().strftime("%d/%m/%Y %H:%M:%S")
                    st.session_state["active_limit"]=max_items; st.session_state["collection_error"]=""
                    st.session_state["monitoring"]=False
                except Exception as e: st.error(f"Não foi possível concluir a busca: {e}")

if st.session_state["results"] is None:
    st.info("Faça uma busca para carregar os vídeos e aplicar os filtros.")
else:
    # Filter settings
    with st.expander("⚙️ Configurar filtros de suspeita",expanded=True):
        fc=st.columns(3)
        with fc[0]: new_days=st.selectbox("Considerar conta recém-criada se tiver até", [7,14,30,60,90],index=2,format_func=lambda x:f"{x} dias")
        with fc[1]: low_engagement_pct=st.slider("Interações baixas abaixo de (%)",min_value=0.1,max_value=5.0,value=0.5,step=0.1)
        with fc[2]: min_views=st.number_input("Mínimo de views para avaliar engajamento",min_value=100,max_value=1000000,value=10000,step=1000)
        st.caption("Os filtros só funcionam se o Actor devolver a data de criação e metadados da conta. Campo ausente aparece como “Não informado”; não significa conta suspeita.")
    controls=st.columns([2,2,4])
    with controls[0]:
        if not st.session_state["monitoring"]:
            if st.button("▶️ Iniciar monitoramento",type="primary",use_container_width=True):
                st.session_state["monitoring"]=True; st.rerun()
        elif st.button("⏸️ Parar monitoramento",use_container_width=True):
            st.session_state["monitoring"]=False; st.rerun()
    with controls[1]:
        if st.button("🔄 Coletar agora",use_container_width=True):
            try:
                token=str(st.secrets.get("APIFY_TOKEN","")).strip()
                raw=collect(token,st.session_state["current_profile"],max_items)
                st.session_state["results"]=parse_items(raw,st.session_state["current_profile"],st.session_state["current_tag"])
                st.session_state["raw_count"]=len(raw); st.session_state["last_collection_at"]=time.time()
                st.session_state["last_collection_label"]=datetime.now().astimezone().strftime("%d/%m/%Y %H:%M:%S")
                st.session_state["collection_error"]=""
            except Exception as e: st.session_state["collection_error"]=str(e)
    @st.fragment(run_every="5s" if st.session_state["monitoring"] else None)
    def dashboard():
        if st.session_state["monitoring"] and time.time()-st.session_state.get("last_collection_at",0)>=COLLECTION_INTERVAL_SECONDS:
            try:
                token=str(st.secrets.get("APIFY_TOKEN","")).strip()
                raw=collect(token,st.session_state["current_profile"],st.session_state.get("active_limit",1000))
                st.session_state["results"]=parse_items(raw,st.session_state["current_profile"],st.session_state["current_tag"])
                st.session_state["raw_count"]=len(raw); st.session_state["last_collection_at"]=time.time()
                st.session_state["last_collection_label"]=datetime.now().astimezone().strftime("%d/%m/%Y %H:%M:%S")
                st.session_state["collection_error"]=""
            except Exception as e: st.session_state["collection_error"]=str(e)
        rows=st.session_state.get("results") or []
        avatar=st.session_state.get("profile_avatar","")
        c1,c2=st.columns([1,5],vertical_alignment="center")
        with c1:
            if avatar: st.image(avatar,width=100)
            else: st.markdown("### 🎬")
        with c2:
            st.markdown(f"### @{st.session_state['current_profile']}")
            st.markdown(f"[Abrir perfil no TikTok](https://www.tiktok.com/@{st.session_state['current_profile']})")
            st.caption("Última coleta: "+st.session_state.get("last_collection_label","não registrada"))
        result=analyze(rows,new_days,low_engagement_pct,min_views)
        cols=st.columns(5)
        cards=[("Vídeos",len(rows),"Correspondentes","🎬"),("Views",result["views"],"Total observado","👁️"),
               ("Curtidas",sum(r["Curtidas"] for r in rows),"Total observado","❤️"),
               ("Comentários",sum(r["Comentários"] for r in rows),"Total observado","💬"),
               ("Compartilhamentos",sum(r["Compartilhamentos"] for r in rows),"Total observado","↗️")]
        for col,(label,val,note,emoji) in zip(cols,cards):
            with col: st.markdown(metric(label,val,note,emoji),unsafe_allow_html=True)
        st.markdown('<div class="section">🧪 Filtros e sinais de atenção</div>',unsafe_allow_html=True)
        a,b,c,d=st.columns(4)
        a.metric(f"Contas até {new_days} dias",len(result["new"]))
        b.metric("Engajamento baixo",len(result["low_engagement"]))
        c.metric("Sinais combinados",len(result["high_signal"]))
        d.metric("Sem data de criação",result["missing"])
        st.warning("Importante: estes são sinais para revisão, não prova de views compradas. A data de criação pode não estar disponível; contas novas também podem ser legítimas. Views e interações públicas não permitem identificar com certeza bots.")
        st.markdown("#### Contas possivelmente recém-criadas")
        if result["new"]:
            dfnew=pd.DataFrame(result["new"]).drop(columns=["_created","_age_days","Foto do perfil"],errors="ignore")
            st.dataframe(dfnew,use_container_width=True,hide_index=True,column_config={"Link":st.column_config.LinkColumn("Vídeo",display_text="Abrir vídeo")})
        else: st.info("Nenhuma conta com data de criação disponível caiu no limite selecionado.")
        st.markdown("#### Vídeos com visualizações altas e poucas interações")
        if result["low_engagement"]:
            dflow=pd.DataFrame(result["low_engagement"]).drop(columns=["_created","_age_days","Foto do perfil"],errors="ignore")
            st.dataframe(dflow,use_container_width=True,hide_index=True,column_config={"Link":st.column_config.LinkColumn("Vídeo",display_text="Abrir vídeo")})
        else: st.info("Nenhum vídeo atingiu os critérios atuais.")
        st.markdown("#### Casos com dois ou mais sinais")
        if result["high_signal"]:
            dfhigh=pd.DataFrame(result["high_signal"]).drop(columns=["_created","_age_days","Foto do perfil"],errors="ignore")
            st.dataframe(dfhigh,use_container_width=True,hide_index=True,column_config={"Link":st.column_config.LinkColumn("Vídeo",display_text="Abrir vídeo")})
        else: st.info("Nenhum caso com dois ou mais sinais nos metadados disponíveis.")
        st.markdown("#### Todos os vídeos")
        if rows:
            all_df=pd.DataFrame(rows).drop(columns=["_created","_age_days","Foto do perfil"],errors="ignore")
            st.dataframe(all_df,use_container_width=True,hide_index=True,column_config={"Link":st.column_config.LinkColumn("Vídeo",display_text="Abrir vídeo"),"Legenda":st.column_config.TextColumn("Legenda",width="large")})
            st.download_button("⬇️ Exportar CSV",data=all_df.to_csv(index=False).encode("utf-8-sig"),file_name="tiktok_tag_counter.csv",mime="text/csv")
        if st.session_state["monitoring"]: st.caption("Interface atualiza a cada 5 s; nova coleta é tentada a cada 60 s. Mantenha a página aberta.")
    st.session_state["active_limit"]=max_items
    dashboard()

st.divider()
st.caption("A data de criação do perfil não costuma estar disponível em todos os coletores de vídeos. O código tenta ler campos conhecidos; confirme no dataset real da Apify. Se o Actor não retornar essa informação, a filtragem por idade da conta não conseguirá funcionar até trocarmos/configurarmos o Actor.")
