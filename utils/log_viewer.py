"""
Simple log viewer utility for analyzing structured JSON logs.

Provides functions to read and filter log files for analysis.
"""

import json
import os
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional


def read_log_file(log_file_path: str, max_lines: int = 1000) -> List[Dict[str, Any]]:
    """
    Read and parse a JSON log file.
    
    Args:
        log_file_path: Path to the log file
        max_lines: Maximum number of lines to read (for large files)
    
    Returns:
        List of parsed log entries
    """
    if not os.path.exists(log_file_path):
        print(f"Log file not found: {log_file_path}")
        return []
    
    entries = []
    line_count = 0
    
    try:
        with open(log_file_path, 'r', encoding='utf-8') as f:
            for line in f:
                if line_count >= max_lines:
                    break
                
                line = line.strip()
                if line:
                    try:
                        entry = json.loads(line)
                        entries.append(entry)
                    except json.JSONDecodeError:
                        print(f"Failed to parse line: {line[:100]}...")
                
                line_count += 1
                
    except Exception as e:
        print(f"Error reading log file: {e}")
    
    return entries


def filter_logs_by_time(entries: List[Dict[str, Any]], 
                       start_time: Optional[datetime] = None,
                       end_time: Optional[datetime] = None) -> List[Dict[str, Any]]:
    """Filter log entries by timestamp range."""
    filtered = []
    
    for entry in entries:
        timestamp_str = entry.get('timestamp')
        if not timestamp_str:
            continue
            
        try:
            # Parse ISO timestamp
            entry_time = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
            
            if start_time and entry_time < start_time:
                continue
            if end_time and entry_time > end_time:
                continue
                
            filtered.append(entry)
        except ValueError:
            continue
    
    return filtered


def print_log_summary(entries: List[Dict[str, Any]]):
    """Print a summary of log entries."""
    if not entries:
        print("No log entries found.")
        return
    
    # Count by level
    level_counts = {}
    logger_counts = {}
    
    for entry in entries:
        level = entry.get('level', 'UNKNOWN')
        logger = entry.get('logger', 'UNKNOWN')
        
        level_counts[level] = level_counts.get(level, 0) + 1
        logger_counts[logger] = logger_counts.get(logger, 0) + 1
    
    print(f"\n=== Log Summary ({len(entries)} entries) ===")
    print("\nBy Level:")
    for level, count in sorted(level_counts.items()):
        print(f"  {level}: {count}")
    
    print("\nBy Logger:")
    for logger, count in sorted(logger_counts.items()):
        print(f"  {logger}: {count}")
    
    # Time range
    timestamps = [entry.get('timestamp') for entry in entries if entry.get('timestamp')]
    if timestamps:
        try:
            start_time = min(timestamps)
            end_time = max(timestamps)
            print(f"\nTime Range: {start_time} to {end_time}")
        except:
            pass


def print_recent_errors(log_dir: str = 'logs', hours: int = 24):
    """Print recent error logs from the last N hours."""
    error_log_path = os.path.join(log_dir, 'error.log')
    if not os.path.exists(error_log_path):
        print("No error log file found.")
        return
    
    entries = read_log_file(error_log_path)
    
    # Filter by time
    cutoff_time = datetime.utcnow() - timedelta(hours=hours)
    recent_errors = filter_logs_by_time(entries, start_time=cutoff_time)
    
    if not recent_errors:
        print(f"No errors found in the last {hours} hours.")
        return
    
    print(f"\n=== Recent Errors (last {hours} hours) ===")
    for entry in recent_errors[-10:]:  # Show last 10 errors
        timestamp = entry.get('timestamp', 'Unknown')
        logger = entry.get('logger', 'Unknown')
        message = entry.get('message', 'No message')
        
        print(f"\n[{timestamp}] {logger}")
        print(f"  {message}")
        
        if 'exception' in entry:
            print(f"  Exception: {entry['exception']}")


def main():
    """Simple command-line interface for log viewing."""
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python log_viewer.py <command> [options]")
        print("\nCommands:")
        print("  errors [hours]     - Show recent errors (default: 24 hours)")
        print("  summary <file>     - Show summary of log file")
        print("  tail <file> [n]    - Show last N lines of log file (default: 50)")
        return
    
    command = sys.argv[1]
    
    if command == 'errors':
        hours = int(sys.argv[2]) if len(sys.argv) > 2 else 24
        print_recent_errors(hours=hours)
    
    elif command == 'summary':
        if len(sys.argv) < 3:
            print("Please specify log file path")
            return
        log_file = sys.argv[2]
        entries = read_log_file(log_file)
        print_log_summary(entries)
    
    elif command == 'tail':
        if len(sys.argv) < 3:
            print("Please specify log file path")
            return
        log_file = sys.argv[2]
        max_lines = int(sys.argv[3]) if len(sys.argv) > 3 else 50
        entries = read_log_file(log_file, max_lines=max_lines)
        
        print(f"\n=== Last {len(entries)} entries from {log_file} ===")
        for entry in entries:
            timestamp = entry.get('timestamp', 'Unknown')
            level = entry.get('level', 'UNKNOWN')
            logger = entry.get('logger', 'Unknown')
            message = entry.get('message', 'No message')
            
            print(f"\n[{timestamp}] {level} - {logger}")
            print(f"  {message}")


if __name__ == '__main__':
    main()
