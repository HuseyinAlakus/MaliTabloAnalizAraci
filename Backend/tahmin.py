from flask import Flask, request, jsonify
from flask_cors import CORS
import pandas as pd
import google.generativeai as genai

app = Flask(__name__)
CORS(app, supports_credentials=True)

# Google Gemini API Anahtarı
genai.configure(api_key="AIzaSyCbbmCskodgNlDorEN9V3eQAsr35bmP9P8")
gemini_model = genai.GenerativeModel("gemini-2.0-flash")

def temizle_yorum(metin):
    paragraflar = metin.strip().split("\n")
    html = ""
    for paragraf in paragraflar:
        satir = paragraf.strip()
        if not satir:
            continue

        # Başlıkları renklendir, ikon ekle ve bold yap
        if satir == "Geleceğe Dönük Tahminler":
            html += "<h4 class='title-section'><i class='fas fa-chart-line'></i> Geleceğe Dönük Tahminler</h4>\n"
        elif satir == "Beklenen Riskler":
            html += "<h4 class='title-section'><i class='fas fa-exclamation-circle'></i> Beklenen Riskler</h4>\n"
        elif satir == "Olası Fırsatlar":
            html += "<h4 class='title-section'><i class='fas fa-lightbulb'></i> Olası Fırsatlar</h4>\n"
        else:
            html += f"<p class='analysis-paragraph'>{satir}</p>\n"
    return html


@app.route('/future-analyze', methods=['POST'])
def future_analyze():
    if 'file' not in request.files:
        return jsonify({"error": "CSV dosyası bulunamadı"}), 400

    file = request.files['file']

    try:
        df = pd.read_csv(file, sep=";", header=None)

        # Sadece yıl bilgisi içeren satırları al
        df = df[df[1].astype(str).str.contains(r"\d", na=False)]
        df.columns = df.iloc[0]  # Başlık satırı
        df = df[1:]
        df.set_index(df.columns[0], inplace=True)

        # Sayısal değerlere dönüştürme
        df = df.replace(",", ".", regex=True)
        df = df.apply(pd.to_numeric, errors='coerce')
        df = df.dropna(axis=0, how='all')
        df = df.dropna(axis=1, how='all')
        df = df.transpose()

        if df.empty:
            return jsonify({"error": "Geçerli veri bulunamadı, CSV içeriğini kontrol edin."}), 400

    except Exception as e:
        return jsonify({"error": f"CSV işlenemedi: {e}"}), 400

    try:
        # Prompt için sadece tabloyu metin olarak veriyoruz
        prompt = (
            "Aşağıdaki geçmiş yıllara ait finansal verileri inceleyerek şirketin gelecekteki finansal performansı hakkında analiz yap:\n\n"
            f"{df.to_string()}\n\n"
            "Lütfen aşağıdaki başlıklarla analiz yap:\n"
            "Yanıtınızda kesinlikle başlık dışında hiçbir yıldız (*), tire (-), numara (1., 2.), ya da markdown biçimi kullanmayın. Her şey düz yazı olsun."
            "- Geleceğe Dönük Tahminler\n"
            "- Beklenen Riskler\n"
            "- Olası Fırsatlar\n"
            "Yalnızca paragraflarla cevap ver, listeleme ve markdown kullanma."
        )

        response = gemini_model.generate_content(prompt)
        yorum = temizle_yorum(response.text)

        return jsonify({
            "future_commentary": yorum
        })

    except Exception as e:
        return jsonify({"error": f"Yapay zeka analizi başarısız: {e}"}), 500

if __name__ == '__main__':
    app.run(debug=True)
