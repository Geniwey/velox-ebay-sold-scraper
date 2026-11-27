import asyncio
import random
import re
from urllib.parse import urlencode
from bs4 import BeautifulSoup
from curl_cffi.requests import AsyncSession
from apify import Actor

DOMAINS = {
    'US': ('www.ebay.com', 'USD'),
    'UK': ('www.ebay.co.uk', 'GBP'),
    'DE': ('www.ebay.de', 'EUR'),
    'ES': ('www.ebay.es', 'EUR'),
    'FR': ('www.ebay.fr', 'EUR'),
    'IT': ('www.ebay.it', 'EUR'),
    'AU': ('www.ebay.com.au', 'AUD'),
    'CA': ('www.ebay.ca', 'CAD'),
}

IMPERSONATIONS = ['chrome124', 'chrome120', 'safari17_0', 'edge101']


def parse_money(raw_text: str) -> float | None:
    if not raw_text:
        return None
    first_part = re.split(r'\b(?:to|a|bis|à)\b', raw_text, flags=re.IGNORECASE)[0]
    cleaned = re.sub(r'[^\d.,]', '', first_part).strip()
    if not cleaned:
        return None

    if ',' in cleaned and '.' in cleaned:
        if cleaned.rfind(',') > cleaned.rfind('.'):
            cleaned = cleaned.replace('.', '').replace(',', '.')
        else:
            cleaned = cleaned.replace(',', '')
    elif ',' in cleaned:
        parts = cleaned.split(',')
        if len(parts[-1]) == 2:
            cleaned = cleaned.replace(',', '.')
        else:
            cleaned = cleaned.replace(',', '')

    try:
        return round(float(cleaned), 2)
    except ValueError:
        return None


def extract_item_id(url: str) -> str | None:
    match = re.search(r'/itm/(?:[^/]+/)?(\d+)', url)
    return match.group(1) if match else None


async def fetch_with_retry(search_url: str, proxy_config, domain: str, max_retries: int = 4) -> str | None:
    for attempt in range(1, max_retries + 1):
        impersonate = random.choice(IMPERSONATIONS)
        proxy_url = await proxy_config.new_url() if proxy_config else None
        proxies = {'http': proxy_url, 'https': proxy_url} if proxy_url else None

        try:
            async with AsyncSession(impersonate=impersonate) as session:
                response = await session.get(
                    search_url,
                    proxies=proxies,
                    timeout=30,
                    headers={
                        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
                        'Accept-Language': 'en-US,en;q=0.9',
                        'Referer': f'https://{domain}/',
                        'Upgrade-Insecure-Requests': '1',
                    },
                )
                if response.status_code == 200 and 's-item' in response.text:
                    return response.text
                Actor.log.warning(f'Attempt {attempt}/{max_retries}: HTTP {response.status_code} (or challenge page). Rotating proxy...')
        except Exception as exc:
            Actor.log.warning(f'Attempt {attempt}/{max_retries} error: {exc}')

        await asyncio.sleep(random.uniform(1.0, 2.5))
    return None


async def main() -> None:
    async with Actor:
        actor_input = await Actor.get_input() or {}
        query = (actor_input.get('query') or '').strip()
        if not query:
            Actor.log.error('Missing required input field: query')
            return

        country = actor_input.get('country', 'US').upper()
        domain, default_currency = DOMAINS.get(country, ('www.ebay.com', 'USD'))
        sold_only = actor_input.get('soldOnly', True)
        condition = actor_input.get('condition', 'ALL')
        max_items = int(actor_input.get('maxItems', 60))

        proxy_input = actor_input.get('proxyConfiguration') or {
            'useApifyProxy': True,
            'apifyProxyGroups': ['RESIDENTIAL'],
        }
        proxy_config = await Actor.create_proxy_configuration(actor_proxy_input=proxy_input)

        collected = 0
        page = 1
        seen_ids = set()

        while collected < max_items:
            params = {
                '_nkw': query,
                '_sacat': '0',
                '_pgn': str(page),
                '_ipg': '60',
                'rt': 'nc',
            }
            if sold_only:
                params['LH_Sold'] = '1'
                params['LH_Complete'] = '1'
            if condition != 'ALL':
                params['LH_ItemCondition'] = condition

            search_url = f'https://{domain}/sch/i.html?{urlencode(params)}'
            Actor.log.info(f'Fetching page {page} on {domain} for "{query}"...')

            html = await fetch_with_retry(search_url, proxy_config, domain)
            if not html:
                Actor.log.error(f'Failed to retrieve page {page} after retries. Stopping.')
                break

            soup = BeautifulSoup(html, 'lxml')
            results_container = soup.select_one('ul.srp-results')
            if results_container:
                nodes = results_container.find_all('li', recursive=False)
            else:
                nodes = soup.select('li.s-item')

            if not nodes:
                Actor.log.info('No more result cards found.')
                break

            page_added = 0
            hit_rewrite_divider = False

            for node in nodes:
                classes = node.get('class') or []
                if 'srp-river-answer--REWRITE_START' in classes:
                    hit_rewrite_divider = True
                    break
                if 's-item' not in classes:
                    continue
                if collected >= max_items:
                    break

                link_el = node.select_one('a.s-item__link')
                title_el = node.select_one('.s-item__title')
                if not link_el or not title_el:
                    continue

                raw_url = link_el.get('href', '').split('?')[0]
                item_id = extract_item_id(raw_url)
                if not item_id or item_id in seen_ids:
                    continue

                for badge in title_el.select('.LIGHT_HIGHLIGHT'):
                    badge.decompose()
                title = title_el.get_text(' ', strip=True)
                if not title or title.lower().startswith('shop on ebay'):
                    continue

                price_el = node.select_one('.s-item__price')
                raw_price = price_el.get_text(' ', strip=True) if price_el else ''
                price = parse_money(raw_price)
                if price is None:
                    continue

                ship_el = node.select_one('.s-item__shipping, .s-item__logisticsCost')
                raw_ship = ship_el.get_text(' ', strip=True) if ship_el else ''
                shipping_cost = parse_money(raw_ship) or 0.0
                total_price = round(price + shipping_cost, 2)

                sold_el = node.select_one('.s-item__title--tag .POSITIVE, .s-item__caption--signal .POSITIVE')
                sold_date = sold_el.get_text(' ', strip=True) if sold_el else None

                cond_el = node.select_one('.SECONDARY_INFO')
                item_condition = cond_el.get_text(' ', strip=True) if cond_el else None

                seller_el = node.select_one('.s-item__seller-info-text')
                seller_info = seller_el.get_text(' ', strip=True) if seller_el else None

                loc_el = node.select_one('.s-item__location')
                location = loc_el.get_text(' ', strip=True) if loc_el else None

                img_el = node.select_one('.s-item__image-wrapper img')
                image_url = (img_el.get('src') or img_el.get('data-src')) if img_el else None

                seen_ids.add(item_id)
                record = {
                    'itemId': item_id,
                    'title': title,
                    'price': price,
                    'shippingCost': shipping_cost,
                    'totalPrice': total_price,
                    'currency': default_currency,
                    'isSold': bool(sold_only or sold_date),
                    'soldDate': sold_date,
                    'condition': item_condition,
                    'sellerInfo': seller_info,
                    'location': location,
                    'country': country,
                    'url': raw_url,
                    'imageUrl': image_url,
                }

                await Actor.push_data(record)
                try:
                    await Actor.charge(event_name='result-scraped', count=1)
                except Exception:
                    pass

                collected += 1
                page_added += 1

            if page_added == 0 or hit_rewrite_divider:
                break

            page += 1

        Actor.log.info(f'Finished. Extracted {collected} listings.')
