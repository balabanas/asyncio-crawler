import argparse
import asyncio
import logging
import os
from collections import namedtuple
from time import sleep
from typing import Union
from urllib.parse import urlparse, urlunparse
import aiofiles
from aiofiles import os as aioos
import requests
from bs4 import BeautifulSoup, Tag

SCHEME = 'https'
HOST = 'news.ycombinator.com'
HTTP_SUCCESS: range = range(200, 300)
HTTP_REDIRECT: range = range(300, 400)
HTTP_FORBIDDEN: int = 403
HTTP_NOT_FOUND: int = 404

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36',
    'Accept': '*/*',
    'Accept-Language': 'en,lv-LV;q=0.9,lv;q=0.8,ru-RU;q=0.7,ru;q=0.6,en-US;q=0.5',
    'Connection': 'keep-alive'
}

Article = namedtuple('Article', ['id', 'link', 'type', 'num'])
DownloadedArticle = namedtuple('DownloadedArticle', ['id', 'content', 'encoding', 'type', 'num', 'article'])


class Crawler:
    def __init__(self, update_cycle: int, destination_dir: str, resources: Union[dict, None] = None, retry_max: int = 5):
        self.update_cycle = update_cycle
        self.destination_dir = destination_dir
        self.resources = resources
        self.retry_max = retry_max
        self.downloads = 0



def is_good_response(r):
    logging.debug(f"STATUS: {r.status_code}")
    if r.status_code in HTTP_SUCCESS or r.status_code in HTTP_REDIRECT:
        return True
    if r.status_code == HTTP_FORBIDDEN or r.status_code == HTTP_NOT_FOUND:
        raise TypeError(f'Page not found or requires authorization, {r.status_code}, {r.links}')
    return False


def is_good_content_type(r):
    logging.debug(f"CONTENT-TYPE: {r.headers.get('content-type', '')}")
    if 'text/html' in r.headers.get('content-type', ''):
        return True
    return False


def get_html(uri):
    logging.debug(f"Processing URI: {uri}")
    try:
        response = requests.get(uri, timeout=3, headers=HEADERS)
        if is_good_response(response):
            if is_good_content_type(response):
                return response
            else:
                raise TypeError(f'Page content is of other than text/html type: {uri}')
        raise ValueError(f'Page could not be processed right now: {uri}')
    except (ConnectionResetError,
            requests.exceptions.ReadTimeout,
            requests.exceptions.RetryError,
            requests.exceptions.ConnectTimeout,
            requests.exceptions.SSLError,
            ConnectionError,
            requests.exceptions.ConnectionError) as e:
        raise ValueError(e)


def normalize_url(url):
    """Removes # fragments, pastes SCHEME+HOST for internal links"""
    parsed_url = urlparse(url)
    scheme = parsed_url.scheme or SCHEME
    netloc = parsed_url.netloc or HOST
    new_url = urlunparse((scheme, netloc, parsed_url.path,
                          parsed_url.params, parsed_url.query, ''))
    return new_url


async def get_html_async(uri):
    return await asyncio.to_thread(get_html, uri)


async def get_content(response: requests.Response):
    try:
        encoding = response.encoding.lower()
        return response.content.decode(encoding), encoding
    except Exception as e:
        raise TypeError(e)


async def get_article(cr, article: Article):
    logging.info(f"Downloading {article.link}...")
    try:
        response: requests.Response = await get_html_async(article.link)
        content, encoding = await get_content(response)
        d_article = DownloadedArticle(id=article.id, content=content, encoding=encoding, type=article.type, num=article.num,
                                      article=article)
        if article.type == 'comment':
            content_soup = BeautifulSoup(content, 'html.parser')
            span_tags: list[Tag, ] = content_soup.find_all('span', attrs={'class': 'commtext'})
            link_tags: list[Tag, ] = list()
            for span_tag in span_tags:
                link_tags += span_tag.find_all('a')
            links = [link.get('href') for link in link_tags]
            links = list(set(links))
            for num, link in enumerate(links):
                link = normalize_url(link)

                resource = Article(id=article.id, link=link, type='resource', num=num)
                if resource not in cr.resources[article.id]:
                    cr.resources[article.id][resource] = 0

    except (TypeError, ValueError) as e:
        d_article = DownloadedArticle(id=article.id, content=e, encoding='', type=article.type, num=article.num, article=article)
    return d_article


async def process_resource(cr: Crawler, article: Article):
    da = await get_article(cr, article)
    return await save_resource(cr, da)


async def get_updates(cr: Crawler):
    home = Article(id=-1, link=normalize_url(''), type='home', num=0)
    home_content: DownloadedArticle = await get_article(cr, home)
    content_soup = BeautifulSoup(home_content.content, 'html.parser')
    things: list[Tag, ] = content_soup.find_all(attrs={'class': 'athing'})

    logging.info(f"Got {len(things)} articles in top.")
    current_top_ids = [thing.get('id') for thing in things]

    queued_resources_not_in_top = [key for key in cr.resources.keys() if key not in current_top_ids]
    if queued_resources_not_in_top:
        for key in queued_resources_not_in_top:
            cr.resources.pop(key)
        logging.info(f"Cleared {len(queued_resources_not_in_top)} from queue, which are not in top anymore.")

    for thing in things:
        thing_id = thing.get('id')
        if thing_id not in cr.resources:
            link = thing.find('span', attrs={'class': 'titleline'}).find('a').get('href')
            link = normalize_url(link)
            article = Article(id=thing_id, link=link, type='article', num=0)
            cr.resources[thing_id] = {article: 0}
            comment_link = normalize_url(f"/item?id={thing_id}")
            comment = Article(id=thing_id, link=comment_link, type='comment', num=0)
            cr.resources[thing_id][comment] = 0

    to_download: list = list()
    for thing_id, articles in cr.resources.items():
        for article, retries in articles.items():
            if 0 <= retries <= cr.retry_max:
                to_download.append(article)

    logging.info(f"Got {len(to_download)} articles to download at current cycle.")

    d_downloads: list[DownloadedArticle, ] = await asyncio.gather(*[process_resource(cr, article) for article in to_download], return_exceptions=True)


async def save_resource(cr: Crawler, da: DownloadedArticle):
    await aioos.makedirs(f'{cr.destination_dir}/{da.id}', exist_ok=True)
    if not isinstance(da.content, ValueError) and not isinstance(da.content, TypeError):
        filename = f'{cr.destination_dir}/{da.id}/{da.type}{da.num}.html'
        async with aiofiles.open(filename, 'w', encoding=da.encoding) as f:
            await f.write(da.content)
            logging.info(f'Saved news: {da.id} - {da.type} - {da.num}')
            cr.resources[da.id][da.article] = -1
            cr.downloads += 1
            return True
    elif isinstance(da.content, ValueError):
        logging.warning(da.content)
        cr.resources[da.id][da.article] += 1
    else:
        if isinstance(da.content, TypeError):
            logging.warning(da.content)
            cr.resources[da.id][da.article] = -2
    return False


def main(cr: Crawler):
    while True:
        logging.info('Checking updates...')
        try:
            asyncio.run(get_updates(cr))

        except ValueError as e:
            logging.error(e)
        total = 0
        completed_successfully = 0
        cancelled = 0
        to_go = 0
        for resources in cr.resources.values():
            total += sum(1 for _ in resources.values())
            to_go += sum(1 for retries in resources.values() if 0 <= retries <= cr.retry_max)

        logging.info(f"Resources, associated with current top: {total}")
        logging.info(f"Scheduled for download: {to_go}")
        logging.info(f"Total files saved: {cr.downloads}")

        sleep(cr.update_cycle)


if __name__ == "__main__":
    os.chdir('/projects/basutils')
    parser = argparse.ArgumentParser(description="Get crawler parameters")
    parser.add_argument("--update_cycle", const=360, default=360, nargs='?', type=int,
                        help="Content check and update periodicity, seconds")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    crawler = Crawler(update_cycle=args.update_cycle, destination_dir='downloads', resources=dict())
    main(crawler)
