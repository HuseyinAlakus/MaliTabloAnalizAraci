from flask import Flask, request, jsonify
from flask_cors import CORS
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.ticker import FuncFormatter
import seaborn as sns
import io
import base64
import google.generativeai as genai
import re
import matplotlib
matplotlib.use('Agg')

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
            
            # Barları ayrı ayrı çiz (renk uygulanmasını garanti eder)
            for i, (label, value) in enumerate(zip(df_copy.index, values)):
                ax.bar(label, value, color=renkler_kar_zarar[i], edgecolor='black', linewidth=0.5, width=50)
                ax.text(label, value + (1e6 if value >= 0 else -1e6), f"{value/1e6:.1f}M", 
                        ha='center', va='bottom' if value >= 0 else 'top', fontsize=8)

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
                            "Yanıtınızda kesinlikle başlık dışında hiçbir yıldız (*), tire (-), numara (1., 2.), ya da markdown biçimi kullanmayın. Her şey düz yazı olsun."
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
