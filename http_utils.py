import asyncio
import logging
from urllib.parse import urlparse, urlunparse

import requests

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


def validate_link(link: str) -> bool:
    if all(lambda ext: not link.endswith(ext) for ext in ['.pdf', '.txt', '.png', '.jpg']):
        return True
    return False


async def get_decoded_content(response: requests.Response) -> (str, str):
    """Attempts to decode response object with encoding
    from encoding attributes, and return it in tuple with encoding itself if succeed"""
    try:
        encoding = response.encoding.lower()
        return response.content.decode(encoding), encoding
    except Exception as e:
        raise TypeError(e)


def validate_response_status(r):
    logging.debug(f"STATUS: {r.status_code}")
    if r.status_code in HTTP_SUCCESS or r.status_code in HTTP_REDIRECT:
        return True
    if r.status_code == HTTP_FORBIDDEN or r.status_code == HTTP_NOT_FOUND:
        raise TypeError(f'Page not found or requires authorization, {r.status_code}, {r.links}')
    return False


def validate_response_content_type(r):
    logging.debug(f"CONTENT-TYPE: {r.headers.get('content-type', '')}")
    if 'text/html' in r.headers.get('content-type', ''):
        return True
    return False


def get_html(uri):
    logging.debug(f"Processing URI: {uri}")
    try:
        response = requests.get(uri, timeout=3, headers=HEADERS)
        if validate_response_status(response):
            if validate_response_content_type(response):
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


async def get_html_async(uri):
    return await asyncio.to_thread(get_html, uri)


def normalize_url(url: str, scheme: str, host: str) -> str:
    """Removes # fragments, pastes SCHEME+HOST for internal links"""
    parsed_url = urlparse(url)
    scheme = parsed_url.scheme or scheme
    netloc = parsed_url.netloc or host
    new_url = urlunparse((scheme, netloc, parsed_url.path,
                          parsed_url.params, parsed_url.query, ''))
    return new_url
