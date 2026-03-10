#!/usr/bin/env python3
#-*- coding: utf-8 -*-
''' github.com/ffdiracex/scrape_py - implementera BeautifulSoup för att skrapa books.toscrape.com - aiohttp och BeautifulSoup. (se GeeksForGeeks.com för mer om denna sida) '''
# För att köra: python main.py
# du kan ändra max_pages i main() för antal sidor att skrapa, ändra hur många threads som används i Scrape(max_concurrent=?)
# du kan ändra timeout i Scrape om du vill ha längre eller kortare http request timeouts, vi använder 30 sekunder, för att ge servern lite luft

import aiohttp
import asyncio
from bs4 import BeautifulSoup
from datetime import datetime
import json
from typing import List, Dict, Any, Optional
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class Scrape:
    """ Hantera skrapandet av data från webbsidor. """
    # @ param base_url: Bas-URL för webbplatsen som ska skrapas.
    # @ param max_concurrent: Max antal samtidiga förfrågningar.
    def __init__(self, base_url:str="http://books.toscrape.com", max_concurrent=10):
        self.base_url = base_url
        self.semaphore = asyncio.Semaphore(max_concurrent)
        self.timeout = aiohttp.ClientTimeout(total=30)

    async def fetch(self, session: aiohttp.ClientSession, url: str) -> Optional[str]:
        """ Hämta innehållet från base_url """
        async with self.semaphore:
            try:
                async with session.get(url, timeout=self.timeout) as response:
                    response.raise_for_status()
                    html = await response.text() # Hämta HTML-innehållet
                    logger.info(f"Hämtade data från {url}")
                    return html # Returnera HTML-innehållet
            except Exception as e:
                logger.error(f"Fel vid hämtning av {url}: {e}")
                return "" # Returnera tom sträng vid fel
    def _get_text(self, soup: BeautifulSoup, selector: str) -> str:
        """Css selector för att hämta text från en BeautifulSoup-objekt."""
        element = soup.select_one(selector) # Query selector (document.querySelector)
        return element.get_text(strip=True) if element else "" # Returnera texten eller tom sträng
    
    def _extract_rating(self, soup: BeautifulSoup) -> str:
        """ Extrahera recension betyg från BeautifulSoup-objektet. """
        rating_element = soup.select_one(".star-rating") # Hämta elementet med klassen "star-rating"
        if rating_element:
            for class_name in rating_element.get('class', []):
                if class_name != 'star-rating':
                    return class_name # Returnera betygsklassen (t.ex. "One", "Two", etc.)
        return "No rating"
    
    def _extract_category(self, soup: BeautifulSoup) -> str:
        """ Extrahera kategori """
        breadcrumb = soup.select('.breadcrumb li')
        if len(breadcrumb) >= 3:
            return self._get_text(soup, '.breadcrumb li:nth-child(3)') # Returnera kategorin från brödsmulan
        return ""
    

    async def parse_page(self, session: aiohttp.ClientSession, url: str) -> Dict[str, Any]:
            html = await self.fetch(session, url)
            if not html:
                return None

            soup = BeautifulSoup(html, 'html.parser')

            # Extrahera grundläggande bokinformation
            title_elem = soup.find('h1')
            title = title_elem.text.strip() if title_elem else "No title"

            price_elem = soup.find('p', class_='price_color')
            price = price_elem.text.strip() if price_elem else "No price"

            stock_elem = soup.find('p', class_='instock availability')
            stock = stock_elem.text.strip() if stock_elem else "No stock info"

            # Extrahera rating
            rating_elem = soup.find('p', class_='star-rating')
            rating = None
            if rating_elem:
                for cls in rating_elem.get('class', []):
                    if cls != 'star-rating':
                        rating = cls
                        break
                    
            # Extrahera produktinformation från tabellen
            product_info = {}
            table = soup.find('table', class_='table table-striped')
            if table:
                for row in table.find_all('tr'):
                    th = row.find('th')
                    td = row.find('td')
                    if th and td:
                        key = th.text.strip().lower().replace(' ', '_')
                        # FIX: Check if td.text exists before calling strip
                        value = td.text.strip() if td.text else ""
                        product_info[key] = value

            # Extrahera beskrivning
            desc_elem = soup.find('div', id='product_description')
            if desc_elem:
                next_p = desc_elem.find_next_sibling('p')
                description = next_p.text.strip() if next_p else ""
            else:
                description = ""

            # Extrahera kategori från brödsmulor
            breadcrumb = soup.find('ul', class_='breadcrumb')
            category = ""
            if breadcrumb:
                links = breadcrumb.find_all('li')
                if len(links) >= 3:
                    category = links[2].text.strip()

            book_data = {
                'title': title,
                'price': price,
                'availability': stock,
                'rating': rating or "No rating",
                'description': description,
                'category': category,
                'url': url,
                'scraped_at': datetime.now().isoformat(),
                **product_info  # Lägg till all produktinformation från tabellen
            }

            return book_data

    async def parse_catalogue(self, session: aiohttp.ClientSession, page_num: int = 1) -> List[Dict]:
        """ Hämta och analysera en katalog"""
        if page_num == 1: 
            catalogue_url = f"{self.base_url}/catalogue/page-1.html"
        else:    
            catalogue_url = f"{self.base_url}/catalogue/page-{page_num}.html"

        html = await self.fetch(session, catalogue_url)
        if not html:
            return []
        
        soup = BeautifulSoup(html, 'html.parser')
        book_links = []

        for article in soup.select('article.product_pod'):
            link = article.select_one('h3 a')
            if link and link.get('href'):
                relative_url = link['href']

                if relative_url.startswith('catalogue/'):
                    book_url = f"{self.base_url}/{relative_url}"
                else:
                    book_url = f"{self.base_url}/catalogue/{relative_url}"
                
                book_links.append(book_url) # Lägg till den fullständiga URL:en för boken i listan

        tasks = [self.parse_page(session, url) for url in book_links]
        books = await asyncio.gather(*tasks) # Kör alla uppgifter parallellt och vänta på att de ska bli klara
        return [book for book in books if book] # returnera böcker och filtrera bort eventuella None-värden
    
    async def scrape(self, max_pages:int=50) -> List[Dict]:
        """ Are you happy pylint? :) => skrapa data från sidan, pylint klagar på att vi inte har docstring, så här har du en docstring pylint! """
        all_books = []

        async with aiohttp.ClientSession() as session: # VEM ORKAR SKRIVA UT HELA AIOHTTP.CLIENTSESSION, DET ÄR JU SÅ LÅNGT, KALLA DET SESSION ISTÄLLET!
            page=1
            while page <= max_pages:
                logger.info(f"Skrapar sida {page}...")
                books = await self.parse_catalogue(session, page)

                if not books:
                    logger.info(f"Inga böcker hittade på {page}")
                    break # STOPPA OM INGA BÖCKER HITTAS, INGEN BEHÖVER SKRAPA TOMMA SIDOR (smärta att debugga och hitta error)

                all_books.extend(books)
                logger.info(f"hittade {len(books)} böcker på sida {page}")
                page += 1
        return all_books # Returnera alla skrapade böcker som en lista av ordböcker
    
    def save_to_json(self, data: List[Dict], filename: str = None):
        """spara till json """
        if not filename:
            filename = f"books_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=4) # Spara data i JSON-format med indentering

            logger.info(f"Sparade {len(data)} böcker till {filename}")
    
async def main():
    """ MAIN funktion för att leda skrapningsprocessen. """
    scraper = Scrape(max_concurrent=5) #allokera Scrape objektet 
    books = await scraper.scrape(max_pages=10) # Skrapa upp till 10 sidor
    print(f"Totalt skrapade böcker: {len(books)}")

    if books:
        print("Exempel på skrapad bokdata:")
        for book in books[:3]:  # Visa bara de första tre böckerna
            print(book)
    
    scraper.save_to_json(books)

if __name__ == "__main__":
    asyncio.run(main()) # Kör main-funktionen med icke-blockerande asynkron körning (asyncio)

