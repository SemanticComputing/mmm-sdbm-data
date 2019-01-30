#!/usr/bin/env python3
#  -*- coding: UTF-8 -*-
"""Linking places to GeoNames and TGN"""

import argparse
import logging
import os
import pprint
from collections import defaultdict
from decimal import Decimal
import unittest

import copy
from rdflib import Graph, URIRef, Literal, RDF, Namespace, OWL
from rdflib.compare import graph_diff
from rdflib.util import guess_format

from geonames import GeoNamesAPI
from linker import handle_tgn_places
from tgn import TGN
from namespaces import *


class TestLinker(unittest.TestCase):

    test_sdbm_data = """
    @prefix :      <https://sdbm.library.upenn.edu/> .
    @prefix wgs:   <http://www.w3.org/2003/01/geo/wgs84_pos#> .
    @prefix mmm-schema: <http://ldf.fi/mmm/schema/> .
    @prefix dct:   <http://purl.org/dc/terms/> .
    @prefix rdf:   <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
    @prefix owl:   <http://www.w3.org/2002/07/owl#> .
    @prefix afn:   <http://jena.hpl.hp.com/ARQ/function#> .
    @prefix skos:  <http://www.w3.org/2004/02/skos/core#> .
    @prefix rdfs:  <http://www.w3.org/2000/01/rdf-schema#> .
    @prefix mmm:   <http://ldf.fi/mmm/> .
    @prefix crm:   <http://www.cidoc-crm.org/cidoc-crm/> .
    @prefix frbroo: <http://erlangen-crm.org/efrbroo/> .
    
    <http://ldf.fi/mmm/production/orphan_61316>
        a                      crm:E12_Production ;
        dct:source             mmm-schema:SDBM ;
        crm:P108_has_produced  <http://ldf.fi/mmm/manifestation_singleton/orphan_61316> ;
        crm:P4_has_time-span   <http://ldf.fi/mmm/timespan/59403> ;
        crm:P7_took_place_at   <http://ldf.fi/mmm/places/2121> .

    <http://ldf.fi/mmm/places/2121>
            a                             crm:E53_Place ;
            mmm-schema:data_provider_url  <https://sdbm.library.upenn.edu/places/2121> ;
            dct:source                    mmm-schema:SDBM ;
            crm:P89_falls_within          <http://ldf.fi/mmm/places/214> ;
            owl:sameAs                    <http://vocab.getty.edu/tgn/1005755> ;
            wgs:lat                       51.5833 ;
            wgs:long                      -0.0833 ;
            skos:prefLabel                "Tottenham" .

    <http://ldf.fi/mmm/places/1012>
            a                             crm:E53_Place ;
            mmm-schema:data_provider_url  <https://sdbm.library.upenn.edu/places/1012> ;
            dct:source                    mmm-schema:SDBM ;
            crm:P89_falls_within          <http://ldf.fi/mmm/places/3991> ;
            owl:sameAs                    <http://vocab.getty.edu/tgn/7005560> ;
            wgs:lat                       "23"^^<http://www.w3.org/2001/XMLSchema#decimal> ;
            wgs:long                      "-102"^^<http://www.w3.org/2001/XMLSchema#decimal> ;
            skos:prefLabel                "Mexico" .
    """

    test_bodley_data = """
    @prefix :      <https://sdbm.library.upenn.edu/> .
    @prefix wgs:   <http://www.w3.org/2003/01/geo/wgs84_pos#> .
    @prefix mmm-schema: <http://ldf.fi/mmm/schema/> .
    @prefix dct:   <http://purl.org/dc/terms/> .
    @prefix rdf:   <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
    @prefix owl:   <http://www.w3.org/2002/07/owl#> .
    @prefix afn:   <http://jena.hpl.hp.com/ARQ/function#> .
    @prefix skos:  <http://www.w3.org/2004/02/skos/core#> .
    @prefix rdfs:  <http://www.w3.org/2000/01/rdf-schema#> .
    @prefix mmm:   <http://ldf.fi/mmm/> .
    @prefix crm:   <http://www.cidoc-crm.org/cidoc-crm/> .
    @prefix frbroo: <http://erlangen-crm.org/efrbroo/> .
    
    <https://medieval.bodleian.ox.ac.uk/catalog/place_1029598>
            a                             crm:E53_Place ;
            mmm-schema:data_provider_url  <https://medieval.bodleian.ox.ac.uk/catalog/place_1029598> ;
            dct:source                    mmm-schema:Bodley ;
            crm:P89_falls_within          <https://medieval.bodleian.ox.ac.uk/catalog/place_place_7002445> ;
            wgs:lat                       "51.983333" ;
            wgs:long                      "-1.483333" ;
            owl:sameAs <http://vocab.getty.edu/tgn/7011931> ;
            skos:altLabel                 "Hochenartone" , "Hook Norton, Oxfordshire" ;
            skos:prefLabel                "Hook Norton, Oxfordshire" .

    <https://medieval.bodleian.ox.ac.uk/catalog/place_7002445>
            a                             crm:E53_Place ;
            mmm-schema:data_provider_url  <https://medieval.bodleian.ox.ac.uk/catalog/place_7002445> ;
            dct:source                    mmm-schema:Bodley ;
            wgs:lat                       "53.0" ;
            wgs:long                      "-2.0" ;
            skos:altLabel                 "Angleterre" , "English"@en , "English" , "Britannia Romana" , "Inglaterra" , "Britannia propria" , "Anglia" , "Britannia maior" , "Inghilterra" , "Engleterre" , "England"@en , "England" ;
            skos:prefLabel                "England" .

    <https://medieval.bodleian.ox.ac.uk/catalog/manuscript_3947/production>
            a                      crm:E12_Production ;
            dct:source             mmm-schema:Bodley ;
            crm:P108_has_produced  <https://medieval.bodleian.ox.ac.uk/catalog/manuscript_3947> ;
            crm:P4_has_time-span   <https://medieval.bodleian.ox.ac.uk/catalog/manuscript_3947/production-time-span> ;
            crm:P7_took_place_at   <https://medieval.bodleian.ox.ac.uk/catalog/place_1029598> , 
                                   <https://medieval.bodleian.ox.ac.uk/catalog/place_7002445> .

    <https://medieval.bodleian.ox.ac.uk/catalog/manuscript_3947>
            a                             frbroo:F4_Manifestation_Singleton ;
            mmm-schema:data_provider_url  <https://medieval.bodleian.ox.ac.uk/catalog/manuscript_3947> ;
            mmm-schema:manuscript_work    <https://medieval.bodleian.ox.ac.uk/catalog/work_16002> ;
            dct:source                    mmm-schema:Bodley ;
            crm:P128_carries              <https://medieval.bodleian.ox.ac.uk/catalog/manuscript_3947%23Christ_Church_MS_343-item1/expression> ;
            crm:P51_has_former_or_current_owner
                    <https://medieval.bodleian.ox.ac.uk/catalog/person_37261411> , <https://medieval.bodleian.ox.ac.uk/catalog/person_2677> , <https://medieval.bodleian.ox.ac.uk/catalog/org_155836576> ;
            skos:prefLabel                "Christ Church MS. 343"@en .
    """

    def test_handle_tgn_places_sdbm(self):
        place1 = URIRef('http://ldf.fi/mmm/places/2121')

        g = Graph()
        g.parse(data=self.test_sdbm_data, format='turtle')

        places = Graph()

        self.assertIsNotNone(g.value(place1, SKOS.prefLabel))

        GEONAMES_APIKEYS = [os.environ['GEONAMES_KEY']]
        geo = GeoNamesAPI(GEONAMES_APIKEYS)
        tgn = TGN()

        g, places = handle_tgn_places(geo, tgn, g, places, 'sdbm_', MMMS.SDBM)

        self.assertIsNone(g.value(place1, SKOS.prefLabel))

        self.assertEquals(len(list(places.triples((None, RDF.type, CRM.E53_Place)))), 2)
        self.assertEquals(len(list(places.triples((None, MMMS.tgn_uri, None)))), 2)

        self.assertEquals(len(list(g.triples((None, RDF.type, CRM.E53_Place)))), 0)
        self.assertEquals(len(list(g.triples((None, CRM.P7_took_place_at, None)))), 1)
        self.assertEquals(len(list(g.triples((None, CRM.P7_took_place_at, URIRef('http://ldf.fi/mmm/places/tgn_1005755'))))), 1)

    def test_handle_tgn_places_bodley(self):
        place1 = URIRef('https://medieval.bodleian.ox.ac.uk/catalog/place_1029598')

        g = Graph()
        g.parse(data=self.test_bodley_data, format='turtle')

        places = Graph()

        self.assertIsNotNone(g.value(place1, SKOS.prefLabel))

        GEONAMES_APIKEYS = [os.environ['GEONAMES_KEY']]
        geo = GeoNamesAPI(GEONAMES_APIKEYS)
        tgn = TGN()

        g, places = handle_tgn_places(geo, tgn, g, places, 'bodley_', MMMS.Bodley)

        pprint.pprint(list(places))

        self.assertIsNone(g.value(place1, SKOS.prefLabel))

        self.assertEquals(len(list(places.triples((None, RDF.type, CRM.E53_Place)))), 2)
        self.assertEquals(len(list(places.triples((None, RDF.type, CRM.E53_Place)))), 2)
        self.assertEquals(len(list(places.triples((None, MMMS.tgn_uri, None)))), 1)

        self.assertEquals(len(list(g.triples((None, RDF.type, CRM.E53_Place)))), 0)
        self.assertEquals(len(list(g.triples((None, CRM.P7_took_place_at, None)))), 2)

        pprint.pprint(list(g.triples((None, CRM.P7_took_place_at, None))))

        self.assertEquals(len(list(g.triples((None, CRM.P7_took_place_at, URIRef('http://ldf.fi/mmm/places/tgn_7011931'))))), 1)