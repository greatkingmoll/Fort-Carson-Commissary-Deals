from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import NoSuchElementException, TimeoutException
from webdriver_manager.chrome import ChromeDriverManager
import time
from datetime import datetime, timedelta
import shutil
import subprocess
import os
import json
import base64
import requests

# GitHub configuration - uses environment variables
GITHUB_TOKEN = os.environ.get('GITHUB_TOKEN')
REPO_OWNER = "greatkingmoll"
REPO_NAME = "Fort-Carson-Commissary-Deals"
TARGET_PATH = "index.html"
BRANCH = "main"
API_URL = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/contents/{TARGET_PATH}"

# Configuration
ALL_COOKIES = [
    # { 'pref': '%7B%22store_id%22%3A%225827%22%7D', 'fp-pref': '%7B%22store_id%22%3A%225827%22%7D', 'fp_user_allowed_save_cookie': 'true' },
    { 'pref': '%7B%22store_id%22%3A%225825%22%7D', 'fp-pref': '%7B%22store_id%22%3A%225825%22%7D', 'fp_user_allowed_save_cookie': 'true' },
    # { 'pref': '%7B%22store_id%22%3A%225824%22%7D', 'fp-pref': '%7B%22store_id%22%3A%225824%22%7D', 'fp_user_allowed_save_cookie': 'true' },
]

URLS = {
    'ALL Departments': 'https://shop.commissaries.com/shop#!/?limit=96&sort=price&filter=is_on_sale',
}

SEEN_FILE = "seen_items.json"

def setup_driver():
    opts = Options()
    opts.add_argument("--headless")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    
    driver_path = ChromeDriverManager().install()
    service = Service(driver_path)
    return webdriver.Chrome(service=service, options=opts)

def extract_items(driver, url, COOKIES):
    MAX_RETRIES = 3
    items = []

    # Determine page count
    first_page = url + '&page=1'
    driver.get(first_page)
    for k,v in COOKIES.items():
        driver.add_cookie({'name': k, 'value': v})
    driver.refresh()
    for _ in range(MAX_RETRIES):
        try:
            WebDriverWait(driver,10).until(EC.presence_of_element_located((By.CSS_SELECTOR,'.fp-paging-list-container')))
            break
        except TimeoutException:
            driver.get(first_page)
    pages = 28  # override

    for p in range(1, pages+1):
        page_url = url + f'&page={p}'
        driver.get(page_url)
        for k,v in COOKIES.items():
            driver.add_cookie({'name': k, 'value': v})
        driver.refresh()

        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(1.5)

        for _ in range(5):
            try:
                WebDriverWait(driver,15).until(EC.presence_of_element_located((By.CSS_SELECTOR,'.fp-item')))
                break
            except TimeoutException:
                driver.get(page_url)

        cards = driver.find_elements(By.CSS_SELECTOR, '.fp-item')
        for card in cards:
            try:
                a = card.find_element(By.CSS_SELECTOR, '.fp-item-name a')
                name = a.text.strip()
                link = a.get_attribute('href')

                img = card.find_element(By.CSS_SELECTOR, '.fp-item-image img')
                src = img.get_attribute('src') or ''
                img_url = img.get_attribute('data-src') if src.startswith('data:') else src

                orig = float(card.find_element(By.CSS_SELECTOR, '.fp-item-base-price').text.strip().replace('$',''))
                sale_txt = card.find_element(By.CSS_SELECTOR, '.fp-item-sale').text.strip()
                if "Buy 1 get 1 free" in sale_txt:
                    sale = orig/2
                elif "%" in sale_txt:
                    pct = float(sale_txt.split('%')[0].split()[-1])
                    sale = orig*(1-pct/100)
                else:
                    try:
                        sale = float(sale_txt.split('$')[1].split()[0])
                    except:
                        sale = 0.0

                items.append({
                    'name': name,
                    'original_price': orig,
                    'sale_price': sale,
                    'product_link': link,
                    'image_url': img_url
                })
            except NoSuchElementException:
                continue

    return items

def find_discounted_items(items, threshold=45):
    out = []
    for it in items:
        disc = ((it['original_price'] - it['sale_price']) / it['original_price']) * 100
        if disc > threshold:
            it['discount'] = disc
            out.append(it)
    return out

def write_html(html_file, store, items, new_items, date_str):
    with open(html_file, 'w', encoding='utf-8') as f:
        f.write(f"<html><head><title>{store} Sales {date_str}</title></head><body>\n")
        f.write(f"<h2>{store} — Items ≥45% Off ({date_str})</h2>\n")

        if new_items:
            f.write("<h3>*** New Items Since Yesterday ***</h3>\n")
            f.write('<table border="1" cellpadding="6">\n')
            f.write("<tr><th>Image</th><th>Item</th><th>Original</th><th>Sale</th><th>Discount</th></tr>\n")
            for it in new_items:
                img_html = f'<img src="{it["image_url"]}" width="64" height="64">' if it["image_url"] else ""
                link_html = f'<a href="{it["product_link"]}" target="_blank">{it["name"]}</a>'
                f.write(
                    f"<tr><td>{img_html}</td>"
                    f"<td>{link_html}</td>"
                    f"<td>${it['original_price']:.2f}</td>"
                    f"<td>${it['sale_price']:.2f}</td>"
                    f"<td>{it['discount']:.1f}%</td></tr>\n"
                )
            f.write("</table>\n<br>\n")

        f.write("<h3>All Discounted Items</h3>\n")
        f.write('<table border="1" cellpadding="6">\n')
        f.write("<tr><th>Image</th><th>Item</th><th>Original</th><th>Sale</th><th>Discount</th></tr>\n")
        if items:
            for it in items:
                img_html = f'<img src="{it["image_url"]}" width="64" height="64">' if it["image_url"] else ""
                link_html = f'<a href="{it["product_link"]}" target="_blank">{it["name"]}</a>'
                f.write(
                    f"<tr><td>{img_html}</td>"
                    f"<td>{link_html}</td>"
                    f"<td>${it['original_price']:.2f}</td>"
                    f"<td>${it['sale_price']:.2f}</td>"
                    f"<td>{it['discount']:.1f}%</td></tr>\n"
                )
        else:
            f.write('<tr><td colspan="5">No items ≥45% off.</td></tr>\n')
        f.write("</table>\n</body></html>")

def main():
    # Load seen items mapping
    try:
        with open(SEEN_FILE, 'r', encoding='utf-8') as f:
            seen = json.load(f)
    except FileNotFoundError:
        seen = {}

    today = datetime.now().date()
    yesterday = today - timedelta(days=1)
    today_str = today.isoformat()
    yesterday_str = yesterday.isoformat()

    for COOKIES in ALL_COOKIES:
        pref = COOKIES['pref']
        if '5825' in pref:
            txt, html, store = "Daily_Commissary_Sales_Fort_Carson.txt", "Daily_Commissary_Sales_Fort_Carson.html", "Fort Carson"
        elif '5824' in pref:
            txt, html, store = "Daily_Commissary_Sales_USAFA.txt", "Daily_Commissary_Sales_USAFA.html", "USAFA"
        elif '5827' in pref:
            txt, html, store = "Daily_Commissary_Sales_PETE.txt", "Daily_Commissary_Sales_PETE.html", "Peterson AFB"
        else:
            txt, html, store = "Daily_Commissary_Sales_Other.txt", "Daily_Commissary_Sales_Other.html", "Other"

        # Backup previous text
        bak = txt + '.bak'
        try:
            shutil.copy(txt, bak)
        except:
            pass

        driver = setup_driver()
        date_str = today_str

        # Extract and filter
        all_items = []
        for cat, url in URLS.items():
            all_items.extend(extract_items(driver, url, COOKIES))
        driver.quit()

        disc_items = find_discounted_items(all_items)

        # Determine new items
        new_items = []
        for it in disc_items:
            name = it['name']
            first_seen = seen.get(name)
            if not first_seen:
                seen[name] = today_str
                first_seen = today_str
            # Item is "new" if first seen today or yesterday
            if first_seen in (today_str, yesterday_str):
                new_items.append(it)

        # Write text file (existing logic)
        with open(txt, 'w', encoding='utf-8') as tf:
            tf.write(f"{date_str}\nItems discounted by 45% or more:\n")
            for it in disc_items:
                marker = "***" if it in new_items else ""
                name_col = f"{it['name'][:84]:<84}"
                orig_col = f"${it['original_price']:.2f}".center(15)
                sale_col = f"${it['sale_price']:.2f}".center(15)
                disc_col = f"{it['discount']:.1f}% {marker}".center(15)
                tf.write(name_col + orig_col + sale_col + disc_col + "\n")
            tf.write(f"\nElapsed Time: N/A\n")

        # Write enhanced HTML
        write_html(html, store, disc_items, new_items, date_str)

    # Persist seen mapping after processing all stores
    with open(SEEN_FILE, 'w', encoding='utf-8') as f:
        json.dump(seen, f, indent=2)

if __name__ == '__main__':
    main()
