import aiohttp
import asyncio
import json
import logging
import os
from dataclasses import dataclass
from typing import Dict, List, Optional, Any
from pathlib import Path

from datetime import datetime

log_filename = datetime.now().strftime('%Y%m%d_%H%M%S.log')
os.makedirs('logs', exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(os.path.join('logs', log_filename)),
        logging.StreamHandler()
    ]
)

@dataclass
class APIConfig:
    base_url: str
    submissions_per_page: int
    submission_types: str
    delay: Dict[str, float]

@dataclass
class Credentials:
    username: str
    password: str

@dataclass
class DownloadConfig:
    save_directory: str
    artist_username: str

class ConfigValidator:
    @staticmethod
    def validate_config(config: Dict[str, Any]) -> bool:
        required_fields = {
            'api': ['base_url', 'submissions_per_page', 'submission_types', 'delay'],
            'credentials': ['username', 'password'],
            'download': ['artist_username', 'save_directory']
        }
        
        try:
            for section, fields in required_fields.items():
                if section not in config:
                    raise ValueError(f"Missing section: {section}")
                for field in fields:
                    if field not in config[section]:
                        raise ValueError(f"Missing field: {field} in section {section}")
                        
            if 'between_files' not in config['api']['delay'] or 'between_pages' not in config['api']['delay']:
                raise ValueError("Missing delay configuration")
                
            return True
        except ValueError as e:
            logging.error(f"Configuration validation failed: {e}")
            return False

class InkbunnyDownloader:
    def __init__(self, config: Dict[str, Any]):
        if not ConfigValidator.validate_config(config):
            raise ValueError("Invalid configuration")
            
        self.config = config
        self.api_config = APIConfig(**config['api'])
        self.credentials = Credentials(**config['credentials'])
        self.download_config = DownloadConfig(**config['download'])
        self.session_id: Optional[str] = None
        self.retry_count = 3
        self.retry_delay = 5
        self.base_url = self.api_config.base_url.rstrip('/')

    async def login(self) -> bool:
        login_url = f"{self.base_url}/api_login.php"
        
        for attempt in range(self.retry_count):
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        login_url,
                        data={
                            "username": self.credentials.username,
                            "password": self.credentials.password,
                            "output_mode": "json"
                        }
                    ) as response:
                        if response.status == 200:
                            data = await response.json()
                            if "sid" in data:
                                self.session_id = data["sid"]
                                logging.info(f"Login successful! Session ID: {self.session_id}")
                                return True
                            logging.error("Session ID not found in response")
                        else:
                            logging.error(f"Login failed with status {response.status}")
                            
            except aiohttp.ClientError as e:
                logging.error(f"Login attempt {attempt + 1} failed: {str(e)}")
                if attempt < self.retry_count - 1:
                    await asyncio.sleep(self.retry_delay)
                continue
                
        return False

    async def get_user_id(self, username: str) -> Optional[str]:
        if not self.session_id:
            raise ValueError("Not logged in")
            
        search_url = f"{self.base_url}/api_search.php"
        params = {
            "sid": self.session_id,
            "username": username,
            "submissions_per_page": 1,
            "output_mode": "json"
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(search_url, params=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        submissions = data.get("submissions", [])
                        if submissions:
                            return submissions[0]["user_id"]
                    logging.error(f"Failed to get user ID for {username}")
                    return None
        except aiohttp.ClientError as e:
            logging.error(f"Error getting user ID: {str(e)}")
            return None

    async def get_user_submissions(self, user_id: str, page: int = 1) -> List[Dict]:
        if not self.session_id:
            raise ValueError("Not logged in")
            
        search_url = f"{self.base_url}/api_search.php"
        params = {
            "sid": self.session_id,
            "user_id": user_id,
            "page": page,
            "submissions_per_page": self.api_config.submissions_per_page,
            "type": self.api_config.submission_types,
            "orderby": "create_datetime",
            "random": "no",
            "output_mode": "json"
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(search_url, params=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        return data.get("submissions", [])
                    logging.error(f"Failed to get submissions (page {page})")
                    return []
        except aiohttp.ClientError as e:
            logging.error(f"Error getting submissions: {str(e)}")
            return []

    async def get_submission_files(self, submission_id: str) -> List[Dict]:
        if not self.session_id:
            raise ValueError("Not logged in")
            
        files_url = f"{self.base_url}/api_submissions.php"
        params = {
            "sid": self.session_id,
            "submission_ids": submission_id,
            "show_description": "yes",
            "show_files": "yes",
            "show_file_urls": "yes",
            "output_mode": "json"
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(files_url, params=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        return data.get("submissions", [])
                    logging.error(f"Failed to get file info for submission {submission_id}")
                    return []
        except aiohttp.ClientError as e:
            logging.error(f"Error getting file info: {str(e)}")
            return []

    async def download_file(self, url: str, filename: str, save_dir: str) -> bool:
        os.makedirs(save_dir, exist_ok=True)
        filepath = Path(save_dir) / filename
        
        if filepath.exists():
            logging.info(f"File already exists: {filename}")
            return True
            
        for attempt in range(self.retry_count):
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(url) as response:
                        if response.status == 200:
                            with open(filepath, 'wb') as f:
                                while True:
                                    chunk = await response.content.read(8192)
                                    if not chunk:
                                        break
                                    f.write(chunk)
                            logging.info(f"Successfully downloaded: {filename}")
                            return True
                        else:
                            logging.error(f"Download failed (HTTP {response.status}): {url}")
                            
            except aiohttp.ClientError as e:
                logging.error(f"Download attempt {attempt + 1} failed: {str(e)}")
                if attempt < self.retry_count - 1:
                    await asyncio.sleep(self.retry_delay)
                continue
                
        return False

    async def process_submission(self, submission: Dict[str, Any]) -> int:
        submission_id = submission["submission_id"]
        title = submission.get("title", "untitled")
        
        logging.info(f"\nProcessing submission: {title} (ID: {submission_id})")
        
        files_info = await self.get_submission_files(submission_id)
        downloaded_count = 0
        
        for file_info in files_info:
            for file_obj in file_info.get("files", []):
                url = file_obj.get("file_url_full") or file_obj.get("file_url_screen")
                if not url:
                    logging.warning(f"No valid URL found for submission {submission_id}")
                    continue
                    
                original_filename = file_obj.get("file_name", "")
                clean_title = "".join(c for c in title if c.isalnum() or c in (' ', '-', '_'))[:50]
                filename = f"{self.download_config.artist_username}_{clean_title}_{original_filename}"
                
                if await self.download_file(url, filename, self.download_config.save_directory):
                    downloaded_count += 1
                    await asyncio.sleep(self.api_config.delay['between_files'])
                    
        return downloaded_count

async def main():
    try:
        with open("config.json", 'r', encoding='utf-8') as f:
            config = json.load(f)
        
        downloader = InkbunnyDownloader(config)
        
        if not await downloader.login():
            logging.error("Login failed! Exiting program.")
            return
        
        artist_username = downloader.download_config.artist_username
        user_id = await downloader.get_user_id(artist_username)
        if not user_id:
            logging.error(f"Could not find artist: {artist_username}")
            return
            
        logging.info(f"Starting download for artist: {artist_username}")
        
        page = 1
        total_downloads = 0
        
        while True:
            submissions = await downloader.get_user_submissions(user_id, page)
            if not submissions:
                break
                
            logging.info(f"\nProcessing page {page}...")
            
            for submission in submissions:
                downloaded = await downloader.process_submission(submission)
                total_downloads += downloaded
                
            logging.info(f"Page {page} completed")
            page += 1
            await asyncio.sleep(downloader.api_config.delay['between_pages'])
            
        logging.info(f"\nDownload completed! Total files downloaded: {total_downloads}")
        
    except Exception as e:
        logging.error(f"Program error: {str(e)}")
        raise

if __name__ == "__main__":
    asyncio.run(main())
