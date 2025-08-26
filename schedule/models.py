from django.db import models

class ScheduleTemplate(models.Model):
    group = models.CharField(max_length=120, db_index=True)
    name = models.CharField(max_length=120)
    positions = models.JSONField(default=list)
    # owner zostaje, ale nieobowiązkowy
    owner = models.ForeignKey(
        'auth.User',
        on_delete=models.CASCADE,
        null=True, blank=True
    )
    updated_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            # UWAGA: unikatowość tylko po group + name
            models.UniqueConstraint(
                fields=["group", "name"],
                name="unique_template_per_group_name"
            )
        ]
        ordering = ["name"]

    def __str__(self):
        return f"{self.group} / {self.name}"
