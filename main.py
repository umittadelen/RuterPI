import requests
import json

def test_entur_alerts():
    url = "https://api.entur.io/journey-planner/v3/graphql"
    
    # The specific stop ID for Fornebuveien
    stop_id = "NSR:StopPlace:3621"
    
    # This query looks for situations in TWO places: 
    # 1. Directly under stopPlace (Station-wide alerts)
    # 2. Under serviceJourney (Individual bus alerts)
    query = f'''{{
      stopPlace(id: "{stop_id}") {{
        name
        situations {{
          summary {{ value }}
        }}
        estimatedCalls(numberOfDepartures: 10) {{
          expectedDepartureTime
          destinationDisplay {{ frontText }}
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

    headers = {"ET-Client-Name": "api-alert-tester"}
    
    print(f"--- Fetching data for {stop_id} ---")
    
    try:
        response = requests.post(url, json={'query': query}, headers=headers, timeout=10)
        
        if response.status_code != 200:
            print(f"Error: API returned status {response.status_code}")
            return

        data = response.json()
        stop_place = data['data']['stopPlace']
        
        print(f"\nSTOP NAME: {stop_place['name']}")
        
        # 1. Check Station-Wide Situations
        print("\n[ STATION-WIDE ALERTS ]")
        stop_situations = stop_place.get('situations', [])
        if not stop_situations:
            print("No station-wide alerts found.")
        else:
            for s in stop_situations:
                print(f"⚠️ ALERT: {s['summary'][0]['value']}")

        # 2. Check Individual Bus Situations
        print("\n[ INDIVIDUAL BUS ALERTS ]")
        calls = stop_place.get('estimatedCalls', [])
        found_bus_alert = False
        
        for c in calls:
            line = c['serviceJourney']['line']['publicCode']
            dest = c['destinationDisplay']['frontText']
            bus_situations = c['serviceJourney'].get('situations', [])
            
            if bus_situations:
                found_bus_alert = True
                for s in bus_situations:
                    print(f"🚌 LINE {line} to {dest}: {s['summary'][0]['value']}")
        
        if not found_bus_alert:
            print("No individual bus alerts found.")

    except Exception as e:
        print(f"Connection failed: {e}")

if __name__ == "__main__":
    test_entur_alerts()