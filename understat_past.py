from understatapi import UnderstatClient
import pandas as pd
from google.cloud import bigquery

client = bigquery.Client()
TABLE_ID = "fpl-optima.fpl_bronze.understat_historical_all"

def ingest_all_understat():
    with UnderstatClient() as understat:
        # Pull everything from the start of your Vaastav data to the last finished season
        seasons = [str(year) for year in range(2016, 2025)] 
        
        for season in seasons:
            print(f"Syncing Understat {season}...")
            data = understat.league(league="EPL").get_player_data(season=season)
            df = pd.DataFrame(data)
            df['season_start_year'] = season
            
            # Data cleaning for BigQuery
            cols_to_fix = ['xG', 'xA', 'npg', 'npxG', 'xGChain', 'xGBuildup', 'goals', 'assists']
            df[cols_to_fix] = df[cols_to_fix].apply(pd.to_numeric)
            
            job_config = bigquery.LoadJobConfig(write_disposition="WRITE_APPEND")
            client.load_table_from_dataframe(df, TABLE_ID, job_config=job_config).result()

if __name__ == "__main__":
    ingest_all_understat()