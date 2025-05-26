import pandas as pd
from transformers import pipeline, AutoTokenizer, AutoModelForSequenceClassification
import sys
import os

# Sentiment modeli kurulumu
model_name = "savasy/bert-base-turkish-sentiment-cased"
tokenizer = AutoTokenizer.from_pretrained(model_name)
model = AutoModelForSequenceClassification.from_pretrained(model_name)
sentiment_analyzer = pipeline("sentiment-analysis", model=model, tokenizer=tokenizer, device=-1)

def generate_financial_comment(old_value, new_value, label):
    if new_value > old_value:
        return f"{label} oranı {old_value:.2f}’ten {new_value:.2f}’ye yükseldi."
    elif new_value < old_value:
        return f"{label} oranı {old_value:.2f}’ten {new_value:.2f}’ye düştü."
    else:
        return f"{label} oranı değişmedi."

def analyze_csv_file(filepath):
    try:
        df = pd.read_csv(filepath, sep=";", index_col=0)
    except Exception as e:
        print(f"Dosya okunamadı: {str(e)}")
        return

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
        except Exception as e:
            continue  # sayı olmayan sütunları atla

    for result in results:
        line = f"{result['oran']}: {result['yorum']} | Duygu: {result['duygu']} (Güven: {result['guven']})"
        print(line)

# aselsan.csv dosyasını oku ve sonucu ekrana yazdır
if __name__ == '__main__':
    if len(sys.argv) < 2:
        # Komut satırı argümanı yoksa aselsan.csv dosyasını kullan
        analyze_csv_file(r"C:\\Users\\Hüseyin\Desktop\\Mali Tablo Analiz Aracı\Backend\\aselsan.csv")
    else:
        csv_path = sys.argv[1]
        if not os.path.exists(csv_path):
            print("Dosya bulunamadı.")
            sys.exit(1)
        analyze_csv_file(csv_path)