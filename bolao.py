"""
Bolão Online - Streamlit + Supabase
Tela do apostador (palpite + Pix + comprovante via WhatsApp) e Painel admin
(escolher times, cronômetro de 2h por inscrição, aceitar/cancelar, caixa 30/70).

Requer no secrets do Streamlit Cloud:
  SUPABASE_URL = "https://xxxx.supabase.co"
  SUPABASE_KEY = "sua-anon-key"
  SENHA_ADMIN  = "sua-senha"
"""

import os
import base64
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

import streamlit as st
from supabase import create_client
from streamlit_autorefresh import st_autorefresh

# ----------------------------------------------------------------------------
# CONFIGURAÇÃO
# ----------------------------------------------------------------------------
VALOR_APOSTA   = 5.00
PERC_ORG       = 0.30           # 30% organizadores
PRAZO_HORAS    = 2              # prazo de confirmação
WHATSAPP       = "5598988119667"
WHATSAPP_LABEL = "(98) 98811-9667"
PIX_COPIA_COLA = ("00020126330014br.gov.bcb.pix0111089410153675204000053039865404"
                  "5.005802BR5925GABRIELA SOARES PIRES PON6008SAO LUIS62070503***63041924")

VERDE, GOLD, AZUL = "#009739", "#D9A300", "#002776"
NOMES_BOLAO = [("Rodrigo", VERDE), ("Gabi", GOLD), ("Léo", AZUL),
               ("Lucas", VERDE), ("Manu", GOLD)]
SENHA_ADMIN = "820862"

# ----------------------------------------------------------------------------
# SUPABASE
# ----------------------------------------------------------------------------
@st.cache_resource
def get_db():
    return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])

def carregar_palpites():
    return get_db().table("palpites").select("*").order("criado_em").execute().data or []

def inserir_palpite(d):
    get_db().table("palpites").insert(d).execute()

def atualizar_palpite(pid, campos):
    get_db().table("palpites").update(campos).eq("id", pid).execute()

def carregar_config():
    r = get_db().table("config").select("*").eq("id", 1).execute().data
    if r:
        return r[0]
    return {"id": 1, "time_a": "Brasil", "time_b": "Argentina"}

def salvar_config(time_a, time_b):
    get_db().table("config").upsert({"id": 1, "time_a": time_a, "time_b": time_b}).execute()

# ----------------------------------------------------------------------------
# UTILITÁRIOS
# ----------------------------------------------------------------------------
def cpf_valido(cpf):
    n = [int(d) for d in cpf if d.isdigit()]
    if len(n) != 11 or len(set(n)) == 1:
        return False
    for i in (9, 10):
        s = sum(n[j] * ((i + 1) - j) for j in range(i))
        dig = (s * 10) % 11
        dig = 0 if dig == 10 else dig
        if dig != n[i]:
            return False
    return True

def fmt_cpf(cpf):
    d = "".join(filter(str.isdigit, cpf))
    return f"{d[:3]}.{d[3:6]}.{d[6:9]}-{d[9:]}" if len(d) == 11 else cpf

def img_b64(path):
    if os.path.exists(path):
        return base64.b64encode(open(path, "rb").read()).decode()
    return ""

def restante_segundos(criado_iso, extra_min=0):
    criado = datetime.fromisoformat(criado_iso)
    if criado.tzinfo is None:
        criado = criado.replace(tzinfo=timezone.utc)
    prazo = criado + timedelta(hours=PRAZO_HORAS, minutes=extra_min)
    return (prazo - datetime.now(timezone.utc)).total_seconds()

def fmt_hms(seg):
    seg = max(0, int(seg))
    return f"{seg // 3600:02d}:{(seg % 3600) // 60:02d}:{seg % 60:02d}"

# ----------------------------------------------------------------------------
# CSS
# ----------------------------------------------------------------------------
def css():
    st.markdown("""
    <style>
      .stApp { background:#FFDF00; }
      .cabecalho { background:#fff; border-radius:16px; padding:12px 16px; margin-bottom:10px;
        box-shadow:0 4px 14px rgba(0,0,0,.12); }
      .nome-bolao { text-align:center; font-size:26px; font-weight:800; line-height:1.2; }
      .eyebrow { text-align:center; font-size:28px; letter-spacing:2px; color:#002776; font-weight:900;
        margin-bottom:2px; }
      .mostradores { display:flex; justify-content:center; gap:12px; flex-wrap:wrap; margin:14px 0 2px; }
      .mcard { display:flex; align-items:center; gap:10px; flex:1 1 0; min-width:150px; max-width:230px;
        justify-content:center;
        background:linear-gradient(135deg,#002776,#001a52); color:#FFCC29;
        border-radius:16px; padding:12px 18px; box-shadow:0 6px 18px rgba(0,39,118,.4); }
      .mcard .num { font-size:28px; font-weight:900; color:#FFCC29; }
      .mcard .lab { font-size:12px; font-weight:700; color:#FFE89A; }
      .jogo { text-align:center; font-size:30px; font-weight:900; color:#002776; letter-spacing:.5px; }
      .jogo .x { color:#009739; margin:0 8px; }
      .valor-aposta { background:#002776; color:#FFCC29; font-weight:800; text-align:center;
        padding:12px; border-radius:10px; font-size:17px; margin:6px 0 4px; }
      .vs { background:#009739; color:#fff; font-weight:800; font-size:14px;
        padding:3px 10px; border-radius:20px; }
      .regras { background:#F7F7F2; border:1px solid #e6e3d6; border-radius:10px;
        padding:10px 14px; font-size:12px; color:#666; }
      .wpp { display:block; text-align:center; text-decoration:none; padding:13px;
        border-radius:11px; background:#25D366; color:#fff; font-weight:700; font-size:15px; }
      div.stButton > button[kind="primary"] { background:#009739; color:#fff;
        font-weight:800; border:none; border-radius:10px; }
    </style>
    """, unsafe_allow_html=True)

# ----------------------------------------------------------------------------
# PÁGINA: APOSTAR
# ----------------------------------------------------------------------------
def pagina_apostar(cfg):
    st_autorefresh(interval=600000, key="ref_publico")  # atualiza contagem a cada 10 min

    nomes_html = ""
    for i, (n, c) in enumerate(NOMES_BOLAO):
        sep = ", " if i < len(NOMES_BOLAO) - 2 else (" e " if i == len(NOMES_BOLAO) - 2 else "")
        nomes_html += f'<span style="color:{c}">{n}</span>{sep}'
    st.markdown('<div class="eyebrow">🏆 BOLÃO</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="nome-bolao">{nomes_html}</div>', unsafe_allow_html=True)

    b = img_b64("banner.jpg")
    if b:
        st.markdown(
            f'<img src="data:image/jpeg;base64,{b}" style="width:100%;border-radius:18px;'
            f'box-shadow:0 8px 24px rgba(0,0,0,.25);margin-top:10px;" />',
            unsafe_allow_html=True)

    palpites = carregar_palpites()
    confirmados = len([p for p in palpites if p.get("status") == "pago"])
    agendados = len([p for p in palpites if p.get("status") == "aguardando"])
    svg = ('<svg width="26" height="26" viewBox="0 0 24 24" fill="#fff">'
           '<path d="M16 11c1.66 0 2.99-1.34 2.99-3S17.66 5 16 5s-3 1.34-3 3 1.34 3 3 3zm-8 0c1.66 0 '
           '2.99-1.34 2.99-3S9.66 5 8 5 5 6.34 5 8s1.34 3 3 3zm0 2c-2.33 0-7 1.17-7 3.5V19h14v-2.5c0-2.33'
           '-4.67-3.5-7-3.5zm8 0c-.29 0-.62.02-.97.05 1.16.84 1.97 1.97 1.97 3.45V19h6v-2.5c0-2.33-4.67-3.5'
           '-7-3.5z"/></svg>')
    st.markdown(
        f'<div class="mostradores">'
        f'<div class="mcard">{svg}<div><span class="num">{confirmados}</span>'
        f'<div class="lab">confirmados (pago)</div></div></div>'
        f'<div class="mcard">{svg}<div><span class="num">{agendados}</span>'
        f'<div class="lab">agendados (aguardando)</div></div></div>'
        f'</div>'
        f'<p style="text-align:center;color:#555;font-size:11px;margin:0">atualiza a cada 10 min</p>',
        unsafe_allow_html=True)

    ta, tb = cfg["time_a"], cfg["time_b"]
    st.markdown(f'<div class="jogo">{ta} <span class="x">X</span> {tb}</div>', unsafe_allow_html=True)
    st.markdown('<p style="text-align:center;color:#999;font-size:11px">Jogo definido pelos organizadores</p>',
                unsafe_allow_html=True)

    st.markdown(f'<div class="valor-aposta">Valor da aposta: R$ {VALOR_APOSTA:.2f}</div>',
                unsafe_allow_html=True)

    nome    = st.text_input("Nome completo")
    contato = st.text_input("Contato (WhatsApp)")
    cpf     = st.text_input("CPF", max_chars=14, placeholder="000.000.000-00")

    st.markdown("**Seu palpite de placar:**")
    c1, c2 = st.columns(2)
    ga = c1.number_input(ta, min_value=0, max_value=50, step=1)
    gb = c2.number_input(tb, min_value=0, max_value=50, step=1)

    st.markdown(
        '<div class="regras"><b style="color:#002776">📋 REGULAMENTO</b>'
        '<ol style="margin:6px 0 0;padding-left:18px;line-height:1.5">'
        '<li>Participação válida só com pagamento + envio do comprovante Pix.</li>'
        '<li>30% do valor fica com os organizadores; 70% vai para o prêmio.</li>'
        '<li>Confirme o pagamento em até <b>2h</b> após salvar o palpite.</li></ol></div>',
        unsafe_allow_html=True)

    st.markdown("### 💸 Pague via Pix")
    st.caption(f"Escaneie o QR Code — o valor de R$ {VALOR_APOSTA:.2f} já vem preenchido")
    q = img_b64("qr_caixa.png")
    if q:
        st.markdown(
            f'<div style="text-align:center"><img src="data:image/png;base64,{q}" '
            f'style="width:210px;border-radius:12px;border:1px solid #eee" /></div>',
            unsafe_allow_html=True)
    st.write("Ou copie o **Pix Copia e Cola**:")
    st.code(PIX_COPIA_COLA, language=None)

    msg = (f"⚽🎉 Eaí! Sou {nome or '[seu nome]'} e tô no bolão! "
           f"Meu palpite é {ta} {int(ga)} x {int(gb)} {tb} 🔥 "
           f"Já fiz o Pix de R$ {VALOR_APOSTA:.2f} e tô mandando o comprovante. Bora pro título! 🏆")
    link = f"https://wa.me/{WHATSAPP}?text={quote(msg)}"
    st.markdown("**Envie o comprovante (obrigatório):**")
    st.markdown(f'<a class="wpp" href="{link}" target="_blank">🟢 Enviar comprovante pelo WhatsApp</a>',
                unsafe_allow_html=True)
    st.markdown(f'<p style="text-align:center;color:#002776;font-size:16px;font-weight:800">{WHATSAPP_LABEL}</p>',
                unsafe_allow_html=True)

    aceito = st.checkbox("Li e aceito as regras do bolão.")

    if st.button("Salvar palpite", type="primary", disabled=not aceito):
        if not nome.strip():
            st.error("Informe seu nome.")
        elif not contato.strip():
            st.error("Informe um contato.")
        elif not cpf_valido(cpf):
            st.error("CPF inválido.")
        else:
            inserir_palpite({
                "nome": nome.strip(), "contato": contato.strip(), "cpf": fmt_cpf(cpf),
                "gols_a": int(ga), "gols_b": int(gb), "status": "aguardando",
                "criado_em": datetime.now(timezone.utc).isoformat(), "extra_min": 0,
            })
            st.success("✅ Palpite salvo! Você tem 2 horas para confirmar o pagamento via WhatsApp.")
            st.balloons()

# ----------------------------------------------------------------------------
# PÁGINA: ADMIN
# ----------------------------------------------------------------------------
def pagina_admin(cfg):
    st.title("🔐 Painel do Administrador")

    if not st.session_state.get("logado"):
        s = st.text_input("Senha", type="password")
        if st.button("Entrar"):
            if s == SENHA_ADMIN:
                st.session_state["logado"] = True
                st.rerun()
            else:
                st.error("Senha incorreta.")
        return

    st_autorefresh(interval=30000, key="ref_admin")  # atualiza cronômetros a cada 30s

    st.subheader("⚽ Jogo")
    c1, c2, c3 = st.columns([3, 3, 1])
    ta = c1.text_input("Time A", value=cfg["time_a"])
    tb = c2.text_input("Time B", value=cfg["time_b"])
    if c3.button("Salvar"):
        salvar_config(ta.strip(), tb.strip())
        st.success("Times atualizados.")
        st.rerun()

    palpites = carregar_palpites()
    pagos = [p for p in palpites if p["status"] == "pago"]
    total = len(pagos) * VALOR_APOSTA
    st.divider()
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Inscrições", len(palpites))
    m2.metric("Pagas", len(pagos))
    m3.metric("Organizadores (30%)", f"R$ {total * PERC_ORG:.2f}")
    m4.metric("Prêmio (70%)", f"R$ {total * (1 - PERC_ORG):.2f}")
    st.divider()

    def chave_ordem(p):
        if p["status"] == "aguardando":
            return (0, restante_segundos(p["criado_em"], p.get("extra_min", 0)))
        return (1, 0)
    palpites.sort(key=chave_ordem)

    if not palpites:
        st.info("Nenhuma inscrição ainda.")
        return

    for p in palpites:
        rem = restante_segundos(p["criado_em"], p.get("extra_min", 0))
        if p["status"] == "pago":
            badge, cor = "✅ Pago", "#1b8f4d"
        elif p["status"] == "cancelado":
            badge, cor = "❌ Cancelado", "#999"
        elif rem <= 0:
            badge, cor = "⏰ Expirado", "#d32f2f"
        elif rem < 1800:
            badge, cor = "⏳ Aguardando", "#e6a700"
        else:
            badge, cor = "⏳ Aguardando", "#1b8f4d"

        cronometro = "—" if p["status"] in ("pago", "cancelado") else fmt_hms(rem)
        with st.expander(f"{p['nome']}  ·  {cfg['time_a']} {p['gols_a']} x {p['gols_b']} {cfg['time_b']}  ·  {badge}"):
            st.markdown(f"<span style='color:{cor};font-size:26px;font-weight:800'>{cronometro}</span>",
                        unsafe_allow_html=True)
            st.write(f"**Contato:** {p['contato']}  |  **CPF:** {p['cpf']}")
            b1, b2, b3 = st.columns(3)
            if p["status"] != "pago" and b1.button("Aceitar", key=f"ok{p['id']}"):
                atualizar_palpite(p["id"], {"status": "pago"}); st.rerun()
            if p["status"] != "cancelado" and b2.button("Cancelar", key=f"cc{p['id']}"):
                atualizar_palpite(p["id"], {"status": "cancelado"}); st.rerun()
            if b3.button("+30 min", key=f"ex{p['id']}"):
                atualizar_palpite(p["id"], {"extra_min": p.get("extra_min", 0) + 30}); st.rerun()

# ----------------------------------------------------------------------------
# MAIN
# ----------------------------------------------------------------------------
def esconder_sidebar():
    st.markdown("""
    <style>
      section[data-testid="stSidebar"] { display:none !important; }
      div[data-testid="stSidebarCollapsedControl"] { display:none !important; }
      button[kind="header"] { display:none !important; }
    </style>
    """, unsafe_allow_html=True)

def main():
    st.set_page_config(page_title="Bolão Online", page_icon="⚽", initial_sidebar_state="collapsed")
    css()
    cfg = carregar_config()

    # Acesso admin somente pela URL com ?admin=1 (ex.: http://localhost:8501/?admin=1)
    admin_mode = st.query_params.get("admin") == "1"

    if admin_mode:
        pagina = st.sidebar.radio("Navegação", ["Admin", "Apostar"])
        if pagina == "Apostar":
            pagina_apostar(cfg)
        else:
            pagina_admin(cfg)
    else:
        esconder_sidebar()
        pagina_apostar(cfg)

if __name__ == "__main__":
    main()
