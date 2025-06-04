from flask import Flask, request, jsonify
from flask_cors import CORS
import pandas as pd
import matplotlib.pyplot as plt
import io
import base64
import google.generativeai as genai
import re

app = Flask(__name__)
CORS(app, supports_credentials=True)

# Gemini API anahtarını yapılandır
# Not: API anahtarınızı doğrudan koda gömmek yerine, güvenli bir şekilde ortam değişkenlerinden veya bir yapılandırma dosyasından okumanız önerilir.
genai.configure(api_key="AIzaSyCbbmCskodgNlDorEN9V3eQAsr35bmP9P8")

# Gemini modelini tanımla
gemini_model = genai.GenerativeModel("gemini-2.0-flash")

def grafik_uret(df, baslik, y_etiketi, is_bar=False, kar_zarar=False):
    img = io.BytesIO()
    fig, ax = plt.subplots(figsize=(10, 5))

    df = df.copy()
    
    # Dönemleri datetime olarak işle (varsayım: yıllık ya da çeyrek bazlı metinler olabilir)
    try:
        df.index = pd.to_datetime(df.index, format="%d.%m.%Y", errors='coerce')
        if df.index.isnull().any():
            df.index = pd.to_datetime(df.index, format="%Y", errors='coerce')
        df = df.sort_index()
    except:
        pass  # en kötü ihtimalle string olarak kalır

    if kar_zarar:
        kar = df["Net Kar"] if "Net Kar" in df else pd.Series(dtype=float)
        zarar = df["Net Zarar"] if "Net Zarar" in df else pd.Series(dtype=float)
        combined = kar.combine_first(zarar * -1)  # zararları negatif yap
        colors = ['green' if v >= 0 else 'red' for v in combined]

        ax.bar(df.index, combined, color=colors)
        ax.set_title("Yıllara Göre Kâr/Zarar")
        ax.set_ylabel("Tutar (TL)")
    elif is_bar:
        df.plot(kind='bar', ax=ax)
    else:
        df.plot(kind="line", marker='o', ax=ax)

    ax.set_xlabel("Dönem")
    ax.set_ylabel(y_etiketi)
    ax.grid(True, linestyle='--', alpha=0.5)
    plt.xticks(rotation=45, ha='right')
    plt.tight_layout()
    
    plt.savefig(img, format='png', bbox_inches='tight')
    plt.close(fig)
    img.seek(0)
    return f"data:image/png;base64,{base64.b64encode(img.getvalue()).decode()}"


def temizle_ve_duzenle_yorum(metin):
    """
    Gemini'den gelen yorum metnini temizler ve HTML formatında düzenler.
    Başlıkları belirginleştirir ve paragraf yapısı oluşturur.
    Özellikle istenmeyen markdown işaretlerini (yıldız, tire) kaldırır.
    """
    # 1. Tüm yıldızları ve tireleri temizle (genel temizlik)
    # Bu adım, Gemini'nin çıktısında kalan tüm markdown yıldızlarını ve tirelerini kaldırır.
    metin = re.sub(r"[\*]+", "", metin) # Tüm yıldızları kaldır
    metin = re.sub(r"[\-]+", "", metin) # Tüm tireleri kaldır

    # 2. Tanımlanmış başlıkları geçici olarak işaretle
    basliklar = [
        "Genel Yapay Zeka Yorumu", "Olumlu Yönler", "Olumsuz Yönler",
        "Genel Değerlendirme", "Öneriler", "Sonuç",
        "Değerlendirme", "Dikkat Edilmesi Gerekenler", "Olumsuz Gelişmeler",
        "Analiz", "Gözlem", "Genel Yorum" # Ek başlıklar
    ]
    
    # Başlıkları HTML etiketlerine dönüştürmek için geçici bir işaretçi kullan
    for b in basliklar:
        pattern = rf"(?im)^\s*{re.escape(b)}\s*[:.]?\s*$"
        metin = re.sub(pattern, f"###TEMP_HEADING###{b}###END_HEADING###", metin)

    # 3. Metni paragraflara ayır ve HTML'e dönüştür
    # Ardışık boş satırları tek bir boş satıra indir, sonra boş satırlara göre ayır
    metin = re.sub(r"\n{2,}", "\n\n", metin) # Birden fazla boş satırı iki boş satıra indir
    paragraflar = metin.split("\n\n") # İki boş satıra göre paragraflara ayır
    
    duzenlenmis_html_parcalar = []

    for paragraf in paragraflar:
        paragraf_temiz = paragraf.strip()
        if not paragraf_temiz:
            continue

        # Eğer paragraf başlık işaretçisi içeriyorsa
        if paragraf_temiz.startswith("###TEMP_HEADING###") and paragraf_temiz.endswith("###END_HEADING###"):
            baslik_metni = paragraf_temiz.replace("###TEMP_HEADING###", "").replace("###END_HEADING###", "")
            duzenlenmis_html_parcalar.append(f"<h3 style='margin-top: 20px; color:#333;'>{baslik_metni.strip()}</h3>")
        else:
            # Geri kalanları paragraf olarak ekle
            # İçindeki satır sonlarını <br> ile değiştirerek tek bir HTML paragrafı oluştur.
            paragraf_with_br = paragraf_temiz.replace("\n", "<br>")
            duzenlenmis_html_parcalar.append(f"<p>{paragraf_with_br}</p>")

    # Son olarak, oluşan HTML parçalarını birleştir
    return "\n".join(duzenlenmis_html_parcalar)


# --- GRAFİK ANALİZ UÇ NOKTASI ---
@app.route('/grafik-analyze', methods=['POST'])
def grafik_analyze():
    if 'file' not in request.files:
        return jsonify({"error": "CSV dosyası eksik"}), 400

    file = request.files['file']
    try:
        df_raw = pd.read_csv(file, sep=";", header=None)
    except Exception as e:
        return jsonify({"error": f"Dosya okunamadı: {str(e)}"}), 400

    grafikler = {}
    ai_yorumlar = []

    table_starts = df_raw[df_raw[0].str.contains("TABLOSU", na=False)].index.tolist()
    table_starts.append(len(df_raw))

    hedef_sutunlar = ["Net Kar", "Net Zarar", "Toplam Varlıklar", "Özsermaye", "Toplam Yükümlülükler"]

    for i in range(len(table_starts) - 1):
        start, end = table_starts[i], table_starts[i + 1]
        header_row = df_raw.iloc[start + 1]
        data_rows = df_raw.iloc[start + 2:end].copy()
        data_rows.columns = header_row
        data_rows = data_rows[1:]

        data_rows = data_rows.set_index(data_rows.columns[0])
        data_rows = data_rows.apply(lambda x: x.astype(str).str.replace('.', '', regex=False).str.replace(',', '.', regex=False))
        data_rows = data_rows.apply(pd.to_numeric, errors='coerce').dropna(how='all').transpose()
        data_rows.index.name = "Dönem"

        for sutun in hedef_sutunlar:
            if sutun in data_rows.columns:
                tek_df = data_rows[[sutun]]
                grafik = grafik_uret(tek_df, f"{sutun} Zaman İçinde", "Tutar (TL)")
                grafikler[sutun] = grafik

                try:
                    ilk = tek_df.iloc[0, 0]
                    son = tek_df.iloc[-1, 0]
                    prompt = (
                        f"{sutun} değeri {ilk:,.2f} TL'den {son:,.2f} TL'ye değişmiştir. "
                        f"Bu değişime dair kısa ve sade 3-5 maddelik mali yorum yaz."
                    )
                    ai_response = gemini_model.generate_content(prompt)
                    temiz_yorum = temizle_ve_duzenle_yorum(ai_response.text)
                    ai_yorumlar.append({
                        "baslik": sutun,
                        "yorum": temiz_yorum
                    })
                except Exception as e:
                    ai_yorumlar.append({
                        "baslik": sutun,
                        "yorum": f"{sutun} için yorum üretilemedi: {str(e)}"
                    })
                    # Kâr/Zarar grafiği özel çizim
    if "Net Kar" in data_rows.columns or "Net Zarar" in data_rows.columns:
        kar_zarar_df = data_rows[["Net Kar", "Net Zarar"]] if "Net Kar" in data_rows.columns and "Net Zarar" in data_rows.columns else data_rows[["Net Kar"]] if "Net Kar" in data_rows.columns else data_rows[["Net Zarar"]]
        grafik = grafik_uret(kar_zarar_df, "Kâr/Zarar Zaman İçinde", "Tutar (TL)", kar_zarar=True)
        grafikler["Kâr/Zarar"] = grafik


    return jsonify({
        "grafikler": grafikler,
        "ai_yorumlar": ai_yorumlar
    })

if __name__ == '__main__':
    app.run(debug=True)
