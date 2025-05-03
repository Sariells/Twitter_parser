import time
import pickle
import json
import random
import requests
import os
import threading
import sys

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager


options = Options()
options.add_argument("--disable-blink-features=AutomationControlled")
options.add_experimental_option("excludeSwitches", ["enable-automation"])
options.add_experimental_option('useAutomationExtension', False)
options.add_argument("--headless=new")
options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

service = Service(ChromeDriverManager().install())
driver = webdriver.Chrome(service=service, options=options)


driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
    "source": """
        Object.defineProperty(navigator, 'webdriver', {
          get: () => undefined
        })
    """
})

def load_config():
    try:
        with open("config.json", "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"❌ Ошибка загрузки config.json: {e}")
        exit(1)

def load_counts():
    if os.path.exists("count.json"):
        with open("count.json", "r", encoding="utf-8") as f:
            return json.load(f)
    else:
        return {}

def login_and_save_cookies():
    driver.get('https://twitter.com/login')
    input("🔐 Войдите вручную в Twitter, решите капчу, и нажмите Enter...")

    time.sleep(5)
    cookies = driver.get_cookies()
    with open("cookies.pkl", "wb") as file:
        pickle.dump(cookies, file)
    print("✅ Cookies сохранены!")

def load_cookies():
    driver.get("https://twitter.com/")
    time.sleep(10)
    with open("cookies.pkl", "rb") as file:
        cookies = pickle.load(file)
        for cookie in cookies:
            driver.add_cookie(cookie)
    driver.get("https://twitter.com/home")
    print("✅ Cookies загружены!")

def load_tweets_from_json():
    if os.path.exists("tweets.json"):
        try:
            with open("tweets.json", "r", encoding="utf-8") as f:
                return json.load(f)
        except json.JSONDecodeError:
            print("⚠️ Ошибка декодирования JSON. Файл может быть поврежден. Создаю новый.")
            return {}
    else:
        print("📂 Файл tweets.json не найден. Создаю новый.")
        return {}

def save_tweets_to_json(tweets_data):
    try:
        with open("tweets.json", "w", encoding="utf-8") as f:
            json.dump(tweets_data, f, ensure_ascii=False, indent=2)
            print("💾 Все твиты сохранены в tweets.json")
    except Exception as e:
        print(f"❌ Ошибка при сохранении файла tweets.json: {e}")

def clean_old_tweets(tweets_data):
    current_time = time.time()
    
    for hashtag, tweets in tweets_data.items():
        tweets_data[hashtag] = [tweet for tweet in tweets if current_time - tweet.get('timestamp', 0) <= 86400]
    
    print("🔄 Старые твиты очищены.")
    return tweets_data


def save_counts(counts):
    with open("count.json", "w", encoding="utf-8") as f:
        json.dump(counts, f, ensure_ascii=False, indent=2)

def choose_balanced_tag(hashtags, counts):
    for tag in hashtags:
        if tag not in counts:
            counts[tag] = 0

    min_count = min(counts.values())
    min_tags = [tag for tag in hashtags if counts[tag] == min_count]
    return random.choice(min_tags)

def check_driver_health():
    try:
        driver.title
    except Exception as e:
        print(f"⚠️ Ошибка с браузером: {e}")
        return False
    return True

def collect_tweets_with_hashtag(hashtag, max_scrolls_limit=10, min_new_tweets_threshold=3):
    driver.get(f"https://twitter.com/hashtag/{hashtag}?src=hashtag_click")
    
    try:
        WebDriverWait(driver, 30).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, 'article'))
        )
        print(f"🔍 Твиты по хештегу #{hashtag} загружены.")
    except Exception as e:
        print(f"⚠️ Ошибка ожидания загрузки твитов: {e}")
        return []

    tweets = []
    seen_urls = set()
    scrolls = 0
    recent_new_counts = []

    while scrolls < max_scrolls_limit:
        print(f"📜 Прокрутка {scrolls + 1}/{max_scrolls_limit}")
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(random.uniform(5, 8))

        new_tweets = 0
        tweet_elements = driver.find_elements(By.CSS_SELECTOR, 'article')

        for tweet in tweet_elements:
            try:
                tweet_text = tweet.find_element(By.CSS_SELECTOR, 'div[lang]').text
                tweet_url = tweet.find_element(By.CSS_SELECTOR, 'a[href*="/status/"]').get_attribute("href")

                if tweet_url and tweet_url not in seen_urls:
                    seen_urls.add(tweet_url)
                    tweets.append({"text": tweet_text, "url": tweet_url})
                    new_tweets += 1
            except Exception:
                continue

        recent_new_counts.append(new_tweets)
        if len(recent_new_counts) >= 2 and sum(recent_new_counts[-2:]) < min_new_tweets_threshold:
            print("📉 Мало новых твитов — остановка прокрутки.")
            break

        scrolls += 1

    return tweets


def filter_ads(tweets):
    filtered_tweets = []
    for tweet in tweets:
        tweet_text = tweet['text']
        
        # Исключаем твиты, содержащие рекламу или ссылки на игры
        if "Pre-order open!!" in tweet_text or "#AmiAmi" in tweet_text or "Order from" in tweet_text:
            print(f"🚫 Пропущено рекламное сообщение: {tweet_text}")
        elif "steam" in tweet_text.lower() or "store.steampowered" in tweet_text.lower():
            print(f"🚫 Пропущено рекламное сообщение (Steam): {tweet_text}")
        elif "https://x.com" in tweet_text or "https://twitter.com" in tweet_text:
            print(f"🚫 Пропущено сообщение с ссылкой: {tweet_text}")
        else:
            filtered_tweets.append(tweet)
    
    return filtered_tweets

def send_to_discord(tweets, hashtag, webhook_url, all_results):
    sent_urls = set()

    for tweet in tweets:
        tweet_url = tweet['url']
        
        # Проверяем, был ли твит отправлен в последние 24 часа
        if any(t['url'] == tweet_url and t['timestamp'] > time.time() - 86400 for t in all_results.get(hashtag, [])):
            print(f"🚫 Твит с URL {tweet_url} уже был отправлен недавно.")
            continue
        
        sent_urls.add(tweet_url)
        
        content = f"#{hashtag}\n**{tweet['text']}**\n{tweet['url']}"
        data = {
            "content": content
        }
        
        time.sleep(random.uniform(2, 3))  # Ожидание между отправками

        try:
            response = requests.post(webhook_url, json=data)
            if response.status_code == 204:
                print(f"✅ Отправлено в Discord: {tweet['url']}")
                # Добавляем метку времени для отправленного твита
                tweet['timestamp'] = time.time()
                all_results.setdefault(hashtag, []).append(tweet)  # Добавляем твит в список
            else:
                print(f"❌ Ошибка отправки в Discord: {response.text}")
        except Exception as e:
            print(f"⚠️ Discord ошибка: {e}")


def restart_script():
    print("🔄 Перезапуск скрипта...")
    time.sleep(3)
    os.execv(sys.executable, ['python'] + sys.argv)

def main():
    try:
        config = load_config()
        webhook_urls = config["webhook_urls"]
        hashtags = config["hashtags"]
        max_scrolls = config.get("max_scrolls", 10)  # ← вот так правильно
        min_wait = config.get("min_wait", 900)
        max_wait = config.get("max_wait", 1800)


        try:
            load_cookies()
        except FileNotFoundError:
            login_and_save_cookies()

        all_results = load_tweets_from_json()
        counts = load_counts()

        while True:
            tag = choose_balanced_tag(hashtags, counts)
            print(f"🔍 Начинаем обработку хештега #{tag}")

            tweets = collect_tweets_with_hashtag(tag, max_scrolls_limit=max_scrolls)
            filtered_tweets = filter_ads(tweets)
            all_results[tag] = filtered_tweets
            print(f"✅ Найдено {len(filtered_tweets)} твитов по хештегу #{tag}")

            # Очищаем старые твиты перед отправкой
            all_results = clean_old_tweets(all_results)

            threads = []
            for url in webhook_urls:
                thread = threading.Thread(target=send_to_discord, args=(filtered_tweets, tag, url, all_results))
                thread.start()
                threads.append(thread)

            for thread in threads:
                thread.join()

            # Обновление и сохранение данных
            counts[tag] += 1
            save_counts(counts)
            save_tweets_to_json(all_results)

            wait_time = random.randint(min_wait, max_wait)
            print(f"⏳ Ожидаем {wait_time // 60} минут...")
            time.sleep(wait_time)

    except Exception as e:
        print(f"❌ Ошибка выполнения скрипта: {e}")
        restart_script()

    driver.quit()


if __name__ == "__main__":
    main()
