# 🏢 Satış ve Tonaj Takip Sistemi (v1.0)

Bu proje, Python ve Streamlit kullanılarak geliştirilmiş, Excel tabanlı çalışan profesyonel bir satış yönetim, veri giriş ve raporlama aracıdır.

**Geliştirici:** Göksel Çapkın  
**Telif Hakkı:** © 2025 Snowflake Inc. & Göksel Çapkın. Tüm hakları saklıdır.

## 🚀 Özellikler

* **Excel Entegrasyonu:** Müşteri, ürün ve fabrika listelerini Excel'den otomatik çeker.
* **Dinamik Veri Girişi:** Bayi, Müşteri ve Ürün seçimli kolay arayüz.
* **Otomatik Kur Takibi:** TCMB güncel döviz kurunu otomatik olarak çeker.
* **Akıllı Hesaplama:** `(Mevcut Fiyat - İndirimli Fiyat) * Tonaj` formülü ile anlık kar/zarar hesabı yapar.
* **Canlı Düzenleme:** Girilen verileri Excel benzeri bir tablo üzerinde anında düzenleme, silme ve güncelleme imkanı.
* **Excel Raporlama:** Analiz sonuçlarını gerçek `.xlsx` formatında indirebilme.

## 🛠️ Kurulum ve Çalıştırma

Bu projeyi kendi bilgisayarınızda çalıştırmak için:

1.  **Depoyu İndirin:**
    ```bash
    git clone [https://github.com/KULLANICI_ADINIZ/REPO_ADINIZ.git](https://github.com/KULLANICI_ADINIZ/REPO_ADINIZ.git)
    cd REPO_ADINIZ
    ```

2.  **Gerekli Kütüphaneleri Yükleyin:**
    ```bash
    pip install -r requirements.txt
    ```

3.  **Uygulamayı Başlatın:**
    ```bash
    streamlit run app.py
    ```

## 📂 Dosya Yapısı

* `app.py`: Uygulamanın ana kaynak kodudur.
* `requirements.txt`: Projenin çalışması için gereken Python kütüphaneleri.
* `satis_verileri.csv`: Satış kayıtlarının tutulduğu veritabanı (otomatik oluşur).
* `sistem_verileri.json`: Tanımlamaların (müşteri/ürün listesi) tutulduğu dosya.

## 📝 Kullanım Kılavuzu

1.  **Veri Yükleme:** Sol menüden elinizdeki Excel listesini yükleyerek Bayi, Müşteri ve Ürün tanımlarını sisteme çekin.
2.  **Satış Girişi:** Formu doldurun ve "Kaydet"e basın. Form otomatik temizlenir.
3.  **Düzenleme:** Tablo üzerinde değişiklik yaparsanız mutlaka **"Hesapla ve Güncelle"** butonuna basın.
4.  **Raporlama:** "Analiz Raporu" sekmesinden verileri filtreleyin ve Excel olarak indirin.

---
*Bu proje Göksel Çapkın tarafından geliştirilmiştir.*
