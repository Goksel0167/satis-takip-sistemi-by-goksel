import streamlit as st
import pandas as pd
import plotly.express as px
import os
import json
import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
import io

# --- 1. AYARLAR VE YAPILANDIRMA ---
# Hakkında metni
about_text = """
### Satış Yönetim Sistemi

**Telif Hakkı 2025 Snowflake Inc.'e ait. Tüm haklar saklıdır.**
**Telif hakkı Göksel Çapkın'a aittir.**
"""

st.set_page_config(
    page_title="Satış Yönetim Sistemi", 
    layout="wide", 
    page_icon="🏢",
    menu_items={
        'About': about_text
    }
)

# Otomatik Config Düzeltici
def fix_config():
    config_dir = ".streamlit"
    if not os.path.exists(config_dir): os.makedirs(config_dir)
    config_file = os.path.join(config_dir, "config.toml")
    if not os.path.exists(config_file):
        with open(config_file, "w") as f:
            f.write("[server]\nenableCORS=false\nenableXsrfProtection=false\nmaxUploadSize=200\n[browser]\ngatherUsageStats=false")

if fix_config():
    st.toast("Ayarlar yapıldı. Lütfen yeniden başlatın.")

# Footer CSS
hide_style = """
<style>
#MainMenu {visibility: visible;}
footer {visibility: hidden;}
.footer {position: fixed; left: 0; bottom: 0; width: 100%; background-color: #f0f2f6; color: #31333F; text-align: center; padding: 10px; font-size: 12px; border-top: 1px solid #d2d2d2; z-index: 1000;}
</style>
<div class="footer"><p>Telif Hakkı 2025 Snowflake Inc.'e ait. Tüm haklar saklıdır. Telif hakkı Göksel Çapkın'a aittir.</p></div>
"""
st.markdown(hide_style, unsafe_allow_html=True)

# --- DOSYA İSİMLERİ ---
SALES_FILE = "satis_verileri.csv"
REF_FILE = "sistem_verileri.json"

COLS = {
    'tarih': 'Tarih',
    'gun': 'Gün',
    'ay': 'Ay_Yil',
    'bayi': 'Bayi/Müşteri Adı',
    'mus': 'Müşteri Adı',
    'fab': 'Fabrika',
    'urun': 'Ürün Adı',
    'mevcut_usd': 'Mevcut Fiyat USD',
    'indirimli_usd': 'İndirimli Fiyat USD',
    'fark_usd': 'Fark USD',
    'tonaj': 'Tonaj KG',
    'tutar_usd': 'Tutar USD',
    'kur': 'TCMB Satış Döviz Kuru USD',
    'tutar_tl': 'Tutar TL'
}

# --- YARDIMCI FONKSİYONLAR ---

@st.cache_data(ttl=3600)
def get_tcmb_rate(target_date):
    date_temp = target_date
    for i in range(7):
        if date_temp.weekday() >= 5: 
            date_temp -= timedelta(days=1)
            continue
        day, month, year = date_temp.strftime("%d"), date_temp.strftime("%m"), date_temp.strftime("%Y")
        url = f"https://www.tcmb.gov.tr/kurlar/{year}{month}/{day}{month}{year}.xml"
        try:
            res = requests.get(url, timeout=2)
            if res.status_code == 200:
                root = ET.fromstring(res.content)
                for currency in root.findall('Currency'):
                    if currency.get('Kod') == 'USD':
                        return float(currency.find('ForexSelling').text)
            else:
                date_temp -= timedelta(days=1)
        except: return None
    return None

def load_system_data():
    if os.path.exists(REF_FILE):
        try: return json.load(open(REF_FILE, "r", encoding="utf-8"))
        except: pass
    return {"bayiler": [], "musteriler": [], "urunler": [], "fabrikalar": ["TR14", "TR15", "TR16"]}

def save_system_data(data):
    json.dump(data, open(REF_FILE, "w", encoding="utf-8"), ensure_ascii=False)

def clean_list(liste):
    return sorted(list(set([str(i).strip() for i in liste if str(i).strip() != "" and str(i).lower() != "nan"])))

def get_turkish_day(date_obj):
    if pd.isnull(date_obj): return ""
    days = {0: "Pazartesi", 1: "Salı", 2: "Çarşamba", 3: "Perşembe", 4: "Cuma", 5: "Cumartesi", 6: "Pazar"}
    return days.get(date_obj.weekday(), "")

def convert_df_to_excel(df):
    output = io.BytesIO()
    try:
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df.to_excel(writer, index=False, sheet_name='Satis Listesi')
            worksheet = writer.sheets['Satis Listesi']
            for i, col in enumerate(df.columns):
                worksheet.set_column(i, i, 20)
    except:
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='Satis Listesi')
    return output.getvalue()

def akilli_excel_import(uploaded_file):
    logs = []
    data_found = {"bayiler": [], "musteriler": [], "urunler": [], "fabrikalar": []}
    try:
        xl = pd.ExcelFile(uploaded_file)
        for sheet in xl.sheet_names:
            s_low = sheet.lower()
            df = pd.read_excel(xl, sheet_name=sheet)
            col = df.iloc[:, 0].dropna().tolist()
            if "bayi" in s_low: data_found["bayiler"].extend(col); logs.append(f"✅ Bayiler: {sheet}")
            elif "musteri" in s_low: data_found["musteriler"].extend(col); logs.append(f"✅ Müşteriler: {sheet}")
            elif "urun" in s_low: data_found["urunler"].extend(col); logs.append(f"✅ Ürünler: {sheet}")
            elif "fabrika" in s_low: data_found["fabrikalar"].extend(col); logs.append(f"✅ Fabrikalar: {sheet}")
        return True, data_found, logs
    except Exception as e: return False, {}, [f"Hata: {str(e)}"]

# --- HESAPLAMA MOTORU ---
def recalculate_dataframe(df):
    numeric_cols = [COLS['mevcut_usd'], COLS['indirimli_usd'], COLS['tonaj'], COLS['kur']]
    for col in numeric_cols:
        if col in df.columns:
            if df[col].dtype == object:
                df[col] = df[col].astype(str).str.replace(',', '.', regex=False)
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
            
    if COLS['tarih'] in df.columns:
        df[COLS['tarih']] = pd.to_datetime(df[COLS['tarih']], errors='coerce')
        df[COLS['gun']] = df[COLS['tarih']].apply(get_turkish_day)

    df[COLS['fark_usd']] = df[COLS['mevcut_usd']] - df[COLS['indirimli_usd']]
    df[COLS['tutar_usd']] = df[COLS['fark_usd']] * df[COLS['tonaj']]
    df[COLS['tutar_tl']] = df[COLS['tutar_usd']] * df[COLS['kur']]
    return df

# --- VERİ YÜKLEME VE SESSION STATE ---
if 'df_sales' not in st.session_state:
    if os.path.exists(SALES_FILE):
        try:
            st.session_state.df_sales = pd.read_csv(SALES_FILE, encoding='utf-8-sig')
        except:
            st.session_state.df_sales = pd.read_csv(SALES_FILE, encoding='utf-8')
    else:
        st.session_state.df_sales = pd.DataFrame(columns=list(COLS.values()))
        
    if COLS['tarih'] in st.session_state.df_sales.columns:
        st.session_state.df_sales[COLS['tarih']] = pd.to_datetime(st.session_state.df_sales[COLS['tarih']], errors='coerce')

sys_data = load_system_data()

st.title("📊 Satış ve Hesaplama Sistemi")

# --- SIDEBAR (KULLANIM KILAVUZU EKLENDİ) ---
with st.sidebar:
    st.header("⚙️ Veri Kurulumu")
    uploaded_file = st.file_uploader("Excel Yükle (Listeleri Güncelle)", type=["xlsx"])
    if uploaded_file and st.button("📥 Listeleri Sisteme Çek"):
        success, new_data, logs = akilli_excel_import(uploaded_file)
        if success:
            sys_data["bayiler"] = clean_list(sys_data.get("bayiler", []) + new_data["bayiler"])
            sys_data["musteriler"] = clean_list(sys_data["musteriler"] + new_data["musteriler"])
            sys_data["urunler"] = clean_list(sys_data["urunler"] + new_data["urunler"])
            if new_data["fabrikalar"]: sys_data["fabrikalar"] = clean_list(new_data["fabrikalar"])
            save_system_data(sys_data)
            st.success("Listeler güncellendi!")
            st.rerun()

    st.divider()
    
    # KULLANIM KILAVUZU BÖLÜMÜ
    with st.expander("📘 Kullanım Kılavuzu"):
        st.markdown("""
        **1. Başlangıç:**
        - İlk kez kullanıyorsanız yukarıdaki 'Excel Yükle' alanından müşteri/ürün listenizi yükleyin.
        
        **2. Satış Girişi:**
        - 'Satış Girişi' sekmesinden formu doldurun.
        - TCMB Kuru otomatik çekilir.
        - 'Kaydet' dediğinizde form temizlenir.
        
        **3. Düzenleme & Hesaplama:**
        - Kayıtları değiştirmek için alttaki tabloyu kullanın.
        - Değerleri değiştirdikten sonra **'Hesapla ve Güncelle'** butonuna MUTLAKA basın.
        
        **4. Raporlama:**
        - 'Analiz Raporu' sekmesinden aylık döküm alın.
        - 'Excel Olarak İndir' butonu ile raporu alın.
        """)

# --- SEKMELER ---
tabs = st.tabs(["📝 Satış Girişi & Düzenleme", "📈 Analiz Raporu", "🛠️ Tanımlamalar"])

# --- TAB 1: VERİ GİRİŞİ ---
with tabs[0]:
    st.markdown("### 1. Yeni Satış Ekle")
    
    with st.form("entry_form", clear_on_submit=True):
        c1, c2, c3 = st.columns(3)
        with c1:
            tarih = st.date_input("Tarih (Gün/Ay/Yıl)", datetime.now(), format="DD/MM/YYYY")
            bayi = st.selectbox("Bayi/Müşteri Adı", options=sys_data.get("bayiler", []), index=None, placeholder="Seçiniz...")
            musteri = st.selectbox("Müşteri Adı (Proje)", options=sys_data["musteriler"], index=None, placeholder="Seçiniz...")
            fabrika = st.selectbox("Fabrika", options=sys_data["fabrikalar"], index=None, placeholder="Seçiniz...")
        with c2:
            urun = st.selectbox("Ürün", options=sys_data["urunler"], index=None, placeholder="Seçiniz...")
            mevcut_fiyat = st.number_input("Mevcut Fiyat USD", min_value=0.0, format="%.2f")
            ind_fiyat = st.number_input("İndirimli Fiyat USD", min_value=0.0, format="%.2f")
        with c3:
            tonaj = st.number_input("Tonaj KG", min_value=0.0, format="%.2f")
            kur_default = get_tcmb_rate(datetime.now()) or 0.0
            kur_inp = st.number_input("TCMB Satış Kuru", value=kur_default, min_value=0.0, format="%.4f")
            
        btn_add = st.form_submit_button("💾 Kaydet")
        
        if btn_add:
            if not musteri or not urun:
                st.error("Müşteri ve Ürün seçimi zorunludur!")
            else:
                ay_yil = tarih.strftime("%Y-%m")
                gun_str = get_turkish_day(tarih)
                fark_usd = mevcut_fiyat - ind_fiyat
                tutar_usd = fark_usd * tonaj
                tutar_tl = tutar_usd * kur_inp
                
                new_row = {
                    COLS['tarih']: pd.to_datetime(tarih),
                    COLS['gun']: gun_str,
                    COLS['ay']: ay_yil,
                    COLS['bayi']: bayi if bayi else "",
                    COLS['mus']: musteri, 
                    COLS['fab']: fabrika if fabrika else "", 
                    COLS['urun']: urun,
                    COLS['mevcut_usd']: mevcut_fiyat, 
                    COLS['indirimli_usd']: ind_fiyat,
                    COLS['fark_usd']: fark_usd, 
                    COLS['tonaj']: tonaj,
                    COLS['tutar_usd']: tutar_usd, 
                    COLS['kur']: kur_inp, 
                    COLS['tutar_tl']: tutar_tl
                }
                
                st.session_state.df_sales = pd.concat([st.session_state.df_sales, pd.DataFrame([new_row])], ignore_index=True)
                st.session_state.df_sales.to_csv(SALES_FILE, index=False, encoding='utf-8-sig')
                st.success(f"✅ Kayıt Başarılı! ({musteri})")
                st.rerun()

    st.divider()
    st.markdown("### 2. Tabloyu Düzenle ve Hesapla")
    
    df = st.session_state.df_sales
    
    if not df.empty:
        t_tonaj = df[COLS['tonaj']].sum()
        t_usd = df[COLS['tutar_usd']].sum()
        t_tl = df[COLS['tutar_tl']].sum()
        
        m1, m2, m3 = st.columns(3)
        m1.metric("📦 Toplam Tonaj", f"{t_tonaj:,.0f} KG")
        m2.metric("💲 Toplam Tutar (USD)", f"${t_usd:,.2f}")
        m3.metric("₺ Toplam Tutar (TL)", f"₺{t_tl:,.2f}")
        
        st.markdown("---")

        df_display = df.sort_values(by=COLS['tarih'], ascending=False)
        
        display_cols = [
            COLS['tarih'], COLS['gun'], 
            COLS['bayi'], COLS['mus'], 
            COLS['fab'], COLS['urun'],
            COLS['mevcut_usd'], COLS['indirimli_usd'],
            COLS['fark_usd'], COLS['tonaj'], 
            COLS['tutar_usd'], COLS['kur'], COLS['tutar_tl']
        ]
        
        edited_df = st.data_editor(
            df_display,
            column_order=display_cols,
            disabled=[COLS['gun'], COLS['fark_usd'], COLS['tutar_usd'], COLS['tutar_tl']],
            column_config={
                COLS['tarih']: st.column_config.DateColumn("Tarih", format="DD/MM/YYYY"),
                COLS['bayi']: st.column_config.SelectboxColumn("Bayi", options=sys_data.get("bayiler", [])),
                COLS['mevcut_usd']: st.column_config.NumberColumn("Mevcut ($)", format="%.2f"),
                COLS['indirimli_usd']: st.column_config.NumberColumn("İndirimli ($)", format="%.2f"),
                COLS['fark_usd']: st.column_config.NumberColumn("Fark ($)", format="%.2f"),
                COLS['tutar_usd']: st.column_config.NumberColumn("Tutar ($)", format="%.2f"),
            },
            num_rows="dynamic",
            use_container_width=True,
            key="data_editor_main",
            height=500
        )
        
        if st.button("🔄 Hesapla ve Güncelle", type="primary"):
            try:
                final_df = recalculate_dataframe(edited_df)
                st.session_state.df_sales = final_df
                final_df.to_csv(SALES_FILE, index=False, encoding='utf-8-sig')
                st.success("✅ Veriler Güncellendi, Hesaplandı ve Kaydedildi!")
                st.rerun()
            except Exception as e:
                st.error(f"Hata: {e}")
    else:
        st.info("Henüz veri girişi yapılmamış.")

# --- TAB 2: ANALİZ ---
with tabs[1]:
    df = st.session_state.df_sales
    if not df.empty:
        st.subheader("📊 Performans Analizi")
        all_months = sorted(df[COLS['ay']].astype(str).unique())
        sel_months = st.multiselect("Dönem Seçimi:", all_months, default=all_months)
        
        if sel_months:
            df_f = df[df[COLS['ay']].isin(sel_months)]
            
            k1, k2, k3 = st.columns(3)
            k1.metric("Toplam Tonaj", f"{df_f[COLS['tonaj']].sum():,.0f} KG")
            k2.metric("Toplam Tutar (USD)", f"${df_f[COLS['tutar_usd']].sum():,.2f}")
            k3.metric("Toplam Tutar (TL)", f"₺{df_f[COLS['tutar_tl']].sum():,.2f}")
            
            g1, g2 = st.columns(2)
            with g1:
                st.caption("Bayi/Müşteri Bazlı Ciro ($)")
                grp_bayi = df_f.groupby(COLS['bayi'])[COLS['tutar_usd']].sum().nlargest(10).reset_index()
                st.plotly_chart(px.bar(grp_bayi, x=COLS['tutar_usd'], y=COLS['bayi'], orientation='h'), use_container_width=True)
            with g2:
                st.caption("Aylık Trend (USD)")
                grp_ay = df_f.groupby(COLS['ay'])[COLS['tutar_usd']].sum().reset_index()
                st.plotly_chart(px.line(grp_ay, x=COLS['ay'], y=COLS['tutar_usd'], markers=True), use_container_width=True)
                
            excel_data = convert_df_to_excel(df_f)
            if excel_data:
                st.download_button(
                    label="📥 Excel Olarak İndir (.xlsx)",
                    data=excel_data,
                    file_name=f"Satis_Raporu_{datetime.now().strftime('%d-%m-%Y')}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
    else:
        st.info("Veri yok.")

# --- TAB 3: YÖNETİM ---
with tabs[2]:
    st.subheader("Veri Tanımlama")
    c1, c2, c3 = st.columns(3)
    
    with c1:
        st.markdown("**Bayi Yönetimi**")
        new_b = st.text_input("Bayi Ekle", key="inp_bayi")
        if st.button("Ekle (Bayi)"):
            if new_b:
                sys_data["bayiler"] = clean_list(sys_data.get("bayiler", []) + [new_b])
                save_system_data(sys_data)
                st.success(f"{new_b} eklendi!")
                st.rerun()
        
        bayiler = sys_data.get("bayiler", [])
        if bayiler:
            del_b = st.selectbox("Sil (Bayi)", bayiler, key="sel_bayi")
            if st.button("Sil (Bayi)"):
                sys_data["bayiler"].remove(del_b)
                save_system_data(sys_data)
                st.success("Silindi!")
                st.rerun()

    with c2:
        st.markdown("**Müşteri Yönetimi**")
        new_m = st.text_input("Müşteri Ekle", key="inp_mus")
        if st.button("Ekle (Müşteri)"):
            if new_m:
                sys_data["musteriler"] = clean_list(sys_data["musteriler"] + [new_m])
                save_system_data(sys_data)
                st.success(f"{new_m} eklendi!")
                st.rerun()
        
        musteriler = sys_data.get("musteriler", [])
        if musteriler:
            del_m = st.selectbox("Sil (Müşteri)", musteriler, key="sel_mus")
            if st.button("Sil (Müşteri)"):
                sys_data["musteriler"].remove(del_m)
                save_system_data(sys_data)
                st.success("Silindi!")
                st.rerun()

    with c3:
        st.markdown("**Ürün Yönetimi**")
        new_u = st.text_input("Ürün Ekle", key="inp_urun")
        if st.button("Ekle (Ürün)"):
            if new_u:
                sys_data["urunler"] = clean_list(sys_data["urunler"] + [new_u])
                save_system_data(sys_data)
                st.success(f"{new_u} eklendi!")
                st.rerun()
        
        urunler = sys_data.get("urunler", [])
        if urunler:
            del_u = st.selectbox("Sil (Ürün)", urunler, key="sel_urun")
            if st.button("Sil (Ürün)"):
                sys_data["urunler"].remove(del_u)
                save_system_data(sys_data)
                st.success("Silindi!")
                st.rerun()
                
    st.divider()
    if st.button("🗑️ TÜM VERİLERİ SIFIRLA"):
        if os.path.exists(SALES_FILE): os.remove(SALES_FILE)
        st.session_state.df_sales = pd.DataFrame(columns=list(COLS.values()))
        save_system_data({"bayiler":[], "musteriler":[], "urunler":[], "fabrikalar":["TR14"]})
        st.warning("Sıfırlandı.")
        st.rerun()