import asyncio
import json
import os
import random
from datetime import datetime
from pathlib import Path
from crawl4ai import AsyncWebCrawler, CrawlerRunConfig, CacheMode
from crawl4ai.extraction_strategy import LLMExtractionStrategy
from crawl4ai.content_filter_strategy import PruningContentFilter
from pydantic import BaseModel, Field
from typing import List, Optional
from dotenv import load_dotenv

load_dotenv()  

class BlogPost(BaseModel):
    title: str
    url: str
    date_published: Optional[str]
    summary: str = Field(..., description="A concise summary of the main points")
    key_concepts: List[str] = Field(..., description="Technical concepts discussed in the post")
    technical_level: str = Field(..., description="Estimated technical complexity: basic, intermediate, or advanced")
    categories: List[str] = Field(default_factory=list, description="Topic categories of the post")
    ethereum_related: bool = Field(..., description="Whether the post primarily discusses Ethereum")
    code_snippets_present: bool = Field(..., description="Whether the post contains code examples")

    class Config:
        arbitrary_types_allowed = True

async def crawl_vitalik_blog():
    # Verify OpenAI API key is set
    api_key = os.getenv('OPENAI_API_KEY')
    if not api_key:
        raise ValueError("OpenAI API key not found. Please set the OPENAI_API_KEY environment variable.")
    
    # Create output directories
    base_dir = Path("vitalik_blog_data")
    raw_dir = base_dir / "raw"
    processed_dir = base_dir / "processed"
    for dir in [raw_dir, processed_dir]:
        dir.mkdir(parents=True, exist_ok=True)

    # Configure extraction strategy
    extraction_strategy = LLMExtractionStrategy(
        provider="openai/gpt-4",
        api_token=api_key,
        schema=BlogPost.model_json_schema(),
        instruction="""
        Analyze this blog post and extract key information:
        1. Identify the main technical concepts and their complexity
        2. Determine if it contains code examples
        3. Categorize the content and its relation to Ethereum
        4. Create a technical summary focused on the main arguments and insights
        Be precise and focus on technical details rather than general descriptions.
        """,
        chunk_token_threshold=3000
    )

    # First, get all article URLs
    async with AsyncWebCrawler(verbose=True) as crawler:
        initial_result = await crawler.arun(
            url="https://vitalik.eth.limo/",
            config=CrawlerRunConfig(cache_mode=CacheMode.BYPASS)
        )
        
        article_urls = []
        for link in initial_result.links.get("internal", []):
            if '/posts/' in link['href'] or '/general/' in link['href']:
                full_url = link['href']
                if not full_url.startswith('http'):
                    full_url = 'https://vitalik.eth.limo' + full_url
                article_urls.append(full_url)
        
        print(f"Found {len(article_urls)} articles to process")

        # Process each article
        for url in article_urls:
            try:
                print(f"\nProcessing article: {url}")
                
                config = CrawlerRunConfig(
                    extraction_strategy=extraction_strategy,
                    process_iframes=True,
                    wait_for_images=True
                )
                
                result = await crawler.arun(url=url, config=config)
                
                if not result.success:
                    print(f"Failed to crawl {url}: {result.error_message}")
                    continue

                # Generate timestamp
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                
                # Save raw content
                raw_content = {
                    "url": url,
                    "html": result.html,
                    "markdown": result.markdown,
                    "metadata": result.metadata,
                    "crawl_date": timestamp
                }
                
                raw_filename = raw_dir / f"raw_{timestamp}.json"
                with open(raw_filename, 'w', encoding='utf-8') as f:
                    json.dump(raw_content, f, ensure_ascii=False, indent=2)
                print(f"Saved raw content to {raw_filename}")

                # Save processed content if available
                if result.extracted_content:
                    try:
                        processed_content = json.loads(result.extracted_content)
                        # Ensure we have all required fields
                        processed_content.update({
                            "url": url,
                            "crawl_date": timestamp,
                            "title": result.metadata.get("title", ""),
                            "date_published": result.metadata.get("date", "")
                        })
                        
                        processed_filename = processed_dir / f"processed_{timestamp}.json"
                        with open(processed_filename, 'w', encoding='utf-8') as f:
                            json.dump(processed_content, f, ensure_ascii=False, indent=2)
                        print(f"Saved processed content to {processed_filename}")
                    except json.JSONDecodeError as e:
                        print(f"Error decoding extracted content: {e}")
                        print("Raw extracted content:", result.extracted_content)

                # Respectful delay between requests
                delay = 2 + random.random()  # 2-3 second delay
                print(f"Waiting {delay:.2f} seconds before next request...")
                await asyncio.sleep(delay)

            except Exception as e:
                print(f"Error processing {url}: {str(e)}")
                import traceback
                print(traceback.format_exc())
                continue

        print("\nCrawling completed!")

if __name__ == "__main__":
    # Verify OpenAI API key before starting
    if not os.getenv('OPENAI_API_KEY'):
        print("Error: OPENAI_API_KEY environment variable not set")
        print("Please set it with: export OPENAI_API_KEY='your-api-key'")
        exit(1)
        
    asyncio.run(crawl_vitalik_blog())
