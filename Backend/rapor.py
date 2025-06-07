import pandas as pd
import matplotlib.pyplot as plt
import io
import base64
import matplotlib.dates as mdates
from matplotlib.ticker import FuncFormatter
import seaborn as sns
import google.generativeai as genai
import re
from flask import Flask, request, jsonify
from flask_cors import CORS
import matplotlib
matplotlib.use('Agg')

app = Flask(__name__)
CORS(app, origins=["http://127.0.0.1:5500"], supports_credentials=True)

genai.configure(api_key="AIzaSyCbbmCskodgNlDorEN9V3eQAsr35bmP9P8")
gemini_model = genai.GenerativeModel("gemini-2.0-flash")

def grafik_uret(df, baslik, y_etiketi, is_bar=False, kar_zarar=False):

    sns.set_theme(style="whitegrid")

    img = io.BytesIO()
    fig, ax = plt.subplots(figsize=(11, 5))

    df_copy = df.copy()

    try:
        index_str = pd.Series(df_copy.index.astype(str))

        if index_str.str.fullmatch(r"\d{4}").all():
            df_copy.index = pd.to_datetime(index_str, format="%Y", errors="coerce")
        elif index_str.str.fullmatch(r"\d{4}[-/]\d{2}").all():
            if "/" in index_str.iloc[0]:
                df_copy.index = pd.to_datetime(index_str, format="%Y/%m", errors="coerce")
            else:
                df_copy.index = pd.to_datetime(index_str, format="%Y-%m", errors="coerce")
        else:
            df_copy.index = pd.to_datetime(index_str, errors="coerce")

        df_copy = df_copy.dropna()
        df_copy = df_copy.sort_index()

    except Exception as e:
        print(f"Tarih dönüşüm hatası: {str(e)}")
        df_copy.index = df.index

    if df_copy.empty or df_copy.index.isnull().all() or df_copy.shape[0] < 2:
        plt.close(fig)
        return None

    renkler = sns.color_palette("deep")

    if kar_zarar:
        if df_copy.shape[1] == 1:
            values = df_copy.iloc[:, 0]
            renkler_kar_zarar = ['green' if v >= 0 else 'red' for v in values]
            ax.bar(df_copy.index, values, color=renkler_kar_zarar)
            ax.set_title("Yıllara Göre Kâr/Zarar", fontsize=14, fontweight='bold')
            ax.set_ylabel("Tutar (M TL)")
        else:
            plt.close(fig)
            return None
    elif is_bar:
        if df_copy.shape[1] == 1:
            ax.bar(df_copy.index, df_copy.iloc[:, 0], color=renkler[0])
            ax.set_title(baslik, fontsize=14, fontweight='bold')
            ax.set_ylabel(f"{y_etiketi} (M TL)")
        else:
            plt.close(fig)
            return None
    else:
        if df_copy.shape[1] == 1:
            ax.plot(df_copy.index, df_copy.iloc[:, 0], marker='o', linestyle='-', color=renkler[1])
            ax.set_title(baslik, fontsize=14, fontweight='bold')
            ax.set_ylabel(f"{y_etiketi} (M TL)")
        else:
            plt.close(fig)
            return None

    ax.set_xlabel("Dönem")
    ax.grid(True, linestyle='--', alpha=0.4)

    # Tarih ekseni formatlama
    if isinstance(df_copy.index[0], pd.Timestamp):
        locator = mdates.YearLocator() if df_copy.index.max() - df_copy.index.min() > pd.Timedelta(days=370) else mdates.MonthLocator()
        formatter = mdates.DateFormatter('%Y') if isinstance(locator, mdates.YearLocator) else mdates.DateFormatter('%Y-%m')
        ax.xaxis.set_major_locator(locator)
        ax.xaxis.set_major_formatter(formatter)
        fig.autofmt_xdate()
    else:
        ax.set_xticks(range(len(df_copy.index)))
        ax.set_xticklabels([str(i)[:4] for i in df_copy.index], rotation=45)

    def milyon_tl_formatter(x, _):
        return f"{x/1e6:.1f}M"

    ax.yaxis.set_major_formatter(FuncFormatter(milyon_tl_formatter))

    plt.tight_layout()
    plt.savefig(img, format='png', bbox_inches='tight')
    plt.close(fig)
    img.seek(0)

    return f"data:image/png;base64,{base64.b64encode(img.getvalue()).decode()}"

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

        if re.match(r"^(Madde \d+:|Genel Yapay Zeka Yorumu|Olumlu Yönler|Olumsuz Yönler|Genel Değerlendirme|Öneriler|Sonuç)", temizlenmis_satir, re.IGNORECASE):
            duzenlenmis_html_parcalar.append(f"<h3 class='ai-heading'>{temizlenmis_satir}</h3>")
        elif any(temizlenmis_satir.lower() == b.lower() for b in basliklar):
            duzenlenmis_html_parcalar.append(f"<h3 class='ai-heading'>{temizlenmis_satir}</h3>")
        else:
            duzenlenmis_html_parcalar.append(f"<p>{satir}</p>")

    return "\n".join(duzenlenmis_html_parcalar)

@app.route('/grafik-analyze', methods=['POST'])
def grafik_analyze():
    if 'file' not in request.files:
        return jsonify({"error": "CSV dosyası eksik"}), 400

    file = request.files['file']
    try:
        lines = file.read().decode('utf-8').splitlines()
    except Exception as e:
        return jsonify({"error": f"Dosya okunamadı: {str(e)}"}), 400

    grafikler = {}
    ai_yorumlar = []

    hedef_kalemler = [
        "Toplam Varlıklar",
        "Toplam Özkaynaklar",   # "Özsermaye" yerine bunu alın
        "Toplam Yükümlülükler",
        "Net Dönem Kârı (Zararı)",
        "Hasılat",
        "Esas Faaliyet Kârı (Zararı)"
    ]


    current_table_name = None
    current_headers = []
    current_rows = []

    def process_current_table():
        nonlocal grafikler, ai_yorumlar
        if not current_table_name or not current_headers or not current_rows:
            return

        try:
            df = pd.DataFrame([row.split(";") for row in current_rows], columns=current_headers)
            ilk_kolon = df.columns[0]
            tarih_kolonlari_raw = df.columns[1:]
            tarih_kolonlari = pd.to_datetime(tarih_kolonlari_raw, errors='coerce')  # 👈 bu satır değiştirildi
            df.columns = [ilk_kolon] + tarih_kolonlari.tolist()
            df = df.set_index(ilk_kolon)
            for col in df.columns:
                df[col] = df[col].astype(str).str.replace('.', '', regex=False).str.replace(',', '.', regex=False)
                df[col] = pd.to_numeric(df[col], errors='coerce')

            df = df.dropna(how='all', axis=0)

        except Exception as e:
            return

        for sutun_adi in hedef_kalemler:
            if sutun_adi in df.index:
                series_for_plot = df.loc[sutun_adi]

                if series_for_plot.empty or series_for_plot.isnull().all():
                    continue

                df_for_plot = series_for_plot.to_frame(name=sutun_adi)
                df_for_plot.index.name = "Dönem"

                is_kar_zarar_plot = (sutun_adi == "Net Dönem Kârı (Zararı)")

                grafik = grafik_uret(df_for_plot, f"{sutun_adi} Zaman İçinde", "Tutar (TL)", kar_zarar=is_kar_zarar_plot)

                if grafik:
                    grafikler[sutun_adi] = grafik

                try:
                    ilk = df_for_plot.iloc[0, 0]
                    son = df_for_plot.iloc[-1, 0]

                    if pd.notna(ilk) and pd.notna(son) and (ilk != 0 or son != 0):
                        prompt = (
                            f"{sutun_adi} adlı finansal kalem {ilk:,.2f} TL'den {son:,.2f} TL'ye değişmiştir.\n"
                            f"Bu değişimin olası nedenlerini analiz et. Sektörel etkiler, ekonomik gelişmeler veya operasyonel faktörleri göz önüne al. "
                            f"Kısa ve sade 3-5 maddelik bir mali yorum yaz. Türkçe yaz, maddeler halinde sırala."
                        )
                        ai_response = gemini_model.generate_content(prompt)
                        temiz_yorum = temizle_ve_duzenle_yorum(ai_response.text)
                        ai_yorumlar.append({
                            "baslik": sutun_adi,
                            "yorum": temiz_yorum
                        })
                except Exception as e:
                    ai_yorumlar.append({
                        "baslik": sutun_adi,
                        "yorum": f"{sutun_adi} için yorum üretilemedi: {str(e)}"
                    })

    for line in lines:
        line = line.strip()
        if not line:
            continue

        if "TABLOSU" in line and ";" in line:
            process_current_table()
            parts = line.split(";")
            current_table_name = parts[0].strip()
            current_headers = parts
            current_rows = []
        else:
            current_rows.append(line)

    process_current_table()

    return jsonify({
        "grafikler": grafikler,
        "ai_yorumlar": ai_yorumlar
    })

if __name__ == '__main__':
    app.run(debug=True)
