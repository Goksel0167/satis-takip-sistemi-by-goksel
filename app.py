import streamlit as st
import pandas as pd
import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
import os
import json
import io
import time
import plotly.express as px

# --- 1. SAYFA AYARLARI ---
st.set_page_config(page_title="Satış Yönetim Sistemi", layout="wide", page_icon="🏢")

# --- 2. SABİT AYARLAR ---
SALES_FILE = "satis_verileri.csv"
REF_FILE = "sistem_verileri.json"

# Sütun İsimleri (Excelinizle Birebir Aynı)
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

# --- 3. KRİTİK FONKSİYONLAR ---

@st.cache_data(ttl=600)
def get_tcmb_rate(target_date):
    """Garantili Kur Çekme (Tatil Korumalı)"""
    date_temp = target_date
    for i in range(10):
        # Hafta sonu atla
        if date_temp.weekday() >= 5:
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

def clean_and_repair_data():
    """Dosyayı okur, hatalı sütunları ve tipleri onarır"""
    if not os.path.exists(SALES_FILE):
        return pd.DataFrame(columns=list(COLS.values()))
    
    try:
        df = pd.read_csv(SALES_FILE)
        
        # 1. Eksik sütunları ekle / Fazlalıkları at
        # Mevcut veriyi koruyarak yeni şemaya uydur
        df_new = pd.DataFrame(columns=list(COLS.values()))
        for c in df_new.columns:
            if c in df.columns:
                df_new[c] = df[c]
            else:
                # Eski isimleri dene (Migration)
                if c == 'Tutar ($)' and 'Tutar USD' in df.columns: df_new[c] = df['Tutar USD']
                elif c == 'Mevcut ($)' and 'Mevcut Fiyat USD' in df.columns: df_new[c] = df['Mevcut Fiyat USD']
                elif c == 'Tonaj KG' and 'Tonaj' in df.columns: df_new[c] = df['Tonaj']
                else:
                    df_new[c] = 0.0 if any(x in c for x in ['($)', 'TL', 'KG', 'Kuru']) else ""

        # 2. Tarih Formatını Zorla (TypeError Çözümü)
        df_new[COLS['tarih']] = pd.to_datetime(df_new[COLS['tarih']], errors='coerce')
        # Geçersiz tarihleri (NaT) bugüne eşitle veya sil (Biz siliyoruz)
        df_new = df_new.dropna(subset=[COLS['tarih']])
        
        # 3. Sayısal Formatları Zorla
        num_cols = [COLS['mevcut_usd'], COLS['indirimli_usd'], COLS['tonaj'], 
                    COLS['kur'], COLS['tutar_usd'], COLS['tutar_tl'], COLS['fark_usd']]
        for c in num_cols:
            df_new[c] = pd.to_numeric(df_new[c], errors='coerce').fillna(0.0)
            
        return df_new
    except Exception as e:
        st.error(f"Veri dosyası bozuktu, sıfırlandı. Hata: {e}")
        return pd.DataFrame(columns=list(COLS.values()))

def save_data(df):
    """Veriyi güvenli kaydeder"""
    df.to_csv(SALES_FILE, index=False)

def get_sys_data():
    if not os.path.exists(REF_FILE):
        default = {"bayiler": [], "musteriler": [], "urunler": [], "fabrikalar": ["TR14", "TR15"]}
        with open(REF_FILE, "w", encoding="utf-8") as f: json.dump(default, f)
        return default
    with open(REF_FILE, "r", encoding="utf-8") as f: return json.load(f)

def save_sys_data(data):
    with open(REF_FILE, "w", encoding="utf-8") as f: json.dump(data, f, ensure_ascii=False)

def get_day_name(date_obj):
    if pd.isnull(date_obj): return ""
    days = {0: "Pazartesi", 1: "Salı", 2: "Çarşamba", 3: "Perşembe", 4: "Cuma", 5: "Cumartesi", 6: "Pazar"}
    return days.get(date_obj.weekday(), "")

def to_excel_export(df):
    output = io.BytesIO()
    df_exp = df.copy()
    df_exp[COLS['tarih']] = df_exp[COLS['tarih']].dt.strftime('%d.%m.%Y')
    
    # Toplam Satırı
    sum_row = pd.DataFrame(columns=df_exp.columns)
    sum_row.loc[0] = ""
    sum_row.loc[0, COLS['mus']] = "GENEL TOPLAM"
    for c in [COLS['tonaj'], COLS['tutar_usd'], COLS['tutar_tl']]:
        sum_row.loc[0, c] = df_exp[c].sum()
        
    df_final = pd.concat([df_exp, sum_row], ignore_index=True)
    
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df_final.to_excel(writer, index=False, sheet_name='Satislar')
    return output.getvalue()

# --- 4. ANA UYGULAMA AKIŞI ---
sys_data = get_sys_data()
st.title("📊 Satış Yönetim Sistemi")

# Sol Menü
with st.sidebar:
    st.header("⚙️ Veri İşlemleri")
    with st.expander("📂 Tanımları Yükle"):
        up_def = st.file_uploader("Tanım Excel", type="xlsx")
        if up_def and st.button("Güncelle"):
            try:
                xl = pd.ExcelFile(up_def)
                for sheet in xl.sheet_names:
                    df_t = pd.read_excel(xl, sheet)
                    col = df_t.iloc[:, 0].dropna().astype(str).tolist()
                    s = sheet.lower()
                    if "bayi" in s: sys_data["bayiler"] += col
                    elif "musteri" in s: sys_data["musteriler"] += col
                    elif "urun" in s: sys_data["urunler"] += col
                for k in sys_data: sys_data[k] = sorted(list(set(sys_data[k])))
                save_sys_data(sys_data)
                st.toast("Tanımlar güncellendi!", icon="✅")
                time.sleep(1)
                st.rerun()
            except: st.error("Dosya formatı hatalı.")

# Sekmeler
tab1, tab2, tab3 = st.tabs(["📝 Satış Girişi", "📈 Raporlama", "🛠️ Tanımlar"])

# --- TAB 1: GİRİŞ ---
with tab1:
    c_date, c_inf = st.columns([1, 2])
    with c_date:
        # Tarih seçimi (Date objesi döner)
        sel_date = st.date_input("Tarih", datetime.now())
    
    # Kur Çek
    kur_val, kur_txt = get_tcmb_rate(sel_date)
    with c_inf:
        if kur_val > 0: st.success(f"**{kur_txt}** Kuru: **{kur_val:.4f}**")
        else: st.warning("Kur bulunamadı (Manuel giriniz)")

    with st.form("entry", clear_on_submit=True):
        c1, c2, c3 = st.columns(3)
        with c1:
            bayi = st.selectbox("Bayi", sys_data["bayiler"], index=None, placeholder="Seçiniz")
            mus = st.selectbox("Müşteri", sys_data["musteriler"], index=None, placeholder="Seçiniz")
            fab = st.selectbox("Fabrika", sys_data["fabrikalar"], index=None)
        with c2:
            urun = st.selectbox("Ürün", sys_data["urunler"], index=None, placeholder="Seçiniz")
            f_mevcut = st.number_input("Mevcut ($)", min_value=0.0, format="%.2f")
            f_ind = st.number_input("İndirimli ($)", min_value=0.0, format="%.2f")
        with c3:
            ton = st.number_input("Tonaj", min_value=0.0, format="%.0f")
            kur = st.number_input("Kur", value=kur_val, min_value=0.0, format="%.4f")
            
        if st.form_submit_button("💾 KAYDET"):
            if not mus or not urun:
                st.error("Müşteri ve Ürün zorunludur!")
            else:
                fark = f_mevcut - f_ind
                t_usd = fark * ton
                t_tl = t_usd * kur
                
                # Timestamp'e çevir (TypeError Çözümü)
                ts_date = pd.to_datetime(sel_date)
                
                new_row = {
                    COLS['tarih']: ts_date,
                    COLS['gun']: get_day_name(sel_date),
                    COLS['ay']: sel_date.strftime("%Y-%m"),
                    COLS['bayi']: bayi, COLS['mus']: mus, COLS['fab']: fab,
                    COLS['urun']: urun, COLS['mevcut_usd']: f_mevcut,
                    COLS['indirimli_usd']: f_ind, COLS['fark_usd']: fark,
                    COLS['tonaj']: ton, COLS['tutar_usd']: t_usd,
                    COLS['kur']: kur, COLS['tutar_tl']: t_tl
                }
                
                df_curr = clean_and_repair_data()
                df_curr = pd.concat([df_curr, pd.DataFrame([new_row])], ignore_index=True)
                save_data(df_curr)
                st.toast("Kayıt Başarılı!", icon="✅")
                time.sleep(0.5)
                st.rerun()

    st.divider()
    
    # Tablo Gösterimi
    df = clean_and_repair_data()
    if not df.empty:
        # Canlı Toplamlar
        t_ton = df[COLS['tonaj']].sum()
        t_usd = df[COLS['tutar_usd']].sum()
        t_tl = df[COLS['tutar_tl']].sum()
        
        m1, m2, m3 = st.columns(3)
        m1.metric("TOPLAM Tonaj", f"{t_ton:,.0f}")
        m2.metric("TOPLAM Tutar ($)", f"${t_usd:,.2f}")
        m3.metric("TOPLAM Tutar (TL)", f"₺{t_tl:,.2f}")
        
        # Sıralama (Güvenli)
        df = df.sort_values(by=COLS['tarih'], ascending=True)
        
        st.subheader("📋 Kayıt Listesi")
        edited_df = st.data_editor(df, num_rows="dynamic", use_container_width=True)
        
        if st.button("🔄 Tabloyu Güncelle"):
            # Güvenli Hesaplama (Row by Row to avoid KeyErrors during edit)
            for idx, row in edited_df.iterrows():
                try:
                    f = row[COLS['mevcut_usd']] - row[COLS['indirimli_usd']]
                    tu = f * row[COLS['tonaj']]
                    ttl = tu * row[COLS['kur']]
                    
                    edited_df.at[idx, COLS['fark_usd']] = f
                    edited_df.at[idx, COLS['tutar_usd']] = tu
                    edited_df.at[idx, COLS['tutar_tl']] = ttl
                    
                    d = pd.to_datetime(row[COLS['tarih']])
                    edited_df.at[idx, COLS['gun']] = get_day_name(d)
                    edited_df.at[idx, COLS['ay']] = d.strftime("%Y-%m")
                except: pass
            
            save_data(edited_df)
            st.toast("Güncellendi!", icon="🔄")
            time.sleep(0.5)
            st.rerun()

# --- TAB 2: RAPOR ---
with tab2:
    df = clean_and_repair_data()
    if df.empty:
        st.info("Veri yok.")
    else:
        aylar = sorted(df[COLS['ay']].astype(str).unique())
        sel_ay = st.multiselect("Ay Seçiniz", aylar, default=aylar)
        df_f = df if not sel_ay else df[df[COLS['ay']].isin(sel_ay)]
        
        c1, c2, c3 = st.columns(3)
        c1.metric("Seçilen Tonaj", f"{df_f[COLS['tonaj']].sum():,.0f}")
        c2.metric("Seçilen USD", f"${df_f[COLS['tutar_usd']].sum():,.2f}")
        c3.metric("Seçilen TL", f"₺{df_f[COLS['tutar_tl']].sum():,.2f}")
        
        st.divider()
        if not df_f.empty:
            piv = df_f.groupby(COLS['mus']).agg({
                COLS['tonaj']: 'sum', COLS['tutar_usd']: 'sum'
            }).reset_index().sort_values(by=COLS['tutar_usd'], ascending=False)
            
            c_ch, c_tb = st.columns([2, 1])
            with c_ch:
                fig = px.bar(piv.head(10), x=COLS['mus'], y=COLS['tutar_usd'], title="Top 10 Müşteri")
                st.plotly_chart(fig, use_container_width=True)
            with c_tb:
                st.dataframe(piv, hide_index=True, use_container_width=True)
        
        st.download_button("📥 Excel İndir", data=to_excel_export(df_f), file_name="Rapor.xlsx")

# --- TAB 3: TANIMLAR ---
with tab3:
    c1, c2, c3 = st.columns(3)
    def man(t, k):
        st.subheader(t)
        v = st.text_input(f"Yeni", key=f"n_{k}")
        if st.button(f"Ekle {t}"):
            if v and v not in sys_data[k]:
                sys_data[k].append(v)
                save_sys_data(sys_data)
                st.rerun()
        d = st.selectbox(f"Sil", sys_data[k], key=f"d_{k}")
        if st.button(f"Sil {t}"):
            sys_data[k].remove(d)
            save_sys_data(sys_data)
            st.rerun()

    with c1: man("Bayi", "bayiler")
    with c2: man("Müşteri", "musteriler")
    with c3: man("Ürün", "urunler")
    
    st.divider()
    if st.button("🔥 SIFIRLA"):
        if os.path.exists(SALES_FILE): os.remove(SALES_FILE)
        st.toast("Sıfırlandı!", icon="⚠️")
        time.sleep(1)
        st.rerun()
