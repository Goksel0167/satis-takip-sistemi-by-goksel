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
COLS = {
    'tarih': 'Tarih', 'gun': 'Gün', 'ay': 'Ay_Yil', 'bayi': 'Bayi', 
    'mus': 'Müşteri', 'fab': 'Fabrika', 'urun': 'Ürün',
    'mevcut_usd': 'Mevcut ($)', 'indirimli_usd': 'İndirimli ($)', 
    'fark_usd': 'Fark ($)', 'tonaj': 'Tonaj', 
    'tutar_usd': 'Tutar ($)', 'kur': 'Kur', 'tutar_tl': 'Tutar (TL)'
}

# --- 1. GARANTİLİ TCMB KUR ÇEKME FONKSİYONU ---
@st.cache_data(ttl=600)
def get_tcmb_rate(target_date):
    """
    Seçilen tarihe ait TCMB Döviz Satış kurunu getirir.
    Tatil veya hafta sonu ise, en son işlem gören güne (geriye doğru) gider.
    """
    date_temp = target_date
    
    # 10 gün geriye gitme hakkı (Bayramlar için)
    for i in range(10):
        # Hafta sonu kontrolü (Cumartesi=5, Pazar=6)
        if date_temp.weekday() >= 5:
            date_temp -= timedelta(days=1)
            continue
            
        # URL Oluştur (TCMB Formatı: GGMMAAAA.xml)
        day = date_temp.strftime("%d")
        month = date_temp.strftime("%m")
        year = date_temp.strftime("%Y")
        url = f"https://www.tcmb.gov.tr/kurlar/{year}{month}/{day}{month}{year}.xml"
        
        try:
            # 2 saniye içinde cevap gelmezse diğer güne geç
            res = requests.get(url, timeout=2)
            
            if res.status_code == 200:
                root = ET.fromstring(res.content)
                for currency in root.findall('Currency'):
                    if currency.get('Kod') == 'USD':
                        # Önce Döviz Satış'a bak
                        val = currency.find('ForexSelling').text
                        # Boşsa Efektif Satış'a bak
                        if not val: val = currency.find('BanknoteSelling').text
                        
                        if val:
                            return float(val), date_temp.strftime("%d.%m.%Y")
            
            # 200 dönmediyse (Tatil vb.) 1 gün geri git
            date_temp -= timedelta(days=1)
            
        except:
            # Bağlantı hatası olursa 1 gün geri git
            date_temp -= timedelta(days=1)
            
    return 0.0, "Bulunamadı"

# --- 2. YARDIMCI FONKSİYONLAR ---
def load_data():
    # Sistem Verileri
    if not os.path.exists(REF_FILE):
        sys_data = {"bayiler": [], "musteriler": [], "urunler": [], "fabrikalar": ["TR14", "TR15"]}
        with open(REF_FILE, "w", encoding="utf-8") as f: json.dump(sys_data, f)
    else:
        with open(REF_FILE, "r", encoding="utf-8") as f: sys_data = json.load(f)
        
    # Satış Verileri (Session State'e yükle)
    if 'df' not in st.session_state:
        if os.path.exists(SALES_FILE):
            st.session_state.df = pd.read_csv(SALES_FILE)
            # Tarih formatını düzelt
            if COLS['tarih'] in st.session_state.df.columns:
                st.session_state.df[COLS['tarih']] = pd.to_datetime(st.session_state.df[COLS['tarih']])
        else:
            st.session_state.df = pd.DataFrame(columns=COLS.values())
            
    return sys_data

def save_sys_data(data):
    with open(REF_FILE, "w", encoding="utf-8") as f: json.dump(data, f, ensure_ascii=False)

def get_day_name(date_obj):
    days = {0: "Pazartesi", 1: "Salı", 2: "Çarşamba", 3: "Perşembe", 4: "Cuma", 5: "Cumartesi", 6: "Pazar"}
    return days.get(date_obj.weekday(), "")

def to_excel(df):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name='Satislar')
    return output.getvalue()

# --- 3. ANA UYGULAMA ---
sys_data = load_data()
st.title("📊 Satış Yönetim Sistemi")

# --- SOL MENÜ (VERİ YÜKLEME) ---
with st.sidebar:
    st.header("⚙️ Veri Yükleme")
    
    # Tanım Yükleme
    with st.expander("📂 Tanımları Yükle"):
        up_def = st.file_uploader("Tanım Excel", type="xlsx", key="def")
        if up_def and st.button("Listeleri Güncelle"):
            xl = pd.ExcelFile(up_def)
            for sheet in xl.sheet_names:
                df_tmp = pd.read_excel(xl, sheet)
                col = df_tmp.iloc[:, 0].dropna().astype(str).tolist()
                s_low = sheet.lower()
                if "bayi" in s_low: sys_data["bayiler"] += col
                elif "musteri" in s_low: sys_data["musteriler"] += col
                elif "urun" in s_low: sys_data["urunler"] += col
            
            # Tekrarları temizle
            for k in sys_data: sys_data[k] = sorted(list(set(sys_data[k])))
            save_sys_data(sys_data)
            st.success("Tanımlar güncellendi!")
            st.rerun()

    # Satış Yükleme
    with st.expander("📥 Geçmiş Satışları Yükle"):
        up_sales = st.file_uploader("Satış Excel", type="xlsx", key="sales")
        if up_sales and st.button("Verileri Aktar"):
            df_new = pd.read_excel(up_sales)
            # Kolon eşleştirme (Basit)
            # Burası kullanıcının excel formatına göre özelleştirilebilir
            # Şimdilik direkt append ediyoruz
            st.session_state.df = pd.concat([st.session_state.df, df_new], ignore_index=True)
            st.session_state.df.to_csv(SALES_FILE, index=False)
            st.success("Veriler eklendi!")
            st.rerun()

# --- SEKMELER ---
tab1, tab2, tab3 = st.tabs(["📝 Satış Girişi", "📈 Raporlama", "🛠️ Tanımlar"])

# --- TAB 1: SATIŞ GİRİŞİ ---
with tab1:
    # ---------------------------------------------------------
    # KRİTİK BÖLÜM: TARİH SEÇİMİ VE KUR ÇEKME (FORM DIŞINDA)
    # ---------------------------------------------------------
    c_date, c_kur_info = st.columns([1, 2])
    with c_date:
        # Tarih değiştiği an sayfa yenilenir (key sayesinde)
        secilen_tarih = st.date_input("Tarih Seçiniz", datetime.now())
    
    # Kuru Çek
    kur_degeri, kur_tarihi = get_tcmb_rate(secilen_tarih)
    
    with c_kur_info:
        if kur_degeri > 0:
            st.success(f"✅ **{kur_tarihi}** tarihli TCMB Satış Kuru alındı: **{kur_degeri:.4f}**")
        else:
            st.error("⚠️ Kur bulunamadı! Lütfen manuel giriniz.")

    # ---------------------------------------------------------
    # FORM ALANI (VERİ GİRİŞİ)
    # ---------------------------------------------------------
    with st.form("satis_form", clear_on_submit=True):
        c1, c2, c3 = st.columns(3)
        
        with c1:
            bayi = st.selectbox("Bayi", sys_data["bayiler"], index=None, placeholder="Seçiniz")
            musteri = st.selectbox("Müşteri", sys_data["musteriler"], index=None, placeholder="Seçiniz")
            fabrika = st.selectbox("Fabrika", sys_data["fabrikalar"], index=None)
            
        with c2:
            urun = st.selectbox("Ürün", sys_data["urunler"], index=None, placeholder="Seçiniz")
            f_mevcut = st.number_input("Mevcut Fiyat ($)", min_value=0.0, format="%.2f")
            f_indirim = st.number_input("İndirimli Fiyat ($)", min_value=0.0, format="%.2f")
            
        with c3:
            tonaj = st.number_input("Tonaj (KG)", min_value=0.0, format="%.0f")
            # Kuru otomatik getiriyoruz, kullanıcı isterse değiştirebilir
            kur_input = st.number_input("Kur (Otomatik)", value=kur_degeri, min_value=0.0, format="%.4f")
            
        kaydet = st.form_submit_button("💾 KAYDET")
        
        if kaydet:
            if not musteri or not urun:
                st.error("Müşteri ve Ürün seçmelisiniz!")
            else:
                # Hesaplamalar
                fark = f_mevcut - f_indirim
                tutar_usd = fark * tonaj
                tutar_tl = tutar_usd * kur_input
                
                new_data = {
                    COLS['tarih']: secilen_tarih,
                    COLS['gun']: get_day_name(secilen_tarih),
                    COLS['ay']: secilen_tarih.strftime("%Y-%m"),
                    COLS['bayi']: bayi, COLS['mus']: musteri, COLS['fab']: fabrika,
                    COLS['urun']: urun, COLS['mevcut_usd']: f_mevcut,
                    COLS['indirimli_usd']: f_indirim, COLS['fark_usd']: fark,
                    COLS['tonaj']: tonaj, COLS['tutar_usd']: tutar_usd,
                    COLS['kur']: kur_input, COLS['tutar_tl']: tutar_tl
                }
                
                # Ekle ve Kaydet
                st.session_state.df = pd.concat([st.session_state.df, pd.DataFrame([new_data])], ignore_index=True)
                st.session_state.df.to_csv(SALES_FILE, index=False)
                st.success("Kayıt Eklendi!")
                st.rerun()

    # --- TABLO DÜZENLEME ---
    st.divider()
    st.subheader("📋 Kayıt Listesi & Düzenleme")
    
    if not st.session_state.df.empty:
        # Tarihe göre sırala
        df_sorted = st.session_state.df.sort_values(by=COLS['tarih'], ascending=False)
        
        # Editör
        edited_df = st.data_editor(
            df_sorted,
            num_rows="dynamic",
            use_container_width=True,
            column_config={
                COLS['tarih']: st.column_config.DateColumn("Tarih", format="DD.MM.YYYY"),
                COLS['kur']: st.column_config.NumberColumn("Kur", format="%.4f")
            }
        )
        
        # Güncelle Butonu
        if st.button("🔄 Tabloyu Güncelle ve Hesapla"):
            # Yeniden Hesaplama Mantığı
            for idx, row in edited_df.iterrows():
                fark = row[COLS['mevcut_usd']] - row[COLS['indirimli_usd']]
                t_usd = fark * row[COLS['tonaj']]
                t_tl = t_usd * row[COLS['kur']]
                
                edited_df.at[idx, COLS['fark_usd']] = fark
                edited_df.at[idx, COLS['tutar_usd']] = t_usd
                edited_df.at[idx, COLS['tutar_tl']] = t_tl
                
                # Tarih değiştiyse günü ve ayı da güncelle
                d = pd.to_datetime(row[COLS['tarih']])
                edited_df.at[idx, COLS['gun']] = get_day_name(d)
                edited_df.at[idx, COLS['ay']] = d.strftime("%Y-%m")

            st.session_state.df = edited_df
            st.session_state.df.to_csv(SALES_FILE, index=False)
            st.success("Tüm satırlar yeniden hesaplandı ve kaydedildi!")
            st.rerun()

# --- TAB 2: RAPORLAMA ---
with tab2:
    df = st.session_state.df
    if df.empty:
        st.info("Veri yok.")
    else:
        # Özet Kartlar
        c1, c2, c3 = st.columns(3)
        c1.metric("Toplam Tonaj", f"{df[COLS['tonaj']].sum():,.0f}")
        c2.metric("Toplam USD", f"${df[COLS['tutar_usd']].sum():,.2f}")
        c3.metric("Toplam TL", f"₺{df[COLS['tutar_tl']].sum():,.2f}")
        
        st.divider()
        
        # Filtreleme
        aylar = sorted(df[COLS['ay']].unique())
        secilen_ay = st.multiselect("Ay Seçiniz", aylar, default=aylar)
        
        if secilen_ay:
            df_filt = df[df[COLS['ay']].isin(secilen_ay)]
            
            # Pivot Tablo (Müşteri Bazlı)
            pivot = df_filt.groupby(COLS['mus']).agg({
                COLS['tonaj']: 'sum',
                COLS['tutar_usd']: 'sum'
            }).reset_index().sort_values(by=COLS['tutar_usd'], ascending=False)
            
            c_chart, c_table = st.columns([2, 1])
            with c_chart:
                fig = px.bar(pivot.head(10), x=COLS['mus'], y=COLS['tutar_usd'], title="En İyi 10 Müşteri (USD)")
                st.plotly_chart(fig, use_container_width=True)
            
            with c_table:
                st.dataframe(pivot, hide_index=True, use_container_width=True)
            
            # Excel İndir
            st.download_button("📥 Raporu İndir (Excel)", data=to_excel(df_filt), file_name="Rapor.xlsx")

# --- TAB 3: TANIMLAR ---
with tab3:
    c1, c2, c3 = st.columns(3)
    
    # Yardımcı fonksiyon
    def manage_list(title, key_name):
        st.subheader(title)
        new_item = st.text_input(f"Yeni {title}", key=f"new_{key_name}")
        if st.button(f"Ekle ({title})"):
            if new_item and new_item not in sys_data[key_name]:
                sys_data[key_name].append(new_item)
                sys_data[key_name].sort()
                save_sys_data(sys_data)
                st.rerun()
        
        del_item = st.selectbox(f"Sil ({title})", sys_data[key_name], key=f"del_{key_name}")
        if st.button(f"Sil ({title})"):
            sys_data[key_name].remove(del_item)
            save_sys_data(sys_data)
            st.rerun()

    with c1: manage_list("Bayi", "bayiler")
    with c2: manage_list("Müşteri", "musteriler")
    with c3: manage_list("Ürün", "urunler")
    
    st.divider()
    if st.button("🔥 TÜM VERİLERİ SIFIRLA"):
        if os.path.exists(SALES_FILE): os.remove(SALES_FILE)
        st.session_state.df = pd.DataFrame(columns=COLS.values())
        st.warning("Veritabanı silindi.")
        st.rerun()
