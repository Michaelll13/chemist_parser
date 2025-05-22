import re
import time
from typing import List, Dict
from selenium import webdriver
from selenium_stealth import stealth
from bs4 import BeautifulSoup
import asyncio
from concurrent.futures import ThreadPoolExecutor
from fastapi import FastAPI, Query
from fastapi.responses import JSONResponse
import uvicorn

app = FastAPI()
executor = ThreadPoolExecutor()

def init_driver():
    options = webdriver.ChromeOptions()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    driver = webdriver.Chrome(options=options)

    stealth(driver,
            languages=["ru-RU", "ru"],
            vendor="Google Inc.",
            platform="Win32",
            webgl_vendor="Intel Inc.",
            renderer="Intel Iris OpenGL Engine",
            fix_hairline=True,
            )

    return driver


def scroll_down(driver, scrolls: int = 15):
    for _ in range(scrolls):
        driver.execute_script("window.scrollBy(0, 800)")
        time.sleep(0.3)


def parse_search_page(driver, query: str) -> List[Dict]:
    results = []
    query_lower = query.lower()
    page = 1

    while True:
        url = f"https://zdravcity.ru/search/?what={query}" if page == 1 else f"https://zdravcity.ru/search/?what={query}&PAGEN_1={page}"
        print(f"🌐 Открываю: {url}")
        driver.get(url)
        scroll_down(driver)

        soup = BeautifulSoup(driver.page_source, "html.parser")
        cards = soup.find_all("div", class_="Horizontal_horizontal-wrapper__Df2dg")
        if not cards:
            print("🔚 Карточки не найдены — конец пагинации.")
            break

        for card in cards:
            try:
                name_tag = card.find("a", class_="Horizontal_horizontal-title__XBc6D")
                name = name_tag.get_text(strip=True)
                if query_lower not in name.lower():
                    continue

                link = "https://zdravcity.ru" + name_tag["href"]
                img_tag = card.find("img")
                image = img_tag["src"] if img_tag else None
                price_tag = card.find("div", class_="Price_price__Y1FnU")
                if price_tag:
                    raw_price = price_tag.get_text(strip=True)
                    price_match = re.search(r"(\d[\d\s]*)",
                                            raw_price.replace("\xa0", " "))  # поддержка "660 ₽", "1 000 ₽"
                    price = price_match.group(1).replace(" ", "") if price_match else "Цена не указана"
                else:
                    price = "Цена не указана"

                category = "Категория не указана"
                info_blocks = card.find_all("div", class_="HorizontalInfoList_list-item__jITg2")
                for block in info_blocks:
                    label = block.find("span", class_="HorizontalInfoList_list-item-label__aV5qZ")
                    value = block.find("span", class_="HorizontalInfoList_list-item-value__Dq5rF")
                    if label and value and "категория" in label.text.lower():
                        category = value.text.strip()
                        break

                results.append({
                    "name": name,
                    "link": link,
                    "price": price,
                    "category": category,
                    "image": image
                })
            except Exception as e:
                print("⚠️ Ошибка при разборе карточки:", e)
                continue

        if not results:
            print("🚫 Нет релевантных товаров — стоп.")
            break
        page += 1

    return results


def search_products_single(query: str) -> Dict:
    print("🔥 START search for:", query)
    driver = init_driver()
    try:
        items = parse_search_page(driver, query)
        print("✅ PARSED", len(items), "items")

        # Очистка
        driver.delete_all_cookies()
        driver.execute_script("window.open('about:blank', '_blank');")
        driver.close()
        driver.switch_to.window(driver.window_handles[0])
    except Exception as e:
        print("❌ Ошибка:", e)
        raise
    finally:
        driver.quit()
    return {"query": query, "results": items}


async def async_search(query: str):
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(executor, search_products_single, query)


# API route
@app.get("/search")
async def search_api(query: str = Query(..., description="Поисковый запрос")):
    try:
        result = await async_search(query)
        return JSONResponse(content=result)
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


# Запуск вручную
if __name__ == "__main__":
    uvicorn.run("main5:app", host="0.0.0.0", port=8000, reload=False)
