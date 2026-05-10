import logging
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
from tools.registry import registry

logger = logging.getLogger(__name__)

@registry.register
def scrape_web_page(url: str) -> str:
    """
    Scrapes the text content of a web page using Playwright.
    
    Args:
        url (str): The URL to scrape.
        
    Returns:
        str: The text content of the page, or an error message.
    """
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(url, timeout=30000)
            content = page.content()
            browser.close()
            
            soup = BeautifulSoup(content, 'html.parser')
            
            # Remove script and style elements
            for script in soup(["script", "style"]):
                script.decompose()
                
            text = soup.get_text()
            
            # Break into lines and remove leading/trailing space on each
            lines = (line.strip() for line in text.splitlines())
            # Break multi-headlines into a line each
            chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
            # Drop blank lines
            text = '\n'.join(chunk for chunk in chunks if chunk)
            
            return text[:10000] # Limit to 10k chars to avoid context overflow
            
    except Exception as e:
        logger.error(f"Error scraping {url}: {e}")
        return f"Error scraping {url}: {str(e)}"
