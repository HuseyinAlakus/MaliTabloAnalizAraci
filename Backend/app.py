from flask import Flask, request, jsonify
from flask_cors import CORS
import pandas as pd
from transformers import pipeline, AutoTokenizer, AutoModelForSequenceClassification

app = Flask(__name__)
CORS(app)

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
        # Dosyayı oku (kullanıcının yüklediği)
        df = pd.read_csv(file, sep=";", index_col=0)
    except Exception as e:
        return jsonify({"error": f"Dosya okunamadı: {str(e)}"}), 400

    results = []
    for col in df.columns:
        try:
            old = float(df[col].iloc[0])
            new = float(df[col].iloc[-1])
            comment = generate_financial_comment(old, new, col)
            sentiment = sentiment_analyzer(comment)[0]
            results.append({
                "oran": col,
                "yorum": comment,
                "duygu": sentiment['label'],
                "guven": round(sentiment['score'], 2)
            })
        except:
            continue  # sayı olmayan sütunları atla

    return jsonify(results)

if __name__ == '__main__':
    app.run(debug=True)
