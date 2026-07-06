"""
Google Haberler RSS üzerinden bir hisseyle ilgili güncel haber başlıklarını
çeker. Google'ın kendi RSS telif metni bu kullanımı (kişisel, ticari olmayan)
açıkça izin veriyor — bu, google.com/search sonuçlarını kazımaktan (scraping)
farklıdır, RSS yayıncı tarafından otomatik tüketim için sunulur.

ÖNEMLİ: Bu modül başlıklardan bir "güven yüzdesi" ÜRETMEZ. Ham başlık,
kaynak, tarih ve link döner — değerlendirmeyi kullanıcıya bırakır. Twitter/X
ve TradingView entegrasyonu YOKTUR (resmi ücretli API / telif kısıtlaması).
"""

from urllib.parse import quote

import feedparser

RSS_BASE = "https://news.google.com/rss/search"

# Başlıklarda aranan, potansiyel olarak fiyatı etkileyebilecek gelişme
# türlerini yakalayan basit anahtar kelime eşleştirmesi. Bu bir "duygu
# analizi" veya güven skoru DEĞİLDİR — sadece hangi haberlerin rutin piyasa
# yorumundan çok, somut bir kurumsal gelişme olabileceğini işaretler.
CRITICAL_KEYWORDS = {
    "Sermaye Artırımı": ["sermaye artır", "bedelli", "bedelsiz"],
    "Temettü": ["temettü"],
    "Birleşme/Devralma": ["birleşme", "devralma", "satın alma"],
    "Yeni Sözleşme/İhale": ["ihale", "sözleşme imza", "sözleşmeye davet", "sözleşme kazan"],
    "Yönetim Değişikliği": ["istifa", "genel müdür", "yönetim kurulu üyeliğine", "atandı"],
    "Hukuki/Düzenleyici Gelişme": ["dava", "soruşturma", "gözaltı", "spk", "iflas", "konkordato", "ceza kesti"],
    "Halka Arz": ["halka arz"],
    "Geri Alım Programı": ["geri alım"],
    "Büyük Ortak Hareketi": ["payını", "hisse alım", "hisse satış", "pay alım", "pay satış"],
}


def categorize_article(title: str) -> list:
    lowered = title.lower()
    return [category for category, keywords in CRITICAL_KEYWORDS.items() if any(kw in lowered for kw in keywords)]


def extract_critical_notes(articles: list) -> list:
    critical = []
    for article in articles:
        categories = categorize_article(article["title"])
        if categories:
            critical.append({**article, "categories": categories})
    return critical


def fetch_news(query: str, days: int = 7, max_items: int = 10) -> list:
    url = f"{RSS_BASE}?q={quote(query)}+when:{days}d&hl=tr&gl=TR&ceid=TR:tr"
    feed = feedparser.parse(url)

    articles = []
    for entry in feed.entries[:max_items]:
        source = entry.get("source", {}).get("title") if entry.get("source") else None
        title = entry.get("title", "")
        if source and title.endswith(f" - {source}"):
            title = title[: -len(f" - {source}")]
        articles.append(
            {
                "title": title,
                "source": source,
                "pub_date": entry.get("published", ""),
                "link": entry.get("link", ""),
            }
        )
    return articles


def get_news_for_symbol(base_symbol: str) -> dict:
    query = f"{base_symbol} hisse"
    articles = fetch_news(query)
    critical_notes = extract_critical_notes(articles)
    return {
        "query": query,
        "critical_notes": critical_notes,
        "articles": articles,
        "note": (
            "Bu başlıklar Google Haberler RSS'inden alınmıştır (kişisel/ticari "
            "olmayan kullanım). Bir güven yüzdesine dönüştürülmemiştir — "
            "başlıkları kendin okuyup değerlendir. 'Kritik Gelişmeler' basit "
            "anahtar kelime eşleştirmesidir (duygu analizi değildir). "
            "Twitter/X ve TradingView kullanıcı yorumları içermez (resmi "
            "ücretli API / telif kısıtlaması)."
        ),
    }
