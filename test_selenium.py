import sys
from selenium import webdriver
from selenium.webdriver.chrome.options import Options

options = webdriver.ChromeOptions()
options.add_argument('--headless=new')
options.add_argument('--no-sandbox')
options.add_argument('--disable-dev-shm-usage')

try:
    driver = webdriver.Chrome(options=options)
    driver.set_page_load_timeout(30)
    driver.get('https://albalegis.nopapercloud.com.br/spl/parlamentares.aspx')
    print(driver.page_source[:2000])
    with open('nopaper.html', 'w', encoding='utf-8') as f:
        f.write(driver.page_source)
    print("SALVOU nopaper.html")
    driver.quit()
except Exception as e:
    print("ERRO:", e)
