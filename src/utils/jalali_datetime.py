from datetime import datetime, timedelta
import pytz
from persiantools.jdatetime import JalaliDateTime as PersianJalaliDateTime

class JalaliDateTime:
    def __init__(self, year, month, day):
        self._jalali = PersianJalaliDateTime(year, month, day)
    @staticmethod
    def to_jalali(dt: datetime) -> PersianJalaliDateTime:
        """Convert Gregorian datetime to Jalali datetime"""
        return PersianJalaliDateTime.to_jalali(dt)
    @staticmethod
    def from_jalali(jalali_date):
        return jalali_date.to_gregorian()
    def strftime(self, fmt):
        return self._jalali.strftime(fmt)
    @property
    def year(self):
        return self._jalali.year
    @property
    def month(self):
        return self._jalali.month
    @property
    def day(self):
        return self._jalali.day
    def __eq__(self, other):
        return (self.year, self.month, self.day) == (other.year, other.month, other.day)
    def __lt__(self, other):
        return (self.year, self.month, self.day) < (other.year, other.month, other.day)
    def __gt__(self, other):
        return (self.year, self.month, self.day) > (other.year, other.month, other.day)
    def __add__(self, days):
        g = self._jalali.to_gregorian() + timedelta(days=days)
        j = PersianJalaliDateTime.to_jalali(g)
        return JalaliDateTime(j.year, j.month, j.day)
    def __sub__(self, days):
        g = self._jalali.to_gregorian() - timedelta(days=days)
        j = PersianJalaliDateTime.to_jalali(g)
        return JalaliDateTime(j.year, j.month, j.day)
    def to_gregorian(self):
        return self._jalali.to_gregorian() 