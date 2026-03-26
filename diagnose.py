#!/usr/bin/env python3
"""
Diagnostic script to investigate UTF-8 encoding errors in Avro files.
"""

import sys
import json

def diagnose_avro_file(filename):
    """Diagnose issues with an Avro file."""
    
    print(f"Diagnosing Avro file: {filename}\n")
    
    # Check file size
    import os
    file_size = os.path.getsize(filename)
    print(f"📊 File size: {file_size:,} bytes ({file_size / (1024*1024):.2f} MB)\n")
    
    # Check magic number
    with open(filename, "rb") as f:
        magic = f.read(4)
        print(f"📋 Magic number: {magic.hex()} ({repr(magic)})")
        if magic == b'Obj\x01':
            print("   ✓ Valid Avro container file header")
        else:
            print("   ✗ NOT a valid Avro container file!")
            return
    
    # Try to get schema without reading records
    print(f"\n🔍 Attempting to read schema...")
    try:
        from fastavro import reader
        with open(filename, "rb") as f:
            avro_reader = reader(f)
            schema = avro_reader.writer_schema
            print(f"   ✓ Schema found:")
            print(f"   {json.dumps(schema, indent=4)[:500]}...\n")
    except Exception as e:
        print(f"   ✗ Error reading schema: {type(e).__name__}: {e}\n")
        return
    
    # Try to read first few records
    print(f"📖 Attempting to read records...")
    try:
        from fastavro import reader
        with open(filename, "rb") as f:
            avro_reader = reader(f)
            
            for i in range(5):
                try:
                    record = next(iter(avro_reader))
                    print(f"   Record {i}: OK ({len(str(record))} chars)")
                    if i == 0:
                        # Show structure of first record
                        print(f"   Keys: {list(record.keys())[:10]}")
                except StopIteration:
                    print(f"   Record {i}: End of file")
                    break
                except Exception as e:
                    print(f"   Record {i}: ✗ {type(e).__name__}")
                    print(f"              {str(e)[:100]}")
                    if i == 0:
                        print(f"\n⚠️  FILE DIAGNOSIS:")
                        print(f"    The file has corrupted or invalid UTF-8 data")
                        print(f"    This typically happens when:")
                        print(f"    1. The file was corrupted during transfer/storage")
                        print(f"    2. String fields contain binary data")
                        print(f"    3. The schema doesn't match the actual data")
                        print(f"    4. The file was truncated\n")
                        print(f"SUGGESTED SOLUTIONS:")
                        print(f"  • Re-download or obtain a fresh copy of the file")
                        print(f"  • Verify the file wasn't corrupted in transit")
                        print(f"  • Check with the data provider about encoding issues")
                        print(f"  • Try extracting it from the original source")
                    return
    except Exception as e:
        print(f"   ✗ Error reading records: {type(e).__name__}: {e}")

if __name__ == "__main__":
    filename = "ta1-theia-1-e5-official-2.bin.35"
    diagnose_avro_file(filename)
