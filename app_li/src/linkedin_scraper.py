import os
import random
import html
import time
from dotenv import load_dotenv
from seleniumbase import SB
import telegram_notifier
from collections import deque
from selenium.webdriver.common.by import By
from selenium.common.exceptions import NoSuchElementException

load_dotenv(dotenv_path=".env-lis")

# --- Config ---
BASE_URL = os.getenv("BASE_URL", "https://www.linkedin.com/login")
JOBS_URL = os.getenv("JOBS_URL")
MIN_REFRESH_INTERVAL = int(os.getenv("MIN_REFRESH_INTERVAL", 60))
MAX_REFRESH_INTERVAL = int(os.getenv("MAX_REFRESH_INTERVAL", 120))
RUN_DURATION = int(os.getenv("RUN_DURATION", 180))
EMAIL = os.getenv("EMAIL")
PASSWORD = os.getenv("USER_PASSWORD")
PROXY_URL = os.getenv("PROXY_URL", None)
IS_HEADLESS = os.getenv("IS_HEADLESS", "False").lower() == "true"
CHROME_PROFILE_PATH = os.getenv("CHROME_PROFILE_PATH")

# --- Filters ---
title_keywords_str = os.getenv("TITLE_KEYWORDS_EXCLUDE", "")
TITLE_KEYWORDS_EXCLUDE = [keyword.strip() for keyword in title_keywords_str.split(',') if keyword]

countries_str = os.getenv("COUNTRIES_EXCLUDE", "")
COUNTRIES_EXCLUDE = [country.strip() for country in countries_str.split(',') if country]

# --- Globals ---
seen_jobs = deque(maxlen=25)
start_time = None

# --- Helper stuff ---

def log_message(message):
    global start_time
    if start_time is None:
        start_time = time.time() 
    
    elapsed_seconds = time.time() - start_time
    minutes, seconds = divmod(elapsed_seconds, 60)
    hours, minutes = divmod(minutes, 60)
    
    timestamp = f"{int(hours):02}:{int(minutes):02}:{int(seconds):02}"
    print(f"[ELAPSED: {timestamp}] {message}")
    
def sign_in(sb):
    log_message("   ...Typing email.")
    sb.press_keys("input#username", EMAIL)
    log_message("   ...Typing password.") 
    sb.press_keys("input#password", PASSWORD)
    
    sb.click('button[aria-label="Sign in"]')
    log_message("   ...Clicked 'Sign in'.")
    
def perform_login(sb):
    log_message(f"✅ Opened {BASE_URL}")
    sb.wait(10)
    
    log_message("   ...Checking for cookies.")
    if sb.is_element_visible('button:contains("Accept")'):
        sb.click('button:contains("Accept")')
        log_message("   ...Cookies accepted.")
        
    if "login" in sb.get_current_url():
      log_message("-> Login page detected. Signing in...")
      sign_in(sb)
    else:
      log_message("-> Already logged in. Proceeding to jobs page...")
        
    sb.wait(10)
    
def save_page_source_for_debug(sb, filename="debug_page_source.html"):
    try:
        source = sb.get_page_source()
        with open(filename, "w", encoding="utf-8") as f:
            f.write(source)
        log_message(f"✅ Successfully saved page source.")
    except Exception as e:
        log_message(f"🚨 Could not save page source. Error: {e}")

def monitor_and_scrape(sb):
    log_message("-> Starting to monitor and scrape jobs...")
    try:
        sb.wait_for_element_present("div.scaffold-layout__list", timeout=30)
        log_message("✅ Job list container is present.")
        #save_page_source_for_debug(sb)

        job_elements = sb.find_elements("li.scaffold-layout__list-item")
        
        if not job_elements:
            log_message("-> No jobs found on the page.")
            return
        else:
            log_message("-> Job elements found.")

        jobs_list = []
        for job_element in job_elements:
            try:
                title_element = job_element.find_element(By.CSS_SELECTOR, "a.job-card-list__title--link")
                title = title_element.find_element(By.CSS_SELECTOR, "strong").text.strip()
                link = title_element.get_attribute("href").split('?')[0]

                if link in seen_jobs:
                    log_message(f"^^ Job already seen: {title}")
                    continue
                
                company = job_element.find_element(By.CSS_SELECTOR, "div.artdeco-entity-lockup__subtitle").text.strip()
                location = job_element.find_element(By.CSS_SELECTOR, "div.artdeco-entity-lockup__caption").text.strip()

                seen_jobs.append(link)
                log_message(f"✨ New Job Found: {title}")
                
                job_info = (
                    f"📌 <a href='{link}'>{html.escape(title)}</a>\n"
                    f"🏢 {html.escape(company)}\n"
                    f"📍 {html.escape(location)}"
                )
                jobs_list.append(job_info)
                
            except NoSuchElementException:
                continue

        if jobs_list:
            message_to_send = "\n\n".join(jobs_list)
            log_message(f"-> Found {len(jobs_list)} jobs. Sending to Telegram...")
            telegram_notifier.send_notification(f"✨ <b>New LinkedIn Jobs Found!</b> ✨\n\n{message_to_send}")
            log_message("✅ Jobs sent to Telegram.")
        else:
            log_message("-> No new jobs to send.")

    except Exception as e:
        log_message(f"💥 An error occurred during scraping: {e}")
        
def scrape_linkedin():
    global start_time
    if start_time is None:
        start_time = time.time()

    if not EMAIL or not PASSWORD:
        log_message("🚨 ERROR: EMAIL or USER_PASSWORD is not set.")
        return
    
    with SB(uc=True, 
            headless=IS_HEADLESS, 
            proxy=PROXY_URL, 
            user_data_dir=CHROME_PROFILE_PATH,
            ) as sb:
        log_message(f"Chrome profile: {CHROME_PROFILE_PATH}")
        log_message(f"Proxy: {PROXY_URL}")
        log_message(f"✅ Opening {BASE_URL}...")
        try:
            sb.open(BASE_URL)
            
            perform_login(sb)
            
            log_message("-> Going to jobs URL...")
            sb.open(JOBS_URL)
            sb.wait(10)
            
            monitor_and_scrape(sb)
            
        except Exception as e:
            log_message(f"💥 A critical error occurred: {e}")
            screenshot_name = "critical_error.png"
            sb.save_screenshot(screenshot_name, folder="latest_logs")
            screenshot_path = os.path.join("latest_logs", screenshot_name)

            error_message = (
                f"💥 <b>A critical error occurred!</b>\n"
                f"The script will now restart.\n\n"
                f"<b>Error:</b>\n<pre>{html.escape(str(e))}</pre>"
            )
            
            log_message(f"...Sending error notification and screenshot to {screenshot_path}")
            if os.path.exists(screenshot_path):
                telegram_notifier.send_photo(screenshot_path, caption=error_message)
            else:
                telegram_notifier.send_notification(error_message)
            
            raise e

if __name__ == "__main__":
    telegram_notifier.send_notification("🤖 Linkedin scraper bot has started.")
    
    while True:
        try:
            log_message(f"--- 🚀 Starting new scraper session ---")
            scrape_linkedin()
            log_message(f"--- ✅ Scraper session finished cleanly. Restarting after {RUN_DURATION / 60:.0f} minutes... ---")
            time.sleep(RUN_DURATION)
        except Exception as e:
            log_message(f"🔥 A critical error forced a full restart: {e}")
            sleep_duration = 45
            log_message(f"--- 😴 Restarting the entire script in {sleep_duration} seconds... ---")
            time.sleep(sleep_duration)