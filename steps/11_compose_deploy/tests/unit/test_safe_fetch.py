"""Урок 46: які адреси сервер завантажує, а які — ні. Без DNS і мережі: лише розбір URL та IP."""
import ipaddress

import pytest

from news_hub.safe_fetch import FetchPolicy, UnsafeURL, check_url, is_public_ip


@pytest.mark.parametrize(("address", "public"), [
    ("93.184.215.14", True), ("2606:4700::6810:84e5", True),
    ("127.0.0.1", False), ("127.8.8.8", False), ("::1", False),
    ("10.0.0.5", False), ("172.16.0.1", False), ("192.168.1.1", False),
    ("169.254.169.254", False),                                   # метадані хмари (AWS, GCP, Azure)
    ("100.64.0.1", False),                                        # спільний простір провайдера (CGNAT)
    ("0.0.0.0", False), ("224.0.0.1", False), ("fe80::1", False), ("fd00::1", False),
    ("::ffff:127.0.0.1", False), ("::ffff:169.254.169.254", False),
])
def test_is_public_ip(address: str, public: bool) -> None:
    assert is_public_ip(ipaddress.ip_address(address)) is public


@pytest.mark.parametrize(("url", "reason"), [
    ("file:///etc/passwd", "схема"),
    ("gopher://example.com/", "схема"),
    ("ftp://example.com/feed.xml", "схема"),
    ("//example.com/feed", "схема"),
    ("http:///feed", "хоста"),
    ("http://example.com:22/", "порт 22"),
    ("http://example.com:6379/", "порт 6379"),
    ("https://user:pass@example.com/", "логін"),
    ("http://127.0.0.1/", "loopback"),
    ("http://[::1]/", "loopback"),
    ("http://[::ffff:127.0.0.1]/", "loopback"),
    ("http://169.254.169.254/latest/meta-data/", "link-local"),
    ("http://10.0.0.5/", "приватна"),
    ("http://0.0.0.0/", "0.0.0.0"),
])
def test_unsafe_urls(url: str, reason: str) -> None:
    with pytest.raises(UnsafeURL, match=reason):
        check_url(url)


@pytest.mark.parametrize("url", ["https://www.pravda.com.ua/rss/view_news/", "http://93.184.215.14/feed.xml",
                                 "https://example.com:443/rss"])
def test_allowed_urls(url: str) -> None:
    assert check_url(url).host


def test_policy_is_explicit() -> None:
    """Локальний сервер для тестів — лише з явно розширеною політикою, а не через змінну середовища."""
    local = FetchPolicy(allow_ip=lambda ip: ip.is_loopback, allowed_ports=frozenset({8080}))
    assert check_url("http://127.0.0.1:8080/feed", local).port == 8080
    with pytest.raises(UnsafeURL):
        check_url("http://127.0.0.1:8080/feed")


def test_ipv4_inside_ipv6_is_the_same_address() -> None:
    """::ffff:10.1.2.3 — це 10.1.2.3: власна політика, що забороняє адресу, має забороняти й цей запис."""
    blocked = ipaddress.IPv4Address("10.1.2.3")
    policy = FetchPolicy(allow_ip=lambda ip: ip != blocked)
    for url in ("http://10.1.2.3/", "http://[::ffff:10.1.2.3]/", "http://[::ffff:a01:203]/"):
        with pytest.raises(UnsafeURL, match="адреса 10.1.2.3 "):
            check_url(url, policy)
