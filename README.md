# Inkbunny Artwork Downloader

An asynchronous artwork downloader for Inkbunny that allows you to automatically download all artworks from specific artists.

## Features

- Bulk download artwork from specific artists
- Efficient asynchronous processing
- Automatic retry mechanism
- Detailed logging
- Duplicate download prevention
- Configurable delays for API rate limiting

## Requirements

- Python 3.7+
- aiohttp
- asyncio

## Installation

1. Clone this repository:
```bash
git clone https://github.com/haram03/inkbunny-downloader.git
cd inkbunny-downloader
```

2. Install required packages:
```bash
pip install aiohttp
```

## Configuration

On first run, the program will automatically create a `config.json` file. You'll need to configure the following settings:

```json
{
    "credentials": {
        "username": "your_username",
        "password": "your_password"
    },
    "download": {
        "save_directory": "downloads",
        "artist_username": "target_artist_username"
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
```

### Configuration Details

- **credentials**
  - `username`: Your Inkbunny account username
  - `password`: Your Inkbunny account password

- **download**
  - `save_directory`: Directory where downloaded files will be saved
  - `artist_username`: Username of the artist whose works you want to download

- **api**
  - `base_url`: Base URL for the Inkbunny API
  - `submissions_per_page`: Number of submissions to fetch per page
  - `submission_types`: Types of submissions to download (1=pictures, 2=sketches, 3=photos, 4=comics, 5=flash)
  - `delay`: Delay between API requests (in seconds)
    - `between_files`: Delay between file downloads
    - `between_pages`: Delay between page requests

## Usage

1. Configure the `config.json` file appropriately
2. Run the program:
```bash
python main.py
```

When running, the program will:
1. Log in using your configured credentials
2. Search for all submissions from the specified artist
3. Download files to the specified directory
4. Log progress to both console and log file

## Logging

All operations are logged to files in the `logs` directory. Log files are named in the following format:
```
YYYYMMDD_HHMMSS.log
```

## Error Handling

- Network errors are retried up to 3 times
- Already downloaded files are skipped
- All errors are logged to the log file

## File Organization

Downloads are organized in the following structure:
```
save_directory/
└── artist_username/
    └── artwork_files
```

## Rate Limiting

The program includes built-in delays between requests to respect API rate limits:
- Configurable delay between file downloads
- Configurable delay between page requests
