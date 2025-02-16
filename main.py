import aiohttp
import asyncio
import json
import logging
import os
import sys
from dataclasses import dataclass
from typing import Dict, List, Optional, Any, Tuple
from pathlib import Path
from datetime import datetime

def get_config_path():
    if getattr(sys, 'frozen', False):
        application_path = os.path.dirname(sys.executable)
    else:
        application_path = os.path.dirname(os.path.abspath(__file__))
    
    config_path = os.path.join(application_path, 'config.json')
    
    if not os.path.exists(config_path):
        default_config = {
            "credentials": {
                "username": "",
                "password": ""
            },
            "download": {
                "save_directory": os.path.join(application_path, "downloads"),
                "artist_username": ""
            },
            "api": {
                "base_url": "https://inkbunny.net/",
                "submissions_per_page": 100,
                "submission_types": "1,2,3,4,5",
                "delay": {
                    "between_files": 1,
                    "between_pages": 2
                }
            }
        }
        
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(default_config, f, indent=4)
            
    return config_path

def setup_logging():
    log_dir = 'logs'
    if getattr(sys, 'frozen', False):
        log_dir = os.path.join(os.path.dirname(sys.executable), 'logs')
    
    os.makedirs(log_dir, exist_ok=True)
    log_filename = os.path.join(log_dir, datetime.now().strftime('%Y%m%d_%H%M%S.log'))
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_filename),
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

    async def get_user_submissions(self, user_id: str, page: int = 1) -> Tuple[List[Dict], int]:
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
                        total_pages = int(data.get("pages_count", 1))
                        return data.get("submissions", []), total_pages
                    logging.error(f"Failed to get submissions (page {page})")
                    return [], 0
        except aiohttp.ClientError as e:
            logging.error(f"Error getting submissions: {str(e)}")
            return [], 0

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
        artist_folder = os.path.join(save_dir, self.download_config.artist_username)
        os.makedirs(artist_folder, exist_ok=True)
        
        filepath = Path(artist_folder) / filename
        
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

    async def process_submission(self, submission: Dict[str, Any]) -> Tuple[int, bool]:
        submission_id = submission["submission_id"]
        title = submission.get("title", "untitled")
        
        logging.info(f"\nProcessing submission: {title} (ID: {submission_id})")
        
        files_info = await self.get_submission_files(submission_id)
        downloaded_count = 0
        all_files_exist = True
        
        for file_info in files_info:
            for file_obj in file_info.get("files", []):
                url = file_obj.get("file_url_full") or file_obj.get("file_url_screen")
                if not url:
                    logging.warning(f"No valid URL found for submission {submission_id}")
                    continue
                    
                original_filename = file_obj.get("file_name", "")
                clean_title = "".join(c for c in title if c.isalnum() or c in (' ', '-', '_'))[:50]
                filename = f"{clean_title}_{original_filename}"
                
                filepath = Path(os.path.join(self.download_config.save_directory, 
                                           self.download_config.artist_username, 
                                           filename))
                if not filepath.exists():
                    all_files_exist = False
                    if await self.download_file(url, filename, self.download_config.save_directory):
                        downloaded_count += 1
                        await asyncio.sleep(self.api_config.delay['between_files'])
                
        return downloaded_count, all_files_exist

async def main():
    try:
        setup_logging()
        config_path = get_config_path()
        
        with open(config_path, 'r', encoding='utf-8') as f:
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
        
        submissions, total_pages = await downloader.get_user_submissions(user_id, page)
        if not submissions:
            logging.info("No submissions found.")
            return
            
        logging.info(f"Found {total_pages} pages of submissions")
        
        while page <= total_pages:
            if page > 1:  
                submissions, _ = await downloader.get_user_submissions(user_id, page)
                if not submissions:
                    logging.info("No more submissions found.")
                    break
            
            logging.info(f"\nProcessing page {page} of {total_pages}...")
            
            for submission in submissions:
                downloaded, _ = await downloader.process_submission(submission)
                total_downloads += downloaded
            
            logging.info(f"Page {page} completed")
            
            if page == total_pages:
                logging.info("Reached the last page. Download completed.")
                break
                
            page += 1
            await asyncio.sleep(downloader.api_config.delay['between_pages'])
            
        logging.info(f"\nDownload completed! Total files downloaded: {total_downloads}")
        
    except Exception as e:
        logging.error(f"Program error: {str(e)}")
        raise
    finally:
        input("\nPress Enter to exit...")

if __name__ == "__main__":
    asyncio.run(main())
