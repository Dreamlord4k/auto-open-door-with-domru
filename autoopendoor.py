import requests
import subprocess
import json
import time
from vosk import Model, KaldiRecognizer

# --- ГЛАВНЫЕ НАСТРОЙКИ ПРОЕКТА ---
SECRET_PHRASE = "ваша секретная фраза"
MODEL_PATH = "vosk-model-small-ru-****" 
ACCESS_TOKEN = "ваш токен домофона"
CAMERA_ID = "id камеры"
API_STREAM_URL = f"ссылка на поток камеры домофона"
API_OPEN_DOOR_URL = "ссылка на действие открытия двери"
API_OPEN_DOOR_PAYLOAD = {"name": "accessControlOpen"}
COOLDOWN_SECONDS = 5
last_open_time = 0

# --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ---
def open_the_door():
    global last_open_time
    print("\n!!! КОДОВАЯ ФРАЗА РАСПОЗНАНА !!!")
    print("--- Отправляю команду на открытие двери... ---")
    try:
        headers = {
            "Authorization": f"Bearer {ACCESS_TOKEN}",
            "Content-Type": "application/json; charset=utf-8",
        }
        response = requests.post(API_OPEN_DOOR_URL, headers=headers, json=API_OPEN_DOOR_PAYLOAD)
        if response.status_code == 200:
            print("--- УСПЕХ! Дверь открыта! ---")
        else:
            print(f"--- ОШИБКА! Не удалось открыть дверь. Статус: {response.status_code} ---")
            print(response.text)
    except Exception as e:
        print(f"--- КРИТИЧЕСКАЯ ОШИБКА СЕТИ: {e} ---")
    last_open_time = time.time()

# --- ШАГ 1: ЕДИНОРАЗОВАЯ ЗАГРУЗКА ТЯЖЕЛОЙ МОДЕЛИ ---
# Мы делаем это ОДИН РАЗ за пределами главного цикла.
print("Загружаю модель распознавания речи (это может занять несколько секунд)...")
try:
    model = Model(MODEL_PATH)
    print("Модель успешно загружена.")
except Exception as e:
    print(f"Критическая ошибка: не удалось загрузить модель из '{MODEL_PATH}'")
    print(e)
    exit()


# --- ГЛАВНЫЙ ЦИКЛ-СУПЕРВАЙЗЕР ---
while True:
    try:
        # --- ШАГ 2: ПОЛУЧАЕМ СВЕЖУЮ ССЫЛКУ (быстрая операция) ---
        print("\n--- (RE)START: Начинаю новый цикл подключения ---")
        print("1. Получаю ссылку на аудио/видео поток...")
        headers = {"Authorization": f"Bearer {ACCESS_TOKEN}", "User-Agent": "okhttp/4.9.1"}
        response = requests.get(API_STREAM_URL, headers=headers)
        if response.status_code != 200:
            print(f"Не удалось получить ссылку. Ошибка: {response.text}. Повтор через 30 секунд...")
            time.sleep(30)
            continue

        stream_url = response.json().get("data", {}).get("URL")
        if not stream_url:
            print("Ссылка на поток не найдена. Повтор через 30 секунд...")
            time.sleep(30)
            continue
        print(f"Ссылка получена.")

        # --- ШАГ 3: ЗАПУСКАЕМ FFMPEG (быстрая операция) ---
        print("2. Запускаю ffmpeg для извлечения аудио...")
        ffmpeg_cmd = [
            'ffmpeg', '-i', stream_url,
            '-vn', '-acodec', 'pcm_s16le', '-ar', '16000', '-ac', '1',
            '-f', 's16le', 'pipe:1']
        ffmpeg_proc = subprocess.Popen(ffmpeg_cmd, stdout=subprocess.PIPE)

        # --- ШАГ 4: ИНИЦИАЛИЗИРУЕМ РАСПОЗНАВАТЕЛЬ (быстрая операция) ---
        # Sam recognizer создается быстро, так как модель уже в памяти
        recognizer = KaldiRecognizer(model, 16000)
        print("3. Начинаю прослушивание потока...")
        print("-------------------------------------------------")

        # --- ШАГ 5: ВНУТРЕННИЙ ЦИКЛ ПРОСЛУШИВАНИЯ ---
        while True:
            audio_chunk = ffmpeg_proc.stdout.read(4000)
            if not audio_chunk:
                print("Аудиопоток завершен (сессия истекла или ошибка).")
                break 

            if recognizer.AcceptWaveform(audio_chunk):
                result = json.loads(recognizer.Result())
                recognized_text = result.get('text', '')
                if recognized_text:
                    print(f"Распознано: '{recognized_text}'")
                    if SECRET_PHRASE in recognized_text and (time.time() - last_open_time) > COOLDOWN_SECONDS:
                        open_the_door()

    except KeyboardInterrupt:
        print("\nПрограмма прервана пользователем.")
        break 
    except Exception as e:
        print(f"\nПроизошла критическая ошибка: {e}")
    
    finally:
        if 'ffmpeg_proc' in locals() and ffmpeg_proc.poll() is None:
            ffmpeg_proc.kill()
            print("Процесс ffmpeg завершен.")

    print("Перезапуск через 10 секунд...")
    time.sleep(10)