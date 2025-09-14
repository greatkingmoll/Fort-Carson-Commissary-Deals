from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import NoSuchElementException, TimeoutException
import time
from datetime import datetime
import shutil
import subprocess
import os
import base64
import requests

GITHUB_TOKEN = GITHUB_TOKEN = os.environ.get('GITHUB_TOKEN')
REPO_OWNER = "greatkingmoll"
REPO_NAME = "Fort-Carson-Commissary-Deals"
TARGET_PATH = "index.html"
BRANCH = "main"
API_URL = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/contents/{TARGET_PATH}"

# powershell_path = r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe"
# script_path = r"C:\Users\robin\Commissary\Send_attachment_multiple.ps1"

ALL_COOKIES = [
#    { 'pref': '%7B%22store_id%22%3A%225827%22%7D', 'fp-pref': '%7B%22store_id%22%3A%225827%22%7D', 'fp_user_allowed_save_cookie': 'true' },
    { 'pref': '%7B%22store_id%22%3A%225825%22%7D', 'fp-pref': '%7B%22store_id%22%3A%225825%22%7D', 'fp_user_allowed_save_cookie': 'true' },
#    { 'pref': '%7B%22store_id%22%3A%225824%22%7D', 'fp-pref': '%7B%22store_id%22%3A%225824%22%7D', 'fp_user_allowed_save_cookie': 'true' },
]

URLS = {
    'ALL Departments': 'https://shop.commissaries.com/shop#!/?limit=96&sort=price&filter=is_on_sale',
}

# CHROME_DRIVER_PATH = '/WINDOWS/SYSTEM32/chromedriver.exe'

def setup_driver():
    opts = Options()
    opts.add_argument("--headless")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    return webdriver.Chrome(options=opts)

def extract_items(driver, url, COOKIES):
    MAX_RETRIES = 3
    items = []
    
    # Determine page count
    page1 = url + '&page=1'
    driver.get(page1)
    for n,v in COOKIES.items():
        driver.add_cookie({'name':n,'value':v})
    driver.refresh()
    for _ in range(MAX_RETRIES):
        try:
            WebDriverWait(driver,10).until(EC.presence_of_element_located((By.CSS_SELECTOR,'.fp-paging-list-container')))
            break
        except TimeoutException:
            driver.get(page1)
    try:
        pages = int(driver.find_element(By.CSS_SELECTOR,'.fp-paging-list-container li:last-child').text)
    except:
        pages = 1
    pages = 28  # preserve override

    for p in range(1, pages+1):
        page_url = url + f'&page={p}'
        driver.get(page_url)
        for n,v in COOKIES.items():
            driver.add_cookie({'name':n,'value':v})
        driver.refresh()

        # Scroll to trigger lazy-load
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
                if src.startswith('data:'):
                    img_url = img.get_attribute('data-src') or ''
                else:
                    img_url = src

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
        
        # New Items section
        if new_items:
            f.write("<h3>*** New Items Since Last Update ***</h3>\n")
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
        
        # All Items section
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

def github_update_index(new_html_content, commit_message="Update Fort Carson deals"):
    # 1. Get the current file SHA
    resp = requests.get(API_URL, headers={
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json"
    })
    resp.raise_for_status()
    file_info = resp.json()
    sha = file_info["sha"]
    
    # 2. Prepare the new content (Base64-encoded)
    b64_content = base64.b64encode(new_html_content.encode("utf-8")).decode("utf-8")
    
    # 3. PUT request to update
    update_payload = {
        "message": commit_message,
        "branch": BRANCH,
        "content": b64_content,
        "sha": sha
    }
    update_resp = requests.put(API_URL, json=update_payload, headers={
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json"
    })
    update_resp.raise_for_status()
    print("index.html updated successfully.")

def main():
    for COOKIES in ALL_COOKIES:
        start = time.time()
        pref = COOKIES['pref']
        if '5825' in pref:
            txt, html, store = "Daily_Commissary_Sales_Fort_Carson.txt", "Daily_Commissary_Sales_Fort_Carson.html", "Fort Carson"
        elif '5824' in pref:
            txt, html, store = "Daily_Commissary_Sales_USAFA.txt", "Daily_Commissary_Sales_USAFA.html", "USAFA"
        elif '5827' in pref:
            txt, html, store = "Daily_Commissary_Sales_PETE.txt", "Daily_Commissary_Sales_PETE.html", "Peterson AFB"
        else:
            txt, html, store = "Daily_Commissary_Sales_Other.txt", "Daily_Commissary_Sales_Other.html", "Other"

        bak = txt + '.bak'
        try:
            shutil.copy(txt, bak)
        except:
            pass

        driver = setup_driver()
        date_str = datetime.now().strftime("%d-%m-%Y")

        with open(txt, 'w', encoding='utf-8') as tf:
            print(date_str, "\nItems discounted by 45% or more:", file=tf)
            try:
                for cat, url in URLS.items():
                    for _ in range(3):
                        try:
                            all_items = extract_items(driver, url, COOKIES)
                            disc_items = find_discounted_items(all_items)
                            print(f"\n{cat}\n", file=tf)
                            print(f"{'Item':<84}{'Orig':^15}{'Sale':^15}{'Disc':^15}\n", file=tf)
                            
                            # Read backup file to check for new items
                            old_content = ""
                            try:
                                with open(bak, 'r', encoding='utf-8') as bf:
                                    old_content = bf.read()
                            except:
                                pass
                            
                            new_items = []
                            for it in disc_items:
                                if it['name'][:84] not in old_content:
                                    new_mark = "***"
                                    new_items.append(it)
                                else:
                                    new_mark = ""
                                
                                print(
                                    f"{it['name'][:84]:<84}"
                                    f"{f'${it['original_price']:.2f}':^15}"
                                    f"{f'${it['sale_price']:.2f}':^15}"
                                    f"{f'{it['discount']:.1f}% {new_mark}':^15}",
                                    file=tf
                                )
                            
                            if not disc_items:
                                print("No items are discounted by more than 45%.", file=tf)
                            
                            # Write HTML with new items separated
                            write_html(html, store, disc_items, new_items, date_str)
                            break
                        except ValueError:
                            continue
                    else:
                        print(f"\n****************** {cat} failed (3x) ****************", file=tf)
            finally:
                driver.quit()

        end_time = time.time()
        elapsed_time = end_time - start
        with open(txt, 'a', encoding='utf-8') as f:
            print(f"\nElapsed Time: {elapsed_time:.0f} seconds", file=f)

#    subprocess.run([powershell_path, "-File", script_path])
	
    try:
	    with open ("Daily_Commissary_Sales_Fort_Carson.html", "r", encoding="utf-8") as f:
	    html_data = f.read()
    github_update_index(html_data, commit_message = "Automated update of Fort Carson deals")
    except FileNotFoundError:
	    print("Fort Carson HTML file not found, skipping GitHub update")
	
if __name__ == '__main__':

    main()
