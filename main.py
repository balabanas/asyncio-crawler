import argparse
import asyncio
import logging
from time import sleep

from crawler import Crawler


def main(cr: Crawler):
    while True:
        logging.info('Checking updates...')
        try:
            asyncio.run(cr.get_updates())

        except ValueError as e:
            logging.error(e)
        total = 0
        to_go = 0
        for resources in cr.resources.values():
            total += sum(1 for _ in resources.values())
            to_go += sum(1 for retries in resources.values() if 0 <= retries <= cr.retry_max)

        logging.info(f"Resources, associated with current top: {total}")
        logging.info(f"Scheduled for download: {to_go}")
        logging.info(f"Total files saved from start: {cr.downloads}")

        sleep(cr.update_cycle)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Get crawler parameters")
    parser.add_argument("--update_cycle", const=360, default=360, nargs='?', type=int,
                        help="Content check and update periodicity, seconds")
    args = parser.parse_args()
    crawler = Crawler(update_cycle=args.update_cycle, destination_dir='downloads', resources=dict())
    logging.basicConfig(level=logging.INFO)
    main(crawler)
