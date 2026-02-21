import time, random
import pandas as pd
from tqdm import tqdm
from understatapi import UnderstatClient
from google.cloud import bigquery

# CONFIG
client = bigquery.Client()
DEST_TABLE = "fpl-optima.fpl_bronze.understat_past_match_level"
ID_MAP_URL = "https://raw.githubusercontent.com/ChrisMusson/FPL-ID-Map/main/Master.csv"

BATCH_SIZE = 50  # Number of players to collect before uploading to BigQuery

def get_already_scraped_ids():
    try:
        query = f"SELECT DISTINCT CAST(player_id AS STRING) as id FROM `{DEST_TABLE}`"
        return set(row.id for row in client.query(query))
    except Exception:
        return set()

def main():
    id_df = pd.read_csv(ID_MAP_URL)
    understat_col = [c for c in id_df.columns if 'understat' in c.lower()][0]
    all_understat_ids = id_df[understat_col].dropna().unique().astype(int).astype(str)
    
    scraped_ids = get_already_scraped_ids()
    to_scrape = [i for i in all_understat_ids if i not in scraped_ids]
    
    print(f"Resuming: {len(scraped_ids)} players already in BigQuery.")
    print(f"To Scrape: {len(to_scrape)} players remaining.")

    batch_dfs = []  # Temporary list to hold DataFrames

    try:
        with tqdm(to_scrape, desc="Overall Progress", unit="player") as pbar:
            for i, p_id in enumerate(pbar):
                try:
                    pbar.set_description(f"Scraping Player {p_id}")
                    
                    with UnderstatClient() as understat:
                        data = understat.player(player=p_id).get_match_data()
                        
                        if data:
                            df = pd.DataFrame(data)
                            df['player_id'] = p_id 
                            batch_dfs.append(df)
                    
                    # Upload if batch is full OR if it's the very last player in the list
                    if len(batch_dfs) >= BATCH_SIZE or (i == len(to_scrape) - 1 and batch_dfs):
                        pbar.write(f" Reached batch limit. Uploading {len(batch_dfs)} players to BigQuery...")
                        
                        # Combine all DataFrames in the current batch
                        final_df = pd.concat(batch_dfs, ignore_index=True)
                        
                        # Clean numeric columns to prevent BigQuery schema mismatches
                        cols_to_fix = ['xG', 'xA', 'npg', 'npxG', 'xGChain', 'xGBuildup','goals', 'assists', 'key_passes', 'shots', 'time']
                        for col in cols_to_fix:
                            if col in final_df.columns:
                                final_df[col] = pd.to_numeric(final_df[col], errors='coerce').astype('float64')

                        # Write the batch to BigQuery
                        job_config = bigquery.LoadJobConfig(write_disposition="WRITE_APPEND")
                        client.load_table_from_dataframe(final_df, DEST_TABLE, job_config=job_config).result()
                        
                        batch_dfs = []  # Clear the list for the next batch
                        pbar.write(" Upload successful.")

                    # Random sleep to stay under Understat's radar
                    time.sleep(random.uniform(1.2, 2.8))
                    
                except Exception as e:
                    pbar.write(f" Error on {p_id}: {e}")
                    # If it's a 403 quota error, you might want to stop the script entirely
                    if "403" in str(e):
                        pbar.write(" Quota still exceeded. Try again in a few hours.")
                        break
                    time.sleep(10)

    except KeyboardInterrupt:
        print("\n Manual stop detected. Any un-uploaded data in the current batch was not saved.")

if __name__ == "__main__":
    main()