# app/models.py
from django.db import models

class Cell(models.Model):
    year = models.PositiveSmallIntegerField()
    month = models.PositiveSmallIntegerField()
    user_name = models.CharField(max_length=255)   # u.name z Twojej tabeli
    day = models.PositiveSmallIntegerField()       # 1..31
    value = models.CharField(max_length=16, blank=True)

    class Meta:
        unique_together = ('year', 'month', 'user_name', 'day')
