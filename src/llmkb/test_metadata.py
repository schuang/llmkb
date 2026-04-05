#!/usr/bin/env python3
import argparse
import json
from llmkb.metadata_resolver import resolve_doi, resolve_isbn

def parse_args():
    parser = argparse.ArgumentParser(description="Test live metadata resolution for a specific DOI or ISBN.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--doi", help="The DOI to resolve (e.g., 10.1063/1.869966)")
    group.add_argument("--isbn", help="The ISBN to resolve (e.g., 0486661105)")
    return parser.parse_args()

def main():
    args = parse_args()
    
    print(f"Querying live API for {'DOI' if args.doi else 'ISBN'}...")
    if args.doi:
        result = resolve_doi(args.doi)
    else:
        result = resolve_isbn(args.isbn)
        
    if result:
        print("\n--- Metadata Found ---")
        print(json.dumps(result, indent=2))
    else:
        print("\nNo metadata found or API request failed.")

if __name__ == "__main__":
    main()
