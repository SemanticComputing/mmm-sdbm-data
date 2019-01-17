#!/usr/bin/env python3
#  -*- coding: UTF-8 -*-
"""Linking Bibale places"""

import argparse
from collections import defaultdict
import logging

import os

import geocoder
from decimal import Decimal

import pycountry
from rdflib import Graph, URIRef, Literal, RDF, Namespace, OWL
from rdflib.util import guess_format

GEONAMES_APIKEY = os.environ['GEONAMES_KEY']

CRM = Namespace('http://www.cidoc-crm.org/cidoc-crm/')
DCT = Namespace('http://purl.org/dc/terms/')
SKOS = Namespace('http://www.w3.org/2004/02/skos/core#')
GEO = Namespace('http://www.geonames.org/ontology#')
WGS84 = Namespace('http://www.w3.org/2003/01/geo/wgs84_pos#')

MMMS = Namespace('http://ldf.fi/mmm/schema/')
MMMP = Namespace('http://ldf.fi/mmm/places/')

log = logging.getLogger(__name__)


def generate_place_key(country: str, region: str, settlement: str):
    """Generate a key for the place from country, region and settlement"""
    return country.lower().strip(), region.lower().strip(), settlement.lower().strip()


def group_places(graph: Graph):
    """Group places into a dict"""
    places = defaultdict(list)

    for place in graph[:RDF.type:CRM.E53_Place]:
        place_country = str(graph.value(place, MMMS.bibale_country, default=''))
        place_region = str(graph.value(place, MMMS.bibale_region, default=''))
        place_settlement = str(graph.value(place, MMMS.bibale_settlement, default=''))
        place_authority_uri = graph.value(place, OWL.sameAs)

        key = generate_place_key(place_country, place_region, place_settlement)

        places[key].append((place_country, place_region, place_settlement, place, place_authority_uri))

    return places


def redirect_refs(graph: Graph, old_uris: list, new_uri: URIRef):
    """Remove old instances and redirect old URI references to the new URI"""
    for uri in old_uris:
        for s, p in graph.subject_predicates(uri):
            graph.add((s, p, new_uri))

        graph.remove((None, None, uri))
        graph.remove((uri, None, None))

    return graph


def query_geonames(q, **kwargs):
    g = None
    while (not hasattr(g, 'status')) or ('Read timed out' in g.status):
        g = geocoder.geonames(q, **kwargs, key=GEONAMES_APIKEY)

    return g or None


def get_geonames_data(geonames_id: str):
    """Fetch data from GeoNames API based on GeoNames ID"""
    if not geonames_id:
        return {}

    log.info('Fetching data for GeoNames id %s' % geonames_id)
    g = query_geonames(geonames_id, method='details')

    if g.status != 'OK':
        return {}

    wikipedia = ('https://' + g.wikipedia) if hasattr(g, 'wikipedia') and g.wikipedia else None

    return {'lat': g.lat,
            'lon': g.lng,
            'feature_class': g.feature_class,
            'class_description': g.class_description,
            'wikipedia': wikipedia,
            'address': g.address,
            'adm1': g.state,
            'country': g.country,
            'name': g.address,
            'id': g.geonames_id
            }


def search_geonames_country(country: str):
    """
    Search for a country in any language and return it's English label

    >>> search_geonames_country('Allemagne')
    'Germany'
    >>> search_geonames_country('Foo') is None
    True
    """

    g = query_geonames(country)

    if g is None or g.address != g.country:
        # Received None or a too specific place, ignore it
        log.info('Country not found for %s' % country)
        return None

    return g.country


def search_geonames_place(country: str, region: str, settlement: str):
    """
    Search for a place from GeoNames API and return place data

    >>> search_geonames_place('Royaume Uni / Angleterre',  'Dorset', 'Abbotsbury').get('wikipedia')
    'https://en.wikipedia.org/wiki/Abbotsbury'
    """
    COUNTRY_MAP = {
        "Vatican City": "Holy See (Vatican City State)",
    }

    if (not region) or (not settlement):
        log.info('Place search with lacking information: %s - %s' % (country, region or settlement or ''))

    country_en = search_geonames_country(country)

    kw_params = dict(featureClass=['A', 'P'])
                     # name=settlement or region or country)
    if country_en:
        q = '%s %s' % (region, settlement)
        country_en = COUNTRY_MAP.get(country_en, country_en)
        pyc = pycountry.countries.get(name=country_en)
        if not pyc:
            log.warning('Country not found in pycountry: %s - %s' % (country, country_en))
        kw_params['country'] = pyc.alpha_2 if pyc else country_en
    else:
        q = '%s %s %s' % (country, region, settlement)

    g = query_geonames(q, **kw_params)

    return get_geonames_data(g.geonames_id) if g else None


def handle_places(graph: Graph):
    """Modify places and create new instances"""
    places = group_places(graph)

    log.info('Got %s places.' % len(places))

    for (key, place_data) in places.items():
        # Get most common values (any of them) for place literals and authority URI
        countries, regions, settlements, old_uris, authority_uris = zip(*place_data)

        country = max(set(countries), key=countries.count)
        region = max(set(regions), key=regions.count)
        settlement = max(set(settlements), key=settlements.count)
        authority_uri_set = set(authority_uris) - {None}
        authority_uri = max(authority_uri_set, key=authority_uris.count) if authority_uri_set else None

        place_label = settlement or region or country
        place_type = graph.value(old_uris[0], MMMS.place_type)

        # Fetch GeoNames data based on GeoNames id
        geo = None
        if authority_uri:
            geo = get_geonames_data(str(authority_uri).split('/')[-1])

        if not geo:
            geo = search_geonames_place(country, region, settlement)

        if geo:
            place_label = geo.get('name') or place_label
            authority_uri = 'http://sws.geonames.org/%s' % geo.get('id')
        else:
            log.info('No GeoNames ID found for %s, %s, %s' % (country, region, settlement))

        # Mint new URI
        uri = MMMP['bibale_' + str(sorted(old_uris)[0]).split(':')[-1]]

        # Modify graph
        graph = redirect_refs(graph, old_uris, uri)

        if authority_uri:
            graph.add((uri, OWL.sameAs, URIRef(authority_uri)))
        if country:
            graph.add((uri, MMMS.bibale_country, Literal(country)))
        if region:
            graph.add((uri, MMMS.bibale_region, Literal(region)))
        if settlement:
            graph.add((uri, MMMS.bibale_settlement, Literal(settlement)))

        graph.add((uri, RDF.type, CRM.E53_Place))
        graph.add((uri, MMMS.place_type, place_type))
        graph.add((uri, DCT.source, MMMS.Bibale))
        graph.add((uri, SKOS.prefLabel, Literal(place_label)))

        if geo:
            graph.add((uri, WGS84.lat, Literal(Decimal(geo['lat']))))
            graph.add((uri, WGS84.long, Literal(Decimal(geo['lon']))))
            graph.add((uri, GEO.featureClass, Literal(geo['feature_class'])))
            graph.add((uri, MMMS.geonames_class_description, Literal(geo['class_description'])))
            if geo.get('wikipedia'):
                graph.add((uri, GEO.wikipediaArticle, URIRef(geo['wikipedia'])))
            graph.add((uri, GEO.name, Literal(geo['address'])))
            graph.add((uri, GEO.parentADM1, Literal(geo['adm1'])))
            graph.add((uri, MMMS.geonames_country_code, Literal(geo['country'])))
            graph.add((uri, DCT.source, URIRef('http://www.geonames.org')))

    return graph


def main():
    argparser = argparse.ArgumentParser(description=__doc__, fromfile_prefix_chars='@')

    argparser.add_argument("input", help="Input RDF file")
    argparser.add_argument("output", help="Output RDF file")
    argparser.add_argument("--loglevel", default='INFO', help="Logging level",
                           choices=["NOTSET", "DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"])
    argparser.add_argument("--logfile", default='tasks.log', help="Logfile")

    args = argparser.parse_args()

    log = logging.getLogger()  # Get root logger
    log_handler = logging.StreamHandler()
    log_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
    log.addHandler(log_handler)
    log.setLevel(args.loglevel)

    input_graph = Graph()
    input_graph.parse(args.input, format=guess_format(args.input))

    handle_places(input_graph).serialize(args.output, format=guess_format(args.output))


if __name__ == '__main__':
    main()