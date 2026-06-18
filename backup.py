import requests

url = "https://api.entur.io/journey-planner/v3/graphql"

query = """
{
  stopPlace(id: "NSR:StopPlace:6008") {
    name
    estimatedCalls(numberOfDepartures: 10) {
      aimedDepartureTime
      expectedDepartureTime
      realtime
      destinationDisplay {
        frontText
      }
      serviceJourney {
        line {
          publicCode
        }
      }
    }
  }
}
"""

r = requests.post(
    url,
    headers={
        "ET-Client-Name": "test-app",
        "Content-Type": "application/json"
    },
    json={"query": query}
)

print(r.json())