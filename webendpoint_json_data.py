import requests
import json
import os
from datetime import datetime, timedelta
import time
import random
from fake_useragent import UserAgent
import cloudscraper
from urllib3.util.ssl_ import create_urllib3_context
import socket
import socks
import csv
from pathlib import Path
import asyncio
import argparse
import logging
from typing import Optional, Dict, List, Callable

# Import modules
from modules.cnn_scraper import CNNScraper
from modules.cnn_fear_greed_parser import CNNFearGreedParser
from modules.aaii_sentiment_manager import AAIISentimentManager

# Logger config
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('CNNBTC_DATA')

# =============================================================================
# CNN-IDX COMPONENT TO CSV FILE MAPPING
# =============================================================================
CNN_COMPONENT_TO_CSV = {
    'junk_bond_demand': 'JUNK_BOND_DEMAND',
    'market_momentum_sp125': 'MARKET_MOMENTUM_SP125',
    'market_volatility_vix': 'MARKET_VOLATILITY_VIX',
    'market_volatility_vix_50': 'MARKET_VOLATILITY_VIX_50',
    'put_call_options': 'PUT_CALL_OPTIONS',
    'safe_haven_demand': 'SAFE_HAVEN_DEMAND',
    'stock_price_breadth': 'STOCK_PRICE_BREADTH',
    'stock_price_strength': 'STOCK_PRICE_STRENGTH',
}


# =============================================================================
# NORMALIZATION FUNCTIONS
# =============================================================================

def clamp(value: float, min_val: float = -50, max_val: float = 50) -> float:
    """Clamps value to the range -50/+50"""
    return max(min_val, min(max_val, value))


def normalize_cnn_component(component_name: str, value: float,
                           historical_data: List[Dict] = None) -> float:
    """
    Normalizes raw CNN indicator value to -50/+50 scale.
    Each indicator has its own normalization formula with fallback clamping.
    """

    if component_name == 'put_call_options':
        # Range: 0 - 2
        # Formula: (value / 2) * 100 - 50
        # 0 → -50, 1 → 0, 2 → +50
        normalized = (value / 2) * 100 - 50
        return clamp(normalized)

    elif component_name == 'junk_bond_demand':
        # Range: 0.5 - 2
        # Formula: ((value - 0.5) / 1.5) * 100 - 50
        # 0.5 → -50, 1.25 → 0, 2 → +50
        normalized = ((value - 0.5) / 1.5) * 100 - 50
        return clamp(normalized)

    elif component_name in ('safe_haven_demand', 'stock_price_strength'):
        # Range: -20 to +20 (practically -10 to +10)
        # Formula: value * 2.5
        # -20 → -50, 0 → 0, +20 → +50
        normalized = value * 2.5
        return clamp(normalized)

    elif component_name == 'stock_price_breadth':
        # Range: 500 - 2000
        # Formula: ((value - 500) / 1500) * 100 - 50
        # 500 → -50, 1250 → 0, 2000 → +50
        normalized = ((value - 500) / 1500) * 100 - 50
        return clamp(normalized)

    elif component_name in ('market_volatility_vix', 'market_volatility_vix_50'):
        # Range: 0 - 100
        # Formula: value - 50
        # 0 → -50, 50 → 0, 100 → +50
        normalized = value - 50
        return clamp(normalized)

    elif component_name == 'market_momentum_sp125':
        # OSCILLATOR: deviation from MA365
        # Requires historical data to calculate MA
        if historical_data and len(historical_data) >= 365:
            # Calculate MA365 from last 365 data points
            recent_values = [d['y'] for d in historical_data[-365:]]
            ma365 = sum(recent_values) / len(recent_values)

            # Percentage deviation
            deviation_pct = ((value - ma365) / ma365) * 100

            # Scaling: ±10% deviation → ±50
            normalized = deviation_pct * 5
            return clamp(normalized)
        else:
            # Fallback if insufficient historical data
            if historical_data and len(historical_data) > 0:
                available_values = [d['y'] for d in historical_data]
                ma = sum(available_values) / len(available_values)
                if ma != 0:
                    deviation_pct = ((value - ma) / ma) * 100
                    normalized = deviation_pct * 5
                    return clamp(normalized)
            return 0.0

    # Default fallback
    return clamp(value - 50)


def normalize_aaii_sentiment(value: float) -> float:
    """
    Converts EquityIndividualInvestorSurvey 0-100% to -50/+50 scale.
    0% → -50, 50% → 0, 100% → +50
    """
    normalized = value - 50
    return clamp(normalized)


def calculate_aaii_composite(bullish: float, bearish: float, neutral: float) -> float:
    """
    Calculates EquityIndividualInvestorSurvey Composite using formula:
    (Bullish - Bearish) * ((1 - Neutral/100)^2)

    Result typically falls within -50/+50 range (extreme: Bull=75, Bear=25 → ~50)
    Clamping as safeguard for edge values.

    Interpretation:
    - fear_greed: difference bullish vs bearish (typically -50 to +50)
    - conviction_squared: (1 - neutral/100)^2 - squaring
      amplifies signal at low neutral, weakens at high neutral
    """
    fear_greed = bullish - bearish                 # typically: -50 to +50 (extreme: -75 to +75)
    conviction_squared = (1 - neutral / 100) ** 2  # range: 0 to 1
    composite = fear_greed * conviction_squared    # typically: -50 to +50
    return clamp(composite)                        # safeguard for extreme values

def get_last_timestamp_from_csv(csv_file):
    if not os.path.exists(csv_file):
        return None

    with open(csv_file, 'r') as f:
        lines = f.readlines()
        if lines:
            last_line = lines[-1]
            return last_line.split(',')[0]  # First element is timestamp
    return None

def append_to_csv(csv_file, new_data):
    # First read existing data
    existing_data = []
    try:
        with open(csv_file, 'r') as f:
            reader = csv.reader(f)
            existing_data = list(reader)
    except FileNotFoundError:
        existing_data = []

    # Remove potentially corrupted or duplicate entries
    valid_existing_data = []
    seen_timestamps = set()
    for row in existing_data:
        if len(row) >= 6 and len(row[0]) == 9:  # Check timestamp format (YYYYMMDDT)
            if row[0] not in seen_timestamps:
                valid_existing_data.append(row)
                seen_timestamps.add(row[0])

    # Add new data
    for timestamp, value in new_data:
        if timestamp not in seen_timestamps and len(timestamp) == 9:
            valid_existing_data.append([timestamp, value, value, value, value, "0"])
            seen_timestamps.add(timestamp)

    # Sort all data by timestamp
    sorted_data = sorted(valid_existing_data, key=lambda x: x[0])

    # Write everything back to file
    with open(csv_file, 'w', newline='') as f:
        writer = csv.writer(f)
        for row in sorted_data:
            writer.writerow(row)

def parse_alternative_me_json(json_file, csv_file):
    last_timestamp = get_last_timestamp_from_csv(csv_file)
    new_data = []

    with open(json_file, 'r') as f:
        data = json.load(f)

    # Reverse data order to process oldest first
    for entry in reversed(data.get('data', [])):
        timestamp = datetime.fromtimestamp(int(entry['timestamp']))
        formatted_timestamp = timestamp.strftime('%Y%m%dT')
        
        if not last_timestamp or formatted_timestamp > last_timestamp:
            value = float(entry['value'])
            new_data.append((formatted_timestamp, f"{value:.1f}"))
    
    if new_data:
        append_to_csv(csv_file, new_data)
        print(f"Added {len(new_data)} new entries to {csv_file}")

def parse_cnn_json(json_file, csv_file):
    last_timestamp = get_last_timestamp_from_csv(csv_file)
    new_data = []

    with open(json_file, 'r') as f:
        data = json.load(f)
        
    fear_greed_data = data.get('fear_and_greed_historical', {}).get('data', [])

    # Reverse data order to process oldest first
    for entry in reversed(fear_greed_data):
        timestamp = datetime.fromtimestamp(entry['x'] / 1000)  # Convert milliseconds to seconds
        formatted_timestamp = timestamp.strftime('%Y%m%dT')

        if not last_timestamp or formatted_timestamp > last_timestamp:
            value = float(entry['y'])
            if value <= 100:  # Check if value is valid
                new_data.append((formatted_timestamp, f"{value:.1f}"))
    
    if new_data:
        append_to_csv(csv_file, new_data)
        print(f"Added {len(new_data)} new entries to {csv_file}")

def get_random_headers():
    ua = UserAgent()
    headers = {
        'User-Agent': ua.random,
        'Accept': 'application/json, text/plain, */*',
        'Accept-Language': random.choice([
            'en-US,en;q=0.9',
            'en-GB,en;q=0.9',
            'en-CA,en;q=0.9',
            'pl-PL,pl;q=0.9',
            'de-DE,de;q=0.9'
        ]),
        'Accept-Encoding': 'gzip, deflate, br',
        'DNT': '1',
        'Connection': random.choice(['keep-alive', 'close']),
        'Sec-Fetch-Dest': 'empty',
        'Sec-Fetch-Mode': 'cors',
        'Sec-Fetch-Site': 'same-origin',
        'Pragma': 'no-cache',
        'Cache-Control': 'no-cache',
        'Referer': 'https://url.com',
    }
    return headers

def get_random_proxy():
    # Example proxy list - replace with working proxies
    proxies = [
        'socks5h://proxy1.example.com:1080',
        'socks5h://proxy2.example.com:1080',
        'http://proxy3.example.com:8080'
    ]
    return random.choice(proxies)

def setup_socks_proxy():
    # SOCKS proxy configuration (e.g., for TOR)
    socks.set_default_proxy(socks.SOCKS5, "127.0.0.1", 9050)
    socket.socket = socks.socksocket

def create_directory():
    os.makedirs('cnnbtc_json_data', exist_ok=True)
    os.makedirs('data', exist_ok=True)

def cleanup_json_files(source_prefix, max_files=11):
    """
    Removes oldest JSON files for given source if file count exceeds max_files.

    Args:
        source_prefix (str): File prefix
        max_files (int): Maximum number of files to keep
    """
    json_dir = Path('cnnbtc_json_data')
    if not json_dir.exists():
        return

    # List all JSON files with given prefix
    json_files = list(json_dir.glob(f"{source_prefix}*.json"))

    if len(json_files) > max_files:
        # Sort files by modification date (oldest first)
        json_files.sort(key=lambda x: x.stat().st_mtime)

        # Remove excess files (oldest ones)
        files_to_remove = json_files[:-max_files]
        for file_path in files_to_remove:
            try:
                file_path.unlink()
                print(f"Removed old JSON file: {file_path}")
            except Exception as e:
                print(f"Error removing file {file_path}: {e}")

def download_cnn_fear_greed(date_str):
    url = f'https://sourceEndpointAPIjson.com/index/{date_str}'
    json_file = f'cnnbtc_json_data/cnn_fear_greed_{date_str}.json'
    csv_file = 'data/CNNFEARGREED.csv'

    # Random delay before request (2-7 seconds)
    time.sleep(random.uniform(2, 7))

    try:
        # Use cloudscraper instead of requests to bypass Cloudflare
        scraper = cloudscraper.create_scraper(
            browser={
                'browser': 'chrome',
                'platform': 'windows',
                'mobile': False
            }
        )

        # Add random headers
        headers = get_random_headers()

        # Use proxy (uncomment if you have working proxies)
        # proxy = get_random_proxy()
        # response = scraper.get(url, headers=headers, proxies={'http': proxy, 'https': proxy})
        
        response = scraper.get(url, headers=headers)
        
        if response.status_code == 200:
            with open(json_file, 'w') as f:
                json.dump(response.json(), f, indent=4)
            print(f"Successfully downloaded CNN data for {date_str}")
            
            # Parse JSON and update CSV after successful download
            parse_cnn_json(json_file, csv_file)
            
            # Cleanup old files
            cleanup_json_files('cnn_fear_greed_')
        else:
            print(f"Failed to download CNN data for {date_str}. Status code: {response.status_code}")

            # Try alternative method on error
            try_alternative_method(url, date_str)
            
    except Exception as e:
        print(f"Error downloading CNN data: {str(e)}")

def try_alternative_method(url, date_str):
    json_file = f'cnnbtc_json_data/cnn_fear_greed_{date_str}.json'
    csv_file = 'data/CNNFEARGREED.csv'

    try:
        # Create SSL context with custom configuration
        ctx = create_urllib3_context()
        ctx.set_ciphers('DEFAULT@SECLEVEL=1')

        session = requests.Session()
        session.mount('https://', requests.adapters.HTTPAdapter(ssl_context=ctx))

        response = session.get(
            url,
            headers=get_random_headers(),
            verify=False  # Warning: this may be unsafe in production
        )
        
        if response.status_code == 200:
            with open(json_file, 'w') as f:
                json.dump(response.json(), f, indent=4)
            print(f"Successfully downloaded CNN data using alternative method for {date_str}")
            
            # Parse JSON and update CSV after successful download
            parse_cnn_json(json_file, csv_file)
    except Exception as e:
        print(f"Alternative method failed for {date_str}: {str(e)}")

def download_alternative_me():
    url = 'https://api.sourceEndpointAPIjson.com/?limit=8'
    json_file = 'cnnbtc_json_data/alternative_me_fng.json'
    csv_file = 'data/BTCFEARGREED.csv'
    
    try:
        response = requests.get(url, headers=get_random_headers())
        if response.status_code == 200:
            # Add timestamp to filename
            current_time = datetime.now().strftime('%Y-%m-%d')
            json_file = f'cnnbtc_json_data/alternative_me_fng-{current_time}.json'
            
            with open(json_file, 'w') as f:
                json.dump(response.json(), f, indent=4)
            print("Successfully downloaded Alternative.me data")
            
            # Parse JSON and update CSV after successful download
            parse_alternative_me_json(json_file, csv_file)
            
            # Cleanup old files
            cleanup_json_files('alternative_me_fng')
        else:
            print(f"Failed to download Alternative.me data. Status code: {response.status_code}")
    except Exception as e:
        print(f"Error downloading Alternative.me data: {str(e)}")

# =============================================================================
# CNN PROCESSING FUNCTIONS
# =============================================================================

def process_historical_to_csv(data: List[Dict], csv_file: str,
                              component_name: str = None) -> None:
    """
    Processes historical data and saves to CSV.

    Args:
        data: List of {x: timestamp_ms, y: value, rating: str}
        csv_file: Path to CSV file
        component_name: Component name for normalization (None = no normalization)
    """
    new_data = []

    for i, entry in enumerate(data):
        timestamp_ms = entry.get('x')
        value = entry.get('y')

        if timestamp_ms is None or value is None:
            continue

        # Convert ms to datetime
        try:
            dt = datetime.fromtimestamp(timestamp_ms / 1000)
            formatted_timestamp = dt.strftime('%Y%m%dT')
        except (OSError, ValueError):
            continue

        # Normalize with historical context (for oscillator)
        if component_name:
            normalized = normalize_cnn_component(component_name, value, data[:i+1])
        else:
            # No normalization (for main Fear & Greed)
            normalized = value

        new_data.append((formatted_timestamp, f"{normalized:.1f}"))

    if new_data:
        append_to_csv(csv_file, new_data)
        logger.info(f"Updated {csv_file}: {len(new_data)} entries")


async def process_cnn_components(date_str: str) -> bool:
    """
    Fetches CNN-IDX data and saves all components to CSV files.

    1. Use CNNScraper (async) to fetch data
    2. Use CNNFearGreedParser for parsing and merging (preserves original values in JSON)
    3. For each component: normalize and save to CSV

    Returns:
        bool: True if successful, False otherwise
    """
    logger.info("Processing CNN-IDX components...")

    try:
        scraper = CNNScraper(max_retries=3)
        parser = CNNFearGreedParser()

        # Ensure historical data is parsed
        parser.check_and_parse_historical_data()

        # Fetch new data
        logger.info(f"Fetching CNN-IDX data for date: {date_str}")
        cnn_data = await scraper.fetch_cnn_data(date_str)
        if cnn_data:
            # Save original data to JSON (without normalization)
            parser.merge_incremental_data(cnn_data)
            logger.info("Updated JSON files with original data")

        # Process main Fear & Greed indicator (no normalization - 0-100 scale)
        fg_data = parser.get_component_data('fear_and_greed_historical')
        if fg_data and 'data' in fg_data:
            process_historical_to_csv(
                fg_data['data'],
                'data/CNNFEARGREED.csv',
                component_name=None  # no normalization
            )
            logger.info("Processed fear_and_greed → CNNFEARGREED.csv (0-100)")

        # Process each CNN component (with normalization to -50/+50)
        for component_name, csv_name in CNN_COMPONENT_TO_CSV.items():
            component_data = parser.get_component_data(component_name)

            if not component_data or 'data' not in component_data:
                logger.warning(f"No data for: {component_name}")
                continue

            historical = component_data['data']
            csv_file = f'data/{csv_name}.csv'

            # Normalize and save to CSV
            process_historical_to_csv(
                historical,
                csv_file,
                component_name=component_name
            )

            logger.info(f"Processed {component_name} → {csv_file}")

        # Scraper statistics
        stats = scraper.get_stats()
        logger.info(f"CNN-IDX scraper stats: {stats.get('successful', 0)}/{stats.get('total_requests', 0)} successful")

        return True

    except Exception as e:
        logger.error(f"CNN-IDX processing error: {e}")
        import traceback
        traceback.print_exc()
        return False


# =============================================================================
# AAII PROCESSING FUNCTIONS
# =============================================================================

def process_aaii_data() -> bool:
    """
    Fetches/updates EquityIndividualInvestorSurvey data and saves to 4 CSV files.

    1. Use AAIISentimentManager to update data (preserves original values in JSON)
    2. Read full historical data from JSON
    3. For each entry: calculate 4 values (bullish, bearish, neutral, composite)
    4. Save to 4 CSV files (normalized to -50/+50)

    Returns:
        bool: True if successful, False otherwise
    """
    logger.info("Processing EquityIndividualInvestorSurvey Sentiment data...")

    try:
        manager = AAIISentimentManager()
        success = manager.run_data_management()

        if not success:
            logger.error("EquityIndividualInvestorSurvey data management failed")
            return False

        # Read full data (original values 0-100%)
        data = manager._read_json_data()
        if not data or 'data' not in data:
            logger.error("No EquityIndividualInvestorSurvey data available")
            return False

        entries = data['data']
        logger.info(f"Processing {len(entries)} EquityIndividualInvestorSurvey records...")

        bullish_data = []
        bearish_data = []
        neutral_data = []
        composite_data = []

        for entry in entries:
            date_str = entry.get('date')
            bullish = entry.get('bullish')
            bearish = entry.get('bearish')
            neutral = entry.get('neutral')

            if not all([date_str, bullish is not None, bearish is not None, neutral is not None]):
                continue

            # Convert date YYYY-MM-DD → YYYYMMDDT
            try:
                dt = datetime.strptime(date_str, '%Y-%m-%d')
                formatted_timestamp = dt.strftime('%Y%m%dT')
            except ValueError:
                continue

            # Normalize to -50/+50 scale
            bullish_norm = normalize_aaii_sentiment(bullish)
            bearish_norm = normalize_aaii_sentiment(bearish)
            neutral_norm = normalize_aaii_sentiment(neutral)
            composite_norm = calculate_aaii_composite(bullish, bearish, neutral)

            bullish_data.append((formatted_timestamp, f"{bullish_norm:.1f}"))
            bearish_data.append((formatted_timestamp, f"{bearish_norm:.1f}"))
            neutral_data.append((formatted_timestamp, f"{neutral_norm:.1f}"))
            composite_data.append((formatted_timestamp, f"{composite_norm:.1f}"))

        # Save to CSV
        append_to_csv('data/AMINDINVESTORBULLISH.csv', bullish_data)
        append_to_csv('data/AMINDINVESTORBEARISH.csv', bearish_data)
        append_to_csv('data/AMINDINVESTORNEUTRAL.csv', neutral_data)
        append_to_csv('data/AMINDINVESTORCOMPOSITE.csv', composite_data)

        logger.info(f"Updated 4 EquityIndividualInvestorSurvey CSV files: {len(entries)} records each")
        return True

    except Exception as e:
        logger.error(f"EquityIndividualInvestorSurvey processing error: {e}")
        import traceback
        traceback.print_exc()
        return False


# =============================================================================
# CLI AND MAIN
# =============================================================================

def parse_arguments():
    """Parses command line arguments."""
    parser = argparse.ArgumentParser(
        description='Fetch and process CNN, BTC and EquityIndividualInvestorSurvey data',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python webendpoint_json_data.py                    # Full update (BTC + CNN + EquityIndividualInvestorSurvey)
  python webendpoint_json_data.py --btc-only         # BTC data only
  python webendpoint_json_data.py --idx-only         # CNN data only (9 files)
  python webendpoint_json_data.py --eis-only        # EquityIndividualInvestorSurvey data only (4 files)
  python webendpoint_json_data.py --date 2026-01-15  # CNN data for specific date
        """
    )
    parser.add_argument('--btc-only', action='store_true',
                       help='BTC Fear & Greed data only')
    parser.add_argument('--idx-only', action='store_true',
                       help='CNN data only (all components)')
    parser.add_argument('--eis-only', action='store_true',
                       help='EquityIndividualInvestorSurvey Sentiment data only')
    parser.add_argument('--date', type=str, default=None,
                       help='Target date for CNN (YYYY-MM-DD), default: 8 days ago')
    parser.add_argument('--debug', action='store_true',
                       help='Enable verbose logging')

    return parser.parse_args()


async def main_async():
    """Asynchronous main function."""
    args = parse_arguments()

    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    create_directory()

    # Determine target date
    today = datetime.now()
    if args.date:
        date_str = args.date
    else:
        target_date = today - timedelta(days=8)
        date_str = target_date.strftime('%Y-%m-%d')

    logger.info("=" * 60)
    logger.info("ALL DATA UPDATER")
    logger.info(f"CNN target date: {date_str}")
    logger.info("=" * 60)

    results = {'btc': True, 'cnn': True, 'aaii': True}
    process_all = not (args.btc_only or args.cnn_only or args.aaii_only)

    # BTC
    if process_all or args.btc_only:
        logger.info("-" * 40)
        logger.info("Processing BTC Fear & Greed...")
        download_alternative_me()

    # CNN - (9 CSV files)
    if process_all or args.cnn_only:
        logger.info("-" * 40)
        results['cnn'] = await process_cnn_components(date_str)

    # EquityIndividualInvestorSurvey - (4 CSV files)
    if process_all or args.aaii_only:
        logger.info("-" * 40)
        results['aaii'] = process_aaii_data()

    # Summary
    logger.info("=" * 60)
    logger.info("SUMMARY")
    logger.info("=" * 60)
    for source, success in results.items():
        status = "OK" if success else "ERROR"
        logger.info(f"{source.upper()}: {status}")

    return all(results.values())


def main():
    """Main entry point - async wrapper."""
    success = asyncio.run(main_async())
    return 0 if success else 1


if __name__ == "__main__":
    exit(main())