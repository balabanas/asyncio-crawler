# asyncio-crawler
Fast link download with asyncio &amp; aiofiles

## Task
Develop asynchronous crawler for a news site news.ycombinator.com.

* Start crawling from site's root, reading top news, i.e. first 30 ones
* For each news: download main article, page with comments to the article, and every page mentioned by links within comments
* Each article, comments, and pages mentioned in comments should reside in a separate folder on the disk
* Cycle of crawling should start each X seconds (pass by a parameter to the script)

## Decisions made
* We rely completely on the web-site's markup (with help of `beautifulsoup`): 
  * Use news `id`
  * Use class names and tags which contain links relevant to that id
  * Use specific classes in the comment's body to find links relevant to user's comments only, and filter out general navigation.
* We limit ourselves with html files only for download: checking content-type header for `text/html`, and additionaly filter out links ending with known file extensions
* We don't aim to download surely all pages available for the current cycle: 
  * say, on the first pass we download only main page and comments, and while parsing comment page, add the links found to the sort of a queue (see `self.resources` attribute of a Crawler class)
  * on the second pass we will try to download all links currently in the queue, and, may be, add more
  * as with massive parallel requests target server tend to return `503`, `403` or similar errors, we do up to `n` attempts of downloading, before marking resource in a queue as unavailable (code `-2`)
* Successfully downloaded resources are marked with `-1` code and are not downloaded again on the future passes.
  * This has an implication that if a comment page for a news will be updated and the new links appear, they will not be downloaded
* At the beginning of each cycle we check if all resources in the queue are belong to the current top of news. If not, we delete such resources from the queue irrespectively of it's status. This way we guarantee that this `self.resources` object will not became too big eventually.
* We use `aiofiles` library for storing files (however, as files are generally small it seems not having much of an effect)
* We don't use `aiohttp` for non-blocking requests. However, we very well might use it! Instead we put the normal `requests` request into thread (`asyncio.to_thread`).

## Tests
No tests ¯\_(ツ)_/¯

## Run
``
python main.py --update_cycle=10
``
, where 10 is number of seconds between updates.

The folder `downloads` will be automatically created in the folder with `main.py`. There you'll find folders with the downloaded news. The name of each folder is the news' `id`.


## TODOs
1) https://github.com/balabanas/asyncio-crawler/blob/main/http_utils.py#L31 - too broad Exception
2) https://github.com/balabanas/asyncio-crawler/blob/main/http_utils.py#L25 - typing package for annotation tuple
3) Typing to all functions, not to some
