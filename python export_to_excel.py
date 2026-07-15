import os
import json
import pandas as pd

# ============================================
#  تنظیمات
# ============================================
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
INPUT_JSONL = os.path.join(SCRIPT_DIR, "all_products.jsonl")
OUTPUT_EXCEL = os.path.join(SCRIPT_DIR, "digikala_data.xlsx")


def load_products(path: str) -> list:
    products = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                products.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return products


def build_products_dataframe(products: list) -> pd.DataFrame:
    """یک ردیف برای هر محصول، با مهم‌ترین فیلدهای مفید برای مدل محبوبیت"""
    rows = []

    for item in products:
        info = item.get("product_info") or {}

        # قیمت معمولاً توی یک ساختار تودرتو مثل default_variant.price هست؛
        # هر دو حالت رایج رو امتحان می‌کنیم
        price = None
        default_variant = info.get("default_variant") or {}
        if isinstance(default_variant, dict):
            price_block = default_variant.get("price") or {}
            if isinstance(price_block, dict):
                price = price_block.get("selling_price") or price_block.get("rrp_price")

        rating = info.get("rating") or {}
        rating_avg = rating.get("rate") if isinstance(rating, dict) else None
        rating_count = rating.get("count") if isinstance(rating, dict) else None

        rows.append({
            "product_id": info.get("id"),
            "title_fa": info.get("title_fa"),
            "title_en": info.get("title_en"),
            "brand": (info.get("brand") or {}).get("title_fa") if isinstance(info.get("brand"), dict) else None,
            "category": (info.get("category") or {}).get("title_fa") if isinstance(info.get("category"), dict) else None,
            "price": price,
            "rating_avg": rating_avg,
            "rating_count": rating_count,
            "comments_count": item.get("comments_count", 0),
            "product_url": item.get("product_url"),
        })

    return pd.DataFrame(rows)


def build_comments_dataframe(products: list) -> pd.DataFrame:
    """یک ردیف برای هر کامنت، همراه با عنوان و آدرس محصول مربوطه"""
    rows = []

    for item in products:
        info = item.get("product_info") or {}
        product_title = info.get("title_fa")
        product_url = item.get("product_url")

        for comment in item.get("comments", []):
            if not isinstance(comment, dict):
                continue
            reactions = comment.get("reactions", {}) or {}
            rows.append({
                "product_title": product_title,
                "product_url": product_url,
                "comment_id": comment.get("id"),
                "user_name": comment.get("user_name"),
                "rate": comment.get("rate"),
                "created_at": comment.get("created_at"),
                "likes": reactions.get("likes", 0),
                "dislikes": reactions.get("dislikes", 0),
                "body": comment.get("body"),
            })

    return pd.DataFrame(rows)


def main():
    if not os.path.exists(INPUT_JSONL):
        print(f"فایل '{INPUT_JSONL}' پیدا نشد. اول اسکریپت اصلی اسکرپ رو اجرا کن.")
        return

    products = load_products(INPUT_JSONL)
    print(f"تعداد محصولات بارگذاری‌شده: {len(products)}")

    products_df = build_products_dataframe(products)
    comments_df = build_comments_dataframe(products)

    print(f"تعداد ردیف‌های شیت محصولات: {len(products_df)}")
    print(f"تعداد ردیف‌های شیت کامنت‌ها: {len(comments_df)}")

    with pd.ExcelWriter(OUTPUT_EXCEL, engine="openpyxl") as writer:
        products_df.to_excel(writer, sheet_name="Products", index=False)
        comments_df.to_excel(writer, sheet_name="Comments", index=False)

    print(f"\nفایل اکسل ذخیره شد: {OUTPUT_EXCEL}")


if __name__ == "__main__":
    main()