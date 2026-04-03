import pandas as pd
import os
import glob

folders = [
    '1_labelled_2021may-ip-10-100-1-105',
    '10_labelled_2021may-ip-10-100-1-95-dns',
    '14_labelled_training_data'
]

for folder in folders:
    print(f"--- Folder: {folder} ---")
    files = glob.glob(os.path.join(folder, '*.csv'))
    if not files:
        print("No CSV files found.")
        continue
    
    # Analyze the first file in the folder
    file_path = files[0]
    print(f"Analyzing file: {file_path}")
    try:
        df = pd.read_csv(file_path)
        print(f"Total Rows: {len(df)}")
        if 'sus' in df.columns:
            print(f"Suspect (sus): {df['sus'].value_counts().to_dict()}")
        if 'evil' in df.columns:
            print(f"Evil (evil): {df['evil'].value_counts().to_dict()}")
        
        if 'processName' in df.columns:
            print(f"Unique Process Names: {df['processName'].nunique()}")
            print(f"Top 5 Processes: {df['processName'].value_counts().head(5).to_dict()}")
        
        if 'hostName' in df.columns:
            print(f"Hosts: {df['hostName'].unique()}")
        
        if 'SensorId' in df.columns: # DNS logs use SensorId
            print(f"Sensor IDs: {df['SensorId'].unique()}")
            
    except Exception as e:
        print(f"Error reading {file_path}: {e}")
    print("\n")
