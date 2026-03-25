import time
from selenium import webdriver
from selenium.webdriver.chrome.options import Options

options = webdriver.ChromeOptions()
options.page_load_strategy = 'eager'
options.add_argument('--headless=new')
options.add_argument('--no-sandbox')
options.add_argument('--disable-dev-shm-usage')

try:
    driver = webdriver.Chrome(options=options)
    driver.set_page_load_timeout(30)
    driver.get('https://albalegis.nopapercloud.com.br/spl/parlamentar.aspx?id=1032112')
    time.sleep(3)
    with open('bio.html', 'w', encoding='utf-8') as f:
        f.write(driver.page_source)
    print("SUCCESS")
except Exception as e:
    print("ERROR:", e)
finally:
    driver.quit()
