#!/usr/bin/env python3
"""
Extract sentiment data from Android app screenshots using OCR.
"""

import re
import subprocess
import argparse
from pathlib import Path
from datetime import datetime
import csv

import pytesseract
from PIL import Image

# Known valid instruments (add more as needed)
KNOWN_INSTRUMENTS = {
    # Forex majors
    'EURUSD', 'GBPUSD', 'USDJPY', 'USDCHF', 'AUDUSD', 'NZDUSD', 'USDCAD',
    # Forex crosses
    'EURGBP', 'EURJPY', 'EURCHF', 'EURAUD', 'EURNZD', 'EURCAD', 'EURPLN',
    'GBPJPY', 'GBPCHF', 'GBPAUD', 'GBPNZD', 'GBPCAD',
    'AUDJPY', 'AUDNZD', 'AUDCAD', 'AUDCHF',
    'NZDJPY', 'NZDCAD', 'NZDCHF',
    'CADJPY', 'CADCHF',
    'CHFJPY', 'CHFPLN',
    'USDPLN', 'USDSEK', 'USDNOK', 'USDMXN', 'USDZAR', 'USDTRY', 'GBPPLN',
    # Metals
    'GOLD', 'SILVER', 'COPPER', 'PLATIN', 'PALLAD',
    # Indices
    'US30', 'US100', 'US500', 'DE30', 'GB100', 'JP225', 'EU50', 'PL20', 'US2000', 'FR40',
    # Commodities
    'OILWTI', 'OILBRNT', 'NATGAS', 'WHEAT', 'CORN', 'SOYBEAN', 'SUGAR',
    'COFFEE', 'COCOA', 'COTTON',
    # Crypto
    'BTCUSD', 'ETHUSD', 'LTCUSD', 'XRPUSD', 'BCHUSD', 'ADAUSD', 'DOGEUSD',
    'SOLUSD', 'DOTUSD', 'LINKUSD', 'UNIUSD', 'AVAXUSD'
}

# OCR corrections for common misreads
OCR_CORRECTIONS = {
    'DE30O': 'DE30',
    'US1OO': 'US100',
    'USDIPY': 'USDJPY',
    'GBPIPY': 'GBPJPY',
    'EURIPY': 'EURJPY',
    'AUDIPY': 'AUDJPY',
    'CADIPY': 'CADJPY',
    'NZDIPY': 'NZDJPY',
    'CHFIPY': 'CHFJPY',
    'NAIGAS': 'NATGAS',
    'USDIP': 'USDJPY',
}

# Invalid words that OCR might pick up from UI text
INVALID_WORDS = {
    'TRADE', 'MARKETS', 'HOTTEST', 'PEOPLE', 'ALSO', 'TRADERS',
    'BUYING', 'SELLING', 'FAVOURITES', 'EXTREMES', 'ALL',
}


def extract_text_from_image(image_path: str) -> str:
    """Extract text from image using Tesseract OCR."""
    img = Image.open(image_path)
    # Convert to grayscale for better OCR
    img = img.convert('L')
    text = pytesseract.image_to_string(img)
    return text


def normalize_instrument(name: str) -> str:
    """Normalize instrument name and apply OCR corrections."""
    name = name.upper().strip()
    # Apply known corrections
    if name in OCR_CORRECTIONS:
        name = OCR_CORRECTIONS[name]
    return name


def is_valid_instrument(name: str) -> bool:
    """Check if instrument name is valid (known or looks like a valid symbol)."""
    name = normalize_instrument(name)
    # Reject known invalid words from UI
    if name in INVALID_WORDS:
        return False
    # Check if it's in our known list
    if name in KNOWN_INSTRUMENTS:
        return True
    # Reject unknown instruments that are not in our list
    # This is stricter - only accept known instruments
    return False


def parse_sentiment_data(text: str) -> list[dict]:
    """
    Parse sentiment data from OCR text.
    
    Expected format in text:
    GOLD
    51% traders are buying
    
    EURUSD
    58% traders are selling
    """
    results = []
    
    # Pattern to match instrument name followed by percentage
    # Multiple patterns for different OCR artifacts
    patterns = [
        # Direct: "GOLD\n51% traders are buying"
        r'([A-Z]{2,}[A-Z0-9]*)\s*\n\s*(\d{1,3})%\s+traders\s+are\s+(buying|selling)',
        # With artifacts: "COCOA\n@ 88% traders" - allow up to 3 non-digit chars
        r'([A-Z]{2,}[A-Z0-9]*)\s*\n[^\d\n]{1,3}\s*(\d{1,3})%\s+traders\s+are\s+(buying|selling)',
    ]
    
    matches = []
    for pattern in patterns:
        matches.extend(re.findall(pattern, text, re.IGNORECASE))
    
    # Alternative approach: find instruments from "People who trade X also trade"
    # and then find the percentage IMMEDIATELY above it (within 3 lines max)
    people_pattern = r'People who trade ([A-Z]{2,}[A-Z0-9]*) also trade'
    instruments_mentioned = re.findall(people_pattern, text, re.IGNORECASE)

    # For each instrument mentioned, try to find its percentage in the text
    for instr in instruments_mentioned:
        instr = instr.upper()
        # Look for percentage that appears within 3 lines BEFORE "People who trade {instr}"
        # This prevents matching wrong percentages from earlier in the text
        pct_pattern = rf'(\d{{1,3}})%\s+traders\s+are\s+(buying|selling)(?:[^\n]*\n){{0,3}}[^\n]*People who trade {instr}'
        pct_match = re.search(pct_pattern, text, re.IGNORECASE)
        if pct_match:
            matches.append((instr, pct_match.group(1), pct_match.group(2)))
    
    for match in matches:
        raw_instrument = match[0].upper()
        instrument = normalize_instrument(raw_instrument)
        
        # Skip invalid instruments (OCR artifacts like "WY", "OW", etc.)
        if not is_valid_instrument(instrument):
            continue
        
        # Skip very short names (likely OCR errors)
        if len(instrument) < 3:
            continue
            
        percentage = int(match[1])
        direction = match[2].lower()
        
        # Calculate long/short percentages
        if direction == 'buying':
            long_pct = percentage
            short_pct = 100 - percentage
        else:
            short_pct = percentage
            long_pct = 100 - percentage
        
        results.append({
            'instrument': instrument,
            'long_pct': long_pct,
            'short_pct': short_pct,
            'direction': direction,
            'raw_pct': percentage
        })
    
    return results


def process_screenshots(screenshot_dir: str, debug: bool = False) -> dict:
    """Process all screenshots and extract unique instruments."""
    screenshot_path = Path(screenshot_dir)
    all_data = {}

    # Debug: save raw OCR text to file for analysis
    # File is overwritten on each run (mode='w') - no accumulation
    debug_file = None
    if debug:
        debug_path = screenshot_path.parent / 'ocr-data' / 'ocr_debug_raw.txt'
        debug_path.parent.mkdir(parents=True, exist_ok=True)
        debug_file = open(debug_path, 'w')  # 'w' mode overwrites existing file
        print(f"[DEBUG] Saving raw OCR text to: {debug_path}")

    for img_file in sorted(screenshot_path.glob('*.png')):
        print(f"Processing: {img_file.name}")
        text = extract_text_from_image(str(img_file))

        # Debug: write raw OCR text
        if debug_file:
            debug_file.write(f"\n{'='*60}\n")
            debug_file.write(f"FILE: {img_file.name}\n")
            debug_file.write(f"{'='*60}\n")
            debug_file.write(text)
            debug_file.write("\n")

        data = parse_sentiment_data(text)

        for item in data:
            instrument = item['instrument']
            if instrument not in all_data:
                all_data[instrument] = item
                print(f"  Found: {instrument} - {item['long_pct']}% long / {item['short_pct']}% short")

    if debug_file:
        debug_file.close()
        print(f"[DEBUG] Raw OCR text saved.")

    return all_data


def save_to_csv(data: dict, output_path: str):
    """Save sentiment data to CSV file."""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    with open(output_path, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['timestamp', 'instrument', 'long_pct', 'short_pct'])
        
        for instrument, values in sorted(data.items()):
            writer.writerow([
                timestamp,
                instrument,
                values['long_pct'],
                values['short_pct']
            ])
    
    print(f"\nSaved {len(data)} instruments to {output_path}")


def main():
    parser = argparse.ArgumentParser(description='Extract sentiment data from Android app screenshots using OCR')
    parser.add_argument('--debug', action='store_true',
                       help='Save raw OCR text to ocr_debug_raw.txt for analysis')
    args = parser.parse_args()

    # Dynamic paths relative to script location (works in both dev and production)
    script_dir = Path(__file__).parent
    screenshot_dir = str(script_dir / 'screenshots')
    output_csv = str(script_dir / 'ocr-data' / 'android_sentiment_raw.csv')

    print("Extracting sentiment data from Android app screenshots...")
    print("=" * 50)

    data = process_screenshots(screenshot_dir, debug=args.debug)
    
    print("=" * 50)
    print(f"Total unique instruments found: {len(data)}")
    
    # Create output directory if needed
    Path(output_csv).parent.mkdir(parents=True, exist_ok=True)
    
    save_to_csv(data, output_csv)
    
    # Also print summary
    print("\nSummary:")
    for instrument, values in sorted(data.items()):
        direction = "↑" if values['long_pct'] > 50 else "↓"
        print(f"  {instrument}: {values['long_pct']}% long {direction}")


if __name__ == '__main__':
    main()
