import asyncio
import logging
from collections import namedtuple
from typing import Union

import aiofiles
from aiofiles import os as aioos
from bs4 import BeautifulSoup, Tag
from requests import Response

from http_utils import get_decoded_content, get_html_async, normalize_url, validate_link

SCHEME = 'https'
HOST = 'news.ycombinator.com'

Article = namedtuple('Article', ['id', 'link', 'type', 'num'])
DownloadedArticle = namedtuple('DownloadedArticle', ['id', 'content', 'encoding', 'type', 'num', 'article'])


class Crawler:
    def __init__(self, update_cycle: int,
                 destination_dir: str,
                 resources: Union[dict, None] = None,
                 retry_max: int = 5):
        self.update_cycle = update_cycle
        self.destination_dir = destination_dir
        self.resources = resources
        self.retry_max = retry_max
        self.downloads = 0

    async def get_updates(self):
        link = normalize_url('', SCHEME, HOST)
        home = Article(id=-1, link=link, type='home', num=0)
        home_content: DownloadedArticle = await self.get_article(home)
        content_soup = BeautifulSoup(home_content.content, 'html.parser')
        things: list[Tag,] = content_soup.find_all(attrs={'class': 'athing'})

        logging.info(f"Got {len(things)} articles in top.")
        current_top_ids = [thing.get('id') for thing in things]

        queued_resources_not_in_top = [key for key in self.resources.keys() if key not in current_top_ids]
        if queued_resources_not_in_top:
            for key in queued_resources_not_in_top:
                self.resources.pop(key)
            logging.info(f"Cleared {len(queued_resources_not_in_top)} from queue, which are not in top anymore.")

        for thing in things:
            thing_id = thing.get('id')
            if thing_id not in self.resources:
                link = thing.find('span', attrs={'class': 'titleline'}).find('a').get('href')
                link = normalize_url(link, SCHEME, HOST)
                if validate_link(link):
                    article = Article(id=thing_id, link=link, type='article', num=0)
                    self.resources[thing_id] = {article: 0}
                link = normalize_url(f"/item?id={thing_id}", SCHEME, HOST)
                comment = Article(id=thing_id, link=link, type='comment', num=0)
                self.resources[thing_id][comment] = 0

        to_download: list = list()
        for thing_id, articles in self.resources.items():
            for article, retries in articles.items():
                if 0 <= retries <= self.retry_max:
                    to_download.append(article)

        logging.info(f"Got {len(to_download)} articles to download at current cycle.")
        await asyncio.gather(*[self.process_resource(article) for article in to_download], return_exceptions=True)

    async def process_resource(self, article: Article) -> Union[bool, BaseException]:
        da = await self.get_article(article)
        return await self.save_resource(da)

    async def get_article(self, article: Article):
        logging.info(f"Downloading {article.link}...")
        try:
            response: Response = await get_html_async(article.link)
            content, encoding = await get_decoded_content(response)
            d_article = DownloadedArticle(id=article.id,
                                          content=content,
                                          encoding=encoding,
                                          type=article.type,
                                          num=article.num,
                                          article=article)
            if article.type == 'comment':
                content_soup = BeautifulSoup(content, 'html.parser')
                span_tags: list[Tag,] = content_soup.find_all('span', attrs={'class': 'commtext'})
                link_tags: list[Tag,] = list()
                for span_tag in span_tags:
                    link_tags += span_tag.find_all('a')
                links = [link.get('href') for link in link_tags]
                links = list(set(links))
                for num, link in enumerate(links):
                    link = normalize_url(link, SCHEME, HOST)

                    resource = Article(id=article.id, link=link, type='resource', num=num)
                    if resource not in self.resources[article.id]:
                        self.resources[article.id][resource] = 0

        except (TypeError, ValueError) as e:
            d_article = DownloadedArticle(id=article.id,
                                          content=e,
                                          encoding='',
                                          type=article.type,
                                          num=article.num,
                                          article=article)
        return d_article

    async def save_resource(self, da: DownloadedArticle) -> Union[bool, BaseException]:
        await aioos.makedirs(f'{self.destination_dir}/{da.id}', exist_ok=True)
        if not isinstance(da.content, (ValueError, TypeError)):
            filename = f'{self.destination_dir}/{da.id}/{da.type}{da.num}.html'
            async with aiofiles.open(filename, 'w', encoding=da.encoding) as f:
                await f.write(da.content)
                logging.info(f'Saved news: {da.id} - {da.type} - {da.num}')
                self.resources[da.id][da.article] = -1
                self.downloads += 1
                return True
        elif isinstance(da.content, ValueError):
            logging.warning(da.content)
            self.resources[da.id][da.article] += 1
        else:
            if isinstance(da.content, TypeError):
                logging.warning(da.content)
                self.resources[da.id][da.article] = -2
        return False
