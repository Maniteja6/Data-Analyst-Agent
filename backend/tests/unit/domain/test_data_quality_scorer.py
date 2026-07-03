"""Unit tests for DataQualityScorer."""
import pytest
from backend.domain.analytics.services.data_quality_scorer import DataQualityScorer


@pytest.mark.unit
class TestDataQualityScorer:

    def setup_method(self):
        self.scorer = DataQualityScorer()

    def _make_profile(self, **kwargs):
        """Create a minimal duck-typed profile object."""
        class _P:
            completeness_score = kwargs.get("completeness_score", 1.0)
            consistency_score  = kwargs.get("consistency_score",  1.0)
            column_profiles    = kwargs.get("column_profiles",    [])
            datetime_columns   = kwargs.get("datetime_columns",   [])
        return _P()

    def test_perfect_profile_scores_above_90(self):
        profile = self._make_profile()
        report  = self.scorer.score(profile)
        assert report.overall_score >= 0.90
        assert report.grade in ("A", "B")

    def test_low_completeness_lowers_score(self):
        profile = self._make_profile(completeness_score=0.5)
        report  = self.scorer.score(profile)
        assert report.overall_score < 0.80

    def test_high_null_rate_columns_reduce_validity(self):
        class _NullyCol:
            null_rate = 0.6
        profile = self._make_profile(column_profiles=[_NullyCol(), _NullyCol()])
        report  = self.scorer.score(profile)
        assert report.validity_score == 0.0

    def test_datetime_columns_boost_timeliness(self):
        class _DtCol: pass
        profile_with = self._make_profile(datetime_columns=[_DtCol()])
        profile_without = self._make_profile()
        r_with    = self.scorer.score(profile_with)
        r_without = self.scorer.score(profile_without)
        assert r_with.timeliness_score  == 1.0
        assert r_without.timeliness_score == 0.5

    def test_grade_f_for_very_low_score(self):
        profile = self._make_profile(completeness_score=0.1, consistency_score=0.1)
        report  = self.scorer.score(profile)
        assert report.grade == "F"
