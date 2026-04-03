import pandas as pd
import glob
import os

folder = '13_labelled_testing_data'
files = glob.glob(os.path.join(folder, '*.csv'))

print(f"--- Sampling args for evil processes in {folder} ---")
count = 0
for f in files:
    try:
        df = pd.read_csv(f)
        evil_df = df[df['evil'] == 1]
        if not evil_df.empty:
            for _, row in evil_df.head(5).iterrows():
                print(f"Process: {row['processName']}, Event: {row['eventName']}, Args: {row['args']}")
                count += 1
            if count > 20: break
    except Exception:
        pass
