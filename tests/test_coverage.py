"""Offline coverage regressions; no live news requests or model download."""
import unittest
from datetime import timedelta
from unittest.mock import patch
import numpy as np
import scripts.update_news as n

class CoverageTests(unittest.TestCase):
    def test_general_signals(self):
        cases=[
            ("Government seizes oilfields after sanctions", "strategic asset intervention"),
            ("Country signs deal to build military drones jointly", "defence industrial agreement"),
            ("Factory blast kills at least 8 workers", "significant accident with human impact"),
            ("Train crash leaves 25 people injured", "significant accident with human impact"),
            ("Researchers warn of systemic risk in frontier AI models", "frontier AI safety development"),
            ("First national astronaut selected for space mission", "historic space milestone"),
            ("Military suicides reach record high according to official figures", "record institutional or health trend"),
        ]
        for title,reason in cases:
            with self.subTest(title=title):
                pts,reasons=n.general_event_signals(title)
                self.assertIn(reason,reasons)
                self.assertGreaterEqual(n.score(title,12,0.5)[0],n.SET["minimum_score"])
        for title in ["Local fire injures one person","New drone goes on sale","AI app adds new theme",
                      "Space mission continues as planned","Annual health report published",
                      "Company opens new office"]:
            with self.subTest(title=title):
                self.assertEqual(n.general_event_signals(title),(0,[]))

    def test_analysis(self):
        for title in ["Analysis: Government seizes oilfields","Why the deal matters","What we know about the explosion"]:
            self.assertTrue(n.is_analysis_headline(title))
        for title in ["Government seizes oilfields","Court rules on what happens next"]:
            self.assertFalse(n.is_analysis_headline(title))

    def test_build_prefers_factual_lead(self):
        def article(title,source,weight):
            return dict(title=title,source=source,weight=weight,summary="",image="",
                        url="https://example.org/"+source,paywalled=False,published_at=n.NOW.isoformat())
        facts=article("Government seizes oilfields","Reuters",12)
        analysis=article("Analysis: Government seizes oilfields","BBC",10)
        with patch.object(n,"embeddings",return_value=(np.ones((2,2)),np.ones((1,2)),"sentence-transformers")),patch.object(n,"cluster",return_value=[[0,1]]):
            stories=n.build([facts,analysis])["stories"]
            self.assertEqual(len(stories),1)
            self.assertEqual(stories[0]["title"],facts["title"])
            self.assertEqual(stories[0]["source_count"],1)
        with patch.object(n,"embeddings",return_value=(np.ones((1,2)),np.ones((1,2)),"sentence-transformers")),patch.object(n,"cluster",return_value=[[0]]):
            self.assertEqual(n.build([analysis])["stories"],[])

    def test_existing_helpers(self):
        pts,reasons=n.generic_quantified_signals("Company market value climbs by almost $1tn")
        self.assertIn("major market-value change",reasons)
        self.assertGreaterEqual(pts,18)
        now=n.NOW.isoformat()
        pts,reasons,trusted=n.cluster_consensus_evidence([dict(source="Reuters",published_at=now),dict(source="AP News",published_at=now)])
        self.assertEqual(len(trusted),2)
        self.assertAlmostEqual(pts,float(n.EW.get("trusted_source_consensus",5)))
        old=dict(title="Aurelia Systems value jumps after Mira Chen returns as CEO",category="Tech",published_at=(n.NOW-timedelta(hours=1)).isoformat(),sources=[dict(name="Reuters"),dict(name="BBC")])
        new=dict(title="Why Aurelia reinstated Mira Chen as chief executive",category="Tech",published_at=now,sources=[dict(name="Reuters"),dict(name="BBC"),dict(name="AP News")])
        self.assertIs(n.match_previous_story(new,[old]),old)

    def test_empty_collection_preserves_feed(self):
        with patch.object(n,"collect",return_value=[]):
            with self.assertRaisesRegex(RuntimeError,"preserving previous feed"):
                n.main()

    def test_consequential_retrospective_is_background_not_breaking(self):
        item=dict(title="A year on, what to know about Port Azure’s deadly fire that killed 168",source="AP News",weight=12,summary="",image="",url="https://example.org/recap",paywalled=False,published_at=n.NOW.isoformat())
        with patch.object(n,"embeddings",return_value=(np.ones((1,2)),np.ones((1,2)),"sentence-transformers")),patch.object(n,"cluster",return_value=[[0]]):
            stories=n.build([item])["stories"]
        self.assertEqual(len(stories),1)
        self.assertTrue(stories[0]["background_only"])
        self.assertEqual(stories[0]["importance"],"Notable")
        self.assertLessEqual(stories[0]["score"],40)

    def test_zero_fatality_reports_do_not_crash_ranking(self):
        for title in ["Fire leaves 0 dead", "0 people killed in earthquake", "Death toll at 0", "0 deaths, later 2 killed"]:
            with self.subTest(title=title):
                points,reasons=n.score(title,12,0.5)
                self.assertTrue(np.isfinite(points))
                self.assertEqual("reported fatalities" in reasons,"2 killed" in title)

if __name__=="__main__":
    unittest.main()
