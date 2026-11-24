import copy
import unittest
from datetime import timedelta
from unittest.mock import patch
import scripts.update_news as n

def date(hours):
    return (n.NOW-timedelta(hours=hours)).isoformat()

def article(title,hours,url="earlier",source="Reuters"):
    return dict(title=title,published_at=date(hours),url="https://example.org/"+url,source=source)

def story():
    return dict(id="event-1",title="Aurelia Energy refinery takeover approved by national court",
                published_at=date(1),lead_url="https://example.org/current",
                sources=[dict(name="Reuters",url="https://example.org/current",published_at=date(1))],
                score=50,importance="Major",category="World")

class ContextTests(unittest.TestCase):
    def test_related_and_unrelated(self):
        title=story()["title"]
        self.assertTrue(n.context_related(title,"Aurelia Energy refinery takeover challenged in court"))
        self.assertFalse(n.context_related(title,"Aurelia Energy announces quarterly earnings"))
        self.assertFalse(n.context_related(title,"Another company opens a refinery"))

    def test_history_without_changing_ranking(self):
        current=story()
        previous={"context_archive":[article("Aurelia Energy refinery takeover challenged in court",240)]}
        payload={"stories":[copy.deepcopy(current)]}
        result=n.add_story_context(payload,previous,[],discover=False)
        enriched=result["stories"][0]
        self.assertEqual(len(enriched["context"]["earlier_reporting"]),1)
        self.assertEqual(enriched["context"]["earlier_reporting"][0]["published_at"],date(240))
        self.assertEqual({k:v for k,v in enriched.items() if k!="context"},current)
        self.assertTrue(result["context_archive"])

    def test_reject_duplicate_untrusted_future_and_expired(self):
        current=story()
        related="Aurelia Energy refinery takeover challenged in court"
        items=[article(current["title"],24,"duplicate"),
               article(related,24,"untrusted","Unknown Blog"),
               article(related,-24,"future"),article(related,31*24,"old"),
               article(related,2,"too-recent")]
        result=n.add_story_context({"stories":[current]}, {},items,discover=False)
        self.assertEqual(result["stories"][0]["context"]["earlier_reporting"],[])

    def test_background_lookup_and_cooldown(self):
        related=article("Aurelia Energy refinery takeover challenged in court",240)
        with patch.object(n,"fetch",return_value=[related]) as fetch:
            first=n.add_story_context({"stories":[story()]},{},[])
            self.assertEqual(fetch.call_count,1)
            self.assertEqual(len(first["stories"][0]["context"]["earlier_reporting"]),1)
            again=n.add_story_context({"stories":[story()]},first,[])
            self.assertEqual(fetch.call_count,1)
            self.assertEqual(len(again["stories"][0]["context"]["earlier_reporting"]),1)

    def test_discovery_budget(self):
        stories=[dict(story(),id=str(i)) for i in range(10)]
        with patch.object(n,"fetch",return_value=[]) as fetch:
            n.add_story_context({"stories":stories},{},[])
            self.assertEqual(fetch.call_count,n.CONTEXT_QUERY_LIMIT)

if __name__=="__main__":
    unittest.main()
