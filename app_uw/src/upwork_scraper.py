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

load_dotenv(dotenv_path=".env-uws")

# --- Config ---
BASE_URL = os.getenv("BASE_URL")
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

# --- Selectors ---
JOB_LIST_SELECTOR = '[data-test="job-tile-list"]'
JOB_LINK_SELECTOR = 'h3.job-tile-title a'

# --- Globals ---
# queue of the last 20 seen jobs
seen_jobs = deque(maxlen=20)
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

def is_job_relevant(title, country):
    title_lower = title.lower()
    if any(keyword.lower() in title_lower for keyword in TITLE_KEYWORDS_EXCLUDE):
        return False
    if any(excluded_country.lower() == country.lower() for excluded_country in COUNTRIES_EXCLUDE):
        return False
    return True

# --- Core  ---

def sign_in(sb):
    log_message("   ...Typing email.")
    sb.type("input#login_username", EMAIL)
    sb.click("button#login_password_continue")
    
    log_message("   ...Typing password.")
    sb.type("input#login_password", PASSWORD)
    
    log_message("   ...Clicking 'Remember me' checkbox.")
    sb.click('span[data-test="checkbox-input"]')
    
    log_message("   ...Clicking final login button.")
    sb.click("button#login_control_continue")
    
def perform_login(sb):
    sb.wait(10)
    
    log_message("   ......Checking for cookies.")
    if sb.is_element_visible("button#onetrust-accept-btn-handler"):
        sb.click("button#onetrust-accept-btn-handler")
        log_message("   ...Cookies accepted.")
        
    if "login" in sb.get_current_url():
        log_message("-> Login page detected. Signing in...")
        sign_in(sb)
    else:
        log_message("-> Already logged in. Proceeding to jobs page...")
        
    sb.wait(10)
    
    log_message("-> Waiting for job feed to load post-login...")
    sb.wait_for_element_visible(JOB_LIST_SELECTOR, timeout=30)
    log_message("✅ Login successful and job feed is fully loaded.")

def extract_job_details(job_container_element):
    details = {}
    try:
        title_element = job_container_element.find_element(By.CSS_SELECTOR, JOB_LINK_SELECTOR)
        href = title_element.get_attribute("href")
        if href and href.startswith('/'):
            href = "https://www.upwork.com" + href
            
        details["href"] = href
        details["title"] = title_element.text
        details["description"] = job_container_element.find_element(By.CSS_SELECTOR, '[data-test="job-description-text"]').text.strip()
        details["spendings"] = job_container_element.find_element(By.CSS_SELECTOR, '[data-test="client-spendings"]').text.strip()
        details["country"] = job_container_element.find_element(By.CSS_SELECTOR, '[data-test="client-country"]').text.strip()
    except NoSuchElementException:
        log_message("   - Could not parse a job tile, skipping.")
        return None
    return details

def format_and_send_job_notification(details):
    job_title_safe = html.escape(details["title"])
    job_description_safe = html.escape(details["description"])
    if len(job_description_safe) > 3000:
        job_description_safe = job_description_safe[:3000] + "..."

    message = (
        f'<b>🚀New Job:</b> <a href="{details["href"]}">{job_title_safe}</a>\n'
        f"<b>Client spent:</b> {details['spendings']}\n"
        f"<b>Country:</b> {html.escape(details['country'])}\n"
        f"<b>Description:</b>\n{job_description_safe}"
    )
    telegram_notifier.send_notification(message)

def process_new_job_posting(job_container_element):
    global seen_jobs
    details = extract_job_details(job_container_element)
    
    if not details or "href" not in details:
        return False
        
    job_href = details["href"]
    if job_href in seen_jobs:
        return False

    seen_jobs.append(job_href)
    log_message(f"✨ New Job Found: {details['title']}")
    log_message(f"   - Country: {details['country']}")

    if is_job_relevant(details['title'], details['country']):
        log_message("   - ✅ Job matches filters! Sending notification...")
        format_and_send_job_notification(details)
    else:
        log_message("   - ❌ Job does not match filters. Skipping.")
    return True

def build_initial_baseline(sb):
    global seen_jobs
    log_message("🔍 Performing initial scan to build a baseline of current jobs...")
    job_container_selector = f'{JOB_LIST_SELECTOR} section'
    sb.wait_for_element_visible(job_container_selector, timeout=20)
    initial_job_containers = sb.find_elements(job_container_selector)
    
    for container in initial_job_containers:
        try:
            title_element = container.find_element(By.CSS_SELECTOR, JOB_LINK_SELECTOR)
            href = title_element.get_attribute("href")
            if href and href.startswith('/'):
                href = "https://www.upwork.com" + href
            if href:
                seen_jobs.append(href)
        except NoSuchElementException:
            continue
    log_message(f"✅ Baseline established. Found {len(seen_jobs)} initial jobs.")

def monitor_and_scrape(sb):
    start_of_run = time.time()
    log_message(f"Monitoring for jobs for the next {RUN_DURATION / 60:.0f} minutes...")

    while time.time() - start_of_run < RUN_DURATION:
        sleep_time = random.randint(MIN_REFRESH_INTERVAL, MAX_REFRESH_INTERVAL)
        if time.time() + sleep_time > start_of_run + RUN_DURATION:
            log_message("🏁 Nearing end of cycle, skipping final sleep to restart cleanly.")
            break
        log_message(f"😴 Sleeping for {sleep_time} seconds before next refresh...")
        time.sleep(sleep_time)
        
        log_message("🔄 Refreshing the page...")
        sb.refresh()
        
        log_message("✅ Page refreshed, looking for jobs list...")
        job_container_selector = f'{JOB_LIST_SELECTOR} section'
        sb.wait_for_element_visible(job_container_selector, timeout=30)
        
        job_containers = sb.find_elements(job_container_selector)
        log_message(f"🔍 Found {len(job_containers)} jobs on the page. Checking for new ones...")
        
        new_jobs_found_count = 0
        for container in job_containers:
            if process_new_job_posting(container):
                new_jobs_found_count += 1
        
        if new_jobs_found_count == 0:
            log_message("... No new jobs found in this check.")
    
    log_message("🏁 Finished monitoring cycle. The browser will now restart.")

def scrape_upwork():
    global start_time
    if start_time is None:
        start_time = time.time()

    if not EMAIL or not PASSWORD:
        log_message("🚨 ERROR: EMAIL or USER_PASSWORD is not set.")
        return

    log_message("🚀 Starting Upwork Scraper...")

    with SB(uc=True, 
            headless=IS_HEADLESS, 
            proxy=PROXY_URL,
            user_data_dir=CHROME_PROFILE_PATH,
            ) as sb:
        log_message(f"✅ Opening {BASE_URL}...")
        try:
            sb.open(BASE_URL)
            sb.set_window_size(1280, 720)
            log_message(f"✅ Opened {BASE_URL}")
            perform_login(sb)
            build_initial_baseline(sb)
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
    telegram_notifier.send_notification("🤖 Upwork scraper bot has started.")
    
    while True:
        try:
            log_message(f"--- 🚀 Starting new scraper session ---")
            scrape_upwork()
            log_message("--- ✅ Scraper session finished cleanly. Restarting after a short delay. ---")
            time.sleep(10)
        except Exception as e:
            log_message(f"🔥 A critical error forced a full restart: {e}")
            sleep_duration = 45
            log_message(f"--- 😴 Restarting the entire script in {sleep_duration} seconds... ---")
            time.sleep(sleep_duration)