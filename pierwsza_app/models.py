# app/models.py
from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator


class Cell(models.Model):
    year = models.PositiveSmallIntegerField()
    month = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(12)]
    )
    day = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(31)]
    )
    user_name = models.CharField(max_length=255)   # np. u.name z tabeli
    value = models.CharField(max_length=16, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["year", "month", "user_name", "day"],
                name="unique_cell_per_day"
            )
        ]
        indexes = [
            models.Index(fields=["year", "month"]),
        ]
        ordering = ["year", "month", "day", "user_name"]

    def __str__(self):
        return f"{self.user_name} {self.year}-{self.month:02d}-{self.day:02d} = {self.value or '-'}"
