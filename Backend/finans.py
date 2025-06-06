from flask import Flask, request, jsonify
from flask_cors import CORS
import pandas as pd
import os
import google.generativeai as genai  # Gemini için gerekli
import re

app = Flask(__name__)
CORS(app, supports_credentials=True)

genai.configure(api_key="AIzaSyCbbmCskodgNlDorEN9V3eQAsr35bmP9P8")


gemini_model = genai.GenerativeModel("gemini-2.0-flash")

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


if __name__ == '__main__':
    app.run(debug=True)
