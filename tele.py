import os
import logging
import requests
import json
from dotenv import load_dotenv
import google.generativeai as genai
from google.generativeai.types import HarmCategory, HarmBlockThreshold
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# .env dosyasındaki environment variable'ları yükle
load_dotenv()

# Telegram ve Gemini API token'larını .env dosyasından al
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Hata ayıklama (logging) ayarları
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Gemini API'yi yapılandır
try:
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel('gemini-2.5-flash-lite')
    logger.info("Gemini API başarıyla yapılandırıldı.")
except Exception as e:
    logger.error(f"Gemini API yapılandırılamadı: {e}")
    model = None

# Veri alınacak API adresi
DATA_API_URL = "https://uky2iqnwpi.execute-api.eu-central-1.amazonaws.com/prod/data"

def fetch_market_data():
    """Piyasa verilerini belirtilen URL'den çeker."""
    try:
        response = requests.get(DATA_API_URL)
        response.raise_for_status()  # HTTP hatalarını kontrol et
        logger.info("Piyasa verileri başarıyla çekildi.")
        return response.json()
    except requests.exceptions.RequestException as e:
        logger.error(f"API'den veri çekilirken hata oluştu: {e}")
        return None

def get_llm_response(user_query, market_data):
    """Kullanıcı sorgusunu ve piyasa verilerini LLM'e göndererek cevap alır."""
    if not model:
        return "LLM modeli şu anda mevcut değil. Lütfen daha sonra tekrar deneyin."

    prompt = f"""
    Giriş Bilgileri:
    1. Kullanıcı Sorusu: "{user_query}"
    2. Piyasa Verileri (JSON formatında): {json.dumps(market_data, indent=2)}

    Talimat:
    1. Kullanıcının sorusundan hangi piyasa verisini istediğini anla. Bunun için hem 'Kod' (örn: 'VIX') hem de 'Aciklama' (örn: 'INDEX VIX INDEX') alanlarını dikkate al.
    2. Piyasa Verileri listesinde, kullanıcının istediği veriye karşılık gelen JSON nesnesini bul.
    3. Bulduğun bu nesnenin **mevcut olan tüm alanlarını (Sira_No, Tarih, Saat, Kod, Aciklama, Son_Fiyat, Yuzde_Degisim)** eksiksiz bir şekilde, her bir bilgiyi yeni bir satıra yazarak listele.
    4. Cevabını "İstediğiniz [Veri Adı] verisinin bilgileri:" şeklinde bir başlıkla başlat. Veri adı olarak 'Kod' ve 'Aciklama' alanını kullan ve 'Kod > Açıklama' formatında belirt.
    5. Eğer istenen bilgi verilerde yoksa, "İstediğiniz bilgi mevcut verilerde bulunmuyor." de.
    6. Ekstra yorum veya açıklama yapma.

    Örnek Çıktı Formatı:
    İstediğiniz VIX > INDEX VIX INDEX verisinin bilgileri:
    
    Sira_No: 1
    Tarih: 2025-09-03
    Saat: 12:19:36
    Kod: VIX
    Aciklama: INDEX VIX INDEX
    Son_Fiyat: 17.06
    Yuzde_Degisim: -0.64
    """
    
    try:
        # Güvenlik ayarları eklenerek API çağrısı yapılıyor
        response = model.generate_content(
            prompt,
            safety_settings={
                HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
                HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
                HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
                HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
            }
        )
        logger.info("LLM'den cevap başarıyla alındı.")
        return response.text
    except Exception as e:
        logger.error(f"LLM'den cevap alınırken bir hata oluştu: {e}")
        return "Veri işlenirken bir sorun oluştu. Lütfen daha sonra tekrar deneyin."

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/start komutu gönderildiğinde hoşgeldin mesajı gönderir."""
    await update.message.reply_text('Merhaba! Piyasa verileri hakkında bilgi almak için sorunuzu yazın.')

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Kullanıcıdan gelen metin mesajlarını işler."""
    user_message = update.message.text
    logger.info(f"Kullanıcıdan mesaj alındı: {user_message}")

    # Piyasa verilerini çek
    market_data = fetch_market_data()
    if market_data is None:
        await update.message.reply_text("Piyasa verileri şu anda alınamıyor. Lütfen daha sonra tekrar deneyin.")
        return

    # LLM'den cevap al ve kullanıcıya gönder
    llm_answer = get_llm_response(user_message, market_data)
    await update.message.reply_text(llm_answer)

def main() -> None:
    """Telegram botunu başlatır ve gelen mesajları dinler."""
    if not TELEGRAM_BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN bulunamadı. Lütfen .env dosyasını kontrol edin.")
        return

    # Application'ı oluştur
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # Komut ve mesaj handler'larını ekle
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("Bot başlatılıyor...")
    # Botu başlat
    application.run_polling(drop_pending_updates=True)

if __name__ == '__main__':
    main()