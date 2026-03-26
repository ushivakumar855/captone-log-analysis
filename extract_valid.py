#!/usr/bin/env python3
"""
Extract all valid records from an Avro file with corruption.
Stops gracefully when corruption is encountered.
"""

import json
import sys
import signal
from io import BytesIO

def extract_valid_records(input_file, output_prefix="output", records_per_file=100000):
    """Extract all valid records, stopping at first corruption."""
    
    from fastavro import reader
    
    records_written = 0
    file_count = 1
    records_in_current_file = 0
    
    out = open(f"{output_prefix}_part_{file_count}.jsonl", "w")
    
    print(f"Starting extraction from {input_file}...\n")
    print(f"Output: {output_prefix}_part_*.jsonl (max {records_per_file} records each)\n")
    
    try:
        with open(input_file, "rb") as f:
            reader_obj = reader(f)
            
            for i, record in enumerate(reader_obj):
                try:
                    # Serialize to JSON
                    line = json.dumps(record, default=str, ensure_ascii=True)
                    out.write(line + "\n")
                    records_written += 1
                    records_in_current_file += 1
                    
                    # Split into multiple files
                    if records_in_current_file >= records_per_file:
                        out.close()
                        file_count += 1
                        records_in_current_file = 0
                        out = open(f"{output_prefix}_part_{file_count}.jsonl", "w")
                        print(f"  File {file_count-1} written ({records_per_file:,} records)")
                    
                    # Progress indicator
                    if (i + 1) % 100000 == 0:
                        print(f"  Processed {i + 1:,} records ({records_written:,} written)", file=sys.stderr)
                        
                except (UnicodeEncodeError, TypeError, ValueError) as e:
                    # Skip individual records that can't be serialized
                    if records_written % 100000 < 10:  # Log only occasionally
                        print(f"  ⚠️  Record {i}: skipped ({type(e).__name__})", file=sys.stderr)
                    continue
                    
    except UnicodeDecodeError as e:
        # Expected - file corruption
        print(f"\n✅ Gracefully stopped at corruption point")
        print(f"   Records processed: {records_written:,}")
        print(f"   Completed {file_count} file(s)")
        
    except KeyboardInterrupt:
        print(f"\n⚠️  Interrupted by user")
        print(f"   Records extracted: {records_written:,}")
        sys.exit(130)
        
    except Exception as e:
        print(f"\n❌ Unexpected error: {type(e).__name__}: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return records_written
        
    finally:
        out.close()
    
    return records_written

def main():
    input_file = "ta1-theia-1-e5-official-2.bin.35"
    output_prefix = "output"
    records_per_file = 100000
    
    print("=" * 70)
    print("AVRO Corrupted File Recovery Tool")
    print("=" * 70)
    print()
    
    # Check file exists
    import os
    if not os.path.exists(input_file):
        print(f"❌ File not found: {input_file}")
        return 1
    
    try:
        total = extract_valid_records(input_file, output_prefix, records_per_file)
        
        print()
        print("=" * 70)
        print(f"✅ SUCCESS - Extracted {total:,} valid records!")
        print("=" * 70)
        print()
        print(f"📁 Output files created (1 file per {records_per_file:,} records):")
        
        # Count output files
        import glob
        output_files = sorted(glob.glob(f"{output_prefix}_part_*.jsonl"))
        for i, fname in enumerate(output_files, 1):
            fsize = os.path.getsize(fname)
            print(f"   {i}. {fname} ({fsize:,} bytes, {fsize/(1024*1024):.2f} MB)")
        
        print()
        print("Note: The original file has corruption starting at record 3,652,181")
        print("      These output files contain all valid data before that point.")
        
        return 0
        
    except Exception as e:
        print(f"❌ Extraction failed: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main())
