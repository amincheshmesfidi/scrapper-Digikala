import os
import re
import json
import time
import random
from playwright.sync_api import sync_playwright

# ============================================
#  تنظیمات
# ============================================
# لینک صفحه دسته‌بندی رو اینجا بذار (مثلاً از منوی دیجی‌کالا وارد "کالای دیجیتال" شو و آدرس بار رو کپی کن)
# لیست همه دسته‌بندی‌هایی که می‌خوایم پیمایش کنیم
CATEGORY_URLS = [
    "https://www.digikala.com/search/category-wearable-gadget/",
    "https://www.digikala.com/search/category-laptop/",
    "https://www.digikala.com/search/category-game-console/",
    "https://www.digikala.com/search/category-tablet-ebook-reader/",
]

MAX_CATEGORY_PAGES_PER_CATEGORY = 30   # حداکثر تعداد صفحه‌ای که از هر دسته‌بندی پیمایش می‌شه
MAX_PRODUCTS = 500                     # سقف کلی محصولات (جمع همه دسته‌بندی‌ها با هم)
DELAY_BETWEEN_PRODUCTS = (2, 4)   # تأخیر تصادفی (ثانیه) بین هر محصول، برای جلوگیری از بلاک شدن

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PRODUCT_URLS_FILE = os.path.join(SCRIPT_DIR, "product_urls.txt")
OUTPUT_JSONL = os.path.join(SCRIPT_DIR, "all_products.jsonl")   # هر خط = یک محصول کامل (با کامنت‌هاش)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


# ============================================
#  توابع کمکی جستجوی بازگشتی در JSON
# ============================================
def find_product_dict(data):
    """
    دنبال دیکشنری‌ای می‌گرده که خودش شامل 'title_fa' باشه (یعنی خودِ آبجکت محصول).
    کل این دیکشنری رو برمی‌گردونه (نه فقط اسم) چون شامل قیمت، امتیاز، دسته‌بندی و... هم هست.
    """
    if isinstance(data, dict):
        if "title_fa" in data and isinstance(data.get("title_fa"), str):
            return data
        for value in data.values():
            result = find_product_dict(value)
            if result:
                return result
    elif isinstance(data, list):
        for item in data:
            result = find_product_dict(item)
            if result:
                return result
    return None


def find_comments_list(data):
    found_lists = []

    def _search(node):
        if isinstance(node, dict):
            for key, value in node.items():
                if key == "comments" and isinstance(value, list) and value:
                    found_lists.append(value)
                else:
                    _search(value)
        elif isinstance(node, list):
            for item in node:
                _search(item)

    _search(data)
    if found_lists:
        return max(found_lists, key=len)
    return []


# ============================================
#  مرحله ۱: کشف لینک محصولات از صفحه دسته‌بندی
# ============================================
def discover_product_urls(page) -> dict:
    """
    همه دسته‌بندی‌های داخل CATEGORY_URLS رو پیمایش می‌کنه.
    خروجی: دیکشنری {product_url: category_url} — بدون هیچ لینک تکراری.
    """
    # لینک‌های قبلی رو (همراه با دسته‌بندی‌شون) به‌عنوان پایه بارگذاری می‌کنیم
    url_to_category = {}
    if os.path.exists(PRODUCT_URLS_FILE):
        with open(PRODUCT_URLS_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                parts = line.split("\t")
                if len(parts) == 2:
                    url_to_category[parts[0]] = parts[1]
                else:
                    url_to_category[parts[0]] = ""
        print(f"{len(url_to_category)} لینک از اجراهای قبلی بارگذاری شد (به‌عنوان پایه، بدون تکرار).")

    def save_progress():
        with open(PRODUCT_URLS_FILE, "w", encoding="utf-8") as f:
            for u, cat in sorted(url_to_category.items()):
                f.write(f"{u}\t{cat}\n")

    for category_url in CATEGORY_URLS:
        if len(url_to_category) >= MAX_PRODUCTS:
            print(f"به سقف کلی {MAX_PRODUCTS} لینک رسیدیم، رفتن به دسته بعدی لازم نیست.")
            break

        print("\n" + "=" * 60)
        print(f"دسته‌بندی: {category_url}")
        print("=" * 60)

        for page_num in range(1, MAX_CATEGORY_PAGES_PER_CATEGORY + 1):
            url = f"{category_url.rstrip('/')}/?page={page_num}"
            print(f"  در حال باز کردن صفحه {page_num}: {url}")

            try:
                page.goto(url, wait_until="networkidle", timeout=45000)
            except Exception as e:
                print(f"    خطا در باز کردن صفحه: {e}")
                continue

            for _ in range(4):
                page.mouse.wheel(0, 2500)
                page.wait_for_timeout(800)

            links = page.eval_on_selector_all(
                "a[href*='/product/dkp-']",
                "elements => elements.map(e => e.href)"
            )

            before_count = len(url_to_category)
            for link in links:
                if link not in url_to_category:
                    url_to_category[link] = category_url
            new_count = len(url_to_category) - before_count
            print(f"    {new_count} لینک جدید (غیرتکراری) اضافه شد (مجموع کلی تا الان: {len(url_to_category)})")

            save_progress()  # ذخیره فوری بعد از هر صفحه

            if new_count == 0:
                print("    لینک جدیدی پیدا نشد، به آخر این دسته‌بندی رسیدیم.")
                break

            if len(url_to_category) >= MAX_PRODUCTS:
                print(f"    به سقف کلی {MAX_PRODUCTS} لینک رسیدیم.")
                break

    return dict(list(url_to_category.items())[:MAX_PRODUCTS])


# ============================================
#  مرحله ۲: اسکرپ کامل یک محصول (اطلاعات + کامنت‌ها)
# ============================================
def scrape_single_product(page, product_url: str, category_url: str = "") -> dict:
    captured_responses = []

    def handle_response(response):
        try:
            content_type = response.headers.get("content-type", "")
            if "application/json" not in content_type:
                return
            body = response.json()
            captured_responses.append(body)
        except Exception:
            pass

    page.on("response", handle_response)

    try:
        page.goto(product_url, wait_until="networkidle", timeout=45000)

        def comments_found_so_far() -> bool:
            return any(find_comments_list(body) for body in captured_responses)

        def scroll_to_bottom(max_scrolls=25, wheel_amount=2500, wheel_wait=1000, stable_needed=3):
            previous_height = 0
            stable_count = 0
            for _ in range(max_scrolls):
                page.mouse.wheel(0, wheel_amount)
                page.wait_for_timeout(wheel_wait)
                current_height = page.evaluate("document.body.scrollHeight")
                if current_height == previous_height:
                    stable_count += 1
                    if stable_count >= stable_needed:
                        break
                else:
                    stable_count = 0
                previous_height = current_height

        # تلاش ۱: اسکرول تطبیقی معمولی تا ته صفحه
        scroll_to_bottom()
        page.wait_for_timeout(2000)

        # تلاش ۲: اگه هنوز کامنتی نگرفتیم، دنبال لینک/دکمه/تب مربوط به نظرات بگرد و کلیک کن
        if not comments_found_so_far():
            review_selectors = [
                "a[href*='#reviews']",
                "a[href*='comment']",
                "text=دیدگاه",
                "text=نظرات کاربران",
                "text=مشاهده نظرات",
                "text=مشاهده همه نظرات",
                "text=مشاهده دیدگاه",
                "text=ثبت دیدگاه",
            ]
            for selector in review_selectors:
                try:
                    locator = page.locator(selector).first
                    if locator.is_visible(timeout=1000):
                        locator.scroll_into_view_if_needed(timeout=2000)
                        page.wait_for_timeout(500)
                        locator.click(timeout=2000)
                        page.wait_for_timeout(2500)
                        try:
                            page.wait_for_load_state("networkidle", timeout=8000)
                        except Exception:
                            pass
                        if comments_found_so_far():
                            break
                except Exception:
                    continue

        # تلاش ۳: اگه بازم چیزی نگرفتیم، یه دور دیگه اسکرول کامل‌تر با صبر بیشتر
        if not comments_found_so_far():
            scroll_to_bottom(max_scrolls=35, wheel_amount=1800, wheel_wait=1200, stable_needed=4)
            page.wait_for_timeout(3000)
            try:
                page.wait_for_load_state("networkidle", timeout=10000)
            except Exception:
                pass

        # مکث نهایی، چون بعضی درخواست‌های کامنت با کمی تأخیر فایر می‌شن
        page.wait_for_timeout(2000)
    finally:
        page.remove_listener("response", handle_response)

    product_dict = None
    all_comments = []

    for body in captured_responses:
        if not product_dict:
            found = find_product_dict(body)
            if found:
                product_dict = found
        comments = find_comments_list(body)
        if comments:
            all_comments.extend(comments)

    # حذف کامنت‌های تکراری بر اساس id
    unique_comments = {}
    for c in all_comments:
        if isinstance(c, dict) and c.get("id"):
            unique_comments[c["id"]] = c
    final_comments = list(unique_comments.values()) if unique_comments else all_comments

    return {
        "product_url": product_url,
        "category_source": category_url,
        "product_info": product_dict,
        "comments_count": len(final_comments),
        "comments": final_comments,
    }


# ============================================
#  اجرای اصلی
# ============================================
def load_already_scraped_urls() -> set:
    """اگه قبلاً اجرا کرده باشیم، محصولاتی که کامل شدن رو نمی‌گیریم دوباره (قابلیت resume)"""
    scraped = set()
    if os.path.exists(OUTPUT_JSONL):
        with open(OUTPUT_JSONL, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    item = json.loads(line)
                    scraped.add(item.get("product_url"))
                except json.JSONDecodeError:
                    continue
    return scraped


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        context = browser.new_context(user_agent=USER_AGENT, locale="fa-IR")
        page = context.new_page()

        # ---------- مرحله ۱: کشف لینک‌ها از همه دسته‌بندی‌ها (ادغام با لینک‌های قبلی، بدون تکرار) ----------
        print("=" * 60)
        print("مرحله ۱: کشف لینک محصولات از همه دسته‌بندی‌ها")
        print("=" * 60)
        url_to_category = discover_product_urls(page)
        print(f"\n{len(url_to_category)} لینک محصول (مجموع همه دسته‌بندی‌ها) در '{PRODUCT_URLS_FILE}' ذخیره شد.\n")

        # ---------- مرحله ۲: اسکرپ هر محصول ----------
        print("=" * 60)
        print("مرحله ۲: اسکرپ اطلاعات و کامنت‌های هر محصول")
        print("=" * 60)

        already_scraped = load_already_scraped_urls()
        if already_scraped:
            print(f"{len(already_scraped)} محصول قبلاً اسکرپ شده، رد می‌شن.\n")

        remaining = {u: cat for u, cat in url_to_category.items() if u not in already_scraped}

        with open(OUTPUT_JSONL, "a", encoding="utf-8") as out_f:
            for index, (product_url, category_url) in enumerate(remaining.items(), start=1):
                print(f"[{index}/{len(remaining)}] در حال اسکرپ: {product_url}")
                try:
                    result = scrape_single_product(page, product_url, category_url)
                    title = (result.get("product_info") or {}).get("title_fa", "نامشخص")
                    print(f"  محصول: {title}  |  کامنت‌ها: {result['comments_count']}")

                    out_f.write(json.dumps(result, ensure_ascii=False) + "\n")
                    out_f.flush()  # ذخیره فوری، حتی اگه اسکریپت وسط راه قطع بشه داده از دست نمی‌ره

                except Exception as e:
                    print(f"  خطا در اسکرپ این محصول: {e}")

                time.sleep(random.uniform(*DELAY_BETWEEN_PRODUCTS))

        browser.close()

    print(f"\nتمام شد. نتایج در '{OUTPUT_JSONL}' ذخیره شدن (هر خط = یک محصول).")


if __name__ == "__main__":
    main()
