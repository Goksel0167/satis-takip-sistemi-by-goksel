import streamlit as st
import pandas as pd
import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
import os
import json
import io
import plotly.express as px

# --- SAYFA AYARLARI ---
st.set_page_config(page_title="Satış Yönetim Sistemi", layout="wide", page_icon="🏢")

# --- DOSYA AYARLARI ---
SALES_FILE = "satis_verileri.csv"
REF_FILE = "sistem_verileri.json"

# SÜTUN İSİMLERİ (Yüklenen Excel ile Birebir Uyumlu)
COLS = {
    'tarih': 'Tarih', 
    'gun': 'Gün', 
    'ay': 'Ay_Yil', 
    'bayi': 'Bayi', 
    'mus': 'Müşteri Adı', 
    'fab': 'Fabrika', 
    'urun': 'Ürün Adı',
    'mevcut_usd': 'Mevcut ($)', 
    'indirimli_usd': 'İndirimli ($)', 
    'fark_usd': 'Fark ($)', 
    'tonaj': 'Tonaj KG', 
    'tutar_usd': 'Tutar ($)', 
    'kur': 'Tcmb Satış Döviz Kuru USD', 
    'tutar_tl': 'Tutar TL'
}

# --- 1. TCMB KUR ÇEKME (GARANTİLİ) ---
@st.cache_data(ttl=600)
def get_tcmb_rate(target_date):
    """Seçilen tarihe ait kuru getirir. Tatilse geriye gider."""
    date_temp = target_date
    for i in range(10):
        if date_temp.weekday() >= 5: # Hafta sonu
            date_temp -= timedelta(days=1)
            continue
            
        day = date_temp.strftime("%d")
        month = date_temp.strftime("%m")
        year = date_temp.strftime("%Y")
        url = f"https://www.tcmb.gov.tr/kurlar/{year}{month}/{day}{month}{year}.xml"
        
        try:
            res = requests.get(url, timeout=2)
            if res.status_code == 200:
                root = ET.fromstring(res.content)
                for currency in root.findall('Currency'):
                    if currency.get('Kod') == 'USD':
                        val = currency.find('ForexSelling').text
                        if not val: val = currency.find('BanknoteSelling').text
                        if val: return float(val), date_temp.strftime("%d.%m.%Y")
            date_temp -= timedelta(days=1)
        except:
            date_temp -= timedelta(days=1)
            
    return 0.0, "Bulunamadı"

# --- 2. VERİ YÖNETİMİ VE ONARIM ---
def normalize_dataframe(df):
    """Excel sütunlarını sisteme uygun hale getirir"""
    # Eksik sütunları tamamla
    for col_name in COLS.values():
        if col_name not in df.columns:
            # Sayısal alanlar için 0.0, metinler için boş string
            if any(x in col_name for x in ['($)', 'TL', 'KG', 'Kuru']):
                df[col_name] = 0.0
            else:
                df[col_name] = ""
            
    # Sadece gerekli sütunları al
    df = df[list(COLS.values())]
    
    # Sayısal Dönüşümler
    numeric_cols = [
        COLS['mevcut_usd'], COLS['indirimli_usd'], COLS['tonaj'], 
        COLS['kur'], COLS['tutar_usd'], COLS['tutar_tl'], COLS['fark_usd']
    ]
    for c in numeric_cols:
        df[c] = pd.to_numeric(df[c], errors='coerce').fillna(0.0)
    
    # TARİH DÜZELTME (HATA BURADA ÇÖZÜLÜYOR)
    if COLS['tarih'] in df.columns:
        df[COLS['tarih']] = pd.to_datetime(df[COLS['tarih']], errors='coerce')

    return df

def load_data():
    # 1. Tanımlar
    if not os.path.exists(REF_FILE):
        sys_data = {"bayiler": [], "musteriler": [], "urunler": [], "fabrikalar": ["TR14", "TR15"]}
        with open(REF_FILE, "w", encoding="utf-8") as f: json.dump(sys_data, f)
    else:
        with open(REF_FILE, "r", encoding="utf-8") as f: sys_data = json.load(f)
        
    # 2. Satış Verileri
    if 'df' not in st.session_state:
        if os.path.exists(SALES_FILE):
            try:
                df_temp = pd.read_csv(SALES_FILE)
                st.session_state.df = normalize_dataframe(df_temp)
            except:
                st.session_state.df = pd.DataFrame(columns=COLS.values())
        else:
            st.session_state.df = pd.DataFrame(columns=COLS.values())
            
    return sys_data

def save_sys_data(data):
    with open(REF_FILE, "w", encoding="utf-8") as f: json.dump(data, f, ensure_ascii=False)

def get_day_name(date_obj):
    if pd.isnull(date_obj): return ""
    days = {0: "Pazartesi", 1: "Salı", 2: "Çarşamba", 3: "Perşembe", 4: "Cuma", 5: "Cumartesi", 6: "Pazar"}
    return days.get(date_obj.weekday(), "")

def to_excel_with_totals(df):
    """Excel çıktısına TOPLAM satırı ekler"""
    output = io.BytesIO()
    df_export = df.copy()
    
    # Tarih formatı
    df_export[COLS['tarih']] = df_export[COLS['tarih']].dt.strftime('%d.%m.%Y')
    
    # Toplam Satırı Oluştur
    total_row = pd.DataFrame(columns=df_export.columns)
    total_row.loc[0] = "" # Boş satır başlat
    total_row.loc[0, COLS['mus']] = "GENEL TOPLAM" # Etiket
    
    # Toplanacak sütunlar
    sum_cols = [COLS['tonaj'], COLS['tutar_usd'], COLS['tutar_tl']]
    for c in sum_cols:
        total_row.loc[0, c] = df_export[c].sum()
        
    # Veriye ekle
    df_final = pd.concat([df_export, total_row], ignore_index=True)
    
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df_final.to_excel(writer, index=False, sheet_name='Satislar')
        
        # Formatlama (Opsiyonel: Toplam satırını kalın yapma)
        workbook = writer.book
        worksheet = writer.sheets['Satislar']
        bold_fmt = workbook.add_format({'bold': True})
        last_row = len(df_final)
        worksheet.set_row(last_row, None, bold_fmt)
        
    return output.getvalue()

# --- 3. ANA UYGULAMA ---
sys_data = load_data()
st.title("📊 Satış Yönetim Sistemi")

# --- SOL MENÜ ---
with st.sidebar:
    st.header("⚙️ Veri Yükleme")
    with st.expander("📂 Tanımları Yükle"):
        up_def = st.file_uploader("Tanım Excel", type="xlsx", key="def")
        if up_def and st.button("Listeleri Güncelle"):
            try:
                xl = pd.ExcelFile(up_def)
                for sheet in xl.sheet_names:
                    df_tmp = pd.read_excel(xl, sheet)
                    col = df_tmp.iloc[:, 0].dropna().astype(str).tolist()
                    s_low = sheet.lower()
                    if "bayi" in s_low: sys_data["bayiler"] += col
                    elif "musteri" in s_low: sys_data["musteriler"] += col
                    elif "urun" in s_low: sys_data["urunler"] += col
                for k in sys_data: sys_data[k] = sorted(list(set(sys_data[k])))
                save_sys_data(sys_data)
                st.success("Tanımlar güncellendi!")
                st.rerun()
            except Exception as e:
                st.error(f"Hata: {e}")

# --- SEKMELER ---
tab1, tab2, tab3 = st.tabs(["📝 Satış Girişi", "📈 Raporlama", "🛠️ Tanımlar"])

# --- TAB 1: SATIŞ GİRİŞİ ---
with tab1:
    c_date, c_kur_info = st.columns([1, 2])
    with c_date:
        secilen_tarih = st.date_input("Tarih Seçiniz", datetime.now())
    
    # Kuru Çek
    kur_degeri, kur_tarihi = get_tcmb_rate(secilen_tarih)
    
    with c_kur_info:
        if kur_degeri > 0:
            st.success(f"✅ **{kur_tarihi}** tarihli Kur: **{kur_degeri:.4f}**")
        else:
            st.warning("⚠️ Kur bulunamadı.")

    with st.form("satis_form", clear_on_submit=True):
        c1, c2, c3 = st.columns(3)
        with c1:
            bayi = st.selectbox("Bayi", sys_data["bayiler"], index=None, placeholder="Seçiniz")
            musteri = st.selectbox("Müşteri Adı", sys_data["musteriler"], index=None, placeholder="Seçiniz")
            fabrika = st.selectbox("Fabrika", sys_data["fabrikalar"], index=None)
        with c2:
            urun = st.selectbox("Ürün Adı", sys_data["urunler"], index=None, placeholder="Seçiniz")
            f_mevcut = st.number_input("Mevcut Fiyat ($)", min_value=0.0, format="%.2f")
            f_indirim = st.number_input("İndirimli Fiyat ($)", min_value=0.0, format="%.2f")
        with c3:
            tonaj = st.number_input("Tonaj KG", min_value=0.0, format="%.0f")
            kur_input = st.number_input("Kur (Otomatik)", value=kur_degeri, min_value=0.0, format="%.4f")
            
        kaydet = st.form_submit_button("💾 KAYDET")
        
        if kaydet:
            if not musteri or not urun:
                st.error("Müşteri ve Ürün seçmelisiniz!")
            else:
                fark = f_mevcut - f_indirim
                tutar_usd = fark * tonaj
                tutar_tl = tutar_usd * kur_input
                
                # --- TARİH FORMATI DÜZELTME (BURASI DEĞİŞTİ) ---
                # secilen_tarih 'date' objesiydi, bunu pandas'ın anlayacağı 'timestamp' formatına çeviriyoruz.
                tarih_ts = pd.to_datetime(secilen_tarih)
                
                new_data = {
                    COLS['tarih']: tarih_ts,
                    COLS['gun']: get_day_name(secilen_tarih),
                    COLS['ay']: secilen_tarih.strftime("%Y-%m"),
                    COLS['bayi']: bayi, COLS['mus']: musteri, COLS['fab']: fabrika,
                    COLS['urun']: urun, COLS['mevcut_usd']: f_mevcut,
                    COLS['indirimli_usd']: f_indirim, COLS['fark_usd']: fark,
                    COLS['tonaj']: tonaj, COLS['tutar_usd']: tutar_usd,
                    COLS['kur']: kur_input, COLS['tutar_tl']: tutar_tl
                }
                
                st.session_state.df = pd.concat([st.session_state.df, pd.DataFrame([new_data])], ignore_index=True)
                st.session_state.df.to_csv(SALES_FILE, index=False)
                st.success("Kayıt Eklendi!")
                st.rerun()

    # --- TABLO DÜZENLEME ---
    st.divider()
    st.subheader("📋 Kayıt Listesi & Düzenleme")
    
    if not st.session_state.df.empty:
        # Canlı Toplamları Göster
        t_ton = st.session_state.df[COLS['tonaj']].sum()
        t_usd = st.session_state.df[COLS['tutar_usd']].sum()
        t_tl = st.session_state.df[COLS['tutar_tl']].sum()
        
        m1, m2, m3 = st.columns(3)
        m1.metric("TOPLAM Tonaj", f"{t_ton:,.0f} KG")
        m2.metric("TOPLAM Tutar ($)", f"${t_usd:,.2f}")
        m3.metric("TOPLAM Tutar (TL)", f"₺{t_tl:,.2f}")
        
        # --- SIRALAMA HATASI İÇİN GÜVENLİK ÖNLEMİ ---
        # Sıralama yapmadan önce Tarih sütununu kesinlikle datetime formatına zorluyoruz.
        st.session_state.df[COLS['tarih']] = pd.to_datetime(st.session_state.df[COLS['tarih']], errors='coerce')
        
        # Eskiden Yeniye (ascending=True)
        df_sorted = st.session_state.df.sort_values(by=COLS['tarih'], ascending=True)
        
        edited_df = st.data_editor(df_sorted, num_rows="dynamic", use_container_width=True)
        
        if st.button("🔄 Tabloyu Güncelle ve Hesapla"):
            edited_df = normalize_dataframe(edited_df)
            for idx, row in edited_df.iterrows():
                try:
                    m_fiyat = float(row[COLS['mevcut_usd']])
                    i_fiyat = float(row[COLS['indirimli_usd']])
                    ton = float(row[COLS['tonaj']])
                    kur = float(row[COLS['kur']])
                    
                    fark = m_fiyat - i_fiyat
                    t_usd = fark * ton
                    t_tl = t_usd * kur
                    
                    edited_df.at[idx, COLS['fark_usd']] = fark
                    edited_df.at[idx, COLS['tutar_usd']] = t_usd
                    edited_df.at[idx, COLS['tutar_tl']] = t_tl
                    
                    d = pd.to_datetime(row[COLS['tarih']])
                    edited_df.at[idx, COLS['gun']] = get_day_name(d)
                    edited_df.at[idx, COLS['ay']] = d.strftime("%Y-%m")
                except: pass

            st.session_state.df = edited_df
            st.session_state.df.to_csv(SALES_FILE, index=False)
            st.success("Güncellendi!")
            st.rerun()

# --- TAB 2: RAPORLAMA ---
with tab2:
    df = st.session_state.df
    if df.empty:
        st.info("Veri yok.")
    else:
        # Filtreleme
        aylar = sorted(df[COLS['ay']].astype(str).unique())
        secilen_ay = st.multiselect("Ay Seçiniz", aylar, default=aylar)
        
        df_filt = df if not secilen_ay else df[df[COLS['ay']].isin(secilen_ay)]
        
        c1, c2, c3 = st.columns(3)
        c1.metric("Toplam Tonaj", f"{df_filt[COLS['tonaj']].sum():,.0f}")
        c2.metric("Toplam USD", f"${df_filt[COLS['tutar_usd']].sum():,.2f}")
        c3.metric("Toplam TL", f"₺{df_filt[COLS['tutar_tl']].sum():,.2f}")
        
        st.divider()
        
        if COLS['mus'] in df_filt.columns:
            pivot = df_filt.groupby(COLS['mus']).agg({
                COLS['tonaj']: 'sum',
                COLS['tutar_usd']: 'sum'
            }).reset_index().sort_values(by=COLS['tutar_usd'], ascending=False)
            
            c_chart, c_table = st.columns([2, 1])
            with c_chart:
                fig = px.bar(pivot.head(10), x=COLS['mus'], y=COLS['tutar_usd'], title="Top 10 Müşteri")
                st.plotly_chart(fig, use_container_width=True)
            with c_table:
                st.dataframe(pivot, hide_index=True, use_container_width=True)
        
        st.download_button("📥 Excel İndir (Toplamlı)", data=to_excel_with_totals(df_filt), file_name="Satis_Raporu.xlsx")

# --- TAB 3: TANIMLAR ---
with tab3:
    c1, c2, c3 = st.columns(3)
    def manage(title, key):
        st.subheader(title)
        val = st.text_input(f"Yeni {title}", key=f"n_{key}")
        if st.button(f"Ekle {title}"):
            if val and val not in sys_data[key]:
                sys_data[key].append(val)
                save_sys_data(sys_data)
                st.rerun()
        d_val = st.selectbox(f"Sil {title}", sys_data[key], key=f"d_{key}")
        if st.button(f"Sil {title}"):
            sys_data[key].remove(d_val)
            save_sys_data(sys_data)
            st.rerun()

    with c1: manage("Bayi", "bayiler")
    with c2: manage("Müşteri", "musteriler")
    with c3: manage("Ürün", "urunler")
    
    if st.button("🔥 VERİTABANINI SIFIRLA"):
        if os.path.exists(SALES_FILE): os.remove(SALES_FILE)
        st.session_state.df = pd.DataFrame(columns=COLS.values())
        st.rerun()
