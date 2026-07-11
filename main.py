import requests
import json

def fetch_transit_alerts_pro(stop_id):
    url = "https://api.entur.io/journey-planner/v3/graphql"
    
    # We ask for:
    # 1. StopPlace situations (Station-wide)
    # 2. Line situations (For every line passing through)
    # 3. Trip situations (Specific to the vehicle)
    query = f'''{{
      stopPlace(id: "{stop_id}") {{
        name
        situations {{
          summary {{ value }}
        }}
        estimatedCalls(numberOfDepartures: 20) {{
          serviceJourney {{
            line {{
              publicCode
              situations {{
                summary {{ value }}
              }}
            }}
            situations {{
              summary {{ value }}
            }}
          }}
        }}
      }}
    }}'''

    headers = {"ET-Client-Name": "pro-kiosk-scanner"}
    
    try:
        r = requests.post(url, json={'query': query}, headers=headers, timeout=10)
        data = r.json()['data']['stopPlace']
        
        all_alerts = set()

        # Check Stop Level
        for s in data.get('situations', []):
            all_alerts.add(s['summary'][0]['value'])

        # Check Line and Trip Level for all scheduled buses
        for c in data.get('estimatedCalls', []):
            sj = c.get('serviceJourney', {})
            # Route level alerts (e.g., Line 31)
            for s in sj.get('line', {}).get('situations', []):
                all_alerts.add(s['summary'][0]['value'])
            # Trip specific alerts
            for s in sj.get('situations', []):
                all_alerts.add(s['summary'][0]['value'])

        if not all_alerts:
            print("No alerts found. (Likely because the 19:30 alert is not yet active in the departure feed).")
        else:
            for i, a in enumerate(all_alerts, 1):
                print(f"{i}. {a}")

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    fetch_transit_alerts_pro("NSR:StopPlace:3621")