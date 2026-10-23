import hashlib
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[5]
STANDARDS = (
    ROOT
    / "skills"
    / "energy-audit"
    / "energy-audit-core"
    / "references"
    / "standards"
)
SHANDONG = STANDARDS / "shandong" / "public_building"
ZHEJIANG = STANDARDS / "zhejiang"
ZHEJIANG_INSTITUTION = ZHEJIANG / "public_institution"

SHANDONG_CITIES = {
    "济南", "青岛", "淄博", "枣庄", "东营", "烟台", "潍坊", "济宁",
    "泰安", "威海", "日照", "临沂", "德州", "聊城", "滨州", "菏泽",
}


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class ShandongPublicBuildingPackIntegrityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.quota = load_json(SHANDONG / "quota-values.json")

    def test_every_city_has_business_office_and_hotel_limits(self):
        office_rows = self.quota["db37_t_5078_2024"]["rows"]
        self.assertEqual(set(office_rows), SHANDONG_CITIES)
        for row in office_rows.values():
            self.assertEqual(len(row), 4)

        hotel_rows = self.quota["db37_t_5076_2024"]["rows"]
        self.assertEqual(set(hotel_rows), {"3", "4", "5"})
        for star_rows in hotel_rows.values():
            self.assertEqual(set(star_rows), SHANDONG_CITIES)
            for row in star_rows.values():
                self.assertEqual(len(row), 4)

    def test_every_city_has_all_four_hospital_types(self):
        hospital_rows = self.quota["db37_t_5079_2024"]["rows"]
        self.assertEqual(
            set(hospital_rows),
            {"三级综合", "三级专科", "二级及以下综合", "二级及以下专科"},
        )
        for type_rows in hospital_rows.values():
            self.assertEqual(set(type_rows), SHANDONG_CITIES)
            for row in type_rows.values():
                self.assertEqual(len(row), 6)

    def test_shandong_uses_two_tiers_and_the_current_equivalent_coefficient(self):
        self.assertEqual(
            self.quota["coefficients"]["electricity_equivalent_kgce_per_kwh"],
            0.1229,
        )
        self.assertNotIn("基准值", json.dumps(self.quota, ensure_ascii=False))
        self.assertNotIn("引导值", json.dumps(self.quota, ensure_ascii=False))

    def test_declared_sources_have_local_pdfs(self):
        sources = load_json(SHANDONG / "sources.json")
        for source in sources["standards"]:
            self.assertTrue(source["source_url"].startswith("https://"))
            local_pdf = source.get("local_pdf")
            if local_pdf:
                pdf_path = SHANDONG / local_pdf
                self.assertTrue(pdf_path.is_file(), local_pdf)
                self.assertEqual(source.get("sha256"), sha256(pdf_path))
            self.assertEqual(source.get("http_status"), 200)


class ZhejiangPublicInstitutionPackIntegrityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.institution = load_json(ZHEJIANG_INSTITUTION / "quota-values.json")
        cls.shared = load_json(ZHEJIANG / "quota-values.json")

    def assert_three_tiers(self, tiers):
        self.assertEqual(len(tiers), 3)
        self.assertGreater(tiers[0], tiers[1])
        self.assertGreater(tiers[1], tiers[2])

    def test_736_reuses_the_single_shared_copy(self):
        shared_736 = self.shared["db33_t_736_2021"]
        self.assertNotIn("db33_t_736_2021", self.institution)
        for metric in shared_736["administrative"].values():
            if isinstance(metric, dict):
                for tiers in metric.values():
                    self.assert_three_tiers(tiers)
            else:
                self.assert_three_tiers(metric)
        for metric in shared_736["venue"].values():
            if isinstance(metric, dict):
                for tiers in metric.values():
                    self.assert_three_tiers(tiers)
            else:
                self.assert_three_tiers(metric)

    def test_737_and_738_all_limits_have_three_descending_tiers(self):
        university = self.institution["db33_t_737_2021"]
        for section in ("primary", "reference"):
            for tiers in university[section].values():
                self.assert_three_tiers(tiers)

        hospital = self.institution["db33_t_738_2021"]
        for section in ("primary", "reference"):
            for metric in hospital[section].values():
                tier_groups = (
                    metric.values() if isinstance(metric, dict) else [metric]
                )
                for tiers in tier_groups:
                    self.assert_three_tiers(tiers)

    def test_zhejiang_uses_the_public_institution_coefficient(self):
        self.assertEqual(
            self.institution["coefficients"]["electricity_kgce_per_kwh"],
            0.1229,
        )
        self.assertNotIn("0.31", json.dumps(self.institution, ensure_ascii=False))
        self.assertNotIn("DB37", json.dumps(self.institution, ensure_ascii=False))

    def test_declared_sources_have_local_pdfs(self):
        sources = load_json(ZHEJIANG_INSTITUTION / "sources.json")
        for source in sources["standards"]:
            self.assertTrue(source["source_url"].startswith("https://"))
            self.assertTrue(
                (ZHEJIANG_INSTITUTION / source["local_pdf"]).is_file(),
                source["local_pdf"],
            )
            self.assertEqual(
                source.get("sha256"),
                sha256(ZHEJIANG_INSTITUTION / source["local_pdf"]),
            )
            self.assertEqual(source.get("http_status"), 200)


if __name__ == "__main__":
    unittest.main()
