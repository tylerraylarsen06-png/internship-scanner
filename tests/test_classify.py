import unittest
from pathlib import Path
from datetime import date

from scanner.classify import class_year, enrich, is_urgent, location_tier
from scanner.model import blank_row, canon_url, row_key


class Classify(unittest.TestCase):
    def test_class_year(self):
        self.assertEqual(class_year("open to first and second year students"), "confirmed 2029")
        self.assertEqual(class_year("must be a rising senior"), "2028 only")
        self.assertEqual(class_year("Marketing Intern"), "none stated")

    def test_no_class_year_language_still_kept(self):
        r = blank_row(company="Skechers", role="Marketing Intern", location="Manhattan Beach, CA")
        self.assertEqual(enrich(r), "")  # the Fox/Skechers tier is the point
        self.assertEqual(r["tier"], "B")

    def test_rule_outs(self):
        for company, role, loc in [("Jane Street", "Trading Intern", "New York, NY"),
                                   ("Palantir", "Business Ops Intern", "Denver, CO"),
                                   ("Acme", "Women in Finance Insight Program", "NY"),
                                   ("Acme", "Strategy Intern", "Singapore"),
                                   ("Acme", "Summer 2028 Analyst Intern", "NY"),
                                   ("Acme", "Strategy Intern Spring 2027", "Chicago, IL")]:
            self.assertTrue(enrich(blank_row(company=company, role=role, location=loc)), (company, role))

    def test_state_codes_case_sensitive(self):
        self.assertEqual(location_tier("Paseo de la Reforma, Mexico City"), 3)
        self.assertEqual(location_tier("Los Angeles, CA"), 1)
        self.assertEqual(location_tier("London"), 2)
        for us in ["NYC", "SF", "Seattle", "Remote in USA", "Boston; Chicago"]:
            self.assertEqual(location_tier(us), 1, us)
        self.assertEqual(location_tier("Bengaluru"), 3)
        for us in ["Albuquerque, New Mexico", "Indianapolis", "Lima, Ohio"]:
            self.assertEqual(location_tier(us), 1, us)

    def test_deadline_inside_30_days_splits_at_fit_3(self):
        from scanner.classify import tab_for
        today = date(2026, 10, 6)
        self.assertEqual(tab_for(blank_row(company="NVIDIA", role="Ignite", deadline="2026-10-18", fit=3.0), today), "URGENT")
        self.assertEqual(tab_for(blank_row(company="Acme", role="SWE Intern", deadline="2026-10-18", fit=2.5), today),
                         "URGENT (SUB 3)")
        self.assertEqual(tab_for(blank_row(company="Acme", role="SWE Intern", deadline="2026-12-30", fit=2.5), today),
                         "PIPELINE")

    def test_dedup_keys(self):
        self.assertEqual(row_key("Fox Corporation", "Summer 2027 Marketing Intern - Los Angeles"),
                         row_key("Fox", "Marketing Intern"))
        self.assertEqual(canon_url("https://www.bain.com/careers"), "")  # generic pages never merge


if __name__ == "__main__":
    unittest.main()


class Corrections20261006(unittest.TestCase):
    def test_old_sheet_class_year_downgraded_unless_verified(self):
        r = blank_row(company="Morgan Stanley", role="Early Insights Program", source="old-sheet:All#27",
                      notes="Soph-specific (old sheet: Sophomore)")
        enrich(r)
        self.assertEqual(r["class_year"], "unclear")

    @unittest.skipUnless((Path(__file__).parent.parent / "config/verified.json").exists(),
                         "needs the local firm-page verification file")
    def test_verified_facts_win(self):
        for company, role in [("Kearney", "Consulting Internship"), ("Oliver Wyman", "Discovery Day"),
                              ("LEK Consulting", "Explore Program")]:
            self.assertTrue(enrich(blank_row(company=company, role=role, source="old-sheet")), (company, role))
        r = blank_row(company="NVIDIA", role="NVIDIA 2027 Ignite Internships: Software Engineering")
        self.assertEqual(enrich(r), "")
        self.assertEqual((r["class_year"], r["verified"], r["deadline"]), ("confirmed 2029", "y", "2026-10-18"))

    def test_non_english_ruled_out(self):
        r = blank_row(company="Accenture", role="Er du nysgjerring på konsulentlivet – bli med på Discovery Programmet!",
                      link="https://accenture.wd103.myworkdayjobs.com/AccentureCareers/job/Oslo/x_R1")
        self.assertIn("English", enrich(r))
        self.assertTrue(enrich(blank_row(company="Acme", role="Werkstudent Strategie (m/w/d)", location="Berlin")))

    def test_location_from_link_when_field_empty(self):
        r = blank_row(company="Barclays", role="Banking Analyst Summer Internship",
                      link="https://barclays.wd3.myworkdayjobs.com/x/job/Mexico-City-Reforma/Banking_JR1")
        self.assertIn("Outside US", enrich(r))

    def test_placeholder_company(self):
        for name in ["TBD Investors", "Confidential", "Stealth Startup", "Various", "Company Name"]:
            self.assertIn("Placeholder", enrich(blank_row(company=name, role="Strategy Intern")), name)

    def test_tier_b_la_no_deadline_is_urgent(self):
        r = blank_row(company="Fox Corporation", role="Summer 2027 FOX Corporation Internship Program - Los Angeles, CA",
                      location="Los Angeles, California, USA", verified="y")
        self.assertEqual(enrich(r), "")
        self.assertGreaterEqual(float(r["fit"]), 4.0)
        self.assertTrue(is_urgent(r, date(2026, 10, 6)))


class Dedup(unittest.TestCase):
    def test_spring_and_summer_postings_stay_separate(self):
        import tempfile
        from pathlib import Path
        from scanner.store import Store
        st = Store(Path(tempfile.mkdtemp()) / "m.json")
        a = blank_row(company="Fox Corporation", role="Summer 2027 FOX Sports Internship Program - Los Angeles",
                      link="https://fox.wd1.myworkdayjobs.com/Domestic/job/LA/Summer_R1001", location="Los Angeles, CA")
        b = blank_row(company="Fox Corporation", role="Spring 2027 FOX Sports Internship Program - Los Angeles",
                      link="https://fox.wd1.myworkdayjobs.com/Domestic/job/LA/Spring_R1002", location="Los Angeles, CA")
        c = blank_row(company="Fox", role="FOX Sports Internship Program", link="https://www.fox.com/careers")
        self.assertEqual([st.add(a, date(2026, 10, 6)), st.add(b, date(2026, 10, 6))], ["new", "new"])
        self.assertIn(st.add(c, date(2026, 10, 6)), ("merged", "dup"))
        repost = blank_row(company="Fox Corporation", role="Summer 2027 FOX Sports Internship Program - Los Angeles",
                           link="https://fox.wd1.myworkdayjobs.com/Domestic/job/LA/Summer_R9999")
        self.assertIn(st.add(repost, date(2026, 10, 6)), ("merged", "dup"))


class Decisions20261006(unittest.TestCase):
    def test_spring_2027_in_la_is_kept(self):
        for loc in ["Burbank, CA, USA", "Los Angeles, California, USA", "Glendale, CA"]:
            r = blank_row(company="Disney", role="Talent & Growth Planning & Operations Intern, Spring 2027", location=loc)
            self.assertEqual(enrich(r), "", loc)

    def test_media_deal_roles_are_business_roles_at_35(self):
        r = blank_row(company="Fox Corporation",
                      role="Summer 2027 FOX Corporation Internship Program - Business and Legal Affairs",
                      location="Los Angeles, California, USA", verified="y")
        self.assertEqual(enrich(r), "")
        self.assertEqual(float(r["fit"]), 3.5)
        self.assertFalse(is_urgent(r, date(2026, 10, 6)))  # visible in PIPELINE, not forced into URGENT
        for role in ["Rights & Clearances Intern", "Content Distribution Intern", "Business Affairs Intern"]:
            r = blank_row(company="Paramount", role=role, location="Los Angeles, CA")
            enrich(r)
            self.assertEqual(float(r["fit"]), 3.5, role)

    def test_legal_outside_media_stays_low(self):
        r = blank_row(company="Acxiom", role="Legal Intern", location="Conway, AR")
        enrich(r)
        self.assertEqual(float(r["fit"]), 2.0)
