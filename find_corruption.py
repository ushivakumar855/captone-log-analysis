#!/usr/bin/env python3
"""
Find the exact record where UTF-8 error occurs and provide recovery options.
"""

import sys

def find_corruption(filename, max_records=None):
    """Find where the file becomes corrupted."""
    
    print(f"🔎 Scanning for corruption in {filename}...\n")
    
    from fastavro import reader
    
    record_count = 0
    
    try:
        with open(filename, "rb") as f:
            avro_reader = reader(f)
            
            for i, record in enumerate(avro_reader):
                record_count = i + 1
                
                # Print progress every 10,000 records
                if (i + 1) % 10000 == 0:
                    print(f"  ✓ Successfully read {i + 1:,} records")
                
                if max_records and i >= max_records:
                    print(f"\n✓ Reached max_records limit at {i + 1}")
                    return record_count
                    
    except UnicodeDecodeError as e:
        print(f"\n❌ UTF-8 Corruption detected!")
        print(f"   Records successfully read: {record_count:,}")
        print(f"   Failed at byte position: {e.start:,}")
        print(f"   Invalid byte: {hex(e.object[e.start] if e.start < len(e.object) else 0)}")
        
        print(f"\n💡 SOLUTION OPTIONS:")
        print(f"\n1. Truncate at last good record:")
        print(f"   The file is OK up to record #{record_count:,}")
        print(f"   You can use that data.\n")
        
        print(f"2. Use the provided truncated-reader script:")
        print(f"   This will extract all valid records before the corruption.\n")
        
        print(f"3. Contact the data provider:")
        print(f"   Ask about re-downloading or re-encoding the file.\n")
        
        return record_count
        
    except Exception as e:
        print(f"\n❌ Unexpected error: {type(e).__name__}: {e}")
        return record_count

if __name__ == "__main__":
    filename = "ta1-theia-1-e5-official-2.bin.35"
    
    # First do a quick scan to find corruption
    valid_records = find_corruption(filename, max_records=None)
    
    if valid_records > 0:
        print(f"\n✅ {valid_records:,} valid records can be extracted from this file")
