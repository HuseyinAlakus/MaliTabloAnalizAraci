from flask import Flask, request, jsonify
from flask_cors import CORS
import pandas as pd
import matplotlib.pyplot as plt
import io
import base64
import google.generativeai as genai
import re

app = Flask(__name__)
CORS(app, supports_credentials=True, resources={r"/*": {"origins": "http://127.0.0.1:5500"}})

# Gemini API ayarı
genai.configure(api_key="AIzaSyCbbmCskodgNlDorEN9V3eQAsr35bmP9P8")
gemini_model = genai.GenerativeModel("gemini-2.0-flash")

# --- Fonksiyonlar ---

def generate_financial_comment(old_value, new_value, label):
    """
    Finansal değer değişimine göre yorum üreten fonksiyon.
    """
    if new_value > old_value:
        return f"{label} oranı {old_value:,.2f}’den {new_value:,.2f}’ye yükseldi."
    elif new_value < old_value:
        return f"{label} oranı {old_value:,.2f}’den {new_value:,.2f}’ye düştü."
    else:
        return f"{label} oranı değişmedi."

def temizle_ve_duzenle_yorum(metin):
    basliklar = [
        "Genel Yapay Zeka Yorumu", "Olumlu Yönler", "Olumsuz Yönler",
        "Genel Değerlendirme", "Öneriler", "Sonuç"
    ]

    duzenlenmis_html_parcalar = []
    satirlar = metin.splitlines()

    for satir in satirlar:
        satir = satir.strip()
        if not satir:
            continue

        satir = re.sub(r"^[\*\-\s]+", "", satir)
        temizlenmis_satir = satir.rstrip(':').strip()

        if any(temizlenmis_satir.lower() == b.lower() for b in basliklar):
            duzenlenmis_html_parcalar.append(
                f"<h3 class='ai-heading'>{temizlenmis_satir}</h3>"
            )
        else:
            duzenlenmis_html_parcalar.append(f"<p>{satir}</p>")

    return "\n".join(duzenlenmis_html_parcalar)

def grafik_uret(df, baslik, y_etiketi, is_bar=False, kar_zarar=False):
    import matplotlib.dates as mdates

    img = io.BytesIO()
    fig, ax = plt.subplots(figsize=(10, 5))

    df_copy = df.copy()

    try:
        df_copy.index = pd.to_datetime(df_copy.index, errors='coerce', format="%Y/%m")
        if df_copy.index.isnull().all():
            df_copy.index = pd.to_datetime(df_copy.index, errors='coerce', format="%Y")
        df_copy = df_copy.sort_index()
        if df_copy.index.isnull().all():
            df_copy.index = df.index  # fallback to original index
    except Exception as e:
        print(f"Zaman dönüştürme hatası: {e}")
        df_copy.index = df.index

    if kar_zarar:
        if "Net Dönem Kârı (Zararı)" in df_copy.columns:
            kar_zarar_degerleri = df_copy["Net Dönem Kârı (Zararı)"]

            if kar_zarar_degerleri.empty or kar_zarar_degerleri.isnull().all():
                print("Kâr/Zarar verisi boş.")
                plt.close(fig)
                return None

            colors = ['green' if v >= 0 else 'red' for v in kar_zarar_degerleri]
            ax.bar(df_copy.index, kar_zarar_degerleri, color=colors)
            ax.set_title("Yıllara Göre Kâr/Zarar", fontsize=14, fontweight='bold')
            ax.set_ylabel("Tutar (TL)")
        else:
            print("'Net Dönem Kârı (Zararı)' bulunamadı.")
            plt.close(fig)
            return None
    elif is_bar:
        if not df_copy.empty and df_copy.shape[1] == 1:
            ax.bar(df_copy.index, df_copy.iloc[:, 0], color="#6699CC")
            ax.set_title(baslik, fontsize=14, fontweight='bold')
            ax.set_ylabel(y_etiketi)
        else:
            print("Bar grafik için uygun değil.")
            plt.close(fig)
            return None
    else:
        if not df_copy.empty:
            ax.plot(df_copy.index, df_copy.iloc[:, 0], marker='o', linestyle='-', color="#1f77b4")
            ax.set_title(baslik, fontsize=14, fontweight='bold')
            ax.set_ylabel(y_etiketi)
        else:
            print("Çizgi grafik için boş.")
            plt.close(fig)
            return None

    ax.set_xlabel("Dönem")
    ax.grid(True, linestyle='--', alpha=0.4)

    # X ekseni yıl formatında
    if isinstance(df_copy.index[0], pd.Timestamp):
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y'))
        ax.xaxis.set_major_locator(mdates.YearLocator())
        fig.autofmt_xdate()

    plt.tight_layout()
    plt.savefig(img, format='png', bbox_inches='tight')
    plt.close(fig)
    img.seek(0)
    return f"data:image/png;base64,{base64.b64encode(img.getvalue()).decode()}"

@app.route('/analyze', methods=['POST'])
def analyze_csv():
    if 'file' not in request.files:
        return jsonify({"error": "CSV dosyası eksik"}), 400

    file = request.files['file']

    try:
        # CSV dosyasını noktalı virgül (;) ayırıcı ile ve başlık olmadan oku
        df_raw = pd.read_csv(file, sep=";", header=None)
    except Exception as e:
        return jsonify({"error": f"Dosya okunamadı: {str(e)}"}), 400

    results = []

    # "TABLOSU" içeren satırları bul ve tablo başlangıçlarını belirle
    table_starts = df_raw[df_raw[0].str.contains("TABLOSU", na=False)].index.tolist()
    table_starts.append(len(df_raw)) # Son tabloyu da dahil etmek için dosya sonunu ekle

    for i in range(len(table_starts) - 1):
        # Her tablo bloğunu işle
        table_df = df_raw.iloc[table_starts[i] + 1:table_starts[i + 1]].copy()
        
        # İlk satırı sütun başlığı olarak ayarla ve bu satırı veri setinden çıkar
        if not table_df.empty:
            table_df.columns = table_df.iloc[0]
            table_df = table_df[1:]
            table_df = table_df.set_index(table_df.columns[0]) # İlk sütunu indeks olarak ayarla
            
            # Tüm değerleri sayısal formata dönüştür, hata durumunda NaN yap
            table_df = table_df.apply(pd.to_numeric, errors='coerce')
            table_df = table_df.dropna(how='all') # Tüm değerleri NaN olan satırları düşür
            
            # Tabloyu transpoze et (satırları sütun, sütunları satır yap)
            table_df = table_df.transpose()

            for col in table_df.columns:
                try:
                    # İlk ve son değerleri alarak finansal yorum oluştur
                    old = float(table_df[col].iloc[0])
                    new = float(table_df[col].iloc[-1])
                    comment = generate_financial_comment(old, new, col)
                    results.append({
                        "oran": col,
                        "yorum": comment
                    })
                except Exception as e:
                    # Hata durumunda (örn. sayısal olmayan veri) bu sütunu atla
                    print(f"Sütun '{col}' işlenirken hata oluştu: {e}")
                    continue

    # Gemini ile genel analiz üretimi
    try:
        # Tüm finansal yorumları birleştirerek prompt oluştur
        yorumlar = "\n".join([f"{item['oran']}: {item['yorum']}" for item in results])
        prompt = (
            "Aşağıdaki finansal değişim yorumlarına göre şirketin genel mali durumu nasıldır?\n\n"
            "Lütfen yanıtını şu başlıklarla yapılandır ve her başlık altında ayrı paragraflar halinde açıklama yap:\n"
            "- Olumlu Yönler\n- Olumsuz Yönler\n- Genel Değerlendirme\n- Öneriler\n- Sonuç\n\n"
            "Yanıtınızda kesinlikle başlık dışında hiçbir yıldız (*), tire (-), numara (1., 2.), ya da markdown biçimi kullanmayın. Her şey düz yazı olsun."
            + yorumlar
        )
        
        # Gemini modelinden yanıt al
        gemini_response = gemini_model.generate_content(prompt)
        
        # Gelen yanıtı temizle ve düzenle
        genel_yorum = temizle_ve_duzenle_yorum(gemini_response.text)

        # Eğer genel yorum anlamsız veya çok kısaysa varsayılan bir mesaj göster
        if not genel_yorum or len(genel_yorum.split()) < 5:
            genel_yorum = "<p>Yapay zeka modeli anlamlı bir genel analiz üretemedi. Lütfen daha kısa bir veri setiyle tekrar deneyin.</p>"
    except Exception as e:
        # Gemini API çağrısında veya yorum işlenirken hata oluşursa
        genel_yorum = f"<p>Genel finansal analiz yapılamadı: {str(e)}</p>"

    return jsonify({
        "results": results,
        "genel_yorum": genel_yorum
    })

@app.route('/grafik-analyze', methods=['POST'])
def grafik_analyze():
    if 'file' not in request.files:
        return jsonify({"error": "CSV dosyası eksik"}), 400

    file = request.files['file']
    try:
        df_raw = pd.read_csv(file, sep=";", header=None)
        print("CSV Ham Veri:")
        print(df_raw) # Tamamını görmek için
    except Exception as e:
        print(f"Dosya okunamadı: {str(e)}")
        return jsonify({"error": f"Dosya okunamadı: {str(e)}"}), 400

    grafikler = {}
    ai_yorumlar = []

    table_starts = df_raw[df_raw[0].str.contains("TABLOSU", na=False)].index.tolist()
    table_starts.append(len(df_raw))

    # İlgilendiğimiz sütunlar (grafik ve yorum üretilecekler)
    hedef_sutunlar = [
        "Toplam Varlıklar",
        "Özsermaye",
        "Toplam Yükümlülükler",
        "Net Dönem Kârı (Zararı)",
        "Hasılat",
        "Esas Faaliyet Kârı (Zararı)"
    ]

    for i in range(len(table_starts) - 1):
        start, end = table_starts[i], table_starts[i + 1]
        
        # Başlık satırını bulma
        if start + 1 < len(df_raw):


            # Tablo başlığı (FİNANSAL DURUM TABLOSU gibi)
            table_name = df_raw.iloc[start, 0] if start < len(df_raw) else "Bilinmeyen Tablo"
            header_row_raw = df_raw.iloc[start + 1].tolist()
            donem_headers = [str(h).strip() for h in header_row_raw[1:] if pd.notna(h) and str(h).strip() != '']
            data_content = df_raw.iloc[start + 2:end].copy()
            
            if data_content.empty:
                print(f"Uyarı: Tablo '{table_name}' için veri satırı bulunamadı. Atlanıyor.")
                continue
            
            # DataFrame'i baştan oluşturma
            df_current_table = pd.DataFrame()
            if not data_content.empty:
                # İlk sütun "Kalem Adı" olacak
                df_current_table['Kalem Adı'] = data_content.iloc[:, 0].astype(str)
                
                # Dönem sütunlarını ekle
                # data_content'in ilk sütunundan sonraki sütunları kullan
                for j, donem_col in enumerate(donem_headers):
                    if (j + 1) < data_content.shape[1]: # data_content sütun sınırlarını aşma
                        col_data = data_content.iloc[:, j + 1].astype(str)
                        # Sayısal dönüşüm burada yapılmalı
                        col_data = col_data.str.replace('.', '', regex=False).str.replace(',', '.', regex=False)
                        df_current_table[donem_col] = pd.to_numeric(col_data, errors='coerce')
                    else:
                        print(f"Uyarı: '{table_name}' tablosunda '{donem_col}' dönemi için veri sütunu bulunamadı.")
                        df_current_table[donem_col] = pd.NA # Yoksa boş bırak

                # Kalem Adı sütununu index yap
                df_current_table = df_current_table.set_index('Kalem Adı')
                df_current_table = df_current_table.dropna(how='all', axis=1) # Tamamen NaN olan dönem sütunlarını at
                df_current_table = df_current_table.dropna(how='all', axis=0) # Tamamen NaN olan kalem satırlarını at

            if df_current_table.empty:
                print(f"Tablo '{table_name}' işlendikten sonra boş kaldı. Atlanıyor.")
                continue

            print(f"\nTablo: {table_name} - İşlenmiş Veri (Transpose Öncesi):")
            print(df_current_table)
            print(f"Data Types: {df_current_table.dtypes}")

            for sutun_adi in hedef_sutunlar:
                if sutun_adi in df_current_table.index: # 'sutun_adi' artık satır indeksi
                    # Bu satır, df_current_table'dan ilgili kalemin tüm dönem verilerini bir Series olarak alır.
                    # Örneğin, df_current_table.loc['Toplam Varlıklar'] --> Series (Index: Dönemler, Value: Tutar)
                    series_for_plot = df_current_table.loc[sutun_adi]

                    # Şimdi bu Series'i DataFrame'e dönüştürürken, index'i dönemler, sütun adı ise kalem adı olsun istiyoruz.
                    # Eğer Series boşsa veya tamamen NaN ise grafik oluşturmamalıyız.
                    if series_for_plot.empty or series_for_plot.isnull().all():
                        print(f"Uyarı: '{sutun_adi}' için veri bulunamadı veya hepsi NaN. Grafik atlanıyor.")
                        continue

                    # df_for_plot'u doğru şekilde oluşturma:
                    # Series'i DataFrame'e çevir, böylece index'i (dönemler) ve tek bir sütunu (değerler) olur.
                    df_for_plot = series_for_plot.to_frame(name=sutun_adi) # Series'i, kalem adıyla bir sütuna sahip DataFrame'e dönüştür

                    # Index'in adını Dönem olarak ayarla (isteğe bağlı, görselleştirme için)
                    df_for_plot.index.name = "Dönem"

                    print(f"\nGrafik için hazırlanmış DF ({sutun_adi}):")
                    print(df_for_plot)
                    print(f"Data Types: {df_for_plot.dtypes}")
                    print(f"Shape: {df_for_plot.shape}")


                    # Net Dönem Kârı (Zararı) için özel bayrak
                    is_kar_zarar_plot = (sutun_adi == "Net Dönem Kârı (Zararı)")

                    grafik = grafik_uret(df_for_plot, f"{sutun_adi} Zaman İçinde", "Tutar (TL)", kar_zarar=is_kar_zarar_plot)
                    
                    if grafik:
                        grafikler[sutun_adi] = grafik
                    else:
                        print(f"Grafik oluşturulamadı: {sutun_adi}")

                    try:
                        # Yorum için ilk ve son değerleri al
                        ilk = df_for_plot.iloc[0, 0] if not df_for_plot.empty and pd.notna(df_for_plot.iloc[0, 0]) else 0
                        son = df_for_plot.iloc[-1, 0] if not df_for_plot.empty and pd.notna(df_for_plot.iloc[-1, 0]) else 0

                        if pd.notna(ilk) and pd.notna(son) and (ilk != 0 or son != 0): # Sayısal değerlerse ve ikisi de 0 değilse
                            prompt = (
                                f"CSV dosyasındaki '{sutun_adi}' değeri {ilk:,.2f} TL'den {son:,.2f} TL'ye değişmiştir. "
                                f"Bu değişime dair kısa ve sade 3-5 maddelik mali yorum yaz. "
                                f"Yorumları Türkçe ve maddeler halinde (örneğin: '- Madde 1', '- Madde 2' şeklinde) yaz."
                            )
                            ai_response = gemini_model.generate_content(prompt)
                            temiz_yorum = temizle_ve_duzenle_yorum(ai_response.text)
                            ai_yorumlar.append({
                                "baslik": sutun_adi,
                                "yorum": temiz_yorum
                            })
                        else:
                            print(f"{sutun_adi} için yorum üretilmiyor: Geçersiz veya sıfır başlangıç/bitiş değeri.")

                    except Exception as e:
                        print(f"{sutun_adi} için yorum üretilirken hata oluştu: {str(e)}")
                        ai_yorumlar.append({
                            "baslik": sutun_adi,
                            "yorum": f"{sutun_adi} için yorum üretilemedi: {str(e)}"
                        })
                else:
                    print(f"Hedef kalem '{sutun_adi}' bu tabloda (index'te) bulunamadı.")
        else:
            print(f"Uyarı: df_raw.iloc[start + 1] index hatası veya data_content boş, start: {start}")

    return jsonify({
        "grafikler": grafikler,
        "ai_yorumlar": ai_yorumlar
    })

if __name__ == '__main__':
    app.run(debug=True)
