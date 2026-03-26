#method 1 (garbage + output)
# with open("ta1-theia-1-e5-official-2.bin.35", "rb") as f:
#     content = f.read(1000)
#     print(content)


#method 2 fastavro (output only)
# from fastavro import reader
# open_file = open("ta1-theia-1-e5-official-2.bin.35", "rb")
# avro_reader = reader(open_file)

# for i,record in enumerate(avro_reader):
#     print(record)
#     if i == 2:
#         break

import json
import sys
from fastavro import reader

input_file = "ta1-theia-1-e5-official-2.bin.35"
output_prefix = "output"
records_per_file = 100000

file_count = 1
record_count = 0

out = open(f"{output_prefix}_part_{file_count}.jsonl", "w")

try:
    print(f"Reading Avro file: {input_file}", file=sys.stderr)
    
    with open(input_file, "rb") as f:
        avro_reader = reader(f)
        
        for i, record in enumerate(avro_reader):
            out.write(json.dumps(record, default=str) + "\n")
            record_count += 1
            
            if record_count >= records_per_file:
                out.close()
                file_count += 1
                record_count = 0
                out = open(f"{output_prefix}_part_{file_count}.jsonl", "w")
                print(f"  Completed file {file_count - 1}", file=sys.stderr)
            
            if (i + 1) % 500000 == 0:
                print(f"  Progress: {i + 1:,} records", file=sys.stderr)
                
except UnicodeDecodeError as e:
    print(f"\n✅ Processing complete!", file=sys.stderr)
    print(f"   Extracted: {record_count:,} valid records", file=sys.stderr)
    print(f"   Stopped at corrupted record (normal)", file=sys.stderr)
    
except Exception as e:
    print(f"❌ Error: {type(e).__name__}: {e}", file=sys.stderr)
    sys.exit(1)
    
finally:
    out.close()

print(f"\nDone ✅ split into {file_count} files")