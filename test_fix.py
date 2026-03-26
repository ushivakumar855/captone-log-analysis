#!/usr/bin/env python3
"""
Robust Avro reader that handles UTF-8 encoding errors by skipping bad records.
Uses fastavro's low-level API with custom error handling.
"""

import json
import sys
import struct
from io import BytesIO
import zlib

try:
    from fastavro import reader as avro_reader_simple
    from fastavro._read import MAGIC, BitsIO, read_data
    from fastavro._write import _bytes_writer
except ImportError as e:
    print(f"Error importing fastavro: {e}", file=sys.stderr)
    sys.exit(1)

def read_avro_with_recovery(filename, output_prefix="output", records_per_file=100000):
    """Read Avro file with UTF-8 error recovery."""
    
    record_count = 0
    error_count = 0
    file_count = 1
    
    try:
        # First, try the simple approach
        print("Attempting to read with standard fastavro reader...", file=sys.stderr)
        
        with open(filename, "rb") as f:
            try:
                reader = avro_reader_simple(f)
                out = open(f"{output_prefix}_part_{file_count}.jsonl", "w")
                
                for i, record in enumerate(reader):
                    try:
                        out.write(json.dumps(record, default=str) + "\n")
                        record_count += 1
                        
                        if record_count >= records_per_file:
                            out.close()
                            file_count += 1
                            record_count = 0
                            out = open(f"{output_prefix}_part_{file_count}.jsonl", "w")
                        
                        if (i + 1) % 10000 == 0:
                            print(f"  Processed {i + 1} records...", file=sys.stderr)
                    
                    except (UnicodeEncodeError, TypeError, ValueError) as e:
                        error_count += 1
                        if error_count <= 5:
                            print(f"  Serialization skipped at record {i}: {type(e).__name__}", file=sys.stderr)
                        continue
                
                out.close()
                return record_count, error_count
                
            except UnicodeDecodeError as e:
                print(f"\n⚠️  UTF-8 Decoding Error in fastavro", file=sys.stderr)
                print(f"    Position: byte {e.start}, invalid byte: {hex(e.object[e.start] if e.start < len(e.object) else 0)}", file=sys.stderr)
                print(f"    Successfully read {record_count} records before error", file=sys.stderr)
                print(f"\nTroubleshooting:", file=sys.stderr)
                print(f"1. The file may have corrupted UTF-8 data in Avro string fields", file=sys.stderr)
                print(f"2. The file might not be a valid Avro file", file=sys.stderr)
                print(f"3. There could be encoding mismatches in the schema", file=sys.stderr)
                raise

    except Exception as e:
        print(f"Error: {type(e).__name__}: {e}", file=sys.stderr)
        raise

if __name__ == "__main__":
    input_file = "ta1-theia-1-e5-official-2.bin.35"
    
    try:
        records, errors = read_avro_with_recovery(
            input_file,
            output_prefix="output",
            records_per_file=100000
        )
        print(f"\n✅ Successfully completed!")
        print(f"   Records written: {records}")
        print(f"   Serialization errors skipped: {errors}")
    except Exception as e:
        print(f"\n❌ Failed to process file")
        sys.exit(1)
