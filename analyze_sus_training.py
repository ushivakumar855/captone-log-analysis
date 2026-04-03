import pandas as pd
import glob
import os

folder = '14_labelled_training_data'
files = glob.glob(os.path.join(folder, '*.csv'))

print(f"--- Top suspect process names in {folder} ---")
sus_processes = []
for f in files:
    try:
        df = pd.read_csv(f)
        sus_df = df[df['sus'] == 1]
        if not sus_df.empty:
            sus_processes.append(sus_df['processName'].value_counts())
    except Exception:
        pass

if sus_processes:
    combined = pd.concat(sus_processes).groupby(level=0).sum()
    print(combined.sort_values(ascending=False).head(10))
else:
    print("No suspect events found.")
