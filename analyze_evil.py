import pandas as pd
import glob
import os

folders_to_check = [
    '1_labelled_2021may-ip-10-100-1-105',
    '7_labelled_2021may-ip-10-100-1-4',
    '13_labelled_testing_data'
]

for folder in folders_to_check:
    print(f"--- Process names for EVIL=1 in {folder} ---")
    files = glob.glob(os.path.join(folder, '*.csv'))
    
    # We'll just collect from all files in the folder
    evil_processes = []
    for f in files:
        try:
            df = pd.read_csv(f)
            evil_df = df[df['evil'] == 1]
            if not evil_df.empty:
                evil_processes.append(evil_df['processName'].value_counts())
        except Exception:
            pass
            
    if evil_processes:
        combined = pd.concat(evil_processes).groupby(level=0).sum()
        print(combined.sort_values(ascending=False).head(10))
    else:
        print("No evil events found.")
    print("\n")
