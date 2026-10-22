"""
Google Maps Routes API Integration Module

This module handles route generation for delivery trips using Google Maps Routes API.
Generates turn-by-turn directions and calculates timestamps for delivery sequences.

Features:
- Route generation from address list using Google Maps Routes API
- Turn-by-turn direction generation from Google Maps navigation instructions
- Unix timestamp calculation with delivery buffers
- Error handling and retry logic
"""

import os
import logging
import time
import requests
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from utils.timezone import ensure_est_timezone
from dotenv import load_dotenv

load_dotenv()

# Configure logging
logger = logging.getLogger(__name__)

class GoogleMapsClient:
    """
    Google Maps Routes API client for delivery route generation.
    
    Generates turn-by-turn directions for delivery routes with proper
    timing calculations including 15-minute delivery buffers.
    """
    
    def __init__(self):
        """Initialize Google Maps API client with configuration."""
        self.api_key = os.getenv('GOOGLE_MAPS_API_KEY')
        if not self.api_key:
            raise ValueError("GOOGLE_MAPS_API_KEY environment variable is required")
        
        self.base_url = "https://routes.googleapis.com/directions/v2:computeRoutes"
        self.headers = {
            'Content-Type': 'application/json',
            'X-Goog-Api-Key': self.api_key,
            'X-Goog-FieldMask': 'routes.duration,routes.distanceMeters,routes.legs.steps.navigationInstruction,routes.legs.steps.distanceMeters,routes.legs.steps.staticDuration'
        }
        
        self.max_retries = 3
        self.retry_delay = 1  # seconds
        
        # Origin address (warehouse)
        self.origin_address = "159 E Main St, Bristol, CT, 06010"
        
        logger.info("Google Maps API client initialized successfully")
    
    def generate_route_segments(self, addresses: List[str], delivery_date: str, approx_start_time: str) -> Optional[List[Dict[str, Any]]]:
        """
        Generate route segments with turn-by-turn directions and timestamps.
        
        Args:
            addresses: List of delivery addresses in order
            delivery_date: Delivery date (YYYY-MM-DD format)
            approx_start_time: Approximate start time (YYYY-MM-DD HH:MM AM/PM format)
            
        Returns:
            List of route segments with departure_time, arrival_time, and route directions
            Each segment includes Unix timestamps and 15-minute delivery buffers
            
        Example:
            addresses = ["100 Location 1, City 1, CT", "200 Location 2, City 2, CT"]
            delivery_date = "2025-08-05"
            approx_start_time = "2025-08-05 07:00 AM"
            
            Returns:
            [
                {
                    "departure_time": 1743897600,
                    "arrival_time": 1743898500,
                    "route": "Turn-by-turn directions from origin to location 1"
                },
                {
                    "departure_time": 1743899400,
                    "arrival_time": 1743900300,
                    "route": "Turn-by-turn directions from location 1 to location 2"
                }
            ]
        """
        logger.info(f"Generating route segments for {len(addresses)} addresses")
        
        if not addresses:
            logger.error("No addresses provided for route generation")
            return None
        
        try:
            # Generate routes between consecutive addresses
            route_segments = self._generate_route_segments(addresses)
            if not route_segments:
                return None
            
            # Calculate timestamps with delivery buffers
            route_segments = self._calculate_timestamps(route_segments, delivery_date, approx_start_time)
            
            logger.info(f"Generated {len(route_segments)} route segments successfully")
            return route_segments
            
        except Exception as e:
            logger.error(f"Route generation failed: {str(e)}")
            return None
    
    def _generate_route_segments(self, addresses: List[str]) -> Optional[List[Dict[str, Any]]]:
        """Generate route segments between consecutive addresses."""
        try:
            route_segments = []
            
            # Create full address list including origin
            full_addresses = [self.origin_address] + addresses
            
            # Generate routes between consecutive addresses
            for i in range(len(full_addresses) - 1):
                origin = full_addresses[i]
                destination = full_addresses[i + 1]
                
                logger.debug(f"Generating route from {origin} to {destination}")
                
                # Get route data from Google Maps
                route_data = self._get_route_between_addresses(origin, destination)
                if not route_data:
                    logger.error(f"Failed to get route from {origin} to {destination}")
                    return None
                
                # Extract navigation instructions
                route_text = self._format_navigation_instructions(route_data)
                
                # Create route segment
                segment = {
                    'departure_time': 0,  # Will be calculated later
                    'arrival_time': 0,    # Will be calculated later
                    'route': route_text,
                    'duration_seconds': self._extract_duration_seconds(route_data),
                    'distance_meters': self._extract_distance_meters(route_data)
                }
                
                route_segments.append(segment)
                logger.debug(f"Created route segment {i+1} with {len(route_text)} characters")
            
            return route_segments
            
        except Exception as e:
            logger.error(f"Route segment generation failed: {str(e)}")
            return None
    
    def _get_route_between_addresses(self, origin: str, destination: str) -> Optional[Dict[str, Any]]:
        """Get route data between two addresses using Google Maps API."""
        payload = {
            "origin": {"address": origin},
            "destination": {"address": destination},
            "travelMode": "DRIVE",
            "routingPreference": "TRAFFIC_AWARE",
            "computeAlternativeRoutes": False,
            "routeModifiers": {
                "avoidTolls": False,
                "avoidHighways": False,
                "avoidFerries": False
            },
            "languageCode": "en-US",
            "units": "IMPERIAL"
        }
        
        for attempt in range(self.max_retries):
            try:
                logger.debug(f"Making Google Maps API request (attempt {attempt + 1})")
                
                response = requests.post(
                    self.base_url, 
                    headers=self.headers, 
                    json=payload,
                    timeout=30
                )
                
                if response.status_code == 200:
                    data = response.json()
                    if 'routes' in data and data['routes']:
                        logger.debug(f"Successfully retrieved route data")
                        return data['routes'][0]
                    else:
                        logger.error(f"No route found between {origin} and {destination}")
                        return None
                elif response.status_code == 429:  # Rate limit
                    logger.warning(f"Rate limit exceeded (attempt {attempt + 1})")
                    if attempt < self.max_retries - 1:
                        time.sleep(self.retry_delay * (2 ** attempt))
                        continue
                    else:
                        logger.error("Max retries exceeded for rate limit")
                        return None
                else:
                    logger.error(f"API Error {response.status_code}: {response.text}")
                    if attempt < self.max_retries - 1:
                        time.sleep(self.retry_delay)
                        continue
                    else:
                        return None
                        
            except requests.exceptions.RequestException as e:
                logger.error(f"Request error (attempt {attempt + 1}): {str(e)}")
                if attempt < self.max_retries - 1:
                    time.sleep(self.retry_delay)
                    continue
                else:
                    return None
            except Exception as e:
                logger.error(f"Unexpected error in route request: {str(e)}")
                return None
        
        return None
    
    def _format_navigation_instructions(self, route_data: Dict[str, Any]) -> str:
        """Format navigation instructions from Google Maps route data."""
        try:
            instructions = []
            legs = route_data.get('legs', [])
            
            for leg in legs:
                steps = leg.get('steps', [])
                for i, step in enumerate(steps, 1):
                    navigation = step.get('navigationInstruction', {})
                    instruction = navigation.get('instructions', 'Continue straight')
                    distance = step.get('distanceMeters', 0)
                    
                    # Format instruction with distance if available
                    if distance > 0:
                        distance_miles = distance / 1609.34
                        if distance_miles >= 0.1:  # Only show distance for significant segments
                            instructions.append(f"{i}. {instruction} ({distance_miles:.1f} mi)")
                        else:
                            instructions.append(f"{i}. {instruction}")
                    else:
                        instructions.append(f"{i}. {instruction}")
            
            # Join instructions and limit length
            route_text = '\n'.join(instructions)
            
            # Limit to reasonable length for route instructions
            if len(route_text) > 1500:
                # Keep first 10 instructions and truncate
                limited_instructions = instructions[:10]
                route_text = '\n'.join(limited_instructions)
                if len(limited_instructions) < len(instructions):
                    route_text += "\n[Route continues with similar directions]"
            
            return route_text
            
        except Exception as e:
            logger.error(f"Error formatting navigation instructions: {str(e)}")
            return "Route directions not available"
    
    def _extract_duration_seconds(self, route_data: Dict[str, Any]) -> int:
        """Extract duration in seconds from route data."""
        try:
            duration = route_data.get('duration', '0s')
            if isinstance(duration, str):
                # Parse duration string like "15m30s" or "1h15m30s"
                import re
                match = re.match(r'(?:(\d+)h)?(?:(\d+)m)?(?:(\d+)s)?', duration)
                if match:
                    hours = int(match.group(1) or 0)
                    minutes = int(match.group(2) or 0)
                    seconds = int(match.group(3) or 0)
                    return hours * 3600 + minutes * 60 + seconds
            return 0
        except Exception as e:
            logger.error(f"Error extracting duration: {str(e)}")
            return 0
    
    def _extract_distance_meters(self, route_data: Dict[str, Any]) -> int:
        """Extract distance in meters from route data."""
        try:
            return route_data.get('distanceMeters', 0)
        except Exception as e:
            logger.error(f"Error extracting distance: {str(e)}")
            return 0
    
    def _calculate_timestamps(self, route_segments: List[Dict[str, Any]], delivery_date: str, approx_start_time: str) -> List[Dict[str, Any]]:
        """
        Calculate Unix timestamps for departure and arrival times with 15-minute buffers.
        
        Args:
            route_segments: Route segments with duration information
            delivery_date: Delivery date (YYYY-MM-DD)
            approx_start_time: Approximate start time (YYYY-MM-DD HH:MM AM/PM)
            
        Returns:
            Route segments with calculated Unix timestamps
        """
        try:
            # Parse delivery date and start time
            try:
                start_datetime = datetime.strptime(approx_start_time, '%Y-%m-%d %I:%M %p')
            except ValueError:
                # Fallback to delivery date with 8 AM start
                start_datetime = datetime.strptime(delivery_date, '%Y-%m-%d')
                start_datetime = start_datetime.replace(hour=8, minute=0, second=0, microsecond=0)
                logger.warning("Invalid start time format, using 8 AM as default")
            
            # Ensure timezone-aware datetime with DST handling
            start_datetime = ensure_est_timezone(start_datetime)
            
            current_time = start_datetime
            
            for i, segment in enumerate(route_segments):
                # Calculate departure and arrival times
                departure_time = current_time
                arrival_time = departure_time + timedelta(seconds=segment.get('duration_seconds', 900))  # Default 15 minutes
                
                # Update segment with Unix timestamps
                segment['departure_time'] = int(departure_time.timestamp())
                segment['arrival_time'] = int(arrival_time.timestamp())
                
                # Update current time for next segment
                current_time = arrival_time
                
                # Add 15-minute buffer for delivery processing (except for last stop)
                if i < len(route_segments) - 1:
                    current_time += timedelta(minutes=15)
                
                logger.debug(f"Segment {i+1}: Departure at {departure_time.strftime('%H:%M')}, "
                           f"Arrival at {arrival_time.strftime('%H:%M')}")
            
            logger.info(f"Calculated timestamps for {len(route_segments)} route segments")
            return route_segments
            
        except Exception as e:
            logger.error(f"Error calculating timestamps: {str(e)}")
            return route_segments
