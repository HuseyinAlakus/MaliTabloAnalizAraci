from flask import Flask, request, jsonify
from flask_cors import CORS
import pandas as pd
from transformers import pipeline, AutoTokenizer, AutoModelForSequenceClassification

app = Flask(__name__)
CORS(app, supports_credentials=True)

# Sentiment modeli kurulumu
model_name = "savasy/bert-base-turkish-sentiment-cased"
tokenizer = AutoTokenizer.from_pretrained(model_name)
model = AutoModelForSequenceClassification.from_pretrained(model_name)
sentiment_analyzer = pipeline("sentiment-analysis", model=model, tokenizer=tokenizer)

def generate_financial_comment(old_value, new_value, label):
    if new_value > old_value:
        return f"{label} oranı {old_value:.2f}’ten {new_value:.2f}’ye yükseldi."
    elif new_value < old_value:
        return f"{label} oranı {old_value:.2f}’ten {new_value:.2f}’ye düştü."
    else:
        return f"{label} oranı değişmedi."

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

    # Tablo başlıklarını tespit et
    table_starts = df_raw[df_raw[0].str.contains("TABLOSU", na=False)].index.tolist()
    table_starts.append(len(df_raw))  # son tabloyu işleyebilmek için

    # Her tablo için
    for i in range(len(table_starts) - 1):
        table_df = df_raw.iloc[table_starts[i] + 1:table_starts[i + 1]].copy()

        # İlk satırı başlık olarak ayarla
        table_df.columns = table_df.iloc[0]
        table_df = table_df[1:]

        # İlk sütunu indeks olarak ayarla
        table_df = table_df.set_index(table_df.columns[0])

        # Geçersiz satırları (örneğin Sunum Para Birimi gibi) çıkar
        table_df = table_df.apply(pd.to_numeric, errors='coerce')
        table_df = table_df.dropna()

        # Transpose ederek dönemleri satır haline getir (analiz kolaylığı için)
        table_df = table_df.transpose()

        # Yalnızca ilk ve son dönem karşılaştırmasını yap
        for col in table_df.columns:
            try:
                old = float(table_df[col].iloc[0])
                new = float(table_df[col].iloc[-1])
                comment = generate_financial_comment(old, new, col)
                sentiment = sentiment_analyzer(comment)[0]
                results.append({
                    "oran": col,
                    "yorum": comment,
                    "duygu": sentiment['label'],
                    "guven": round(sentiment['score'], 2)
                })
            except:
                continue  # float'a çevrilemeyen verileri atla

    return jsonify(results)

if __name__ == '__main__':
    app.run(debug=True)
