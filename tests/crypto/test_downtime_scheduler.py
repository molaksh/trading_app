"""
Test downtime scheduling (crypto 24/7 with daily downtime).
"""

import pytest
from datetime import datetime
import pytz

from crypto.scheduling import DowntimeScheduler, TradingState


class TestDowntimeScheduler:
    """Test downtime scheduling for crypto."""
    
    @pytest.fixture
    def scheduler(self):
        """Create scheduler with default window (03:00-05:00 UTC)."""
        return DowntimeScheduler(downtime_start_utc="03:00", downtime_end_utc="05:00")
    
    def test_init_valid(self):
        """Test valid scheduler initialization."""
        scheduler = DowntimeScheduler("03:00", "05:00")
        assert scheduler.downtime_start.hour == 3
        assert scheduler.downtime_end.hour == 5
    
    def test_init_invalid_order(self):
        """Test that start must be before end."""
        with pytest.raises(ValueError):
            DowntimeScheduler("05:00", "03:00")
    
    def test_trading_hours(self, scheduler):
        """Test trading state during trading hours."""
        # 10:00 UTC = trading
        now = datetime(2026, 2, 5, 10, 0, 0, tzinfo=pytz.UTC)
        assert scheduler.get_current_state(now) == TradingState.TRADING
        assert scheduler.is_trading_allowed(now)
        assert not scheduler.is_training_allowed(now)
    
    def test_downtime_hours(self, scheduler):
        """Test downtime state during downtime window."""
        # 04:00 UTC = downtime (03:00-05:00)
        now = datetime(2026, 2, 5, 4, 0, 0, tzinfo=pytz.UTC)
        assert scheduler.get_current_state(now) == TradingState.DOWNTIME
        assert not scheduler.is_trading_allowed(now)
        assert scheduler.is_training_allowed(now)
    
    def test_downtime_boundary_start(self, scheduler):
        """Test boundary at downtime start."""
        # 03:00 UTC = downtime starts
        now = datetime(2026, 2, 5, 3, 0, 0, tzinfo=pytz.UTC)
        assert scheduler.get_current_state(now) == TradingState.DOWNTIME
    
    def test_downtime_boundary_end(self, scheduler):
        """Test boundary at downtime end."""
        # 05:00 UTC = downtime ends (not included)
        now = datetime(2026, 2, 5, 5, 0, 0, tzinfo=pytz.UTC)
        assert scheduler.get_current_state(now) == TradingState.TRADING
    
    def test_time_until_downtime(self, scheduler):
        """Test time calculation until downtime."""
        # 02:00 UTC = 1 hour until downtime
        now = datetime(2026, 2, 5, 2, 0, 0, tzinfo=pytz.UTC)
        delta = scheduler.time_until_downtime(now)
        assert delta.total_seconds() == 3600  # 1 hour
    
    def test_time_until_downtime_already_in(self, scheduler):
        """Test time calculation when already in downtime."""
        # 04:00 UTC = 1 day + 23 hours until next downtime
        now = datetime(2026, 2, 5, 4, 0, 0, tzinfo=pytz.UTC)
        delta = scheduler.time_until_downtime(now)
        expected = (24 - 4 + 3) * 3600  # = 23 hours
        assert delta.total_seconds() == expected
    
    def test_time_until_trading_resumes(self, scheduler):
        """Test time calculation until trading resumes."""
        # 04:00 UTC = 1 hour until trading
        now = datetime(2026, 2, 5, 4, 0, 0, tzinfo=pytz.UTC)
        delta = scheduler.time_until_trading_resumes(now)
        assert delta.total_seconds() == 3600  # 1 hour
    
    def test_validate_training_completion_success(self, scheduler):
        """Test validation when training completes before downtime ends."""
        start = datetime(2026, 2, 5, 3, 30, 0, tzinfo=pytz.UTC)
        end = datetime(2026, 2, 5, 4, 45, 0, tzinfo=pytz.UTC)
        
        valid, msg = scheduler.validate_training_completion(start, end)
        assert valid is True
        assert "Training completed" in msg
    
    def test_validate_training_completion_overrun(self, scheduler):
        """Test validation when training overruns downtime."""
        start = datetime(2026, 2, 5, 3, 30, 0, tzinfo=pytz.UTC)
        end = datetime(2026, 2, 5, 5, 10, 0, tzinfo=pytz.UTC)  # 10 min after end
        
        valid, msg = scheduler.validate_training_completion(start, end)
        assert valid is False
        assert "overran" in msg.lower()
    
    def test_custom_downtime_window(self):
        """Test custom downtime window."""
        scheduler = DowntimeScheduler("22:00", "23:30")  # 10pm-11:30pm UTC
        
        # 22:30 UTC = in downtime
        now = datetime(2026, 2, 5, 22, 30, 0, tzinfo=pytz.UTC)
        assert scheduler.is_training_allowed(now)
        
        # 23:45 UTC = past downtime
        now = datetime(2026, 2, 5, 23, 45, 0, tzinfo=pytz.UTC)
        assert not scheduler.is_training_allowed(now)
    
    def test_dst_handling(self):
        """Test handling of daylight saving transitions (edge case)."""
        scheduler = DowntimeScheduler("03:00", "05:00")
        
        # UTC doesn't observe DST, so this should always work consistently
        now_summer = datetime(2026, 7, 5, 4, 0, 0, tzinfo=pytz.UTC)
        now_winter = datetime(2026, 1, 5, 4, 0, 0, tzinfo=pytz.UTC)
        
        assert scheduler.is_training_allowed(now_summer)
        assert scheduler.is_training_allowed(now_winter)
