#!/usr/bin/env python3
"""
Transfer OCR sentiment data from AndroidApp to individual CSV files.

This script:
1. Reads raw OCR data from ocr-data/android_sentiment_raw.csv
2. Maps Android app instrument names to system symbol names
3. Converts sentiment from 0-100% long to -50/+50 scale
4. Appends new data to individual data/<SYMBOL>SENTIMENT.csv files
5. Only processes symbols defined in symbol_info/github_repo_name.json
"""

import csv
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, Set, Optional
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# Mapping from Android app instrument names to system symbol names
# The Android app uses different naming conventions for some instruments
ANDROID_TO_SYSTEM_SYMBOL = {
    # Forex pairs - mostly direct mapping (Android app uses same names)
    'EURUSD': 'EURUSD',
    'GBPUSD': 'GBPUSD',
    'USDJPY': 'USDJPY',
    'USDCHF': 'USDCHF',
    'USDCAD': 'USDCAD',
    'AUDUSD': 'AUDUSD',
    'NZDUSD': 'NZDUSD',
    'EURJPY': 'EURJPY',
    'GBPJPY': 'GBPJPY',
    'EURGBP': 'EURGBP',
    'EURCHF': 'EURCHF',
    'EURCAD': 'EURCAD',
    'EURAUD': 'EURAUD',
    'EURNZD': 'EURNZD',
    'GBPCHF': 'GBPCHF',
    'GBPCAD': 'GBPCAD',
    'GBPAUD': 'GBPAUD',
    'GBPNZD': 'GBPNZD',
    'AUDCAD': 'AUDCAD',
    'AUDCHF': 'AUDCHF',
    'AUDJPY': 'AUDJPY',
    'AUDNZD': 'AUDNZD',
    'NZDCAD': 'NZDCAD',
    'NZDCHF': 'NZDCHF',
    'NZDJPY': 'NZDJPY',
    'CADCHF': 'CADCHF',
    'CADJPY': 'CADJPY',
    'CHFJPY': 'CHFJPY',
    'CHFPLN': 'CHFPLN',
    'EURPLN': 'EURPLN',
    'GBPPLN': 'GBPPLN',
    'USDPLN': 'USDPLN',
    
    # Indices - Android app uses different names
    'DE30': 'DAX',
    'US30': 'DJ30',
    'US100': 'NASDAQ',
    'US500': 'SP500',
    'EU50': 'EUROSTOX50',
    'FR40': 'FRANCE40',
    'GB100': 'GB100',
    'JP225': 'JAPAN225',
    'PL20': 'POLANDWIG20',
    'US2000': 'USA2000',
    
    # Commodities
    'GOLD': 'XAUUSD',
    'XAUUSD': 'XAUUSD',
    'SILVER': 'XAGUSD',
    'XAGUSD': 'XAGUSD',
    'COPPER': 'COPPER',
    'OILWTI': 'OILWTI',
    'COFFEE': 'COFFEE',
    'WHEAT': 'WHEAT',
    'COCOA': 'COCOA',
    'COTTON': 'COTTON',
    'NATGAS': 'NATGAS',
    'OILBRNT': 'OILBRENT',
    'PALLAD': 'PALLAD',
    'PLATIN': 'PLATIN',
    'SOYBEAN': 'SOYBEAN',
    'SUGAR': 'SUGAR',
    
    # Crypto
    'BTCUSD': 'BTC',
    'ETHUSD': 'ETH',
    'ADAUSD': 'ADA',
    'AVAXUSD': 'AVAX',
    'DOGEUSD': 'DOGE',
    'DOTUSD': 'DOT',
    'LINKUSD': 'LINK',
    'LTCUSD': 'LTC',
    'SOLUSD': 'SOL',
    'UNIUSD': 'UNI',
}


def load_allowed_symbols(seed_file: str) -> Set[str]:
    """Load list of allowed symbols from seed JSON file."""
    try:
        with open(seed_file, 'r') as f:
            data = json.load(f)
        
        # Extract base symbol names (remove 'SENTIMENT' suffix)
        symbols = set()
        for symbol in data.get('symbol', []):
            if symbol.endswith('SENTIMENT'):
                base = symbol[:-9]  # Remove 'SENTIMENT'
                symbols.add(base)
            elif symbol.endswith('FEARGREED'):
                # Skip fear/greed indices - they come from different sources
                pass
            else:
                symbols.add(symbol)
        
        logging.info(f"Loaded {len(symbols)} allowed symbols from seed file")
        return symbols
    except Exception as e:
        logging.error(f"Error loading seed file: {e}")
        return set()


def convert_sentiment(long_pct: int) -> float:
    """
    Convert sentiment from 0-100% long scale to -50/+50 scale.
    
    - 0% long (100% short) = -50 (maximum bearish)
    - 50% long (50% short) = 0 (neutral)
    - 100% long (0% short) = +50 (maximum bullish)
    
    Formula: sentiment = long_pct - 50
    """
    return round(long_pct - 50, 1)


def read_ocr_data(ocr_file: str) -> Dict[str, Dict[str, int]]:
    """
    Read OCR data file and return dict of {instrument: {date: long_pct}}.
    """
    data = {}
    
    try:
        with open(ocr_file, 'r', newline='') as f:
            reader = csv.DictReader(f)
            for row in reader:
                instrument = row['instrument']
                timestamp = row['timestamp']
                long_pct = int(row['long_pct'])
                
                # Parse timestamp and format as YYYYMMDDT
                try:
                    dt = datetime.strptime(timestamp, '%Y-%m-%d %H:%M:%S')
                    date_key = dt.strftime('%Y%m%dT')
                except ValueError:
                    logging.warning(f"Invalid timestamp format: {timestamp}")
                    continue
                
                if instrument not in data:
                    data[instrument] = {}
                
                # Store latest reading for each date
                data[instrument][date_key] = long_pct
        
        logging.info(f"Read OCR data for {len(data)} instruments")
        return data
    except Exception as e:
        logging.error(f"Error reading OCR file: {e}")
        return {}


def read_existing_csv(csv_file: str) -> Dict[str, tuple]:
    """Read existing CSV file and return dict of {timestamp: (sentiment, ...)}."""
    existing = {}
    
    if not os.path.exists(csv_file):
        return existing
    
    try:
        with open(csv_file, 'r', newline='') as f:
            reader = csv.reader(f)
            for row in reader:
                if row and len(row) >= 6:
                    timestamp = row[0]
                    existing[timestamp] = tuple(row[1:])
        
        logging.debug(f"Read {len(existing)} existing records from {csv_file}")
        return existing
    except Exception as e:
        logging.error(f"Error reading existing CSV {csv_file}: {e}")
        return {}


def write_csv(symbol: str, data: Dict[str, tuple], output_dir: str) -> bool:
    """Write sentiment data to CSV file."""
    output_file = os.path.join(output_dir, f"{symbol}SENTIMENT.csv")
    
    try:
        # Sort data by timestamp
        sorted_data = sorted(data.items())
        
        with open(output_file, 'w', newline='') as f:
            writer = csv.writer(f)
            for timestamp, values in sorted_data:
                row = [timestamp] + list(values)
                writer.writerow(row)
        
        logging.info(f"Wrote {len(sorted_data)} records to {output_file}")
        return True
    except Exception as e:
        logging.error(f"Error writing CSV {output_file}: {e}")
        return False


def process_ocr_data(
    ocr_file: str,
    seed_file: str,
    output_dir: str
) -> int:
    """
    Process OCR data and update individual CSV files.
    
    Returns number of symbols updated.
    """
    # Load allowed symbols
    allowed_symbols = load_allowed_symbols(seed_file)
    if not allowed_symbols:
        logging.error("No allowed symbols loaded")
        return 0
    
    # Read OCR data
    ocr_data = read_ocr_data(ocr_file)
    if not ocr_data:
        logging.error("No OCR data to process")
        return 0
    
    # Create output directory if needed
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    
    updated_count = 0
    
    # Process each instrument from OCR data
    for android_instrument, date_data in ocr_data.items():
        # Map Android app instrument to system symbol
        system_symbol = ANDROID_TO_SYSTEM_SYMBOL.get(android_instrument)

        if not system_symbol:
            # Try direct match
            if android_instrument in allowed_symbols:
                system_symbol = android_instrument
            else:
                logging.debug(f"Skipping unmapped instrument: {android_instrument}")
                continue
        
        # Check if symbol is in allowed list
        if system_symbol not in allowed_symbols:
            logging.debug(f"Skipping symbol not in seed file: {system_symbol}")
            continue
        
        # Read existing data
        csv_file = os.path.join(output_dir, f"{system_symbol}SENTIMENT.csv")
        existing_data = read_existing_csv(csv_file)
        
        # Merge with new data
        new_records = 0
        for date_key, long_pct in date_data.items():
            if date_key not in existing_data:
                # Convert to -50/+50 scale
                sentiment = convert_sentiment(long_pct)
                
                # Create row with same value in all sentiment columns (OHLC-style)
                existing_data[date_key] = (
                    f"{sentiment:.1f}",
                    f"{sentiment:.1f}",
                    f"{sentiment:.1f}",
                    f"{sentiment:.1f}",
                    "0"
                )
                new_records += 1
        
        # Write updated data
        if new_records > 0:
            if write_csv(system_symbol, existing_data, output_dir):
                updated_count += 1
                logging.info(f"Added {new_records} new records for {system_symbol}")
    
    return updated_count


def main():
    """Main entry point."""
    # Paths
    script_dir = Path(__file__).parent
    ocr_file = script_dir / 'ocr-data' / 'android_sentiment_raw.csv'
    seed_file = script_dir / 'symbol_info' / 'github_repo_name.json'
    output_dir = script_dir / 'data'
    
    logging.info("=" * 50)
    logging.info("Starting OCR data transfer to CSV files")
    logging.info("=" * 50)
    
    # Check if OCR file exists
    if not ocr_file.exists():
        logging.error(f"OCR data file not found: {ocr_file}")
        return 1
    
    # Process data
    updated = process_ocr_data(str(ocr_file), str(seed_file), str(output_dir))
    
    logging.info("=" * 50)
    logging.info(f"Transfer complete. Updated {updated} symbol files.")
    logging.info("=" * 50)
    
    return 0


if __name__ == '__main__':
    exit(main())
