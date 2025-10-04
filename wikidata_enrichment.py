#!/usr/bin/env python3
"""
Test script for enriching entities with Wikidata coordinates and dates
"""

import requests
import json
import time
from urllib.parse import quote

class WikidataEnricher:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'KindleLLM/1.0 (https://github.com/user/kindlellm) Python/3.x'
        })

    def search_entity(self, entity_name, limit=3):
        """Search for an entity in Wikidata"""
        url = "https://www.wikidata.org/w/api.php"
        params = {
            'action': 'wbsearchentities',
            'search': entity_name,
            'language': 'en',
            'format': 'json',
            'limit': limit
        }

        try:
            response = self.session.get(url, params=params)
            response.raise_for_status()
            return response.json().get('search', [])
        except Exception as e:
            print(f"Error searching for {entity_name}: {e}")
            return []

    def get_entity_data(self, qid):
        """Get detailed data for a Wikidata entity"""
        url = "https://www.wikidata.org/w/api.php"
        params = {
            'action': 'wbgetentities',
            'ids': qid,
            'format': 'json',
            'props': 'claims|labels|descriptions'
        }

        try:
            response = self.session.get(url, params=params)
            response.raise_for_status()
            data = response.json()
            return data.get('entities', {}).get(qid, {})
        except Exception as e:
            print(f"Error getting data for {qid}: {e}")
            return {}

    def extract_coordinates(self, claims):
        """Extract coordinates from Wikidata claims"""
        # P625 is "coordinate location"
        coords = claims.get('P625', [])
        if coords:
            coord_claim = coords[0]
            if 'mainsnak' in coord_claim and coord_claim['mainsnak'].get('snaktype') == 'value':
                coord_data = coord_claim['mainsnak']['datavalue']['value']
                return {
                    'latitude': coord_data['latitude'],
                    'longitude': coord_data['longitude'],
                    'precision': coord_data.get('precision', 0.001)
                }
        return None

    def extract_dates(self, claims):
        """Extract birth/death dates or other temporal data"""
        dates = {}

        # P569 = date of birth, P570 = date of death
        # P571 = inception, P576 = dissolved/abolished
        date_properties = {
            'P569': 'birth_date',
            'P570': 'death_date',
            'P571': 'inception_date',
            'P576': 'dissolution_date',
            'P585': 'point_in_time'  # Generic date property
        }

        for prop_id, date_type in date_properties.items():
            if prop_id in claims:
                date_claims = claims[prop_id]
                if date_claims:
                    date_claim = date_claims[0]
                    if 'mainsnak' in date_claim and date_claim['mainsnak'].get('snaktype') == 'value':
                        date_value = date_claim['mainsnak']['datavalue']['value']
                        dates[date_type] = date_value['time']

        return dates

    def enrich_entity(self, entity_name):
        """Full enrichment pipeline for an entity"""
        print(f"\n=== Enriching: {entity_name} ===")

        # Search for the entity
        search_results = self.search_entity(entity_name)
        if not search_results:
            print(f"No results found for {entity_name}")
            return None

        # Show search results
        print("Search results:")
        for i, result in enumerate(search_results):
            desc = result.get('description', 'No description')
            print(f"  {i+1}. {result['label']} ({result['id']}) - {desc}")

        # Use the first result (highest confidence)
        best_match = search_results[0]
        qid = best_match['id']

        # Get detailed data
        entity_data = self.get_entity_data(qid)
        if not entity_data:
            print(f"Could not get detailed data for {qid}")
            return None

        # Extract enrichment data
        claims = entity_data.get('claims', {})
        coordinates = self.extract_coordinates(claims)
        dates = self.extract_dates(claims)

        # Build enriched entity
        enriched = {
            'original_name': entity_name,
            'wikidata_id': qid,
            'wikidata_label': best_match['label'],
            'description': best_match.get('description', ''),
            'coordinates': coordinates,
            'dates': dates,
            'wikidata_url': f"https://www.wikidata.org/entity/{qid}"
        }

        print(f"Coordinates: {coordinates}")
        print(f"Dates: {dates}")

        return enriched

def test_entities():
    """Test enrichment on sample entities from the knowledge graph"""

    # Sample entities from your dataset
    test_entities = [
        "murray-rothbard",
        "great-britain",
        "europe",
        "the-industrial-revolution"
    ]

    enricher = WikidataEnricher()
    results = {}

    for entity in test_entities:
        # Clean up entity name for search
        clean_name = entity.replace('-', ' ').replace('_', ' ').title()
        if clean_name.startswith('The '):
            clean_name = clean_name[4:]  # Remove "The " prefix

        enriched = enricher.enrich_entity(clean_name)
        if enriched:
            results[entity] = enriched

        # Be nice to Wikidata API
        time.sleep(0.5)

    return results

def generate_map_data(enriched_entities):
    """Generate data structure for map visualization"""
    map_features = []

    for entity_id, data in enriched_entities.items():
        if data['coordinates']:
            feature = {
                'type': 'Feature',
                'properties': {
                    'name': data['wikidata_label'],
                    'original_id': entity_id,
                    'description': data['description'],
                    'dates': data['dates'],
                    'wikidata_url': data['wikidata_url']
                },
                'geometry': {
                    'type': 'Point',
                    'coordinates': [
                        data['coordinates']['longitude'],
                        data['coordinates']['latitude']
                    ]
                }
            }
            map_features.append(feature)

    return {
        'type': 'FeatureCollection',
        'features': map_features
    }

if __name__ == "__main__":
    print("Testing Wikidata enrichment...")

    # Run the test
    enriched = test_entities()

    # Save results
    with open('enriched_entities.json', 'w') as f:
        json.dump(enriched, f, indent=2)

    # Generate map data
    map_data = generate_map_data(enriched)
    with open('map_data.geojson', 'w') as f:
        json.dump(map_data, f, indent=2)

    print(f"\nEnriched {len(enriched)} entities")
    print("Results saved to:")
    print("- enriched_entities.json")
    print("- map_data.geojson")

    # Show summary
    print("\n=== SUMMARY ===")
    for entity_id, data in enriched.items():
        coords = data['coordinates']
        dates = data['dates']
        coord_str = f"({coords['latitude']:.3f}, {coords['longitude']:.3f})" if coords else "No coordinates"
        date_str = ", ".join([f"{k}: {v}" for k, v in dates.items()]) if dates else "No dates"
        print(f"{entity_id}: {coord_str} | {date_str}")