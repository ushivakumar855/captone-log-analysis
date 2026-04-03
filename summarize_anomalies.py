import pandas as pd
import os
import glob

all_folders = [d for d in os.listdir('.') if os.path.isdir(d) and d[0].isdigit()]
all_folders.sort(key=lambda x: int(x.split('_')[0]))

summary = []

for folder in all_folders:
    files = glob.glob(os.path.join(folder, '*.csv'))
    total_sus = 0
    total_evil = 0
    total_rows = 0
    
    for f in files:
        try:
            # We only read the relevant columns to save time
            cols = pd.read_csv(f, nrows=0).columns
            cols_to_use = [c for c in cols if c.lower() in ['sus', 'evil']]
            if cols_to_use:
                # Still reading the whole file to count... 
                # but maybe just sus/evil is faster.
                df = pd.read_csv(f, usecols=cols_to_use)
                total_rows += len(df)
                if 'sus' in df.columns:
                    total_sus += df['sus'].sum()
                elif 'Suspect' in df.columns:
                    total_sus += df['Suspect'].sum()
                elif 'sus' in [c.lower() for c in df.columns]:
                     # handle case sensitivity
                     col = [c for c in df.columns if c.lower() == 'sus'][0]
                     total_sus += df[col].sum()

                if 'evil' in df.columns:
                    total_evil += df['evil'].sum()
                elif 'Evil' in df.columns:
                    total_evil += df['Evil'].sum()
                elif 'evil' in [c.lower() for c in df.columns]:
                     col = [c for c in df.columns if c.lower() == 'evil'][0]
                     total_evil += df[col].sum()
        except Exception:
            pass
            
    summary.append({
        'folder': folder,
        'total_rows': total_rows,
        'total_sus': total_sus,
        'total_evil': total_evil
    })

df_summary = pd.DataFrame(summary)
print(df_summary.to_string(index=False))
