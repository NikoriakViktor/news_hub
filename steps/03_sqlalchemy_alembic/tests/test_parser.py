from news_hub.parser import parse_rbc_news

# HTML — з ноутбука про web scraping («демо на прикладі»)
SAMPLE_HTML = """
<html><body>
  <div class="newsline">
    <div class="newsline__item">
      <a class="newsline__item-title" href="/ukr/news/2024/1234/">
        Уряд затвердив новий бюджет на 2024 рік
      </a>
      <span class="newsline__item-category">Економіка</span>
      <time class="newsline__item-date" datetime="2024-05-08T10:30:00">
        08 травня 2024, 10:30
      </time>
    </div>
    <div class="newsline__item">
      <a class="newsline__item-title" href="/ukr/news/2024/5678/">
        Збірна України перемогла у фіналі
      </a>
      <span class="newsline__item-category">Спорт</span>
      <time class="newsline__item-date" datetime="2024-05-08T09:15:00">
        08 травня 2024, 09:15
      </time>
    </div>
  </div>
</body></html>
"""


def test_containers_strategy():
    news = parse_rbc_news(SAMPLE_HTML)
    assert [n["title"] for n in news] == ["Уряд затвердив новий бюджет на 2024 рік", "Збірна України перемогла у фіналі"]
    assert news[0] == {"title": "Уряд затвердив новий бюджет на 2024 рік", "url": "https://www.rbc.ua/ukr/news/2024/1234/",
                       "category": "Економіка", "description": "", "datetime": "2024-05-08T10:30:00"}


def test_links_strategy_splits_time():
    html = '<a href="/rus/news/putina-1778325455.html">14:19 У Путіна заявили про мирну угоду</a>'
    assert parse_rbc_news(html) == [{"title": "У Путіна заявили про мирну угоду",
                                     "url": "https://www.rbc.ua/rus/news/putina-1778325455.html",
                                     "category": "", "description": "", "datetime": "14:19"}]
