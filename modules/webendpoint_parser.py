"""
CNN Index Data Parser

This module handles parsing of the CNN-IDX historical data
from a local JSON file and manages incremental updates.

Features:
- Parse large historical JSON file into separate component files
- Extract all 10 CNN-IDX indicators
- Manage incremental updates for new data
- Handle missing data gracefully
"""

import json
import os
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from pathlib import Path

logger = logging.getLogger(__name__)

class CNNFearGreedParser:
    """Parser for CNN-IDX data"""

    def __init__(self, base_data_dir: str = "data-works"):
        """
        Initialize the parser

        Args:
            base_data_dir: Base directory for data storage
        """
        self.base_data_dir = Path(base_data_dir)
        self.cnn_data_dir = self.base_data_dir / "cnn-fear-greed-index"
        self.parsed_data_dir = self.cnn_data_dir / "parsed"
        self.historical_file = self.cnn_data_dir / "cnn-fear-greed-allhistory.json"

        # All CNN-IDX components to extract
        self.components = [
            "fear_and_greed",
            "fear_and_greed_historical",
            "market_momentum_sp500",
            "market_momentum_sp125",
            "stock_price_strength",
            "stock_price_breadth",
            "put_call_options",
            "market_volatility_vix",
            "market_volatility_vix_50",
            "junk_bond_demand",
            "safe_haven_demand"
        ]

    def check_and_parse_historical_data(self) -> bool:
        """
        Check if historical data file exists and parse it if needed

        Returns:
            bool: True if parsing was successful or already done, False if file missing
        """
        logger.info("🔍 Checking for CNN-IDX historical data...")

        # Check if historical file exists
        if not self.historical_file.exists():
            logger.warning(f"⚠️ Historical data file not found: {self.historical_file}")
            logger.info("📁 Please save cnn-fear-greed-index.json file in /data-works/cnn-fear-greed-index directory")
            return False

        # Check if already parsed
        if self._check_parsed_files_exist():
            logger.info("✅ Parsed CNN-IDX data already exists")
            return True

        # Parse the historical file
        logger.info("📊 Parsing CNN-IDX historical data...")
        try:
            return self._parse_historical_file()
        except Exception as e:
            logger.error(f"❌ Error parsing historical data: {e}")
            return False

    def _check_parsed_files_exist(self) -> bool:
        """Check if all parsed component files exist"""
        if not self.parsed_data_dir.exists():
            return False

        for component in self.components:
            component_file = self.parsed_data_dir / f"{component}.json"
            if not component_file.exists():
                return False

        return True

    def _parse_historical_file(self) -> bool:
        """
        Parse the historical JSON file into separate component files

        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Create parsed directory if it doesn't exist
            self.parsed_data_dir.mkdir(parents=True, exist_ok=True)

            # Read the historical file in chunks to avoid memory issues
            logger.info(f"📖 Reading historical data file: {self.historical_file}")

            with open(self.historical_file, 'r', encoding='utf-8') as f:
                data = json.load(f)

            logger.info("🔧 Extracting component data...")

            # Extract each component
            extracted_count = 0
            for component in self.components:
                if component in data:
                    success = self._extract_component_data(component, data[component])
                    if success:
                        extracted_count += 1
                        logger.info(f"✅ Extracted {component}")
                    else:
                        logger.warning(f"⚠️ Failed to extract {component}")
                else:
                    logger.warning(f"⚠️ Component {component} not found in historical data")

            logger.info(f"📊 Successfully extracted {extracted_count}/{len(self.components)} components")
            return extracted_count > 0

        except json.JSONDecodeError as e:
            logger.error(f"❌ Invalid JSON in historical file: {e}")
            return False
        except FileNotFoundError:
            logger.error(f"❌ Historical file not found: {self.historical_file}")
            return False
        except Exception as e:
            logger.error(f"❌ Unexpected error parsing historical file: {e}")
            return False

    def _extract_component_data(self, component_name: str, component_data: Dict) -> bool:
        """
        Extract a single component's data to its own JSON file

        Args:
            component_name: Name of the component
            component_data: The component's data

        Returns:
            bool: True if successful, False otherwise
        """
        try:
            component_file = self.parsed_data_dir / f"{component_name}.json"

            with open(component_file, 'w', encoding='utf-8') as f:
                json.dump(component_data, f, indent=2, ensure_ascii=False)

            return True

        except Exception as e:
            logger.error(f"❌ Error extracting {component_name}: {e}")
            return False

    def get_latest_timestamp(self) -> Optional[float]:
        """
        Get the latest timestamp from all parsed component files

        Returns:
            Optional[float]: Latest timestamp in milliseconds, None if no data
        """
        latest_timestamp = None

        try:
            for component in self.components:
                component_file = self.parsed_data_dir / f"{component}.json"

                if not component_file.exists():
                    continue

                with open(component_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)

                # Check for timestamp in component data
                component_timestamp = None
                if 'timestamp' in data:
                    timestamp_value = data['timestamp']
                    # Convert ISO string to Unix timestamp if needed
                    if isinstance(timestamp_value, str):
                        from datetime import datetime
                        try:
                            dt = datetime.fromisoformat(timestamp_value.replace('Z', '+00:00'))
                            component_timestamp = dt.timestamp() * 1000  # Convert to milliseconds
                        except:
                            continue
                    else:
                        component_timestamp = float(timestamp_value)
                elif 'data' in data and isinstance(data['data'], list) and data['data']:
                    # Find latest timestamp in data array
                    for item in reversed(data['data']):
                        if 'x' in item:
                            component_timestamp = float(item['x'])
                            break

                if component_timestamp:
                    if latest_timestamp is None or component_timestamp > latest_timestamp:
                        latest_timestamp = component_timestamp

            return latest_timestamp

        except Exception as e:
            logger.error(f"❌ Error getting latest timestamp: {e}")
            return None

    def merge_incremental_data(self, new_data: Dict) -> bool:
        """
        Merge new incremental data with existing parsed data

        Args:
            new_data: New data

        Returns:
            bool: True if successful, False otherwise
        """
        try:
            logger.info("🔄 Merging incremental data...")
            merged_count = 0

            for component in self.components:
                if component in new_data:
                    success = self._merge_component_data(component, new_data[component])
                    if success:
                        merged_count += 1
                        logger.info(f"✅ Merged {component}")
                    else:
                        logger.warning(f"⚠️ Failed to merge {component}")

            logger.info(f"🔄 Successfully merged {merged_count} components")
            return merged_count > 0

        except Exception as e:
            logger.error(f"❌ Error merging incremental data: {e}")
            return False

    def _merge_component_data(self, component_name: str, new_component_data: Dict) -> bool:
        """
        Merge new data for a specific component

        Args:
            component_name: Name of the component
            new_component_data: New data for the component

        Returns:
            bool: True if successful, False otherwise
        """
        try:
            component_file = self.parsed_data_dir / f"{component_name}.json"

            # Load existing data
            existing_data = {}
            if component_file.exists():
                with open(component_file, 'r', encoding='utf-8') as f:
                    existing_data = json.load(f)

            # Update timestamp and score if available
            if 'timestamp' in new_component_data:
                existing_data['timestamp'] = new_component_data['timestamp']
            if 'score' in new_component_data:
                existing_data['score'] = new_component_data['score']
            if 'rating' in new_component_data:
                existing_data['rating'] = new_component_data['rating']

            # Merge data arrays
            if 'data' in new_component_data and isinstance(new_component_data['data'], list):
                if 'data' not in existing_data:
                    existing_data['data'] = []

                # Add new data points that don't already exist
                existing_timestamps = {item.get('x') for item in existing_data['data'] if 'x' in item}

                for new_item in new_component_data['data']:
                    if 'x' in new_item and new_item['x'] not in existing_timestamps:
                        existing_data['data'].append(new_item)

                # Sort by timestamp
                existing_data['data'].sort(key=lambda x: x.get('x', 0))

            # Save updated data
            with open(component_file, 'w', encoding='utf-8') as f:
                json.dump(existing_data, f, indent=2, ensure_ascii=False)

            return True

        except Exception as e:
            logger.error(f"❌ Error merging {component_name}: {e}")
            return False

    def get_component_data(self, component_name: str) -> Optional[Dict]:
        """
        Get data for a specific component

        Args:
            component_name: Name of the component to retrieve

        Returns:
            Optional[Dict]: Component data or None if not found
        """
        try:
            component_file = self.parsed_data_dir / f"{component_name}.json"

            if not component_file.exists():
                return None

            with open(component_file, 'r', encoding='utf-8') as f:
                return json.load(f)

        except Exception as e:
            logger.error(f"❌ Error loading {component_name}: {e}")
            return None

    def get_all_components_data(self) -> Dict[str, Optional[Dict]]:
        """
        Get data for all components

        Returns:
            Dict[str, Optional[Dict]]: All component data
        """
        all_data = {}

        for component in self.components:
            all_data[component] = self.get_component_data(component)

        return all_data

    def get_fear_greed_index(self) -> Optional[Dict]:
        """
        Get the main Fear & Greed index data

        Returns:
            Optional[Dict]: Fear & Greed index data
        """
        return self.get_component_data("fear_and_greed")