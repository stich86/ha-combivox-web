"""Standalone parser regressions; run with python3 -m unittest discover -s tests.

Uses a namespace package to avoid importing Home Assistant's integration setup.
Fixtures preserve only the observed zone bytes and layout, not private payloads.
"""
import importlib.util
import os
from pathlib import Path
import sys
import types
import unittest

ROOT = next(p for p in Path(__file__).resolve().parents
            if (p / 'custom_components' / 'combivox_web').is_dir())
COMPONENT = ROOT / 'custom_components' / 'combivox_web'
PACKAGE = '_combivox_zone_tests'
pkg = types.ModuleType(PACKAGE)
pkg.__path__ = [str(COMPONENT)]
sys.modules[PACKAGE] = pkg
for name in ('const', 'xml_parser'):
    path = Path(os.environ.get('COMBIVOX_TEST_PARSER', COMPONENT / 'xml_parser.py')) if name == 'xml_parser' else COMPONENT / 'const.py'
    spec = importlib.util.spec_from_file_location(f'{PACKAGE}.{name}', path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
Parser = module.CombivoxXMLParser
VARIANT = 'Elisa 24 GSM + SmartWeb'


def payload(marker=96, length=1506, writes=()):
    chars = list('0' * length)
    chars[marker:marker + 6] = 'FFFFFF'
    chars[marker - 32:marker - 30] = '08'
    for pos, value in writes:
        chars[pos:pos + len(value)] = value
    return '<root><si>' + ''.join(chars) + '</si></root>'


def parse(xml, variant=VARIANT, ids=None):
    return Parser.parse_status_xml(xml, zone_ids=ids or list(range(9, 19)), device_variant=variant)


class ZoneOpenTests(unittest.TestCase):
    def test_observed_contacts_and_motion(self):
        # Independent expected mapping from the physical test, September 12.
        for zid, offset, raw in [(10,112,'02'), (11,112,'04'), (13,112,'10'),
                                 (14,112,'20'), (15,112,'40'), (16,112,'80'),
                                 (17,114,'01'), (18,114,'02')]:
            with self.subTest(zone=zid):
                active = parse(payload(writes=[(offset, raw)]))['zones']
                self.assertEqual([z for z, v in active.items() if v['open']], [zid])
                self.assertFalse(parse(payload())['zones'][zid]['open'])

    def test_simultaneous_contact_and_motion(self):
        zones = parse(payload(writes=[(112,'04'), (114,'02')]))['zones']
        self.assertEqual([z for z, v in zones.items() if v['open']], [11,18])

    def test_armed_and_disarmed_areas(self):
        for mask in ('0000','0001'):
            with self.subTest(mask=mask):
                result = parse(payload(writes=[(84,mask),(114,'02')]))
                self.assertTrue(result['zones'][18]['open'])
                self.assertEqual(result['armed_areas'], [1] if mask == '0001' else [])

    def test_unknown_and_other_models_keep_legacy_mapping(self):
        for variant in (None, '', 'Amica 64 LTE + AmicaWeb Plus',
                        'Elisa 24 LTE + SmartWeb', 'Elisa 24 GSM + AmicaWeb Plus'):
            with self.subTest(variant=variant):
                zones = parse(payload(writes=[(110,'01'),(114,'02')]), variant)['zones']
                self.assertTrue(zones[17]['open'])
                self.assertFalse(zones[18]['open'])

    def test_unverified_layout_keeps_legacy_mapping(self):
        for marker, length in ((64,1506),(96,1504),(96,1508)):
            with self.subTest(marker=marker,length=length):
                xml = payload(marker,length,[(marker+14,'01'),(marker+18,'02')])
                zones = parse(xml)['zones']
                self.assertTrue(zones[17]['open'])
                self.assertFalse(zones[18]['open'])

    def test_inclusion_memory_and_other_fields_are_unchanged(self):
        # Deliberately conflicting bytes at old and shifted metadata offsets.
        xml = payload(writes=[(110,'01'),(114,'02'),(192,'04'),(196,'80'),
                              (1424,'04'),(1428,'80'),(84,'0001')])
        legacy, fixed = parse(xml,None), parse(xml)
        self.assertNotEqual(legacy['zones'][18]['open'],fixed['zones'][18]['open'])
        self.assertTrue(fixed['zones'][11]['included'])
        self.assertTrue(fixed['zones'][11]['alarm_memory'])
        for result in (legacy,fixed):
            for zone in result['zones'].values():
                zone.pop('open')
        self.assertEqual(legacy,fixed)

    def test_sparse_zone_configuration(self):
        result = parse(payload(writes=[(114,'02')]), ids=[11,18])
        self.assertEqual(set(result['zones']), {11,18})
        self.assertTrue(result['zones'][18]['open'])

    def test_legacy_marker_boundary_zone_ids(self):
        for zid in (1,8,9,16,17,24,64,128,320):
            for marker in (64,96):
                with self.subTest(zone=zid,marker=marker):
                    offset = marker+10+2*((zid-1)//8)
                    raw = f'{1 << ((zid-1)%8):02X}'
                    result = parse(payload(marker=marker,writes=[(offset,raw)]),None,[zid])
                    self.assertTrue(result['zones'][zid]['open'])


if __name__ == '__main__':
    unittest.main()
