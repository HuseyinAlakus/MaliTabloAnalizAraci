from flask import Flask, request, jsonify
from flask_cors import CORS
import pandas as pd
import os
import google.generativeai as genai  # Gemini için gerekli
import re




app = Flask(__name__)
CORS(app, supports_credentials=True)

# Gemini API anahtarını yapılandır
genai.configure(api_key="AIzaSyCbbmCskodgNlDorEN9V3eQAsr35bmP9P8")

# Gemini modelini tanımla
gemini_model = genai.GenerativeModel("gemini-2.0-flash")

def generate_financial_comment(old_value, new_value, label):
    if new_value > old_value:
        return f"{label} oranı {old_value:,.2f}’den {new_value:,.2f}’ye yükseldi."
    elif new_value < old_value:
        return f"{label} oranı {old_value:,.2f}’den {new_value:,.2f}’ye düştü."
    else:
        return f"{label} oranı değişmedi."
    
def temizle_ve_duzenle_yorum(metin):
    basliklar = [
        "Genel Yapay Zeka Yorumu", "Olumlu Yönler", "Olumlu Gelişmeler",
        "Olumsuz Yönler", "Olumsuz Gelişmeler", "Genel Değerlendirme",
        "Öneri", "Öneriler", "Sonuç", "Uyarı", "Dikkat Edilmesi Gerekenler"
    ]

    for b in basliklar:
        # Markdown yerine HTML etiketleriyle biçimlendir
        metin = re.sub(
            rf"[-\*\s]*{b}[:：]?",
            rf"<h3 style='margin-top: 20px; color:#333;'>{b}</h3>",
            metin,
            flags=re.IGNORECASE
        )

    # Madde işaretlerini <li> gibi yapmaya gerek yoksa sadece düz çizgi ile bırak
    metin = re.sub(r"\n\s*\*\s*", "\n- ", metin)
    metin = re.sub(r"(?<!- )\n\s*-\s*", "\n- ", metin)

    # Çift newline yerine <br> kullanabilirsin veya sadece düzenli hale getir
    metin = re.sub(r"\n{2,}", "\n", metin)

    return metin.strip()




@app.route('/analyze', methods=['POST'])
def analyze_csv():
    if 'file' not in request.files:
        return jsonify({"error": "CSV dosyası eksik"}), 400

    file = request.files['file']

    try:
        df_raw = pd.read_csv(file, sep=";", header=None)
    except Exception as e:
        return jsonify({"error": f"Dosya okunamadı: {str(e)}"}), 400

    results = []

    table_starts = df_raw[df_raw[0].str.contains("TABLOSU", na=False)].index.tolist()
    table_starts.append(len(df_raw))

    for i in range(len(table_starts) - 1):
        table_df = df_raw.iloc[table_starts[i] + 1:table_starts[i + 1]].copy()
        table_df.columns = table_df.iloc[0]
        table_df = table_df[1:]
        table_df = table_df.set_index(table_df.columns[0])
        table_df = table_df.apply(pd.to_numeric, errors='coerce')
        table_df = table_df.dropna()
        table_df = table_df.transpose()

        for col in table_df.columns:
            try:
                old = float(table_df[col].iloc[0])
                new = float(table_df[col].iloc[-1])
                comment = generate_financial_comment(old, new, col)
                results.append({
                    "oran": col,
                    "yorum": comment
                })
            except Exception:
                continue

    # Gemini ile genel analiz üretimi
    try:
        yorumlar = "\n".join([f"{item['oran']}: {item['yorum']}" for item in results])
        prompt = (
            "Aşağıdaki finansal değişim yorumlarına göre şirketin genel mali durumu nasıldır? "
            "Yorumları analiz et ve kısa bir genel değerlendirme yap:\n" + yorumlar
        )

        gemini_response = gemini_model.generate_content(prompt)
        genel_yorum = temizle_ve_duzenle_yorum(gemini_response.text)

        if not genel_yorum or len(genel_yorum.split()) < 5:
            genel_yorum = "Yapay zeka modeli anlamlı bir genel analiz üretemedi. Lütfen daha kısa bir veri setiyle tekrar deneyin."
    except Exception as e:
        genel_yorum = f"Genel finansal analiz yapılamadı: {str(e)}"

    return jsonify({
        "results": results,
        "genel_yorum": genel_yorum
    })

if __name__ == '__main__':
    app.run(debug=True)
