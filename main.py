import requests
import json

def fetch_transit_alerts(stop_id):
    url = "https://api.entur.io/journey-planner/v3/graphql"
    
    # This query scans the three "Truth levels":
    # 1. StopPlace (Station level - e.g., "The stop is closed")
    # 2. ServiceJourney (Trip level - e.g., "This specific bus is delayed")
    # 3. Line (Route level - e.g., "Line 31 is diverted due to roadwork")
    query = f'''{{
      stopPlace(id: "{stop_id}") {{
        name
        situations {{
          summary {{ value }}
          description {{ value }}
        }}
        estimatedCalls(numberOfDepartures: 50) {{
          serviceJourney {{
            line {{
              publicCode
              situations {{
                summary {{ value }}
                description {{ value }}
              }}
            }}
            situations {{
              summary {{ value }}
            }}
          }}
        }}
      }}
    }}'''

    headers = {"ET-Client-Name": "pro-alert-scanner"}
    
    try:
        response = requests.post(url, json={'query': query}, headers=headers, timeout=10)
        data = response.json()['data']['stopPlace']
        
        print(f"=== SCANNING: {data['name']} ({stop_id}) ===")

        # Using a set to automatically deduplicate alerts
        all_unique_alerts = set()

        # --- LEVEL 1: STATION ALERTS ---
        for sit in data.get('situations', []):
            txt = sit['summary'][0]['value']
            all_unique_alerts.add(f"[STATION] {txt}")

        # --- LEVEL 2 & 3: TRIP & LINE ALERTS ---
        calls = data.get('estimatedCalls', [])
        for c in calls:
            sj = c.get('serviceJourney', {})
            line = sj.get('line', {})
            line_code = line.get('publicCode', '??')

            # Check Line-wide alerts (Most common for "Arrangements" or "Divertions")
            for sit in line.get('situations', []):
                txt = sit['summary'][0]['value']
                all_unique_alerts.add(f"[LINE {line_code}] {txt}")

            # Check Trip-specific alerts
            for sit in sj.get('situations', []):
                txt = sit['summary'][0]['value']
                all_unique_alerts.add(f"[VEHICLE {line_code}] {txt}")

        # --- RESULTS ---
        if not all_unique_alerts:
            print("\n✅ No active alerts found for this stop or any passing lines.")
        else:
            print(f"\n⚠️ FOUND {len(all_unique_alerts)} UNIQUE ALERTS:\n")
            for i, alert in enumerate(all_unique_alerts, 1):
                print(f"{i}. {alert}")

    except Exception as e:
        print(f"Network error: {e}")

if __name__ == "__main__":
    # Test for Fornebuveien
    fetch_transit_alerts("NSR:StopPlace:3621")